#!/usr/bin/env python3
"""Cache only SHA-matching EPUB witnesses for the current reading editions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CORE = {"ga-003", "ga-004", "ga-009", "ga-010", "ga-013"}


def fetch_sources(destination, workers=8):
    destination.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((ROOT / "server/priv/library/catalog.json").read_text())
    recovery = {w["id"]: w for w in json.loads((ROOT / "tools/recovered-reader-scope.json").read_text())["works"]}
    selected = [w for w in catalog["works"] if w.get("content_path") and w["id"] not in CORE]

    def fetch(work):
        work_id = work["id"]
        payload = json.loads(gzip.decompress((ROOT / "server/priv/content" / (work_id + ".json.gz")).read_bytes()))
        expected = payload["source_epub_sha256"]
        path = destination / (work_id + ".epub")
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            return {"id": work_id, "status": "cached", "sha256": expected}
        if work_id in recovery:
            data = (ROOT / recovery[work_id]["source_path"]).read_bytes()
        else:
            last_error = None
            for attempt in range(3):
                try:
                    request = Request(payload["source_url"], headers={"User-Agent": "GA-source-proofreading/1.0"})
                    with urlopen(request, timeout=45) as response:
                        data = response.read()
                    break
                except Exception as error:
                    last_error = error
                    time.sleep(attempt + 1)
            else:
                raise RuntimeError(f"{work_id}: {last_error}")
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"{work_id}: source hash changed ({actual}); do not reimport")
        temporary = path.with_suffix(".epub.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        return {"id": work_id, "status": "verified", "sha256": expected, "bytes": len(data)}

    results, failures = [], []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {executor.submit(fetch, w): w["id"] for w in selected}
        for future in as_completed(jobs):
            try:
                results.append(future.result())
            except Exception as error:
                failures.append({"id": jobs[future], "error": str(error)})
            if (len(results) + len(failures)) % 25 == 0:
                print(f"Sources: {len(results)} verified; {len(failures)} failed", flush=True)
    report = {"verified": sorted(results, key=lambda w: w["id"]), "failures": failures}
    (destination / "source-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Verified {len(results)}/{len(selected)} source EPUBs; {len(failures)} failures")
    if failures:
        raise RuntimeError(json.dumps(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "research/proofreading-sources")
    parser.add_argument("--workers", type=int, default=8)
    arguments = parser.parse_args()
    fetch_sources(arguments.destination, arguments.workers)
