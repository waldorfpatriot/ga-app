#!/usr/bin/env python3
"""Trace the approved lettering into native SVG paths; no replacement font.

Reads the reference without changing it. The gold/blue colour separation yields
subpixel contours using marching squares. RDP removes pixel stair steps, and
corner-aware cubic Bezier handles smooth the remaining points. SVG is rendered
only to create new white silhouette masks, using ImageMagick.

Requires Python with Pillow/numpy and ImageMagick. All output paths are restricted
to this asset package. Set --reference to reproduce with a relocated reference.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

CANVAS = 1024
FILL = '#DAD4B9'
REFERENCE = str(Path(__file__).resolve().parents[1] / 'reference' / 'approved-layout.png')
LAYERS = (
    ('02-rudolf', 'Rudolf', (480, 155, 780, 245)),
    ('03-steiner', 'Steiner', (480, 255, 780, 338)),
    ('04-ga', 'GA', (325, 422, 935, 738)),
)


def marching_squares(field, offset):
    """Return ordered subpixel closed contours for the level zero set."""
    h, w = field.shape
    adjacency, points = {}, {}

    def edge(row, col, side):
        # Grid-edge identity avoids joining using rounded floating coordinates.
        if side == 0:   # top
            key, a, b = ('h', row, col), (row, col), (row, col + 1)
        elif side == 1: # right
            key, a, b = ('v', row, col + 1), (row, col + 1), (row + 1, col + 1)
        elif side == 2: # bottom
            key, a, b = ('h', row + 1, col), (row + 1, col), (row + 1, col + 1)
        else:           # left
            key, a, b = ('v', row, col), (row, col), (row + 1, col)
        if key not in points:
            va, vb = field[a], field[b]
            t = float(va / (va - vb))
            # Raster samples are centred at (x + .5, y + .5) in the
            # SVG canvas coordinate system, not at pixel boundary corners.
            points[key] = np.array((a[1] + t * (b[1] - a[1]) + offset[0] + .5,
                                    a[0] + t * (b[0] - a[0]) + offset[1] + .5))
        return key

    pairs = {
        1: ((3, 0),), 2: ((0, 1),), 3: ((3, 1),),
        4: ((1, 2),), 6: ((0, 2),), 7: ((3, 2),),
        8: ((2, 3),), 9: ((0, 2),), 11: ((1, 2),),
        12: ((3, 1),), 13: ((0, 1),), 14: ((3, 0),),
    }
    bits = ((field[:-1, :-1] > 0).astype(np.uint8) |
            ((field[:-1, 1:] > 0).astype(np.uint8) << 1) |
            ((field[1:, 1:] > 0).astype(np.uint8) << 2) |
            ((field[1:, :-1] > 0).astype(np.uint8) << 3))
    for row, col in zip(*np.where((bits != 0) & (bits != 15))):
        case = int(bits[row, col])
        if case in (5, 10):
            center_positive = np.mean(field[row:row+2, col:col+2]) > 0
            if (case == 5) == center_positive:
                segments = ((0, 1), (2, 3))
            else:
                segments = ((3, 0), (1, 2))
        else:
            segments = pairs[case]
        for ea, eb in segments:
            ka, kb = edge(row, col, ea), edge(row, col, eb)
            adjacency.setdefault(ka, []).append(kb)
            adjacency.setdefault(kb, []).append(ka)
    unused, contours = set(adjacency), []
    while unused:
        start = next(iter(unused))
        current, previous, loop = start, None, []
        while True:
            loop.append(points[current])
            unused.discard(current)
            neighbors = adjacency[current]
            assert len(neighbors) == 2, 'Open contour; enlarge the layer region.'
            next_key = neighbors[0] if neighbors[0] != previous else neighbors[1]
            previous, current = current, next_key
            if current == start:
                break
        contours.append(np.array(loop))
    return contours


def area(points):
    q = np.roll(points, -1, axis=0)
    return .5 * float(np.sum(points[:, 0] * q[:, 1] - q[:, 0] * points[:, 1]))


def simplify_open(p, epsilon):
    if len(p) < 3:
        return p
    ab = p[-1] - p[0]
    if np.dot(ab, ab) == 0:
        distances = np.linalg.norm(p - p[0], axis=1)
    else:
        t = np.clip((p - p[0]) @ ab / (ab @ ab), 0, 1)
        distances = np.linalg.norm(p - p[0] - t[:, None] * ab, axis=1)
    split = int(np.argmax(distances))
    if distances[split] > epsilon:
        return np.concatenate((simplify_open(p[:split+1], epsilon)[:-1],
                               simplify_open(p[split:], epsilon)))
    return p[[0, -1]]


def simplify_closed(p, epsilon=.2):
    # Anchor to geometric extrema so reproductions have stable path starts.
    anchor = int(np.argmin(p[:, 0] + .0001 * p[:, 1]))
    p = np.roll(p, -anchor, axis=0)
    split = int(np.argmax(np.linalg.norm(p - p[0], axis=1)))
    first = simplify_open(p[:split+1], epsilon)
    second = simplify_open(np.concatenate((p[split:], p[:1])), epsilon)
    return np.concatenate((first[:-1], second[:-1]))


def path_cubics(p):
    """Use short tangents; retain corners with more than a 40 degree turn."""
    n = len(p)
    tangents, corners = [], []
    for i in range(n):
        incoming, outgoing = p[i] - p[(i-1) % n], p[(i+1) % n] - p[i]
        ai, ao = np.linalg.norm(incoming), np.linalg.norm(outgoing)
        ui, uo = incoming / ai, outgoing / ao
        corners.append(float(ui @ uo) < math.cos(math.radians(40)))
        tangent = ui + uo
        tangents.append(tangent / np.linalg.norm(tangent) if np.linalg.norm(tangent) > 0 else uo)
    result = []
    for i in range(n):
        j = (i + 1) % n
        delta = p[j] - p[i]
        distance = np.linalg.norm(delta)
        # Catmull-type handles capped by neighboring edge lengths prevent
        # overshoot at tiny serif details and changes in the sampling density.
        before = np.linalg.norm(p[i] - p[(i-1) % n])
        after = np.linalg.norm(p[(j+1) % n] - p[j])
        h1 = min(distance, before) / 3
        h2 = min(distance, after) / 3
        c1 = p[i] + (delta / 3 if corners[i] else tangents[i] * h1)
        c2 = p[j] - (delta / 3 if corners[j] else tangents[j] * h2)
        result.append((p[i], c1, c2, p[j]))
    return result


def number(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.')


def vectorize(contours, scale):
    all_curves, sections = [], []
    for contour in sorted(contours, key=lambda c: (float(np.min(c[:, 0])), -abs(area(c)))):
        if abs(area(contour)) < 2:
            continue
        points = simplify_closed(contour) * scale
        curves = path_cubics(points)
        all_curves.extend(curves)
        section = 'M' + ' '.join(number(v) for v in points[0])
        for _, c1, c2, end in curves:
            section += ' C' + ' '.join(number(v) for v in np.concatenate((c1, c2, end)))
        sections.append(section + ' Z')
    sample = []
    for start, c1, c2, end in all_curves:
        for t in np.linspace(0, 1, 30):
            sample.append((1-t)**3*start + 3*(1-t)**2*t*c1 + 3*(1-t)*t*t*c2 + t**3*end)
    sample = np.array(sample)
    bbox = [*np.min(sample, axis=0), *np.max(sample, axis=0)]
    return ' '.join(sections), [round(float(v), 3) for v in bbox], len(sections), len(all_curves)


def svg_document(title, paths, fill=FILL):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">\n'
            f'  <title>{title}</title>\n'
            '  <desc>Native outlines traced from the approved 1254px reference. '
            'Full-canvas alignment preserved; no font, embedded image or filter.</desc>\n'
            f'  <path fill="{fill}" fill-rule="evenodd" d="{paths}"/>\n'
            '</svg>\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', default=REFERENCE)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    reference = Path(args.reference).resolve()
    rgb = np.asarray(Image.open(reference).convert('RGB'), dtype=np.float64)
    height, width = rgb.shape[:2]
    assert width == height == 1254, 'This trace is defined for the approved 1254px reference.'
    # Gold is ~+100 and blue ~-95 in red-minus-blue chroma. The halfway
    # threshold of zero locates antialiased boundaries at subpixel precision.
    field = rgb[:, :, 0] - rgb[:, :, 2]
    scale = CANVAS / width
    all_paths, metadata = [], []
    for name, title, box in LAYERS:
        x0, y0, x1, y1 = box
        contours = marching_squares(field[y0:y1, x0:x1], (x0, y0))
        paths, bbox, loops, cubics = vectorize(contours, scale)
        destination = root / 'vectors' / f'{name}.svg'
        destination.write_text(svg_document(title, paths), encoding='utf-8')
        # This renders NEW vector geometry. It never edits the source image.
        mask_svg = root / 'sources' / f'{name}-white-mask.svg'
        mask_svg.write_text(svg_document(title + ' white silhouette', paths, '#FFFFFF'), encoding='utf-8')
        mask = root / 'masks' / f'{name}-mask.png'
        subprocess.run(['magick', '-background', 'none', '-density', '384', str(mask_svg),
                        '-resize', '1024x1024', '-depth', '8', 'PNG32:' + str(mask)], check=True)
        mask_svg.unlink()
        im = Image.open(mask)
        assert im.size == (CANVAS, CANVAS) and im.mode == 'RGBA'
        assert np.asarray(im)[:, :, 3].min() == 0
        all_paths.append(paths)
        metadata.append({'file': destination.name, 'bbox_xyxy': bbox,
                         'closed_contours': loops, 'cubic_segments': cubics,
                         'mask': mask.name})
    combined_paths = ' '.join(all_paths)
    (root / 'vectors' / '05-lettering-combined.svg').write_text(
        svg_document('Rudolf Steiner GA — combined aligned lettering', combined_paths), encoding='utf-8')
    combined_mask_svg = root / 'sources' / '05-lettering-combined-white-mask.svg'
    combined_mask_svg.write_text(svg_document('Combined white silhouettes', combined_paths, '#FFFFFF'), encoding='utf-8')
    subprocess.run(['magick', '-background', 'none', '-density', '384', str(combined_mask_svg),
                    '-resize', '1024x1024', '-depth', '8',
                    'PNG32:' + str(root / 'masks' / '05-lettering-combined-mask.png')], check=True)
    combined_mask_svg.unlink()
    result = {'reference': str(reference), 'reference_size': [width, height],
              'canvas': [CANVAS, CANVAS], 'fill': FILL,
              'method': 'Red-minus-blue level-zero marching-squares trace; subpixel interpolation; '
                        '0.20 source-pixel RDP simplification; corner-aware cubic Bezier paths; '
                        'evenodd holes; white mask rasterization from SVG at 4x resolution.',
              'layers': metadata}
    (root / 'sources' / 'lettering-trace.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
