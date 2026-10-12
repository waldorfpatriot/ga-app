#!/usr/bin/env python3
"""Inventory and package the selected assets without modifying artwork."""
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
    item = {'file': str(path.relative_to(root)), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if path.suffix.lower() == '.png':
        with Image.open(path) as image:
            item.update(dimensions=list(image.size), mode=image.mode)
            if 'A' in image.getbands():
                alpha = image.getchannel('A')
                item['alphaRange'] = list(alpha.getextrema())
                item['alphaBounds'] = alpha.getbbox()
    entries.append(item)

manifest = {
    'name': 'Rudolf Steiner GA — blue linen and pale gold',
    'canvas': [1024, 1024],
    'layerOrderBottomToTop': ['01-linen-background.png', '02-rudolf-gold.png',
                             '03-steiner-gold.png', '04-ga-gold.png'],
    'combinedAlternative': ['01-linen-background.png', 'alternatives/02-lettering-combined-gold.png'],
    'material': 'materials/gold-stamping.png',
    'vectors': ['vectors/02-rudolf.svg', 'vectors/03-steiner.svg', 'vectors/04-ga.svg'],
    'fontsRequired': False,
    'roundCornersApplied': False,
    'materialReference': 'reference/original-book-cover.png',
    'layoutReference': 'reference/approved-layout.png',
    'materialMethod': 'Built-in ImageGen reference-based reconstruction from the original 300×400 photo. Not exact pixel extraction.',
    'selectedMaterialSources': {'linen': 'sources/linen-imagegen.png', 'gold': 'sources/gold-imagegen-selected.png'},
    'letteringMethod': 'Native SVG outline trace of the approved layout, exported through alpha masks with the shared reconstructed gold material.',
    'measuredSourceColorTargets': {'linen': '#3B5D90', 'gold': '#DAD4B9'},
    'recommendedComposerSettings': {'effects': False, 'opacity': 1.0, 'shadow': 'none'},
    'guide': 'IMPORT.txt',
    'prompts': 'sources/final-prompts.txt',
    'appleGuidance': ['https://developer.apple.com/documentation/xcode/creating-your-app-icon-using-icon-composer',
                     'https://developer.apple.com/design/human-interface-guidelines/app-icons/',
                     'https://developer.apple.com/videos/play/wwdc2025/361/'],
    'verification': {'importPNGs': '1024×1024; full-canvas alignment; foreground alpha matches masks exactly',
                     'SVGs': 'Paths only; glyph holes preserved; no fonts required',
                     'preview': 'Visually inspected; no clipped letters, leftover text, opaque foreground rectangles or rounded outer mask'},
    'files': entries,
}
(root / 'asset-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.name != '.DS_Store':
            archive.write(path, str(Path(root.name) / path.relative_to(root)))
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None, 'Archive integrity failure'
    count = len(archive.namelist())
print(json.dumps({'folder': str(root), 'zip': str(out), 'files': count, 'zipBytes': out.stat().st_size}, ensure_ascii=False))
