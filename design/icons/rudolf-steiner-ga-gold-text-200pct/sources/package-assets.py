#!/usr/bin/env python3
"""Package finished native lettering exports without changing artwork."""
from pathlib import Path
import hashlib
import json
import zipfile
from PIL import Image

root = Path(__file__).resolve().parents[1]
out = root.parent / (root.name + '-assets.zip')
entries = []
for path in sorted(root.rglob('*')):
    if not path.is_file() or path.name in {'.DS_Store', 'asset-manifest.json'}:
        continue
    record = {'file': str(path.relative_to(root)), 'bytes': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if path.suffix.lower() == '.png':
        with Image.open(path) as image:
            record.update(dimensions=list(image.size), mode=image.mode)
            if 'A' in image.getbands():
                alpha = image.getchannel('A')
                record['alphaRange'] = list(alpha.getextrema())
                record['alphaBounds'] = alpha.getbbox()
    entries.append(record)
manifest = {
    'name': 'Rudolf Steiner GA — gold-textured lettering, 200% size',
    'canvas': [1024, 1024],
    'letteringScale': 2.0,
    'increasePercent': 100,
    'combinedPNG': 'rudolf-steiner-ga-gold-200pct.png',
    'separatePNGs': ['02-rudolf-gold-200pct.png', '03-steiner-gold-200pct.png', '04-ga-gold-200pct.png'],
    'transparentForeground': True,
    'goldTextureBakedIn': True,
    'materialChanged': False,
    'fontsRequired': False,
    'geometry': 'sources/export-metadata.json',
    'guide': 'IMPORT.txt',
    'files': entries,
}
(root / 'asset-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name != '.DS_Store':
            archive.write(path, str(Path(root.name) / path.relative_to(root)))
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None, 'Archive integrity failure'
    count = len(archive.namelist())
print(json.dumps({'zip': str(out), 'files': count, 'bytes': out.stat().st_size}))
