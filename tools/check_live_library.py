#!/usr/bin/env python3
"""Verify live reader catalog, all download HEADs, and sampled JSON integrity."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://fototausch.eu/ga-reader"
ROOT = Path(__file__).resolve().parents[1]


def request(path, method="GET", headers=None):
    with urlopen(Request(BASE + path, method=method, headers=headers or {}), timeout=30) as response:
        return response.read(), response.headers


def check_head(work):
    body, _ = request("/api/catalog/" + work["id"] + "/manifest")
    manifest = json.loads(body)
    assert manifest["work"]["content_completeness"] == "complete", work["id"]
    [bundle] = manifest["bundles"]
    _, headers = request(work["content_path"], "HEAD")
    assert headers.get_content_type() == "application/json", work["id"]
    assert int(headers["Content-Length"]) == bundle["byte_size"], work["id"]
    assert bundle["passages"] == [p["id"] for p in work["passages"]], work["id"]
    return work["id"], bundle


def assert_source_safe(value):
    if isinstance(value, dict):
        assert "source_text" not in value
        for child in value.values():
            assert_source_safe(child)
    elif isinstance(value, list):
        for child in value:
            assert_source_safe(child)


body, catalog_headers = request("/api/catalog")
assert body == (ROOT / "apple/GA/BundledCatalog/catalog.json").read_bytes()
catalog = json.loads(body)
assert_source_safe(catalog)
works = catalog["works"]
available = [w for w in works if w.get("content_path")]
assert len(works) == 463 and len(available) == 324
assert all(w.get("content_completeness") == ("complete" if w.get("content_path") else "unavailable") for w in works)
with ThreadPoolExecutor(max_workers=8) as workers:
    bundles = dict(workers.map(check_head, available))

sample_ids = ["ga-001", "ga-003", "ga-012", "ga-040", "ga-093a", "ga-120", "ga-265", "ga-270-1", "ga-333", "ga-344", "ga-354", "ga-293", "ga-294", "ga-296", "ga-299"]
for work_id in sample_ids:
    content_body, headers = request("/api/catalog/" + work_id + "/content")
    bundle = bundles[work_id]
    assert hashlib.sha256(content_body).hexdigest() == bundle["checksum"], work_id
    assert len(content_body) == bundle["byte_size"], work_id
    content = json.loads(content_body)
    assert content["work_id"] == work_id and content["passages"]
    assert content["content_completeness"] == "complete", work_id
    assert content["passage_count"] == len(content["passages"]) == len(bundle["passages"]), work_id
    assert_source_safe(content)
    for passage in content["passages"]:
        assert hashlib.sha256(passage["text"].encode()).hexdigest() == passage["checksum"]

for path in ["/api/catalog/ga-k-11/content", "/api/catalog/ga-999999/content", "/api/developer/catalog/ga-004/proofing"]:
    try:
        request(path)
        raise AssertionError("Unexpected public resource: " + path)
    except HTTPError as error:
        assert error.code == 404, (path, error.code)

try:
    request("/api/catalog", headers={"If-None-Match": catalog_headers["ETag"]})
    raise AssertionError("Conditional catalog request did not return 304")
except HTTPError as error:
    assert error.code == 304
print(f"Live library passed: 463 entries, 324 download HEADs/manifests, {len(sample_ids)} full JSON hashes, unavailable/private 404s, ETag 304.")
