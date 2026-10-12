#!/usr/bin/env python3
"""Rebuild the gold-text PNGs and native vectors from local package inputs.

Python dependencies: Pillow and numpy. Renderer: ImageMagick's `magick`.
The existing lettering paths are scaled by exactly 2, while the existing gold
texture keeps its native 1024px scale and position. No new texture is generated.

Run this file from any working directory. The required source SVGs and unchanged
gold texture are included under sources/input for a portable, repeatable export.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 1024
SCALE = 2.0
SUPERSAMPLE = 4
FILL = '#DAD4B9'
LAYERS = (('02-rudolf', 'Rudolf'), ('03-steiner', 'Steiner'), ('04-ga', 'GA'))
NS = '{http://www.w3.org/2000/svg}'
TOKEN = re.compile(r'[MCZ]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?')


def read_path(filename):
    svg = ET.parse(filename).getroot()
    assert svg.attrib.get('viewBox') == '0 0 1024 1024'
    paths = svg.findall(NS + 'path')
    assert paths and all(p.attrib.get('fill-rule') == 'evenodd' for p in paths)
    commands = []
    for path in paths:
        tokens = TOKEN.findall(path.attrib['d'])
        i = 0
        while i < len(tokens):
            command = tokens[i]
            i += 1
            assert command in ('M', 'C', 'Z'), f'Unsupported SVG command: {command}'
            count = {'M': 2, 'C': 6, 'Z': 0}[command]
            coords = np.array([float(v) for v in tokens[i:i+count]]).reshape((-1, 2))
            i += count
            commands.append((command, coords))
    return commands


def bezier_point(p, t):
    return ((1-t)**3*p[0] + 3*(1-t)**2*t*p[1] +
            3*(1-t)*t*t*p[2] + t**3*p[3])


def bounds(commands):
    """Use analytic extrema, rather than control bounds or curve sampling."""
    extrema, current, start = [], None, None
    for command, coords in commands:
        if command == 'M':
            current = start = coords[0]
            extrema.append(current)
        elif command == 'C':
            p = np.vstack((current, coords))
            candidates = {0.0, 1.0}
            for dimension in (0, 1):
                q = p[:, dimension]
                # B'(t)/3 = a*t^2 + b*t + c.
                a = -q[0] + 3*q[1] - 3*q[2] + q[3]
                b = 2*(q[0] - 2*q[1] + q[2])
                c = q[1] - q[0]
                if abs(a) < 1e-12:
                    if abs(b) > 1e-12:
                        t = -c / b
                        if 0 < t < 1:
                            candidates.add(t)
                else:
                    discriminant = b*b - 4*a*c
                    if discriminant >= 0:
                        for t in ((-b + math.sqrt(discriminant))/(2*a),
                                  (-b - math.sqrt(discriminant))/(2*a)):
                            if 0 < t < 1:
                                candidates.add(t)
            extrema.extend(bezier_point(p, t) for t in candidates)
            current = coords[-1]
        else:
            current = start
    extrema = np.array(extrema)
    return np.concatenate((extrema.min(axis=0), extrema.max(axis=0)))


def serialize(commands):
    return ' '.join(command + (' ' + ' '.join(f'{v:.6f}'.rstrip('0').rstrip('.')
                                             for v in coords.flatten()) if coords.size else '')
                    for command, coords in commands)


def svg(title, paths, fill=FILL, pixel_size=SIZE):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{pixel_size}" '
            f'height="{pixel_size}" viewBox="0 0 1024 1024">\n'
            f'  <title>{title}</title>\n'
            '  <desc>Original native lettering paths enlarged exactly 2.0 times '
            'and centred together on a 1024px canvas. No replacement font.</desc>\n'
            f'  <path fill="{fill}" fill-rule="evenodd" d="{paths}"/>\n'
            '</svg>\n')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rect_from_alpha(alpha):
    yy, xx = np.where(alpha > 0)
    return [int(xx.min()), int(yy.min()), int(xx.max())+1, int(yy.max())+1]


def main():
    package = Path(__file__).resolve().parents[1]
    inputs = package / 'sources' / 'input'
    material = inputs / 'gold-stamping.png'
    gold = Image.open(material).convert('RGB')
    assert gold.size == (SIZE, SIZE), 'Gold texture must remain at its native 1024px scale.'
    gold_rgb = np.asarray(gold)
    original = [(name, title, read_path(inputs / 'vectors' / (name + '.svg')))
                for name, title in LAYERS]
    all_original = [command for _, _, commands in original for command in commands]
    old_bounds = bounds(all_original)
    old_center = (old_bounds[:2] + old_bounds[2:]) / 2
    translation = np.array([SIZE/2, SIZE/2]) - SCALE*old_center
    transformed = [(name, title, [(command, coords*SCALE + translation)
                                  for command, coords in commands])
                   for name, title, commands in original]
    all_new = [command for _, _, commands in transformed for command in commands]
    new_bounds = bounds(all_new)
    assert np.all(new_bounds[:2] > 0) and np.all(new_bounds[2:] < SIZE), 'Clipped geometry.'
    assert np.allclose(new_bounds[2:] - new_bounds[:2],
                       SCALE*(old_bounds[2:] - old_bounds[:2]), atol=1e-9)
    assert np.allclose((new_bounds[:2]+new_bounds[2:])/2, [SIZE/2, SIZE/2], atol=1e-9)
    combined = ('05-lettering-combined', 'Rudolf Steiner GA', all_new)
    outputs, masks = [], {}
    for name, title, commands in [*transformed, combined]:
        paths = serialize(commands)
        native = package / 'vectors' / (name + '-200pct.svg')
        native.write_text(svg(title + ' — 200%', paths), encoding='utf-8')
        render_source = package / 'sources' / ('.render-' + name + '.svg')
        render_source.write_text(svg(title + ' white silhouette', paths, '#FFFFFF',
                                     SIZE*SUPERSAMPLE), encoding='utf-8')
        highres = package / 'masks' / '4x' / (name + '-mask-200pct-4096.png')
        subprocess.run(['magick', '-background', 'none', str(render_source), '-depth', '8',
                        'PNG32:' + str(highres)], check=True)
        render_source.unlink()
        hi = Image.open(highres).convert('RGBA')
        assert hi.size == (SIZE*SUPERSAMPLE, SIZE*SUPERSAMPLE)
        alpha_image = hi.getchannel('A').resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        alpha = np.asarray(alpha_image)
        assert alpha.max() == 255 and alpha.min() == 0
        assert not np.any(alpha[[0, -1], :]) and not np.any(alpha[:, [0, -1]])
        assert not np.any(np.asarray(hi.getchannel('A'))[[0, -1], :])
        mask = Image.new('RGBA', (SIZE, SIZE), (255, 255, 255, 0))
        mask.putalpha(alpha_image)
        mask_path = package / 'masks' / (name + '-mask-200pct.png')
        mask.save(mask_path, optimize=True)
        masks[name] = alpha
        # Keep straight (unpremultiplied) RGBA texture color at edge pixels.
        # Set fully transparent RGB to zero for compact and clean PNG export.
        rgba = np.dstack((gold_rgb, alpha)).copy()
        rgba[alpha == 0, :3] = 0
        filename = ('rudolf-steiner-ga-gold-200pct.png' if name == combined[0]
                    else name + '-gold-200pct.png')
        png = package / filename
        Image.fromarray(rgba, 'RGBA').save(png, optimize=True)
        reopened = np.asarray(Image.open(png))
        assert Image.open(png).mode == 'RGBA' and Image.open(png).size == (SIZE, SIZE)
        assert np.array_equal(reopened[:, :, 3], alpha)
        assert np.array_equal(reopened[alpha > 0, :3], gold_rgb[alpha > 0])
        source_commands = all_original if name == combined[0] else next(c for n, _, c in original if n == name)
        source_bounds = bounds(source_commands)
        output_bounds = bounds(commands)
        assert np.allclose(output_bounds[2:] - output_bounds[:2],
                           SCALE*(source_bounds[2:] - source_bounds[:2]), atol=1e-9)
        outputs.append({'name': title, 'png': filename, 'svg': str(native.relative_to(package)),
                        'mask': str(mask_path.relative_to(package)),
                        'mask_4x': str(highres.relative_to(package)),
                        'source_geometry_bbox_xyxy': source_bounds.tolist(),
                        'geometry_bbox_xyxy': output_bounds.tolist(),
                        'visible_alpha_bbox_xyxy_exclusive': rect_from_alpha(alpha),
                        'geometry_width_scale': float((output_bounds[2]-output_bounds[0])/(source_bounds[2]-source_bounds[0])),
                        'geometry_height_scale': float((output_bounds[3]-output_bounds[1])/(source_bounds[3]-source_bounds[1])),
                        'closed_contours': sum(command == 'M' for command, _ in commands)})
    merged_individuals = np.maximum.reduce([masks[name] for name, _ in LAYERS])
    assert np.array_equal(merged_individuals, masks[combined[0]]), 'Individual/combined export mismatch.'
    metadata = {
        'canvas_px': [SIZE, SIZE], 'lettering_scale': SCALE,
        'scale_meaning': 'Visible glyph width and height are 200% of the preceding native paths on the SAME 1024px canvas.',
        'transform': {'formula': 'output_xy = 2.0 * source_xy + translation_xy',
                      'translation_xy': translation.tolist(), 'source_geometry_center_xy': old_center.tolist(),
                      'output_geometry_center_xy': [SIZE/2, SIZE/2]},
        'source_combined_geometry_bbox_xyxy': old_bounds.tolist(),
        'output_combined_geometry_bbox_xyxy': new_bounds.tolist(),
        'gold_texture': {'input': str(material.relative_to(package)), 'native_size_px': list(gold.size),
                         'sha256': sha256(material), 'sampling': 'unchanged 1:1 at the same canvas coordinates'},
        'antialiasing': 'SVG rasterization at 4096x4096; alpha downsampled to 1024x1024 with Lanczos.',
        'checks': {'exact_geometry_scale_2x': True, 'all_geometry_centred': True,
                   'no_clipping': True, 'transparent_rgba': True,
                   'texture_rgb_preserved': True, 'combined_equals_aligned_individuals': True},
        'outputs': outputs,
    }
    (package / 'sources' / 'export-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
