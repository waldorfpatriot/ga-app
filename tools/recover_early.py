#!/usr/bin/env python3
"""Preserve public GA source HTML and extract embedded German originals.

Run with the bundled Python runtime (lxml). Downloads never update the reader
catalog. The manifest deliberately separates text coverage from edition proof.
"""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/unavailable-recovery/early"
REPORT = ROOT / "tools/recovery-early.json"
UA = "Mozilla/5.0 (compatible; GA source research)"
SCOPES = {
    "001f": ("Books", "German/"),
    "018a": ("Books", None),
    "019": ("Books", "German/index.html"),
    "037": ("Articles", None),
    "041a": ("Articles", None),
    "041b": ("Articles", None),
    "042": ("Articles", None),
    "043": ("Articles", None),
    "046": ("Articles", None),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes(), url
    # The public site accepts its canonical HTTP links and redirects to HTTPS.
    # Mozilla user agent avoids an otherwise inconsistent 403 for normal pages.
    failures = []
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                resolved = response.url
            if len(data) < 500 or b"Just a moment..." in data[:5000]:
                raise ValueError("Empty page or Cloudflare interstitial")
            path.write_bytes(data)
            return data, resolved
        except Exception as error:
            failures.append(str(error))
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError("; ".join(failures))


def block_text(element):
    # Keep verse/stage directions line by line and prose paragraph boundaries.
    for tag in element.xpath('.//br'):
        tag.tail = '\n' + (tag.tail or '')
    for tag in element.xpath('.//p|.//h1|.//h2|.//h3|.//h4|.//h5|.//tr|.//li'):
        tag.tail = '\n\n' + (tag.tail or '')
    return re.sub(r'\n[ \t]+', '\n', element.text_content()).strip()


def extract(data, url):
    tree = html.fromstring(data.decode('utf-8', errors='replace'))
    title = tree.xpath('string(//title)').strip()
    nodes = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," German ")]')
    mode = 'embedded_original_German'
    if not nodes and '/German/' in url:
        nodes = tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," articleBox ")]')
        mode = 'standalone_German_article'
        if nodes:
            for bad in nodes[0].xpath('.//*[contains(@class,"lectureNav")]|.//script|.//button'):
                bad.getparent().remove(bad)
    if not nodes:
        return title, '', 'no_German_original_found'
    # Recent archive pages nest an automatic English translation inside the
    # German container. Only the original text belongs in the German corpus.
    originals = [n for node in nodes for n in node.xpath('.//*[@id="original"]')]
    if originals:
        nodes = originals
        mode += '_original_only'
    for node in nodes:
        for bad in node.xpath('.//*[@id="autoTranslation"]|.//script|.//button'):
            bad.getparent().remove(bad)
    text = '\n\n'.join(block_text(n) for n in nodes)
    return title, text, mode


def chapter(work, order, label, url):
    filename = f"{order:03d}-" + urllib.parse.unquote(Path(urllib.parse.urlsplit(url).path).name)
    path = OUT / ('ga-' + work) / 'originals' / filename
    record = {'order': order, 'label': label, 'source_url': url, 'original_path': str(path.relative_to(ROOT))}
    try:
        data, resolved = fetch(url, path)
        title, text, mode = extract(data, url)
        record.update(resolved_url=resolved, original_sha256=digest(data), original_bytes=len(data), title=title, extraction_mode=mode)
        if text:
            txt = path.parent.parent / 'german' / (path.stem + '.txt')
            txt.parent.mkdir(exist_ok=True)
            txt.write_text(text + '\n', encoding='utf-8')
            record.update(text_path=str(txt.relative_to(ROOT)), text_sha256=digest(txt.read_bytes()), text_chars=len(text), status='German_text_recovered')
        else:
            record.update(text_chars=0, status='no_German_original_in_HTML')
    except Exception as error:
        record.update(status='download_failed', text_chars=0, error=str(error))
    return record


def recover(work, folder, tail):
    index_url = f'http://rsarchive.org/{folder}/GA{work}/' + (tail or '')
    target = OUT / ('ga-' + work)
    data, resolved = fetch(index_url, target / 'index-original.html')
    tree = html.fromstring(data.decode('utf-8', errors='replace'))
    prefix = f'/{folder}/GA{work}/'
    links = []
    seen = set()
    for a in tree.xpath('//a[@href]'):
        u = urllib.parse.urljoin(index_url, a.get('href'))
        path = urllib.parse.urlsplit(u).path
        if not path.startswith(prefix) or not path.endswith('.html') or path.endswith('index.html'):
            continue
        if not ('/English/' in path or '/German/' in path):
            continue
        if work == '018a':
            u = 'http://rsarchive.org/Books/GA018a/German/' + Path(path).name
        if work == '019':
            # Five index links are stale. Existing neighboring source pages'
            # lecture navigation supplies the actual canonical filenames.
            repaired = {
                '46-1_Zweites_Memorandum_erste_Fassung.html': 'GA019_c46-1.html',
                '46-2_Zweites Memorandum_zweites_fassung.html': 'GA019_c46-2.html',
                'GA019_c47«Die_‹Schuld›_am_Kriege».html': 'GA019_c47.html',
                '47-1_An_das_deutsche_Volk.html': 'GA019_c47-1.html',
                'GA019_c49«Matin»-Interview.html': 'GA019_c49.html',
            }
            name = urllib.parse.unquote(Path(path).name)
            if name in repaired:
                u = 'http://rsarchive.org/Books/GA019/German/' + repaired[name]
        # Percent encode Unicode titles in legacy GA19 page URLs.
        u = urllib.parse.quote(u, safe=':/?=&%')
        if u not in seen:
            seen.add(u)
            links.append((' '.join(a.itertext()).strip(), u))
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(chapter, work, n, label, u) for n, (label, u) in enumerate(links, 1)]
        records = [f.result() for f in futures]
    related_records = []
    if work == '043':
        # The current GA43 index references two essays housed in GA36. Preserve
        # them separately because the current GA43 volume prints excerpts.
        for a in tree.xpath('//a[@href]'):
            path = urllib.parse.urlsplit(a.get('href')).path
            if path.startswith('/Articles/GA036/') and path.endswith('.html'):
                related_records.append(chapter(work, len(records) + len(related_records) + 1,
                    ' '.join(a.itertext()).strip(), urllib.parse.urljoin(index_url, a.get('href'))))
    combined = '\n\n'.join((ROOT / r['text_path']).read_text() for r in records if r.get('text_path'))
    combined_path = target / 'german-author-text.txt'
    combined_path.write_text(combined, encoding='utf-8')
    passages = []
    for r in records:
        if not r.get('text_path'):
            continue
        if work == '018a' and Path(urllib.parse.urlsplit(r['source_url']).path).name == 'Reviews.html':
            continue  # Third-party contemporary reviews remain preserved separately.
        original = (ROOT / r['text_path']).read_text().rstrip('\n')
        source_tree = html.fromstring((ROOT / r['original_path']).read_bytes())
        german_nodes = source_tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," German ")]')
        headings = (german_nodes[0] if german_nodes else source_tree).xpath('.//h3|.//h4')
        heading = ' '.join(headings[0].itertext()).strip() if headings else r['label']
        passages.append({
            'id': f'ga-{work}-recovered-{r["order"]:03d}', 'title': heading,
            'text': original, 'source_text': original, 'checksum': digest(original.encode()),
            'source_url': r['resolved_url'], 'source_label': 'Rudolf Steiner Archive: original German source text',
            'ga_page': None, 'metadata': {'page_numbers': [], 'annotations': [], 'original_html_sha256': r['original_sha256'], 'original_html_path': r['original_path']},
        })
    candidate_path = target / 'reader-candidate.json'
    candidate_path.write_text(json.dumps({'work_id': 'ga-' + work, 'language': 'de', 'content_completeness': 'candidate', 'proofing': {'status': 'requires_edition_collation', 'publishable': False}, 'passages': passages}, ensure_ascii=False, indent=2) + '\n')
    result = {
        'id': 'ga-' + work, 'index_url': index_url, 'resolved_index_url': resolved,
        'index_path': str((target / 'index-original.html').relative_to(ROOT)), 'index_sha256': digest(data),
        'indexed_sections': len(records), 'recovered_sections': sum(r['status'] == 'German_text_recovered' for r in records),
        'text_chars': len(combined), 'combined_text_path': str(combined_path.relative_to(ROOT)), 'combined_text_sha256': digest(combined.encode()),
        'status': 'author_text_candidate_requires_volume_collation',
        'completeness': 'Web index coverage only; modern GA front matter, facsimiles, annotations and exact volume completeness not established.',
        'language': 'de', 'chapters': records,
        'related_chapters': related_records,
        'reader_candidate_path': str(candidate_path.relative_to(ROOT)), 'reader_candidate_sha256': digest(candidate_path.read_bytes()),
    }
    print(json.dumps({k: result[k] for k in ['id','indexed_sections','recovered_sections','text_chars']}, ensure_ascii=False), flush=True)
    return result


def main():
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {'works': []}
    report.update(generated_at=datetime.now(timezone.utc).isoformat(), scope='Early unavailable GA source recovery; reader catalog untouched')
    existing = {work['id']: work for work in report['works']}
    for work, (folder, tail) in SCOPES.items():
        try:
            existing['ga-' + work] = recover(work, folder, tail)
        except Exception as error:
            existing['ga-' + work] = {'id': 'ga-' + work, 'status': 'recovery_failed', 'error': str(error), 'text_chars': 0}
        report['works'] = list(existing.values())
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
