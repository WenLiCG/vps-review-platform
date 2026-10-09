"""Conservative, offline validation of already-existing browser archives.

This is a separate historical-import boundary, not an alternate way to submit
new analysis. No source files are rewritten, no model is called, and historical
``ai_review`` declarations are preserved without being independently attested.
Only an unpacked assets/<post_id>/manifest.json directory is supported; archives
are never opened or extracted. All source bytes are bounded and hash checked.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from . import archive as ar
from .analysis import SKILL_ROOT, _load_review


VALIDATOR_VERSION = 'vps-pipeline-legacy/1'
MAX_ANALYSIS_BYTES = 8 * 1024 * 1024
MAX_REPORT_DEPTH = 2
_RESERVED = {'manifest.json', 'analysis.json', 'provenance.json', 'validation.json', 'bundle.json'}
_ARCHIVES = {'.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.7z', '.rar'}
_URL = re.compile(r'https?://[^\s<>"\x27`\x1b]+')
_SKIP = {'script', 'style', 'template', 'noscript'}
LIMITATIONS = [
    'Historical browser_import first-post identity is a capture declaration, not a fresh verified capture.',
    'Historical ai_review is retained as supplied; reviewer identity, reading and OCR accuracy are not independently verified.',
    'No new review, model call, observation, or review log is created by legacy import.',
    'Structural, integrity and quote checks do not prove that factual claims or images are correct.',
]


class LegacyError(ar.ArchiveError):
    """An existing archive cannot safely enter the historical import layer."""


def _require(condition, message):
    if not condition:
        raise LegacyError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _compact(text):
    # This is the unchanged original validator's quotation normalization.
    return ''.join(text.split())


def _load_json(data, label):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, 'Duplicate JSON properties are not accepted')
            result[key] = value
        return result

    def nonfinite(value):
        raise LegacyError('Nonfinite JSON numbers are not accepted')

    try:
        value = json.loads(ar._decode(data), object_pairs_hook=unique, parse_constant=nonfinite)
        # Also rejects exponent overflows such as 1e999, not just NaN tokens.
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, LegacyError):
            raise
        raise LegacyError(f'{label} must contain valid finite JSON') from exc
    _require(isinstance(value, dict), f'{label} must be a JSON object')
    return value


def _safe_evidence_path(base, value, used):
    path = ar._safe_relative(base, value)
    parts = value.split('/')
    _require(not any(any(ord(c) < 32 or ord(c) == 127 for c in part)
                     or part.endswith((' ', '.')) for part in parts), 'Unsafe evidence path component')
    _require(not any(part.casefold() in _RESERVED for part in parts),
             'Evidence path collides with reserved metadata')
    _require(not any(re.fullmatch(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])',
                                 part.split('.')[0], re.I) for part in parts),
             'Platform-reserved evidence path is not accepted')
    _require(path.suffix.lower() not in _ARCHIVES, 'Archive evidence and ZIP import are not supported')
    key = tuple(part.casefold() for part in parts)
    _require(not any(key == other or key[:len(other)] == other or other[:len(key)] == key
                     for other in used), 'Duplicate or conflicting evidence paths')
    used.add(key)
    return path


def _visible_nodes(node):
    """Unlike a flat DOM walk, this never discovers script/template-only URLs."""
    if node.tag in _SKIP or node.has_class('xterm-helpers'):
        return
    yield node
    for child in node.children:
        if isinstance(child, ar._Node):
            yield from _visible_nodes(child)


def _kind(url):
    if ar._is_report(url):
        return 'report'
    if re.search(r'cart\.php|aff=|affiliate|/order|/buy', url, re.I):
        return 'purchase'
    return 'other'


def _observed(root, text, base, exact=False):
    """Return image/link URL evidence with locators, never manifest assertions.

    Report-to-report edges require an absolute target literally present in a
    readable text token or an anchor/iframe attribute. Relative URL expansion,
    encoded redirect targets and substring matches cannot create second hops.
    """
    images, links = {}, {}
    for index, node in enumerate(_visible_nodes(root)):
        if node.tag == 'img' and not exact:
            attr = 'data-src' if node.attrs.get('data-src') else 'src'
            value = node.attrs.get(attr)
            if value:
                url = ar._resolve(value, base)
                images.setdefault(url, {'locator': f'html-node:{index}/img@{attr}', 'quote': value})
        if node.tag in {'a', 'iframe'}:
            attr = 'href' if node.tag == 'a' else 'src'
            value = node.attrs.get(attr)
            if value:
                url = ar._resolve(value, base)
                if (not exact or value == url) and url.startswith(('https://', 'http://')):
                    links.setdefault(url, {'locator': f'html-node:{index}/{node.tag}@{attr}', 'quote': value})
    for match in _URL.finditer(text):
        url = match.group().rstrip('.,;，。；)）')
        links.setdefault(url, {'locator': f'text-character:{match.start()}-{match.start() + len(url)}',
                               'quote': url})
    _require(len(images) + len(links) <= ar.MAX_RESOURCES, 'Resource/link count limit exceeded')
    return images, links


class _FragmentDOM(ar._DOM):
    """Saved outerHTML is balanced; do not repair an ambiguous pasted snippet."""

    def handle_endtag(self, tag):
        _require(len(self.stack) > 1 and self.stack[-1].tag == tag,
                 'First-post fragment has unbalanced or mismatched HTML tags')
        super().handle_endtag(tag)


def _fragment(document):
    _require(not re.search(r'<!doctype|<\?xml|cf-chl-|challenge-platform', document, re.I),
             'Full-page, challenge or non-fragment HTML is not supported')
    dom = _FragmentDOM(document)
    _require(len(dom.stack) == 1, 'First-post fragment has unclosed HTML tags')
    root = dom.root
    elements = [n for n in root.children if isinstance(n, ar._Node)]
    all_nodes = list(root.walk())
    _require(len(elements) == 1 and elements[0].tag == 'article'
             and elements[0].has_class('post-content')
             and not any(isinstance(n, str) and n.strip() for n in root.children),
             'first_post_html must be one article.post-content fragment')
    _require(sum(n.tag == 'article' for n in all_nodes) == 1
             and sum(n.has_class('post-content') for n in all_nodes) == 1
             and not any(n.tag in {'html', 'head', 'body', 'title'}
                         or (n.attrs.get('id') or '').strip().isdigit()
                         or any(n.has_class(c) for c in {'reply', 'replies', 'post-list', 'post-item'})
                         for n in all_nodes), 'Full-page, reply or numeric post markers are ambiguous')
    _require(bool(root.text().strip()), 'First-post fragment has no readable text')
    return root


def _collapsed_text(node):
    """Model the documented 971510 visible-text capture's closed details only."""
    if node.tag in _SKIP or node.has_class('xterm-helpers'):
        return ''
    children = node.children
    if node.tag == 'details' and 'open' not in node.attrs:
        children = [n for n in children if isinstance(n, ar._Node) and n.tag == 'summary'][:1]
    return ''.join(_collapsed_text(n) if isinstance(n, ar._Node) else n for n in children)


def _supplement(manifest, first, by_id, texts, root):
    candidates = [f for f in by_id.values() if f['source_url'] == manifest['source_url'] + '#0']
    if not candidates:
        _require(root.text().strip() == texts[first['first_post_text']['id']].strip(),
                 'First-post HTML and primary text disagree')
        return None
    _require(manifest['post_id'] == '971510' and len(candidates) == 1,
             'Only the documented 971510 first-post supplement is supported')
    extra = candidates[0]
    _require(extra['role'] == 'report_text' and extra['content_type'] == 'text/plain',
             'First-post supplement must retain its historical report_text role')
    note = manifest['capture_note']
    # These terms tie the exception to the existing recorded derivation. An
    # arbitrary #0 report or new assertion alone is never enough: both text
    # equalities below are checked against the original hashed fragment.
    _require(all(token in note for token in ('首帖', 'details', 'report_text', 'DOM', '#0', '提取')),
             'Capture note must declare the existing first-post details derivation')
    _require(_compact(texts[extra['id']]) == _compact(root.text()),
             'First-post supplement does not exactly match full fragment text')
    _require(_compact(texts[first['first_post_text']['id']]) == _compact(_collapsed_text(root)),
             'Historical visible text does not match the collapsed first-post fragment')
    return {'file_id': extra['id'], 'original_role': extra['role'],
            'derived_role': 'first_post_supplement', 'from_file_id': first['first_post_html']['id'],
            'source_url': extra['source_url'], 'derivation': 'full_fragment_text_whitespace_normalized',
            'primary_text_check': 'closed_details_summary_only_whitespace_normalized'}


def _verify_manifest(path, manifest):
    _require(manifest.get('schema_version') == 'vps-archive/1', 'Unsupported legacy archive schema')
    post_id, canonical = ar.normalize_post_url(manifest.get('source_url'))
    _require(manifest.get('post_id') == post_id and path.parent.name == post_id
             and manifest['source_url'] == canonical, 'Legacy archive identity mismatch')
    _require(manifest.get('capture_method') == 'browser_import'
             and isinstance(manifest.get('capture_note'), str) and manifest['capture_note'].strip(),
             'Explicit browser_import and a nonempty capture_note are required')
    note = manifest['capture_note']
    _require(re.search(r'#0|零楼|首帖|first[- ]post', note, re.I)
             and re.search(r'非回复|不含回复|排除回复|no replies|not replies|exclud(?:e|es|ing) replies', note, re.I),
             'Capture note must explicitly declare first-post identity and exclusion of replies')
    _require(manifest.get('status') in {'ready', 'partial'}, 'Legacy archive must be ready or partial')
    try:
        captured = datetime.fromisoformat(manifest['captured_at'])
        _require(captured.utcoffset() is not None, 'captured_at must include a timezone')
    except (KeyError, ValueError, TypeError) as exc:
        raise LegacyError('captured_at must be an ISO timestamp with timezone') from exc
    _require(all(manifest.get(k) is None or isinstance(manifest[k], str) for k in ('title', 'author')),
             'Title and author must be strings or null')
    files = manifest.get('files')
    _require(isinstance(files, list) and 2 <= len(files) <= ar.MAX_RESOURCES + 2,
             'Invalid legacy evidence file list')
    by_id, texts, first, paths, used, total = {}, {}, {}, {}, set(), 0
    for item in files:
        _require(isinstance(item, dict), 'Invalid legacy evidence record')
        role, mime, fid = item.get('role'), item.get('content_type'), item.get('id')
        _require(isinstance(role, str) and role in ar.ROLES and isinstance(mime, str) and mime in ar.ROLES[role],
                 'Unsupported evidence role or MIME')
        _require(isinstance(fid, str) and fid.strip() and len(fid) <= 200 and fid != 'manifest' and fid not in by_id,
                 'Missing, reserved or duplicate evidence ID')
        digest, length, source = item.get('sha256'), item.get('bytes'), item.get('source_url')
        _require(isinstance(digest, str) and ar._SHA.fullmatch(digest)
                 and type(length) is int and 0 < length <= ar.MAX_BYTES, 'Invalid evidence digest or byte length')
        _require(isinstance(source, str), 'Evidence source URL is missing')
        if role.startswith('first_post_'):
            _require(source == canonical and role not in first, 'Duplicate or unexpected first-post source')
            first[role] = item
        else:
            ar._public_url_syntax(source)
            _require(not role.startswith('report_') or ar._is_report(source)
                     or (post_id == '971510' and source == canonical + '#0' and role == 'report_text'),
                     'Report host is not allowed')
        target = _safe_evidence_path(path.parent, item.get('path'), used)
        _require(total + length <= ar.MAX_TOTAL_BYTES, 'Archive exceeds total evidence size limit')
        contents = ar._read_bytes(target, min(ar.MAX_BYTES, ar.MAX_TOTAL_BYTES - total))
        _require(len(contents) == length and _sha(contents) == digest, 'Legacy evidence SHA256/byte integrity failure')
        total += length
        if role == 'image':
            _require(ar._image_type(contents, source)[0] == mime, 'Image MIME differs from signature')
        else:
            decoded = ar._decode(contents)
            _require(bool(decoded.strip()), 'Empty text evidence')
            if role.startswith('report_'):
                _require(not (role == 'report_text' and re.search(
                    r'<!doctype\s+html|</?(?:html|head|body|script|style|template|noscript|a|iframe|img)\b', decoded, re.I)),
                         'HTML cannot claim report_text MIME')
                _require(ar._report_type(contents, target)[0] == role, 'Report role does not match content')
            texts[fid] = decoded
        by_id[fid], paths[fid] = item, target
    _require(set(first) == {'first_post_html', 'first_post_text'}, 'Both first-post HTML and text are required')
    html_id = first['first_post_html']['id']
    root = _fragment(texts[html_id])
    supplement = _supplement(manifest, first, by_id, texts, root)
    images, links = _observed(root, root.text(), canonical)
    observed_links = {url: _kind(url) for url in links}
    for url in images.keys() | links.keys():
        ar._public_url_syntax(url)
    roots = {(url, 'image'): locator for url, locator in images.items()}
    roots.update({(url, 'report'): locator for url, locator in links.items()
                  if ar._is_report(url) and url not in images})
    chains, reached, resources = [], {}, {}
    supplement_id = supplement['file_id'] if supplement else None
    for fid, item in by_id.items():
        if item['role'].startswith('first_post_') or fid == supplement_id:
            continue
        key = (item['source_url'], 'image' if item['role'] == 'image' else 'report')
        _require(key not in resources, 'Duplicate resource source identity')
        resources[key] = fid
        if key in roots:
            reached[fid] = 1
            chains.append({'from_file_id': html_id, 'target_file_id': fid, 'url': key[0],
                           'depth': 1, **roots[key]})
    # Only first-hop reports can establish second-hop report provenance. Images
    # and unreachable/self-citing reports can never authorize another file.
    second_links = {}
    for fid, depth in list(reached.items()):
        item = by_id[fid]
        if not item['role'].startswith('report_') or depth >= MAX_REPORT_DEPTH:
            continue
        if item['role'] == 'report_html':
            report_root = ar._DOM(texts[fid]).root
            _, found = _observed(report_root, report_root.text(), item['source_url'], exact=True)
        else:
            _, found = _observed(ar._Node(), texts[fid], item['source_url'], exact=True)
        for url, locator in found.items():
            if not ar._is_report(url):
                continue
            ar._public_url_syntax(url)
            second_links.setdefault(url, (fid, locator))
            target_id = resources.get((url, 'report'))
            if target_id and target_id not in reached:
                reached[target_id] = 2
                chains.append({'from_file_id': fid, 'target_file_id': target_id, 'url': url,
                               'depth': 2, **locator})
    _require(set(resources.values()) <= reached.keys(),
             'Resource lacks an observed first-post or bounded report provenance chain')
    declared = manifest.get('links')
    _require(isinstance(declared, list) and len(declared) <= ar.MAX_RESOURCES, 'Invalid manifest links')
    declared_by_url = {}
    for link in declared:
        _require(isinstance(link, dict) and isinstance(link.get('url'), str)
                 and isinstance(link.get('kind'), str), 'Invalid manifest link')
        url, kind = link['url'], link['kind']
        _require(url not in declared_by_url, 'Duplicate manifest links')
        _require((url in observed_links and kind == observed_links[url])
                 or (url in second_links and kind == 'report')
                 or (supplement and url == supplement['source_url'] and kind == 'report'),
                 'Manifest link is not supported by observed evidence')
        declared_by_url[url] = kind
    _require(all(declared_by_url.get(url) == kind for url, kind in observed_links.items()),
             'Manifest omits or misclassifies an observed first-post link')
    expected = set(roots) | {(url, 'report') for url, kind in declared_by_url.items()
                            if kind == 'report' and url in second_links}
    failures = manifest.get('failures')
    _require(isinstance(failures, list) and len(failures) <= ar.MAX_RESOURCES, 'Invalid resource failures')
    missing = {url for url, kind in expected if (url, kind) not in resources}
    failed = set()
    for failure in failures:
        _require(isinstance(failure, dict) and isinstance(failure.get('url'), str)
                 and isinstance(failure.get('reason'), str) and failure['reason'].strip()
                 and failure['url'] in missing and failure['url'] not in failed,
                 'Failure does not identify one missing observed resource')
        failed.add(failure['url'])
    _require(failed == missing, 'Missing observed resources require explicit failure reasons')
    _require(manifest['status'] == ('partial' if failures else 'ready'), 'Status differs from resource failures')
    return by_id, paths, texts, root, chains, supplement, total


def _source_binding(evidence, fact, files, first_root):
    """Recognize narrow historical DOM bindings, never factual measurements.

    Historical analysis sometimes cited the image URL/tab label to distinguish
    report panels, alongside an independently cited archived image. This does
    not permit arbitrary raw markup, attribute strings or script quotations.
    """
    image_ids = {e['file_id'] for e in fact['evidence']
                 if e['file_id'] != 'manifest' and files[e['file_id']]['role'] == 'image'}
    if not image_ids:
        return None
    quote = evidence['quote']
    nodes = list(_visible_nodes(first_root))
    matches = {fid for fid in image_ids if files[fid]['source_url'] == quote}
    if matches and any(node.tag == 'img'
                       and not any(attr.startswith('on') for attr in node.attrs)
                       and quote in (node.attrs.get('src'), node.attrs.get('data-src'))
                       for node in nodes):
        return {'binding_type': 'image_source_url', 'image_file_ids': sorted(matches)}
    # The only supported historical markup locator is a plain tab-title div,
    # with no extra attributes, nested markup, executable content or wildcards.
    if re.fullmatch(r'<div class="nsk-magic-tab-title">[^<>]+</div>', quote):
        candidate = ar._DOM(quote).root.children[0]
        if (isinstance(candidate, ar._Node) and candidate.text().strip()
                and candidate.markup() == quote
                and any(node.tag == 'div' and node.attrs == {'class': 'nsk-magic-tab-title'}
                        and all(isinstance(c, str) for c in node.children)
                        and node.markup() == quote for node in nodes)):
            return {'binding_type': 'tab_label_dom', 'image_file_ids': sorted(image_ids)}
    return None


def _validate_analysis(analysis, manifest, base, files, texts, first_root):
    for key, expected in {
        'sources': manifest['files'], 'archive_status': manifest['status'],
        'download_failures': manifest['failures'],
        'source_metadata': {k: manifest.get(k) for k in ('title', 'author', 'captured_at', 'capture_method', 'capture_note')},
    }.items():
        _require(key not in analysis or analysis[key] == expected,
                 f'Historical analysis {key} does not match the original manifest')
    ai = analysis.get('ai_review')
    _require(isinstance(ai, dict) and isinstance(ai.get('reviewed_files'), list)
             and all(isinstance(fid, str) and fid.strip() for fid in ai['reviewed_files'])
             and len(ai['reviewed_files']) == len(set(ai['reviewed_files'])),
             'Historical reviewed_files must contain unique file IDs')
    review = _load_review()
    quote_checks = []
    try:
        # This unchanged vendor code validates the original 61-field contract
        # and declared historical ai_review. Its computed return is discarded.
        normalized = review.normalized(analysis, manifest, base)
        _require(normalized == analysis,
                 'Historical analysis requires normalization changes; original values cannot be silently repaired')
        for field_id, fact in analysis['facts'].items():
            for evidence in fact['evidence']:
                fid = evidence['file_id']
                if fid == 'manifest' or files[fid]['role'] == 'image':
                    continue
                role = files[fid]['role']
                text = (first_root.text() if role == 'first_post_html' else
                        ar._DOM(texts[fid]).root.text() if role == 'report_html' else texts[fid])
                if _compact(evidence['quote']) not in _compact(text):
                    binding = _source_binding(evidence, fact, files, first_root) if role == 'first_post_html' else None
                    _require(binding is not None, 'Historical quote is absent from readable source text')
                    quote_checks.append({'field_id': field_id, 'file_id': fid, 'locator': evidence['locator'],
                                         'kind': 'historical_html_source_binding',
                                         'measurement_verified': False, **binding})
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        if isinstance(exc, LegacyError):
            raise
        # Do not interpolate untrusted validator values or local source paths.
        raise LegacyError('Historical analysis fails the original 61-field/review protocol') from exc
    return quote_checks


def verify_legacy(manifest_path, analysis_path=None) -> dict:
    """Verify existing browser evidence and analysis without modifying either.

    ``analysis_path`` defaults to sibling analysis.json. The returned manifest
    and analysis are their unchanged original parsed values. The bundle digest
    binds the original bytes with explicit 64-bit big-endian length framing:
    SHA256(b'vps-legacy-bundle/1\\0' + manifest length + manifest bytes + analysis
    length + analysis bytes). Evidence bytes are transitively bound by manifest
    SHA-256 entries. No internal filesystem paths are added to the result.
    """
    try:
        path = ar._local_path(manifest_path)
        _require(path.suffix.lower() not in _ARCHIVES, 'ZIP/archive import is not supported; use an unpacked directory')
        _require(path.name == 'manifest.json' and path.parent.parent.name == 'assets',
                 'Expected assets/<post_id>/manifest.json protocol directory')
        analysis_file = ar._local_path(analysis_path if analysis_path is not None else path.parent / 'analysis.json')
        _require(analysis_file.suffix.lower() == '.json', 'Analysis must be a JSON file, never a ZIP/archive')
        manifest_bytes = ar._read_bytes(path, ar.MAX_MANIFEST_BYTES)
        analysis_bytes = ar._read_bytes(analysis_file, MAX_ANALYSIS_BYTES)
        manifest = _load_json(manifest_bytes, 'Manifest')
        analysis = _load_json(analysis_bytes, 'Analysis')
        files, paths, texts, root, chains, supplement, total = _verify_manifest(path, manifest)
        _require(analysis_file not in paths.values(), 'Analysis path collides with evidence')
        quote_checks = _validate_analysis(analysis, manifest, path.parent, files, texts, root)
        _require(ar._read_bytes(path, ar.MAX_MANIFEST_BYTES) == manifest_bytes
                 and ar._read_bytes(analysis_file, MAX_ANALYSIS_BYTES) == analysis_bytes,
                 'Original metadata changed during legacy verification')
        for fid, target in paths.items():
            contents = ar._read_bytes(target)
            _require(len(contents) == files[fid]['bytes'] and _sha(contents) == files[fid]['sha256'],
                     'Evidence changed during legacy verification')
    except (ar.ArchiveError, OSError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, LegacyError):
            raise
        if isinstance(exc, ar.ArchiveError):
            raise LegacyError(str(exc)) from exc
        raise LegacyError('Cannot safely verify legacy inputs') from exc
    bundle = (b'vps-legacy-bundle/1\0' + len(manifest_bytes).to_bytes(8, 'big') + manifest_bytes
              + len(analysis_bytes).to_bytes(8, 'big') + analysis_bytes)
    missing = [key for key in ('observations', 'review_log') if key not in analysis]
    warnings = list(LIMITATIONS)
    if missing:
        warnings.append('Historical analysis lacks new-envelope fields: ' + ', '.join(missing))
    if manifest['status'] == 'partial':
        warnings.append('Original archive is partial; its download failures remain unchanged.')
    return {
        'status': 'legacy_imported', 'post_id': manifest['post_id'], 'source_url': manifest['source_url'],
        'manifest': manifest, 'analysis': analysis, 'manifest_sha256': _sha(manifest_bytes),
        'analysis_sha256': _sha(analysis_bytes), 'bundle_sha256': _sha(bundle),
        'provenance': {'schema_version': 'vps-legacy-provenance/1',
                       'capture_method': manifest['capture_method'],
                       'first_post_identity': 'historical_browser_import_declaration',
                       'resource_chains': chains, 'max_report_depth': MAX_REPORT_DEPTH,
                       'derived_files': [supplement] if supplement else [],
                       'quote_checks': quote_checks,
                       'historical_ai_review': analysis['ai_review'],
                       'missing_new_envelope_fields': missing,
                       'original_bytes_preserved': True},
        'validation': {'validator_version': VALIDATOR_VERSION,
                       'original_validator_sha256': _sha((SKILL_ROOT / 'scripts' / 'review.py').read_bytes()),
                       'field_catalog_sha256': _sha((SKILL_ROOT / 'references' / 'fields.json').read_bytes()),
                       'field_count': 61, 'archive_status': manifest['status'],
                       'evidence_file_count': len(files), 'evidence_bytes': total,
                       'missing_new_envelope_fields': missing, 'warnings': warnings,
                       'new_review_performed': False, 'ai_invoked': False,
                       'review_attestation_verified': False, 'new_analysis_accepted': False},
    }
