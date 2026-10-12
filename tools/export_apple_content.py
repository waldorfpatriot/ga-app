#!/usr/bin/env python3
"""Package published reader text for an Apple installation without a server."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK_IDS = ("ga-003", "ga-004", "ga-009", "ga-010", "ga-013")


def export_content():
    output = ROOT / "apple" / "GA" / "BundledContent"
    output.mkdir(parents=True, exist_ok=True)
    # Remove the retired excerpt from earlier generated installations.
    (output / "ga-120.json").unlink(missing_ok=True)
    total = 0
    for work_id in WORK_IDS:
        source = ROOT / "server" / "priv" / "content" / f"{work_id}.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        passages = []
        for passage in payload["passages"]:
            # Preserve reader metadata and notes, without the developer source diff.
            passages.append({
                key: passage[key]
                for key in ("id", "title", "ga_page", "source_label", "text", "metadata")
                if key in passage
            })
        assert passages and all(passage["text"].strip() for passage in passages)
        (output / f"{work_id}.json").write_text(
            json.dumps({"work_id": work_id, "content_completeness": "complete", "passage_count": len(passages), "passages": passages}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        total += len(passages)
    print(f"Packaged {len(WORK_IDS)} works with {total} sections.")


if __name__ == "__main__":
    export_content()
