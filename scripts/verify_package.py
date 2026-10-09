"""Verify the exact source package files without running imported package code."""
from pathlib import Path,PurePosixPath
import hashlib,json,stat

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
if manifest.get('schema_version')!='source-package/1' or not isinstance(manifest.get('sha256'),dict):
 raise SystemExit('Unsupported source package manifest')
for name,digest in manifest['sha256'].items():
 path=PurePosixPath(name)
 if path.is_absolute() or not path.parts or path.parts[0]!='vps-review-pipeline' or any(p in {'','.', '..'} for p in path.parts) or '\\' in name:
  raise SystemExit('Unsafe manifest path')
 target=root.joinpath(*path.parts[1:])
 for part in [target,*target.parents]:
  if part==root.parent:break
  info=part.lstat()
  if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise SystemExit('Symlink/reparse file rejected')
 if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise SystemExit('Hash mismatch: '+str(target.relative_to(root)))
print(json.dumps({'status':'pass','verified_files':len(manifest['sha256']),'algorithm':'SHA-256'}))
