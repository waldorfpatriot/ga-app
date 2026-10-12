#!/usr/bin/env python3
"""Add historical source sets, facsimile, and unresolved rows to recovery manifest.

Run after recover_early.py. Source files are preserved in the research directory;
this only writes the research manifest, never the catalog.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'research/unavailable-recovery/early'
REPORT = ROOT / 'tools/recovery-early.json'
CATALOG = {w['id']: w for w in json.loads((ROOT / 'server/priv/library/catalog.json').read_text())['works']}
IDS = ['001a-e', '001f', '004a', '018a', '019', '037', '038-1', '038-2', '038-3', '038-4', '038-5', '038-6', '041a', '041b', '042', '043', '046', '047-48', '048', '049']
PUBLISHER_CATALOG = 'https://steinerverlag.com/wp-content/uploads/RudolfSteinerVerlag_GV_2022.pdf'
ARCHIVE_REPORT = 'https://www.rudolf-steiner.com/wp-content/uploads/2025/04/250307_RSA_Jahresbericht_24-klein.pdf'
PUBLISHER_2025 = 'https://steinerverlag.com/wp-content/uploads/RSV-Fruehjahr_2025.pdf'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_file(path, url):
    return {'local_path': str(path.relative_to(ROOT)), 'source_url': url, 'sha256': sha(path), 'bytes': path.stat().st_size,
            'text_chars': len(path.read_text(errors='replace')) if path.suffix == '.txt' else None}


def historical(work, identifiers, mapping):
    sources = []
    chars = 0
    for item in identifiers:
        target = BASE / ('ga-' + work) / 'historical-sources' / item
        metadata = BASE / 'goethe-source-metadata' / (item + '.json')
        record = {'identifier': item, 'scope': mapping[item], 'metadata_url': 'https://archive.org/metadata/' + item,
                  'details_url': 'https://archive.org/details/' + item, 'files': []}
        if metadata.exists():
            data = json.loads(metadata.read_text())
            record['metadata_path'] = str(metadata.relative_to(ROOT))
            record['metadata_sha256'] = sha(metadata)
            record['archive_volume_metadata'] = data.get('metadata', {}).get('volume')
        if target.exists():
            for path in sorted(target.iterdir()):
                file = source_file(path, 'https://archive.org/download/' + item + '/' + path.name)
                if item == 'pt01werkegoe36goetuoft':
                    file['canonical_archive_url'] = file['source_url']
                    file['source_url'] = 'https://ia601807.us.archive.org/30/items/' + item + '/' + path.name
                    file['download_note'] = 'Archive.org canonical download returned HTTP 500; metadata d1 public storage host supplied the file.'
                record['files'].append(file)
                if path.suffix == '.txt':
                    chars += file['text_chars']
                    text = path.read_text(errors='replace')
                    record['ocr_front_sample'] = re.sub(r'\s+', ' ', text[:5500])[-1700:]
                    record['ocr_characters'] = len(text)
        sources.append(record)
    return {'id': 'ga-' + work, 'status': 'historical_source_documents_recovered_needs_scope_and_OCR_review',
            'text_chars': chars, 'language': 'de', 'sources': sources,
            'completeness': 'Historical source volumes are preserved; this does not establish a complete contemporary GA edition.',
            'blockers': ['Fraktur OCR has numerous visibly corrupted words; extraction requires correction against scans.',
                         'Historical source contents and Steiner-authored spans require collation to the current catalog row.']}


def main():
    report = json.loads(REPORT.read_text())
    rows = {w['id']: w for w in report['works']}
    bundle = ['werkegoe33goetuoft','werkegoe34goetuoft','werkegoe35goetuoft','pt01werkegoe36goetuoft','pt02werkegoe36goetuoft']
    rows['ga-001a-e'] = historical('001a-e', bundle, dict(zip(bundle, [
        'GA1a candidate: Goethe Werke 33 / Deutsche National-Litteratur 114 / Naturwissenschaftliche Schriften 1',
        'GA1b candidate: Goethe Werke 34 / Deutsche National-Litteratur 115 / Naturwissenschaftliche Schriften 2',
        'GA1c candidate: Goethe Werke 35 / Deutsche National-Litteratur 116 / Naturwissenschaftliche Schriften 3',
        'GA1d candidate: Goethe Werke 36 part 1 / Deutsche National-Litteratur 117 part 1 / Naturwissenschaftliche Schriften 4 part 1',
        'GA1e candidate: Goethe Werke 36 part 2 / Deutsche National-Litteratur 117 part 2 / Naturwissenschaftliche Schriften 4 part 2',
    ])))
    rows['ga-001a-e']['evidence'] = [{'url':'https://de.wikisource.org/wiki/Deutsche_National-Litteratur',
        'finding':'Lists all five physical source volumes with Steiner as editor and the selected scan links.'},
        {'url':'https://anthrowiki.at/GA_1a-e','finding':'GA 1a-e is the five-volume reprint of the Berlin/Stuttgart 1883–1897 edition; no assessment borrowed from GA1.'}]
    weimar = ['pt02werkegoeth06goet','pt02werkegoeth07goet','s02p03werkegoethe08goet','s02p01werkegoethe09goet','s02p02werkegoethe10goet','bub_gb_PiNAAAAAYAAJ','werkeabthnaturw00raabgoog']
    ga1f_historical = historical('001f', weimar, {item: f'Weimarer Goethe-Ausgabe, II. Abteilung, Band {n}: underlying historical source for Steiner editorial afterword; entire Goethe volume retained' for n, item in enumerate(weimar, 6)})
    rows['ga-001f']['historical_sources'] = ga1f_historical['sources']
    rows['ga-001f']['historical_OCR_chars'] = ga1f_historical['text_chars']
    rows['ga-001f']['scope_evidence'] = ['All eight German source pages recovered: seven editorial source volumes and documents.', 'The cleaner web collection includes 2017 editorial contextual labels and mixed-author archival documents. Complete current-volume scope and authorship still require review.']
    rows['ga-001f']['blockers'] = ga1f_historical['blockers']
    rows['ga-001f']['evidence'] = [{'url':'https://de.wikisource.org/wiki/Johann_Wolfgang_von_Goethe','finding':'Lists II. Abteilung source volumes 6–12. For Band 11 the first Wikisource scan actually has a Band 4 title page; selected Google/Harvard alternative identifies Band 11,1893 instead.'},
        {'url':'https://anthrowiki.at/GA_1f','finding':'2017 GA 1f edits Steiner material from II. Abteilung 6–12 plus additional materials; source volumes cannot silently replace the 187-page GA edition.'}]
    rows['ga-001f']['blockers'].append('Exact source-text spans and archival document authorship from the 2017 GA 1f edition require collation; documents are now preserved in the web source collection.')
    pdf = BASE / 'ga-004a/originals/GA004a-1994.pdf'
    txt = BASE / 'ga-004a/GA004a-pdftotext.txt'
    rows['ga-004a'] = {'id':'ga-004a','status':'facsimile_recovered_OCR_requires_handwriting_and_scope_review','language':'de','text_chars':len(txt.read_text()),
        'sources':[source_file(pdf,'https://rudolfsteinerelib.org/Download/German/Dokumente_zu_Philosophie_der_Freiheit--Rudolf_Steiner--004a.pdf'),
                   {**source_file(txt,'https://rudolfsteinerelib.org/Download/German/Dokumente_zu_Philosophie_der_Freiheit--Rudolf_Steiner--004a.pdf'),'extraction_engine':'Poppler pdftotext -layout'}],
        'pages':544,'control_character_U0002_count':txt.read_text().count('\x02'),
        'textless_PDF_pages_1_based':[n for n,s in enumerate(txt.read_text().split('\f')[:-1],1) if not s.strip()],
        'completeness':'Entire 544-page PDF preserved; handwritten facsimiles and OCR completeness not validated across all pages.',
        'evidence':[{'url':'https://rudolfsteinerelib.org/Download/German/Dokumente_zu_Philosophie_der_Freiheit--Rudolf_Steiner--004a.pdf','finding':'Title/imprint 1. Auflage 1994 and full TOC match GA4a; sample PDF page 33 shows handwritten alterations that text extraction cannot adequately represent.'}],
        'blockers':['Retain manuscript/facsimile images; clean text alone does not represent this documentary volume.','Textless pages and many handwritten areas need page-by-page review.','Historical reviews and Eduard von Hartmann marginalia have distinct authorship.']}
    notes = {
        '001f': ['All eight indexed German pages recovered: editorial materials for seven Weimar source volumes, plus the Documents section. Twelve historical Goethe source scans are also preserved across GA 1a-e and GA 1f.', 'The cleaner web collection includes 2017 contextual labels and mixed-author archival documents. Exact author-text spans, document authorship, and current volume completeness still require collation.'],
        '018a': ['Both original 1900/1901 author-text volumes represented by 14 chapters; contemporary reviews kept separately from reader candidate.', 'This is a genuine GA 18a source, not GA 18 revised 1914 text. Scan/2022 edition collation remains outstanding.'],
        '019': ['All 11 indexed German sections recovered after repairing stale index URLs from neighboring-page navigation.', 'Includes both versions of the second 1917 memorandum,1919 Moltke preface,1919 leaflet and1921 Matin responses.', '2023 GA 19 French appendix and editorial annotations are not in this recovered German author-text set.'],
        '037': ['148 of 149 indexed German items recovered.1904 annual report source is only the English rendering by Marie Steiner; retained HTML but no German invented.', 'Recent GA 37 scope includes previously unpublished/additional material; exact 2019 volume collation still required.'],
        '041a': ['17 of 18 indexed German sources recovered; the John HTML page contains empty English and German containers.', 'Many sections only point to other GAs with See GA references; 17 sections do not establish a complete 293-page volume.'],
        '041b': ['Key to Theosophy including all 14 parts plus Conclusion, Theosophical Glossary, Canticle of the Sun and Voice of Silence extracted in original German.', 'Dreamsong of Olaf Åsteson is only linked as existing GA 158; the three newly published stanzas and all 2018 manuscript material are not established.'],
        '042': ['All 17 indexed German pages recovered: Eleusis introduction and 3 acts, Lucifer introduction and 5 acts, Soulkeeper introduction and 4 acts, two prefaces.', 'Three dramatic adaptations and prefaces are covered; facsimiles/2021 apparatus and mixed Schuré/Marie Steiner/Rudolf Steiner authorship need verification.'],
        '043': ['All three Oberuferer plays recovered in German with stage directions: Paradise, Nativity, Three Kings. The two December 1922 GA 36 essays referenced by this index are preserved separately as related source texts.', 'The current 2023 edition prints excerpts from the two essays and a manuscript facsimile; exact excerpt boundaries and facsimile material remain unverified. Scripts are not silently presented as the complete GA 43 volume.'],
        '046': ['All 143 indexed German essays/fragments recovered, greatly exceeding the prior isolated pp. 64–82 excerpt.', 'The complete 1030-page 2020 volume has notes and image material not represented in web author texts; exact TOC/scope collation still required.'],
    }
    for work, scope in notes.items():
        rows['ga-'+work]['scope_evidence'] = scope
        rows['ga-'+work]['evidence'] = [{'url':rows['ga-'+work].get('resolved_index_url',rows['ga-'+work].get('index_url')),'finding':'Own-volume source index and preserved German source pages bound to SHA-256 hashes.'}, {'url':PUBLISHER_CATALOG,'finding':'Publisher catalog documents distinct editions and intended volume scope.'}]
        rows['ga-'+work]['blockers'] = [scope[-1]]
    for n in range(1,7):
        work = f'ga-038-{n}'
        rows[work] = {'id':work,'status':'no_public_current_subvolume_text_found','language':'de','text_chars':0,
            'completeness':'unavailable','evidence':[{'url':PUBLISHER_CATALOG,'finding':'New six-volume Sämtliche Briefe edition explicitly replaces older incomplete GA 38/39 volumes; no older volume substitution.'},
                {'url':ARCHIVE_REPORT,'finding':'February 2025 archive plan lists volumes 1–3 as published in 2021/2023/2024 and 4–6 planned for 2026–2028.'},
                {'url':PUBLISHER_2025,'finding':'Spring 2025 publisher preview announcesBand 4as1.Auflage2025; publication timing conflicts with archive plan and is not a full text source.'}],
            'blockers':['No public full text for this exact current subvolume found in checked catalogs/Archive sources.','Older GA 38/39 correspondence is a different edition and incomplete scope.']}
    for work in ['047-48','048']:
        rows['ga-'+work] = {'id':'ga-'+work,'status':'current_notebook_edition_subscription_and_selection_scope','language':'de','text_chars':0,'completeness':'unavailable',
            'evidence':[{'url':'https://steinerverlag.com/wp-content/uploads/Flyer-GA-online-web.pdf','finding':'Publisher identifies eGA 47/48 as exclusive to GA-online, with scans and line-identical transcriptions published incrementally.'},
                {'url':PUBLISHER_2025,'finding':'Print GA 47/48 is a selection/example edition; complete 600+ notebooks and 7500+ notes are a separate ongoing digital edition.'}],
            'blockers':['No openly available complete selection volume or digital notebook corpus found.','GA 48 alias must not be counted as a second independent complete volume.']}
    rows['ga-049'] = {'id':'ga-049','status':'no_public_current_volume_text_found','language':'de','text_chars':0,'completeness':'unavailable',
        'evidence':[{'url':ARCHIVE_REPORT,'finding':'Archive plan identifies 2025 volume on Helmuth/Eliza Moltke materials.'},
            {'url':'https://dasgoetheanum.com/eine-bitte-auf-der-zielgeraden/','finding':'December 2025 report confirms GA 49 among latest published volumes.'}],
        'blockers':['No public full German source found for 2025 GA 49; current edition includes newly edited letters/documents/notes.', 'Older Moltke publications or GA 19 Moltke texts cannot establish complete GA 49 scope.']}
    evidence_paths = {
        PUBLISHER_CATALOG: 'RudolfSteinerVerlag_GV_2022.pdf',
        ARCHIVE_REPORT: 'RSA_Jahresbericht_2024.pdf',
        PUBLISHER_2025: 'RSV-Fruehjahr_2025.pdf',
        'https://steinerverlag.com/wp-content/uploads/Flyer-GA-online-web.pdf': 'Flyer-GA-online-web.pdf',
    }
    report['evidence_documents'] = []
    for url, filename in evidence_paths.items():
        path = BASE / 'evidence' / filename
        if path.exists():
            report['evidence_documents'].append(source_file(path, url))
            report['evidence_documents'].append({**source_file(path.with_suffix('.txt'), url),
                'extraction_engine': 'Poppler pdftotext -layout'})
    for row in rows.values():
        for evidence in row.get('evidence', []):
            if evidence['url'] in evidence_paths:
                path = BASE / 'evidence' / evidence_paths[evidence['url']]
                evidence['local_original_path'] = str(path.relative_to(ROOT))
                evidence['original_sha256'] = sha(path)
    # One actual notebook passage is reproduced in the publisher preview. It is
    # useful recovered text, but cannot stand for the selection or digital corpus.
    excerpt = BASE / 'evidence' / 'notebook-321-page-5-preview.txt'
    if excerpt.exists():
        for work in ['ga-047-48', 'ga-048']:
            rows[work]['partial_sources'] = [{**source_file(excerpt, PUBLISHER_2025),
                'scope': 'Publisher preview, PDF page 6: fragment from Notizbuch 321, page 5.',
                'completeness': 'single excerpt; both rows refer to the same recovered fragment'}]
    report['works'] = []
    for short in IDS:
        work = 'ga-' + short
        row = rows[work]
        row['title'] = CATALOG[work]['title']
        row['previous_source_summary'] = CATALOG[work]['source_summary']
        report['works'].append(row)
    report['summary'] = {'assigned_rows':len(IDS), 'rows_with_recovered_German_source_material':sum(w.get('text_chars',0)>0 for w in report['works']),
        'recovered_HTML_German_sections':sum(w.get('recovered_sections',0) for w in report['works']),
        'HTML_German_chars':sum(w.get('text_chars',0) for w in report['works'] if w.get('chapters')),
        'no_catalog_rows_promoted':True,'original_source_files_preserved':True}
    support_log = BASE / 'support-downloads.json'
    if support_log.exists():
        report['support_download_log'] = {'local_path': str(support_log.relative_to(ROOT)), 'sha256': sha(support_log)}
    report['reproduction'] = {
        'full_recovery_command': 'python3 tools/recover_all_early.py',
        'verification_command': 'python3 tools/verify_early_recovery.py',
        'requirements': ['Python 3 with lxml', 'Poppler pdftotext on PATH', 'Network access for uncached public sources'],
        'stages': ['tools/download_early_support.py', 'tools/recover_early.py', 'tools/finalize_early_recovery.py', 'tools/verify_early_recovery.py'],
        'effects': 'Preserved research sources, extracted German candidates, and all 20 report rows; reader catalog remains unchanged.',
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['summary'],ensure_ascii=False))


if __name__ == '__main__':
    main()
