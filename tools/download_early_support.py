#!/usr/bin/env python3
"""Download and preserve historical source scans, OCR, and public evidence.

The selected Archive.org identifiers are source volumes, never substitutes for
the contemporary GA edition. Existing files are reused after size validation.
No catalog files are written. Requires Poppler pdftotext for PDF extraction.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'research/unavailable-recovery/early'
UA = 'Mozilla/5.0 (compatible; GA source research)'
SETS = {
    '001a-e': ['werkegoe33goetuoft', 'werkegoe34goetuoft', 'werkegoe35goetuoft',
               'pt01werkegoe36goetuoft', 'pt02werkegoe36goetuoft'],
    '001f': ['pt02werkegoeth06goet', 'pt02werkegoeth07goet', 's02p03werkegoethe08goet',
             's02p01werkegoethe09goet', 's02p02werkegoethe10goet',
             'bub_gb_PiNAAAAAYAAJ', 'werkeabthnaturw00raabgoog'],
}
EVIDENCE = {
    'RudolfSteinerVerlag_GV_2022.pdf': 'https://steinerverlag.com/wp-content/uploads/RudolfSteinerVerlag_GV_2022.pdf',
    'RSV-Fruehjahr_2025.pdf': 'https://steinerverlag.com/wp-content/uploads/RSV-Fruehjahr_2025.pdf',
    'Flyer-GA-online-web.pdf': 'https://steinerverlag.com/wp-content/uploads/Flyer-GA-online-web.pdf',
    'RSA_Jahresbericht_2024.pdf': 'https://www.rudolf-steiner.com/wp-content/uploads/2025/04/250307_RSA_Jahresbericht_24-klein.pdf',
}
GA4A = 'https://rudolfsteinerelib.org/Download/German/Dokumente_zu_Philosophie_der_Freiheit--Rudolf_Steiner--004a.pdf'


def download(url, path, size=None, fallback=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (size is None or path.stat().st_size == size):
        # This one file pair was retrieved through the public storage host after
        # the canonical endpoint repeatedly returned HTTP 500.
        used = fallback if 'pt01werkegoe36goetuoft' in str(path) and fallback else url
    else:
        errors = []
        for used in [url, fallback]:
            if not used:
                continue
            try:
                request = urllib.request.Request(used, headers={'User-Agent': UA})
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = response.read()
                    used = response.url
                if size is not None and len(data) != size:
                    raise ValueError(f'Expected {size} bytes, got {len(data)}')
                tmp = path.with_name(path.name + '.part')
                tmp.write_bytes(data)
                tmp.replace(path)
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as error:
                errors.append(str(error))
        else:
            raise RuntimeError(f'{url}: {errors}')
    return {'source_url': used, 'canonical_url': url,
            'local_path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def historical_source(pair):
    work, identifier = pair
    metadata_path = BASE / 'goethe-source-metadata' / (identifier + '.json')
    log = [download('https://archive.org/metadata/' + identifier, metadata_path)]
    metadata = json.loads(metadata_path.read_text())
    filenames = [identifier + ('.djvu' if identifier == 'werkeabthnaturw00raabgoog' else '.pdf'),
                 identifier + '_djvu.txt']
    files = {file['name']: file for file in metadata['files']}
    for filename in filenames:
        file = files[filename]
        path = BASE / ('ga-' + work) / 'historical-sources' / identifier / filename
        url = 'https://archive.org/download/' + identifier + '/' + urllib.parse.quote(filename)
        fallback = 'https://' + metadata['d1'] + metadata['dir'] + '/' + urllib.parse.quote(filename)
        record = download(url, path, int(file['size']), fallback)
        if file.get('md5') and hashlib.md5(path.read_bytes()).hexdigest() != file['md5']:
            raise ValueError('Archive metadata MD5 mismatch: ' + str(path))
        record['archive_md5_verified'] = bool(file.get('md5'))
        log.append(record)
    print(json.dumps({'historical_source': identifier, 'preserved_files': len(filenames)}), flush=True)
    return log


def pdf_source(pair):
    filename, url = pair
    path = BASE / 'evidence' / filename
    record = download(url, path)
    txt = path.with_suffix('.txt')
    subprocess.run(['pdftotext', '-layout', str(path), str(txt)], check=True)
    record['extracted_text_path'] = str(txt.relative_to(ROOT))
    return record


def main():
    pairs = [(work, identifier) for work, identifiers in SETS.items() for identifier in identifiers]
    log = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for records in pool.map(historical_source, pairs):
            log.extend(records)
    pdf = BASE / 'ga-004a/originals/GA004a-1994.pdf'
    log.append(download(GA4A, pdf))
    subprocess.run(['pdftotext', '-layout', str(pdf), str(BASE / 'ga-004a/GA004a-pdftotext.txt')], check=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        log.extend(pool.map(pdf_source, EVIDENCE.items()))
    preview = BASE / 'evidence/RSV-Fruehjahr_2025.txt'
    lines = preview.read_text().splitlines()
    start = next(n for n, text in enumerate(lines) if 'Habe eben Nietzsche gesehen.' in text)
    column = lines[start].index('Habe')
    end = next(n for n in range(start, len(lines)) if '(Notizbuch 321, S. 5)' in lines[n])
    excerpt = '\n'.join(text[column:].replace('\u00ad', '').strip() for text in lines[start:end + 1])
    (BASE / 'evidence/notebook-321-page-5-preview.txt').write_text(excerpt + '\n')
    discovery = {
        'Wikisource-Goethe-original.html': 'https://de.wikisource.org/wiki/Johann_Wolfgang_von_Goethe',
        'Wikisource-DNL-original.html': 'https://de.wikisource.org/wiki/Deutsche_National-Litteratur',
    }
    for filename, url in discovery.items():
        try:
            log.append(download(url, BASE / 'evidence' / filename))
        except Exception as error:
            log.append({'source_url': url, 'status': 'discovery_page_download_failed', 'error': str(error)})
    (BASE / 'support-downloads.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'support_source_records': len(log)}), flush=True)


if __name__ == '__main__':
    main()
