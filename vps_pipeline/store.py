"""Transactional task ledger, immutable archives and versioned review imports.

No credentials, background scheduler or implicit network calls live here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import time
import uuid

ACTIVE = {'archiving', 'validating'}
URL = re.compile(r'https://www\.nodeseek\.com/post-([1-9][0-9]*)-1\Z')
ID = re.compile(r'[a-f0-9]{32}\Z')


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_url(url):
    if not isinstance(url, str) or not URL.fullmatch(url):
        raise ValueError('only canonical public NodeSeek first-page HTTPS URLs are accepted')
    return url


def check_plain_path(path):
    path = Path(path).absolute()
    if '..' in path.parts or any(':' in part for part in path.parts if part != path.anchor):
        raise ValueError('parent traversal and alternate data streams are not accepted')
    for component in [path, *path.parents]:
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('symlinks and junctions are not accepted')
    return path


def reason(exc):
    # Keep paths, URL credentials and tracebacks out of the API / ledger.
    message = str(getattr(exc, 'reason', exc)).replace('\n', ' ')[:500]
    message = re.sub(r'[A-Za-z]:[\\/][^\s\"\']+', '[local path]', message)
    message = re.sub(r'(?<!:)//[^\s\"\']+', '[path]', message)
    return type(exc).__name__ + ': ' + message


class Store:
    def __init__(self, data_root):
        self.root = check_plain_path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ['archives', 'tmp']:
            check_plain_path(self.root / name).mkdir(exist_ok=True)
        self.db_path = check_plain_path(self.root / 'pipeline.sqlite3')
        with self._db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, source_url TEXT NOT NULL UNIQUE,
                    post_id TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
                    network_blocked INTEGER NOT NULL DEFAULT 0,
                    archive_rel TEXT, archive_sha256 TEXT,
                    lease_token TEXT, lease_until REAL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    event TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id));
                CREATE TABLE IF NOT EXISTS analyses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    version INTEGER NOT NULL, digest TEXT NOT NULL,
                    envelope TEXT NOT NULL, normalized TEXT NOT NULL,
                    validation TEXT NOT NULL, archive_rel TEXT NOT NULL,
                    archive_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(job_id,digest), UNIQUE(job_id,version),
                    FOREIGN KEY(job_id) REFERENCES jobs(id));
                CREATE TABLE IF NOT EXISTS legacy_records(
                    id TEXT PRIMARY KEY, post_id TEXT NOT NULL, source_url TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL, analysis_sha256 TEXT NOT NULL,
                    archive_rel TEXT NOT NULL, summary TEXT NOT NULL,
                    imported_at TEXT NOT NULL);
            ''')

    @contextmanager
    def _db(self):
        check_plain_path(self.db_path)
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _event(db, job_id, event, detail=None):
        db.execute('INSERT INTO events(job_id,event,detail,at) VALUES(?,?,?,?)',
                   (job_id, event, encoded(detail or {}), now()))

    @staticmethod
    def _row(db, job_id):
        if not isinstance(job_id, str) or not ID.fullmatch(job_id):
            raise ValueError('invalid job id')
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise KeyError('job not found')
        return row

    @staticmethod
    def _public(db, row):
        value = {k: row[k] for k in ['id', 'source_url', 'post_id', 'status', 'attempts',
                 'last_error', 'network_blocked', 'archive_sha256', 'created_at', 'updated_at']}
        value['accepted_version'] = db.execute(
            'SELECT max(version) FROM analyses WHERE job_id=?', (row['id'],)).fetchone()[0]
        return value

    def enqueue(self, source_url):
        canonical_url(source_url)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM jobs WHERE source_url=?', (source_url,)).fetchone()
            if row is None:
                job_id, stamp = uuid.uuid4().hex, now()
                db.execute('INSERT INTO jobs(id,source_url,post_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                           (job_id, source_url, URL.fullmatch(source_url)[1], 'queued', stamp, stamp))
                self._event(db, job_id, 'queued', {'source_url': source_url})
                row = self._row(db, job_id)
            return self._public(db, row)

    def list_jobs(self):
        with self._db() as db:
            return [self._public(db, r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at,id').fetchall()]

    def get_job(self, job_id):
        with self._db() as db:
            value = self._public(db, self._row(db, job_id))
            value['events'] = [dict(r) | {'detail': json.loads(r['detail'])} for r in db.execute(
                'SELECT seq,event,detail,at FROM events WHERE job_id=? ORDER BY seq', (job_id,))]
            return value

    def _claim(self, job_id, status, allowed):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._row(db, job_id)
            if row['status'] not in allowed:
                raise ValueError('task state does not allow this action: ' + row['status'])
            token = uuid.uuid4().hex
            db.execute('UPDATE jobs SET status=?,attempts=attempts+1,lease_token=?,lease_until=?,updated_at=? WHERE id=?',
                       (status, token, time.time() + 600, now(), job_id))
            self._event(db, job_id, status)
            return dict(row), token

    def _finish_error(self, job_id, token, exc, status='failed'):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._row(db, job_id)
            if row['lease_token'] != token:
                return
            error = reason(exc)
            if status == 'blocked':
                db.execute('UPDATE jobs SET network_blocked=1 WHERE id=?', (job_id,))
            db.execute('UPDATE jobs SET status=?,last_error=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                       (status, error, now(), job_id))
            self._event(db, job_id, 'operation_failed' if status in {'accepted', 'awaiting_analysis'} else status,
                        {'reason': error, 'retained_status': status})

    def _manifest(self, row):
        relative = row['archive_rel']
        if not relative:
            raise ValueError('task has no archive')
        path = check_plain_path(self.root / relative)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('archive path outside data root')
        if sha(path.read_bytes()) != row['archive_sha256']:
            raise ValueError('archive manifest hash changed')
        return path

    def _ingest_claimed(self, row, token, html_path, resources):
        from .archive import archive_from_html, verify_archive
        snapshot = self.root / 'archives' / row['id'] / ('snapshot-' + token)
        manifest = archive_from_html(html_path, row['source_url'], snapshot, resources=resources)
        m = verify_archive(manifest)
        duplicate = False
        if row.get('archive_rel'):
            previous_path = self._manifest(row)
            previous = verify_archive(previous_path)
            comparison = ['schema_version', 'post_id', 'source_url', 'title', 'author',
                          'status', 'files', 'links', 'failures', 'capture_metadata']
            duplicate = all(previous.get(k) == m.get(k) for k in comparison)
            if duplicate:
                manifest = previous_path
                # This path is generated above under our dedicated snapshots root.
                if not snapshot.resolve().is_relative_to((self.root/'archives'/row['id']).resolve()):
                    raise ValueError('invalid duplicate snapshot cleanup path')
                shutil.rmtree(snapshot)
        state = row['status'] if duplicate and row['status'] == 'accepted' else 'awaiting_analysis'
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._row(db, row['id'])
            if current['lease_token'] != token:
                raise ValueError('task lease changed; archive retained for recovery')
            db.execute('UPDATE jobs SET status=?,archive_rel=?,archive_sha256=?,lease_token=NULL,lease_until=NULL,last_error=NULL,updated_at=? WHERE id=?',
                       (state, manifest.relative_to(self.root).as_posix(), sha(manifest.read_bytes()), now(), row['id']))
            self._event(db, row['id'], 'archive_duplicate' if duplicate else 'awaiting_analysis', {'archive_status': m['status'],
                                                         'failures': m.get('failures', [])})
        return self.get_job(row['id'])

    def import_html(self, job_id, html_path, resources=None):
        row, token = self._claim(job_id, 'archiving', {'queued', 'failed', 'blocked', 'awaiting_analysis', 'accepted'})
        try:
            return self._ingest_claimed(row, token, check_plain_path(html_path), resources)
        except Exception as exc:
            self._finish_error(job_id, token, exc, row['status'] if row.get('archive_rel') else 'failed')
            raise

    def import_archive(self, job_id, manifest_path):
        """Offline, byte-preserving ingress of an existing strict archive."""
        from .archive_import import import_archive
        return import_archive(self, job_id, manifest_path)

    def collect(self, limit=1):
        """Explicit bounded network operation. CLI requires --allow-network.

        No API route invokes this method. Encountering a restriction stops this
        entire batch. Missing resources are recorded by the archive adapter.
        """
        from .network import fetch_first_post, NetworkBlocked
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit must be an integer from 1 to 100')
        candidates = [x for x in self.list_jobs() if x['status'] == 'queued' and not x['network_blocked']][:limit]
        results = []
        for job in candidates:
            try:
                row, token = self._claim(job['id'], 'archiving', {'queued'})
            except ValueError:
                continue  # Another process claimed the same bounded candidate.
            temporary = self.root / 'tmp' / uuid.uuid4().hex
            temporary.mkdir()
            try:
                fetched = fetch_first_post(row['source_url'], temporary / 'input.html')
                with self._db() as db:
                    self._event(db, row['id'], 'http_response_received',
                                {k: fetched[k] for k in ['url', 'sha256', 'bytes', 'status',
                                 'content_type', 'fetched_at', 'remote_ip', 'scope'] if k in fetched})
                results.append(self._ingest_claimed(row, token, temporary / 'input.html', None))
            except NetworkBlocked as exc:
                self._finish_error(row['id'], token, exc, 'blocked')
                results.append(self.get_job(row['id']))
                break
            except Exception as exc:
                self._finish_error(row['id'], token, exc)
                results.append(self.get_job(row['id']))
                break  # No unattended retries or broad crawling after an error.
            finally:
                shutil.rmtree(temporary)
        return results

    def export_task(self, job_id, output_path):
        from .analysis import create_work_package
        with self._db() as db:
            row = dict(self._row(db, job_id))
        if row['status'] not in {'awaiting_analysis', 'accepted'}:
            raise ValueError('task is not ready for assistant review')
        result = create_work_package(self._manifest(row), check_plain_path(output_path))
        with self._db() as db:
            self._event(db, job_id, 'review_package_exported', {'archive_sha256': row['archive_sha256']})
        return result

    def submit(self, job_id, envelope):
        from .analysis import validate_submission
        digest = sha(encoded(envelope).encode('utf-8'))
        with self._db() as db:
            row = dict(self._row(db, job_id))
            if not isinstance(envelope, dict) or envelope.get('archive_sha256') != row['archive_sha256']:
                raise ValueError('submission does not match the current archive snapshot')
            existing = db.execute('SELECT version FROM analyses WHERE job_id=? AND digest=?', (job_id, digest)).fetchone()
            if existing:
                from .archive import verify_archive
                verify_archive(self._manifest(row))
                return {'status': 'accepted', 'job_id': job_id, 'version': existing['version'], 'duplicate': True}
        row, token = self._claim(job_id, 'validating', {'awaiting_analysis', 'accepted'})
        try:
            result = validate_submission(self._manifest(row), envelope)
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                current = self._row(db, job_id)
                if current['lease_token'] != token:
                    raise ValueError('task lease changed')
                # A matching submission can commit after the initial lookup but
                # before this caller acquires its lease. Recheck while holding
                # the write transaction rather than relying on UNIQUE to fail.
                existing = db.execute('SELECT version FROM analyses WHERE job_id=? AND digest=?',
                                      (job_id, digest)).fetchone()
                if existing:
                    db.execute('UPDATE jobs SET status=?,last_error=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                               ('accepted', now(), job_id))
                    self._event(db, job_id, 'submission_duplicate', {'version': existing['version']})
                    return {'status': 'accepted', 'job_id': job_id, 'version': existing['version'], 'duplicate': True}
                version = db.execute('SELECT coalesce(max(version),0)+1 FROM analyses WHERE job_id=?', (job_id,)).fetchone()[0]
                db.execute('INSERT INTO analyses(job_id,version,digest,envelope,normalized,validation,archive_rel,archive_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                           (job_id, version, digest, encoded(envelope), encoded(result['normalized']),
                            encoded(result['validation']), row['archive_rel'], row['archive_sha256'], now()))
                db.execute('UPDATE jobs SET status=?,last_error=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                           ('accepted', now(), job_id))
                self._event(db, job_id, 'accepted', {'version': version, 'submission_sha256': digest,
                                                  'meaning': 'schema and evidence checks passed; visual statements remain reviewer declarations'})
            return {'status': 'accepted', 'job_id': job_id, 'version': version, 'duplicate': False}
        except Exception as exc:
            self._finish_error(job_id, token, exc, row['status'])
            raise

    def cancel(self, job_id):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._row(db, job_id)
            if row['status'] in ACTIVE:
                raise ValueError('active bounded operation must finish; cancellation does not kill a process')
            if row['status'] == 'accepted':
                raise ValueError('accepted records are immutable; cancel only unfinished tasks')
            db.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?', ('cancelled', now(), job_id))
            self._event(db, job_id, 'cancelled')
        return self.get_job(job_id)

    def retry(self, job_id):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._row(db, job_id)
            if row['network_blocked'] and not row['archive_rel']:
                raise ValueError('access restriction cannot be retried automatically; import authorized offline evidence instead')
            if row['status'] not in {'failed', 'cancelled'}:
                raise ValueError('only failed or cancelled tasks can be resumed')
            state = 'awaiting_analysis' if row['archive_rel'] else 'queued'
            db.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?', (state, now(), job_id))
            self._event(db, job_id, 'resumed', {'previous_status': row['status'], 'state': state})
        return self.get_job(job_id)

    def recover(self):
        recovered = []
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT * FROM jobs WHERE status IN (?,?) AND lease_until<?',
                              ('archiving', 'validating', time.time())).fetchall()
            for row in rows:
                state = 'awaiting_analysis' if row['archive_rel'] else 'queued'
                if row['archive_rel'] and db.execute(
                        'SELECT 1 FROM analyses WHERE job_id=? AND archive_sha256=? LIMIT 1',
                        (row['id'], row['archive_sha256'])).fetchone():
                    state = 'accepted'
                db.execute('UPDATE jobs SET status=?,lease_token=NULL,lease_until=NULL,last_error=?,updated_at=? WHERE id=?',
                           (state, 'interrupted operation recovered after lease expiry', now(), row['id']))
                self._event(db, row['id'], 'recovered', {'previous_status': row['status'], 'state': state})
                recovered.append(row['id'])
        return {'recovered': recovered, 'lease_seconds': 600}

    def import_legacy(self, manifest_path, analysis_path=None):
        """Copy verified historical bytes privately; never create accepted jobs.

        Only directory-based manifests are supported. Staging is private and an
        atomic rename precedes the ledger commit; interrupted copies never appear
        as imported records. A fully copied orphan is safely reverified on retry.
        """
        from .legacy import verify_legacy, MAX_ANALYSIS_BYTES
        from .archive import _safe_relative, _read_bytes, MAX_BYTES, MAX_MANIFEST_BYTES

        source = check_plain_path(manifest_path)
        analysis_source = check_plain_path(analysis_path if analysis_path is not None
                                           else source.parent / 'analysis.json')
        result = verify_legacy(source, analysis_source)
        identity = result['bundle_sha256']
        with self._db() as db:
            exists = db.execute('SELECT id FROM legacy_records WHERE id=?', (identity,)).fetchone()
        if exists:
            existing = self.get_legacy(identity)
            return {'status': 'legacy_imported', 'id': identity, 'post_id': existing['post_id'],
                    'duplicate': True, 'new_review_performed': False}

        staging = check_plain_path(self.root / 'tmp' / ('legacy-' + uuid.uuid4().hex))
        staging.mkdir(mode=0o700)
        try:
            stage_post = staging / 'assets' / result['post_id']
            stage_post.mkdir(parents=True)
            for filename, original, expected, limit in [
                    ('manifest.json', source, result['manifest_sha256'], MAX_MANIFEST_BYTES),
                    ('analysis.json', analysis_source, result['analysis_sha256'], MAX_ANALYSIS_BYTES)]:
                payload = _read_bytes(original, limit)
                if sha(payload) != expected:
                    raise ValueError('Legacy metadata changed during import')
                with (stage_post / filename).open('xb') as stream:
                    stream.write(payload)
            for record in result['manifest']['files']:
                original = _safe_relative(source.parent, record['path'])
                payload = _read_bytes(original, MAX_BYTES)
                if len(payload) != record['bytes'] or sha(payload) != record['sha256']:
                    raise ValueError('Legacy evidence changed during import')
                target = _safe_relative(stage_post, record['path'])
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if target.read_bytes() != payload:
                        raise ValueError('Legacy evidence path collision')
                else:
                    with target.open('xb') as stream:
                        stream.write(payload)
            staged = verify_legacy(stage_post / 'manifest.json')
            if staged['bundle_sha256'] != identity:
                raise ValueError('Legacy import changed metadata')
            destination = check_plain_path(self.root / 'legacy_archives' / identity)
            destination.parent.mkdir(mode=0o700, exist_ok=True)
            target_manifest = destination / 'assets' / result['post_id'] / 'manifest.json'
            summary = {'id': identity, 'post_id': result['post_id'], 'source_url': result['source_url'],
                       'status': 'legacy_imported', 'archive_status': result['manifest']['status'],
                       'fact_count': len(result['analysis']['facts']),
                       'file_count': len(result['manifest']['files']),
                       'image_count': sum(f['role'] == 'image' for f in result['manifest']['files']),
                       'missing_resource_count': len(result['manifest'].get('failures', [])),
                       'new_review_performed': False, 'historical_analysis_generated_at': result['analysis'].get('generated_at')}
            duplicate = False
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                exists = db.execute('SELECT id FROM legacy_records WHERE id=?', (identity,)).fetchone()
                if exists:
                    duplicate = True
                else:
                    if destination.exists():
                        if verify_legacy(target_manifest)['bundle_sha256'] != identity:
                            raise ValueError('Legacy destination differs from verified snapshot')
                    else:
                        staging.rename(destination)
                    stamp = now()
                    db.execute('INSERT INTO legacy_records(id,post_id,source_url,manifest_sha256,analysis_sha256,archive_rel,summary,imported_at) VALUES(?,?,?,?,?,?,?,?)',
                               (identity, result['post_id'], result['source_url'], result['manifest_sha256'],
                                result['analysis_sha256'], target_manifest.relative_to(self.root).as_posix(), encoded(summary), stamp))
            # Reverify a concurrent winner rather than report a stale digest.
            self.get_legacy(identity)
            return {'status': 'legacy_imported', 'id': identity, 'post_id': result['post_id'],
                    'duplicate': duplicate, 'new_review_performed': False}
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def list_legacy(self):
        with self._db() as db:
            return [json.loads(row['summary']) | {'imported_at': row['imported_at']}
                    for row in db.execute('SELECT summary,imported_at FROM legacy_records ORDER BY post_id,imported_at,id')]

    def get_legacy(self, identity):
        from .legacy import verify_legacy
        if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{64}', identity):
            raise ValueError('invalid legacy record id')
        with self._db() as db:
            row = db.execute('SELECT * FROM legacy_records WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError('legacy record not found')
        manifest = check_plain_path(self.root / row['archive_rel'])
        if not manifest.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Legacy archive path outside data root')
        result = verify_legacy(manifest)
        if (result['bundle_sha256'] != identity or result['manifest_sha256'] != row['manifest_sha256']
                or result['analysis_sha256'] != row['analysis_sha256']):
            raise ValueError('Legacy archive identity changed')
        return result | {'id': identity, 'imported_at': row['imported_at']}

    def export_public(self, output_dir):
        """Compatibility method for a PRIVATE evidence dump, not a website.

        Exposed only as CLI export-evidence. Use catalog.export_catalog or CLI
        export-public/export-v5 for a safe public website. Original source bytes
        may include IPs, authors and quotations and must remain private.
        """
        destination = check_plain_path(output_dir)
        if destination.exists() and any(destination.iterdir()):
            raise ValueError('public export requires a new or empty directory')
        destination.mkdir(parents=True, exist_ok=True)
        records = []
        with self._db() as db:
            rows = db.execute('''SELECT a.*,j.source_url,j.post_id
                FROM analyses a JOIN jobs j ON j.id=a.job_id
                WHERE a.version=(SELECT max(b.version) FROM analyses b WHERE b.job_id=a.job_id)
                ORDER BY j.post_id''').fetchall()
        for row in rows:
            from .archive import verify_archive
            manifest_path = self._manifest(row)
            manifest = verify_archive(manifest_path)
            envelope = json.loads(row['envelope'])
            record = {'post_id': row['post_id'], 'source_url': row['source_url'],
                      'analysis_version': row['version'], 'archive_sha256': row['archive_sha256'],
                      'analysis': json.loads(row['normalized']), 'observations': envelope['observations'],
                      'review_log': envelope['review_log'], 'manifest': manifest,
                      'validation': json.loads(row['validation'])}
            # Public evidence has a .txt/.bin suffix for HTML/SVG to avoid active content.
            public_files = []
            for f in manifest['files']:
                filename = f['id'] + ('.txt' if f['role'].endswith('text') else '.bin')
                if not re.fullmatch(r'[A-Za-z0-9_-]+\.(?:txt|bin)', filename):
                    raise ValueError('invalid public evidence identifier')
                relative = Path('evidence') / row['post_id'] / filename
                out = destination / relative
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes((manifest_path.parent / f['path']).read_bytes())
                public_files.append({'id': f['id'], 'path': relative.as_posix(),
                                     'sha256': f['sha256'], 'content_type': f['content_type']})
            record['public_evidence'] = public_files
            records.append(record)
        from .legacy_projection import public_legacy_record
        # Historical imports stay distinguishable from newly accepted analyses.
        # Their original quotes, HTML, images, author and review declarations stay
        # in the private archive and are never copied into the public directory.
        legacy_records = [public_legacy_record(self.get_legacy(item['id'])) for item in self.list_legacy()]
        payload = {'schema_version': 'vps-public-export/1', 'v5_ui_integration': 'use_safe_catalog_export',
                   'visibility': 'private_evidence', 'publish_safe': False,
                   'generated_at': now(), 'records': records, 'legacy_records': legacy_records}
        (destination / 'reviews.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        (destination / 'README.txt').write_text('PRIVATE EVIDENCE EXPORT. DO NOT PUBLISH.\nContains original source text/images and reviewer declarations; may contain IP addresses, author information and quotations.\nUse export-public or export-v5 for the safe facts-only website.\n', encoding='utf-8')
        return {'status': 'exported', 'visibility': 'private_evidence', 'publish_safe': False,
                'records': len(records), 'legacy_records': len(legacy_records), 'v5_ui_integration': 'use_safe_catalog_export',
                'output': str(destination)}
