#!/usr/bin/env python3
"""Bind the reviewed GA 040 roles to machine-extracted original DOC layout.

Run source_layout.py first. Only source-proven small gaps in reviewed verse
regions are joined; known cross-page continuations have explicit exceptions.
The resulting recipe runs without Word/LibreOffice or the original DOC.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

from finalize_library import read_json
from repair_source_structure import sha, apply_passage_plan

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Original 1991 DOC, SHA-256 9263a2efd8f66c17f6c686a4bf1c169f477331f1e2aa1bf4fea01fcfe950229a; retained source paragraph formatting and explicit page breaks."
HEADINGS = {9: [0,3,13], 10: [43,45,75,149,154], 12: [49,72,77], 13:[15], 17:[2,4], 18:[5,20,23,25,58], 19:[0,2,4,8], 20:[0,2,4,6], 21:[3,5,14,15,17,19,24,26,28,31,34,37], 23:[0,4,8,15,22,27,28,30,32], 24:[0,4,5,9,12],25:[3,7,8],26:[0],27:[4,71]}
ATTRIBUTIONS = {10:[28,72,74,81,83],12:[6,9,12,14,16,19],19:[9]}
PROSE = {19:[6],24:[14]}
FOOTERS = {6:{214:62},10:{84:91},16:{13:139},21:{13:159},26:{36:179}}


def segment(kind, parts, join=None, **kwargs):
    return {"kind":kind,"parts":parts,"join":join or ("\n" if kind=="verse" else " "),**kwargs}


def source_parts(segments, mapping, cues, blocks):
    for item in segments:
        ids = [part if type(part) is int else part["block"] for part in item["parts"]]
        matched = [mapping[i] for i in ids]
        item["source_paragraph_indices"] = sorted({node for block in matched for node in block["source_paragraph_indices"]})
        item["source_evidence"] = SOURCE
        item["page_evidence"] = []
        for part_index,(part,block) in enumerate(zip(item["parts"],matched)):
            block_index = part if type(part) is int else part["block"]
            start = 0 if type(part) is int else part.get("start",0)
            end = len(blocks[block_index]) if type(part) is int else part.get("end",len(blocks[block_index]))
            starts = block.get("source_page_starts",[])
            if not starts and len(block.get("source_sections",[])) == 1:
                starts = [{"source_section":block["source_sections"][0],"start_codepoint":0}]
            if not starts and block.get("source_sections"):
                raise ValueError("Source block spans pages without exact boundaries")
            active = [entry for entry in starts if entry["start_codepoint"]<=start][-1:]
            active += [entry for entry in starts if start<entry["start_codepoint"]<end]
            for entry in active:
                section = entry["source_section"]
                cue = cues.get(str(section),{})
                if cue.get("page"):
                    item["page_evidence"].append({**cue,"source_section":section,"part_index":part_index,
                                                  "start_codepoint":max(start,entry["start_codepoint"])-start})


def build(payload, evidence, later, poem_boundaries, work_sections=None):
    if evidence["source_doc_sha256"] != payload["source_sha256"]:
        raise ValueError("Original DOC evidence does not belong to this edition")
    if poem_boundaries["source_sha256"] != payload["source_sha256"] or poem_boundaries["evidence_docx_sha256"] != evidence["conversion_docx_sha256"]:
        raise ValueError("Reviewed poem boundaries do not belong to this exact source layout")
    work_sections = work_sections or {"passages": {}}
    if work_sections["passages"] and (work_sections.get("work_id") != payload["work_id"] or
            work_sections.get("source_sha256") != payload["source_sha256"] or
            work_sections.get("evidence_docx_sha256") != evidence["conversion_docx_sha256"]):
        raise ValueError("Reviewed work sections do not belong to this exact source layout")
    recipe = {"schema_version":1,"work_id":payload["work_id"],"source_sha256":payload["source_sha256"],"source_epub_sha256":payload["source_epub_sha256"],"source_url":evidence["source_url"],
              "evidence_docx_sha256":evidence["conversion_docx_sha256"],"offset_unit":"utf16","passages":{}}
    mappings={p["id"]:p["blocks"] for p in evidence["passages"]}
    groups=["Anthroposophischer Seelenkalender","Planetentanz · Zwölf Stimmungen · Das Lied von der Initiation. Eine Satire","Wahrspruchworte – Richtspruchworte","Wahrsprüche und Widmungen · Gebete","Credo: Der Einzelne und das All"]
    group=0
    for passage in payload["passages"]:
        pid=passage["id"]
        number=int(pid.rsplit("-",1)[1]) if "heading-" in pid else None
        if number==5:group=1
        elif number==7:group=2
        elif number==28:group=3
        elif number==40:group=4
        blocks=passage["text"].split("\n\n")
        mapping=mappings[pid]
        if len(blocks) != len(mapping) or any(sha(text) != item["text_sha256"] for text,item in zip(blocks,mapping)):
            raise ValueError("Layout evidence differs from the exact pre-layout passage: " + pid)
        plan=deepcopy(later.get(pid,{}))
        plan.update(input_sha256=sha(passage["text"]),group_title=groups[group])
        plan["typographic_dashes"]="Reviewed literary GA 040 profile: standalone ASCII hyphens denote Gedankenstriche or date ranges, normalized to German en dashes. Word/compound hyphens remain unchanged; this rule is not enabled for mathematical material."
        segments=plan.get("segments",[])
        if number==2:
            segments=[segment("prose",[0,1]),segment("heading",[2],level=1),segment("prose",[3]),segment("prose",[4])]
            for i,block in enumerate(blocks[5:],5):
                match=re.match(r"^(5 2|[1-9]\d?) (?=[A-ZÄÖÜ])",block)
                if match:
                    end=len(match[1])
                    segments.extend([segment("heading",[{"block":i,"end":end}],level=3),segment("verse",[{"block":i,"start":end+1}],poem_start=True)])
                else:
                    segments.append(segment("heading",[i],level=1 if block in {"FRÜHLING","SOMMER","HERBST","WINTER"} else 2))
            plan["edits"]=[{"old":"5 2","new":"52","evidence":SOURCE+" Sequential calendar label, matching source poem 52."},
                           {"old":"rinden.","new":"finden.","evidence":"Matching calendar poem 2, printed 1998 GA 040 p23 confirms finden; characteristic OCR r/f confusion."},
                           {"old":"WinterhorTnung","new":"Winterhoffnung","evidence":"Matching calendar poem 29, printed 1998 GA 040 p37 confirms Winterhoffnung; OCR ff ligature corruption."},
                           {"old":"heiPge","new":"heil'ge","evidence":"Matching calendar poem 38, printed 1998 GA 040 p41 confirms heil'ge; OCR ligature/apostrophe corruption."}]
            for old in blocks[5:]:
                if re.match(r"^(?:Erste|Zweite|Dritte|Vierte|Fünfte|Oster|Johanni|Michaeli|Weihe|Frühling-Erwartung)",old):
                    new=re.sub(r"(?<=\d\.) *(?=(?:April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|Januar|Februar|März))"," ",old)
                    if new!=old:plan["edits"].append({"old":old,"new":new,"evidence":SOURCE+" Date heading spacing, without changing any date values."})
            plan["annotations"]={"EPUB/chapter-0001.xhtml#footnote-recovered-6":{"text":"Zweite Ausgabe 1918/19","reference_context":"Oster-Stimmung 1.-6. April *"}}
        elif number==6:
            segments=[]
            joins={1,3,21,28,30}
            i=0
            while i<32:
                if i==7:segments.append(segment("verse",list(range(7,19))));i=19;continue
                if i==22:segments.append(segment("verse",[22,23]));i=24;continue
                parts=[i]
                if i+1 in joins:parts.append(i+1)
                segments.append(segment("prose",parts));i+=len(parts)
            for i in range(32,46):segments.append(segment("heading" if i in {32,45} else "verse",[i],**({"level":1} if i in {32,45} else {})))
            for start in range(46,130,7):
                last=start+6
                tail=blocks[last].rsplit(" ",1)
                end=len(blocks[last])-len(tail[1])-1
                segments.extend([segment("verse",list(range(start,last))+[{"block":last,"end":end}]),segment("attribution",[{"block":last,"start":end+1}])])
            segments.extend([segment("heading",[130],level=1),segment("heading",[131],level=2)])
            for start in range(132,188,7):
                last=start+6;tail=blocks[last].rsplit(" ",1);end=len(blocks[last])-len(tail[1])-1
                segments.extend([segment("verse",list(range(start,last))+[{"block":last,"end":end}]),segment("attribution",[{"block":last,"start":end+1}])])
            for start,last,label in [(188,194,195),(196,202,203),(204,204,205),(206,212,213)]:
                segments.extend([segment("verse",list(range(start,last+1))),segment("attribution",[label])])
            plan["annotations"]={"EPUB/chapter-0001.xhtml#footnote-recovered-5":{"text":"Zu den «Zwölf Stimmungen» liegt jetzt eine Komposition für kleines Orchester von Jan Stuten vor.","reference_context":"musikalische Begleitung werden haben müssen*"}}
        elif not segments:
            if number in {5,7}:
                segments=[segment("prose",[i]) for i in range(len(blocks))]
            else:
                for i,block in enumerate(blocks):
                    if i in FOOTERS.get(number,{}):continue
                    kind="heading" if i in HEADINGS.get(number,[]) else "attribution" if i in ATTRIBUTIONS.get(number,[]) else "prose" if i in PROSE.get(number,[]) else "verse"
                    # Reviewed multiline label splits, independent of typography inference.
                    split_label = (number==12 and i in {1,3,21}) or (number==20 and i in {1,3,5})
                    split_heading = number==18 and i in {21,22}
                    if split_label:
                        cut=block.rindex("\n")
                        first=[{"block":i,"end":cut}]
                        if segments and segments[-1]["kind"]=="verse" and mapping[i].get("small_gap_join_candidate"):
                            segments[-1]["parts"].extend(first)
                        else:segments.append(segment("verse",first))
                        segments.append(segment("attribution",[{"block":i,"start":cut+1}]))
                    elif split_heading:
                        cut=block.index("\n")
                        segments.extend([segment("heading",[{"block":i,"end":cut}],level=3),segment("verse",[{"block":i,"start":cut+1}])])
                    elif kind=="verse" and segments and segments[-1]["kind"]==kind and (mapping[i].get("small_gap_join_candidate") or number==12 and i in {101,102}):
                        segments[-1]["parts"].append(i)
                    else:
                        segments.append(segment(kind,[i],**({"level":2} if kind=="heading" else {})))
                if pid=="ga-040-chapter-0001":
                    segments[0]=segment("heading",[0],level=1)
                    # Source beginning is a title followed by four p-per-line verses.
                    if len(segments[1]["parts"])==4:pass
                    plan["title"]="Wintersonnenwende"
                elif pid=="ga-040-chapter-0002":plan["title"]="Welterkenntnis – Selbsterkenntnis"
        if number==5:plan["title"]="Planetentanz · Zwölf Stimmungen · Das Lied von der Initiation. Eine Satire"
        if number==7:plan["title"]="Wahrspruchworte – Richtspruchworte"
        if number==14:plan["title"]="Herbst: Der Erdenleib und die Wärmeseele"
        if number==10:plan["title"]="Pfingst-Stimmung"
        if number==40:plan["title"]="Credo: Zur Textgrundlage"
        if number==41:plan["title"]="Credo: Der Einzelne und das All"
        if number in FOOTERS:
            plan["omitted_parts"]=[{"block":i,"page":page,"evidence":SOURCE+" Isolated numeric original page footer, not a poem/date."} for i,page in FOOTERS[number].items()]
        plan["segments"]=segments
        source_parts(segments,mapping,evidence["page_cues"],blocks)
        if number==28:
            segments[0]["page_evidence"]=[{"page":188,"confidence":"reviewed_original_toc_and_facing_bibliography_page","source_section":mapping[0]["source_sections"][0]}]
        reviewed={entry["block_index"]:entry for entry in poem_boundaries["passages"].get(pid,[])}
        used=set()
        for index,item in enumerate(segments):
            first=item["parts"][0]
            first_index=first if type(first) is int else first["block"]
            if number==2:continue  # The 52 numbered calendar poems have explicit starts.
            item.pop("poem_start",None)
            if first_index in reviewed:
                if item["kind"]!="verse" or not index or segments[index-1]["kind"]!="verse" or not reviewed[first_index].get("evidence"):
                    raise ValueError("Reviewed independent poem start no longer matches its source role")
                item["poem_start"]=True
                item["poem_start_evidence"]=reviewed[first_index]["evidence"]
                used.add(first_index)
        if used!=set(reviewed):raise ValueError("Reviewed poem boundary was lost during source grouping: " + pid)
        if pid in work_sections["passages"]:
            plan["sections"] = deepcopy(work_sections["passages"][pid])
        # One unmatched inscription drawing is reviewed explicitly, not guessed.
        if number==10:
            plan.setdefault("edits",[]).append({"old":"das Es an Es in Es ich vom ich Aus mir ich ins Es","new":"das Es\nan Es\nin Es\nich\nvom ich\nAus mir\nich ins Es","evidence":SOURCE+" Seven separate inscriptions in DER SÄULEN WORTE drawing, source p85."})
        exact={2:{"Wil- lenswelt":"Willenswelt","Gedan- kenrhythmus":"Gedankenrhythmus","Sich- eins-Fühlen":"Sich-eins-Fühlen","er- stehendes":"erstehendes"},6:{"Sich- eins-Fühlen":"Sich-eins-Fühlen","buch- stabengemäß":"buchstabengemäß","emporschwin- gen":"emporschwingen","Menschenge- setze":"Menschengesetze","un- sinnigen":"unsinnigen","Waage- Stimmung":"Waage-Stimmung","Son- nenhafte":"Sonnenhafte","bur- leske":"burleske","dra- piert":"drapiert","Zwölf heit":"Zwölfheit"},7:{"Richt- spruchworte":"Richtspruchworte"}}
        for old,new in exact.get(number,{}).items():
            if old in passage["text"]:plan.setdefault("edits",[]).append({"old":old,"new":new,"evidence":SOURCE+" Original line-end wrap/spacing, retaining compound hyphens where lexical."})
        recipe["passages"][pid]=plan
    # Freeze the expected final text checksums in the recipe after full coverage validation.
    for passage in payload["passages"]:
        plan=recipe["passages"][passage["id"]]
        probe=deepcopy(passage)
        apply_passage_plan(probe,plan,"recipe-generation")
        plan["output_sha256"]=probe["checksum"]
    return recipe


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload",type=Path,default=ROOT/"server/priv/content/ga-040.json.gz")
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--later-plan",type=Path,default=ROOT/"tools/ga040_later_plan.json")
    parser.add_argument("--poem-boundaries",type=Path,default=ROOT/"tools/ga040_poem_boundaries.json")
    parser.add_argument("--work-sections",type=Path,default=ROOT/"tools/ga040_work_sections.json")
    parser.add_argument("--output",type=Path,default=ROOT/"tools/ga040_structure.json")
    args=parser.parse_args()
    result=build(read_json(args.payload),read_json(args.evidence),read_json(args.later_plan),read_json(args.poem_boundaries),read_json(args.work_sections))
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"recipe":str(args.output),"passages":len(result["passages"]),"segments":sum(len(p["segments"]) for p in result["passages"].values())}))
