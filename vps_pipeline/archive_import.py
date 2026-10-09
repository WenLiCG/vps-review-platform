"""Explicit offline ingress for existing, strictly verified evidence archives.

This is not capture or historical-analysis import. Only the named manifest and
its referenced evidence are copied, byte for byte. Nothing is extracted,
rewritten, fetched, or declared reviewed. Existing snapshots remain immutable.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from . import archive as ar
from .store import check_plain_path, now, sha


_ARCHIVES = {'.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.7z', '.rar'}
_RESERVED = {'manifest.json', '.import.lock'}


def _layout(source, manifest):
    """Preflight paths and the entire declared budget before reading evidence."""
    files = manifest.get('files') if isinstance(manifest, dict) else None
    if not isinstance(files, list) or not 2 <= len(files) <= ar.MAX_RESOURCES + 2:
        raise ar.ArchiveError('Invalid evidence file list')
    total, paths = 0, {}
    for record in files:
        if not isinstance(record, dict):
            raise ar.ArchiveError('Invalid evidence file record')
        length = record.get('bytes')
        if type(length) is not int or not 0 < length <= ar.MAX_BYTES:
            raise ar.ArchiveError('Invalid evidence byte length')
        total += length
        if total > ar.MAX_TOTAL_BYTES:
            raise ar.ArchiveError('Archive exceeds total evidence size limit')
        path = ar._safe_relative(source.parent, record.get('path'))
        parts = record['path'].split('/')
        if any(part.casefold() in _RESERVED or part.endswith((' ', '.'))
               or any(ord(c) < 32 or ord(c) == 127 for c in part)
               or re.fullmatch(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])', part.split('.')[0], re.I)
               for part in parts):
            raise ar.ArchiveError('Unsafe or reserved evidence path component')
        if path.suffix.lower() in _ARCHIVES:
            raise ar.ArchiveError('Archive evidence and ZIP import are not supported')
        key = tuple(part.casefold() for part in parts)
        signature = tuple(record.get(k) for k in ('path', 'sha256', 'bytes', 'role', 'content_type'))
        for previous, previous_signature in paths.items():
            # Identical content-addressed files may be shared by different URLs.
            if key == previous and signature == previous_signature:
                continue
            if key[:len(previous)] == previous or previous[:len(key)] == key:
                raise ar.ArchiveError('Conflicting evidence paths')
        paths[key] = signature


def _verified_source(manifest_path):
    source = check_plain_path(manifest_path)
    if source.name != 'manifest.json' or source.parent.parent.name != 'assets':
        raise ar.ArchiveError('Expected assets/<post_id>/manifest.json; ZIP input is not supported')
    payload = ar._read_bytes(source, ar.MAX_MANIFEST_BYTES)
    try:
        manifest = json.loads(ar._decode(payload), object_pairs_hook=ar._json_unique)
        # Do not copy non-finite metadata that other JSON consumers cannot use.
        json.dumps(manifest, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ar.ArchiveError('Invalid finite manifest JSON') from exc
    _layout(source, manifest)
    verified = ar.verify_archive(source)
    if verified != manifest or ar._read_bytes(source, ar.MAX_MANIFEST_BYTES) != payload:
        raise ar.ArchiveError('Archive manifest changed during verification')
    return source, payload, verified


def _write_new(path, payload):
    # Staging is owner-only. Exclusive writes cannot modify an earlier snapshot.
    with path.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def import_archive(store, job_id, manifest_path):
    """Copy one verified archive into a queued job, ready for fresh review.

    Claims the same bounded lease as HTML ingress. A duplicate current manifest
    is reverified without creating files and keeps its accepted state. A changed
    manifest gets a new snapshot; prior accepted analysis versions stay intact.
    """
    row, token = store._claim(job_id, 'archiving',
                              {'queued', 'failed', 'blocked', 'awaiting_analysis', 'accepted'})
    staging = None
    try:
        source, payload, manifest = _verified_source(manifest_path)
        if manifest['post_id'] != row['post_id'] or manifest['source_url'] != row['source_url']:
            raise ar.ArchiveError('Archive identity does not match the queued job')
        digest = sha(payload)
        duplicate = bool(row.get('archive_rel') and digest == row['archive_sha256'])
        if duplicate:
            current = check_plain_path(store.root / row['archive_rel'])
            if not current.resolve().is_relative_to(store.root.resolve()):
                raise ar.ArchiveError('Current archive path is outside the data root')
            _, previous_payload, _ = _verified_source(current)
            if previous_payload != payload:
                raise ar.ArchiveError('Current archive differs from the imported manifest')
            target_manifest = current
        else:
            stage = check_plain_path(store.root / 'tmp' / ('archive-' + token))
            stage.mkdir(mode=0o700)
            # Assign only after successful creation: never clean another owner's path.
            staging = stage
            stage_post = stage / 'assets' / row['post_id']
            stage_post.mkdir(parents=True)
            _write_new(stage_post / 'manifest.json', payload)
            remaining, copied = ar.MAX_TOTAL_BYTES, set()
            for record in manifest['files']:
                original = ar._safe_relative(source.parent, record['path'])
                data = ar._read_bytes(original, min(ar.MAX_BYTES, remaining, record['bytes']))
                if len(data) != record['bytes'] or sha(data) != record['sha256']:
                    raise ar.ArchiveError('Archive evidence changed during import')
                remaining -= len(data)
                if record['path'] not in copied:
                    target = ar._safe_relative(stage_post, record['path'])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _write_new(target, data)
                    copied.add(record['path'])
            if ar._read_bytes(source, ar.MAX_MANIFEST_BYTES) != payload:
                raise ar.ArchiveError('Archive manifest changed during import')
            _, staged_payload, _ = _verified_source(stage_post / 'manifest.json')
            if staged_payload != payload:
                raise ar.ArchiveError('Copied archive manifest differs')
            parent = check_plain_path(store.root / 'archives' / job_id)
            parent.mkdir(mode=0o700, exist_ok=True)
            destination = check_plain_path(parent / ('snapshot-' + token))
            target_manifest = destination / 'assets' / row['post_id'] / 'manifest.json'

        state = 'accepted' if duplicate and row['status'] == 'accepted' else 'awaiting_analysis'
        with store._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = store._row(db, job_id)
            if (current['lease_token'] != token or current['status'] != 'archiving'
                    or current['lease_until'] is None or current['lease_until'] <= time.time()):
                raise ValueError('Task lease changed or expired before archive commit')
            if not duplicate:
                check_plain_path(destination)
                if destination.exists():
                    raise ar.ArchiveError('Immutable archive destination already exists')
                # The atomic rename comes before SQL. A failed commit can leave
                # a complete orphan, but never a ledger pointer to a partial copy.
                staging.rename(destination)
            db.execute('UPDATE jobs SET status=?,archive_rel=?,archive_sha256=?,lease_token=NULL,'
                       'lease_until=NULL,last_error=NULL,updated_at=? WHERE id=?',
                       (state, target_manifest.relative_to(store.root).as_posix(), digest, now(), job_id))
            store._event(db, job_id, 'archive_duplicate' if duplicate else 'awaiting_analysis',
                         {'ingress': 'verified_archive', 'archive_status': manifest['status'],
                          'failures': manifest.get('failures', []), 'capture_metadata_preserved': True})
        return store.get_job(job_id) | {'duplicate': duplicate}
    except Exception as exc:
        store._finish_error(job_id, token, exc, row['status'] if row.get('archive_rel') else 'failed')
        raise
    finally:
        if staging is not None and staging.exists():
            check_plain_path(staging)
            shutil.rmtree(staging)
