"""Build a reproducible source ZIP from an explicit deliverable allowlist."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile


def build(output):
    root = Path(__file__).resolve().parents[1]
    files = []
    top_files = ['README.md', 'NOTICE', '.gitignore', 'pyproject.toml',
                 'requirements.txt', 'provenance.json', 'discovery.json']
    folders = ['vps_pipeline', 'vendor', 'tests', 'docs', 'deploy', 'examples', 'validation', 'scripts', 'website', 'bridge', 'skills', 'references']
    for name in top_files:
        files.append(root/name)
    for name in folders:
        files.extend(p for p in (root/name).rglob('*') if p.is_file())
    entries = {}
    for p in sorted(files):
        relative = p.relative_to(root)
        if '__pycache__' in relative.parts or p.suffix in {'.pyc', '.pyo'}:
            continue
        for component in (p, *p.parents):
            if component == root.parent:
                break
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Refusing symlink/reparse content in source package')
        if p.suffix in {'.sqlite', '.sqlite3', '.db'} or p.name in {'.env', '.import.lock'}:
            raise ValueError('Private runtime data must not enter the source package')
        entries['vps-review-pipeline/'+relative.as_posix()] = p.read_bytes()
    hashes = {name:hashlib.sha256(data).hexdigest() for name,data in entries.items()}
    entries['vps-review-pipeline/PACKAGE-MANIFEST.json'] = (
        json.dumps({'schema_version':'source-package/1','sha256':hashes},ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    payload = stream.getvalue()
    output = Path(output).absolute()
    if output.exists():
        if output.read_bytes() != payload:
            raise ValueError('Output exists with different bytes; choose another filename')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as handle:
            handle.write(payload)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name,digest in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    return {'path':str(output),'files':len(entries),'bytes':len(payload),
            'sha256':hashlib.sha256(payload).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(build(parser.parse_args().output),ensure_ascii=False,indent=2))
