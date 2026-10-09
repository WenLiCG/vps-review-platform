"""Immutable public-site profiles and offline URL scope checks. No new dependencies."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
import uuid

import soupsieve


def _public_ip(value):
    address = ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and not (address.version == 6 and address.ipv4_mapped and not address.ipv4_mapped.is_global)


def _path(value):
    decoded = unquote(value)
    if ('\\' in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
            or any(part in {'.', '..'} for part in decoded.split('/'))
            or unquote(decoded) != decoded):
        raise ValueError('Ambiguous or traversing URL path')
    return decoded


def validate_public_url(url, resolve=False):
    """Validate syntax/public literals; DNS is opt-in and must also be checked at transport."""
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url) or '\\' in url:
        raise ValueError('Invalid public URL')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 80 if parsed.scheme == 'http' else 443}):
            raise ValueError()
        host = parsed.hostname.rstrip('.').encode('idna').decode('ascii').lower()
        if '%' in host:
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if ('.' not in host or host.endswith(('.localhost', '.local', '.internal', '.invalid', '.test'))
                    or all(part.isdecimal() for part in host.split('.'))
                    or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.'))):
                raise ValueError()
        else:
            if not _public_ip(host):
                raise ValueError()
            host = address.compressed
        path = parsed.path or '/'
        _path(path)
        normalized = urlunsplit((parsed.scheme, '[' + host + ']' if ':' in host else host, path, parsed.query, ''))
    except (ValueError, UnicodeError):
        raise ValueError('URL must use a public host, HTTP(S), and its standard port without credentials') from None
    if resolve:
        public_addresses(normalized)
    return normalized


def public_addresses(url):
    """Resolve all addresses and reject mixed/private answers; callers must pin the connection."""
    parsed = urlsplit(validate_public_url(url))
    try:
        values = tuple(sorted({item[4][0] for item in socket.getaddrinfo(
            parsed.hostname, 443 if parsed.scheme == 'https' else 80, type=socket.SOCK_STREAM)},
            key=lambda value: (ipaddress.ip_address(value).version, value)))
        if not values or not all(_public_ip(value) for value in values):
            raise ValueError('Target DNS includes a non-public address')
        return values
    except (OSError, ValueError):
        raise ValueError('Target does not resolve exclusively to public addresses') from None


def normalize_custom_url(profile, url, base=None):
    if not isinstance(url, str) or not url.strip():
        return ''
    try:
        result = validate_public_url(urljoin(base or profile['seed'], url))
        candidate, seed = urlsplit(result), urlsplit(profile['seed'])
        if (candidate.scheme, candidate.netloc) != (seed.scheme, seed.netloc):
            return ''
        path = _path(candidate.path)
        if not any(prefix == '/' or path == prefix.rstrip('/') or path.startswith(prefix.rstrip('/') + '/')
                   for prefix in profile['path_prefixes']):
            return ''
        return result
    except (ValueError, TypeError):
        return ''


def validate_profile(value, resolve=False):
    allowed = {'schema_version', 'id', 'label', 'seed', 'allowed_hosts', 'path_prefixes',
               'platform', 'content_selector', 'link_selector'}
    if (not isinstance(value, dict) or set(value) - allowed
            or type(value.get('schema_version', 1)) is not int or value.get('schema_version', 1) != 1):
        raise ValueError('Invalid site profile schema')
    ident = value.get('id', '')
    if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', ident):
        raise ValueError('Profile id must contain lowercase letters, digits, underscores or hyphens')
    label = value.get('label', ident)
    if not isinstance(label, str) or not label.strip() or len(label) > 120 or any(ord(c) < 32 for c in label):
        raise ValueError('Invalid profile label')
    seed = validate_public_url(value.get('seed'), resolve=resolve)
    parsed = urlsplit(seed)
    hosts = value.get('allowed_hosts', [parsed.hostname])
    if not isinstance(hosts, list) or hosts != [parsed.hostname]:
        raise ValueError('A custom profile is restricted to the seed host; use another profile for another origin')
    default_path = parsed.path if parsed.path.endswith('/') else parsed.path.rsplit('/', 1)[0] + '/'
    paths = value.get('path_prefixes', [default_path])
    if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
        raise ValueError('Supply 1 to 16 path prefixes')
    normalized_paths = []
    for path in paths:
        if not isinstance(path, str) or not path.startswith('/') or '?' in path or '#' in path or any(c.isspace() for c in path):
            raise ValueError('Invalid path prefix')
        normalized_paths.append(_path(path).rstrip('/') or '/')
    platform = value.get('platform', 'auto')
    if not isinstance(platform, str) or platform not in {'auto', 'xenforo', 'vbulletin', 'discuz', 'html'}:
        raise ValueError('Unsupported site platform')
    profile = dict(schema_version=1, id=ident, label=label.strip(), seed=seed, allowed_hosts=hosts,
                   path_prefixes=sorted(set(normalized_paths)), platform=platform)
    for key in ('content_selector', 'link_selector'):
        selector = value.get(key)
        if selector is not None:
            if not isinstance(selector, str) or not selector.strip() or len(selector) > 512:
                raise ValueError('Invalid ' + key)
            try:
                soupsieve.compile(selector)
            except Exception:
                raise ValueError('Invalid CSS selector: ' + key) from None
            profile[key] = selector
    if not normalize_custom_url(profile, seed):
        raise ValueError('Seed is outside the configured paths')
    return profile


def profile_hash(profile):
    return hashlib.sha256(json.dumps(validate_profile(profile), sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def register_profiles(profiles):
    from sites import SITES
    if not isinstance(profiles, list):
        raise ValueError('Profiles must be a list')
    normalized = [validate_profile(profile) for profile in profiles]
    if len({p['id'] for p in normalized}) != len(normalized):
        raise ValueError('Duplicate profile id')
    for profile in normalized:
        old = SITES.get(profile['id'])
        if old and (not old.get('custom') or profile_hash(old['profile']) != profile_hash(profile)):
            raise ValueError('Profile id is already registered with another immutable definition')
    for profile in normalized:
        SITES.setdefault(profile['id'], {'custom': True, 'profile': profile, 'seed': profile['seed'],
                                       'hosts': set(profile['allowed_hosts']), 'platform': profile['platform']})
    return normalized


def _snapshot(profiles):
    if not isinstance(profiles, list):
        raise ValueError('Profiles must be a list')
    normalized = sorted((validate_profile(p) for p in profiles), key=lambda p: p['id'])
    if len({p['id'] for p in normalized}) != len(normalized):
        raise ValueError('Duplicate profile id')
    return {'schema_version': 1, 'profiles': normalized, 'hashes': {p['id']: profile_hash(p) for p in normalized}}


def load_profiles(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'profiles', 'hashes'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise ValueError('Invalid frozen profile document')
    expected = _snapshot(value['profiles'])
    if value != expected:
        raise ValueError('Frozen profile definitions or hashes do not match')
    return register_profiles(expected['profiles'])


def save_profiles(path, profiles):
    """Publish once atomically. A different existing snapshot is never overwritten."""
    value = _snapshot(profiles)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            if json.loads(path.read_text(encoding='utf-8')) != value:
                raise ValueError('This run already has a different frozen profile') from None
    finally:
        temporary.unlink(missing_ok=True)
    return value
