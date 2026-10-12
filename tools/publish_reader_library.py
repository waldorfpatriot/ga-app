#!/usr/bin/env python3
"""Publish a validated reader-only snapshot on the existing GA download host."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess


def run_remote(host, code):
    subprocess.run(["ssh", "-o", "BatchMode=yes", host, "python3 -"], input=code, text=True, check=True)


def publish(source, host, configure_nginx):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", host):
        raise ValueError("Expected a configured SSH alias or host")
    catalog = json.loads((source / "catalog.json").read_text())
    files = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in delivery snapshot")
        if path.is_file():
            body = path.read_bytes()
            payload = json.loads(body)
            if re.search(rb'"source_text"\s*:', body):
                raise ValueError("Private developer source in public snapshot")
            files[path.relative_to(source).as_posix()] = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    available = [work for work in catalog["works"] if work.get("content_path")]
    for work in catalog["works"]:
        expected = "complete" if work.get("content_path") else "unavailable"
        if work.get("content_completeness") != expected or work.get("state") == "published_seed":
            raise ValueError("Invalid completeness declaration: " + work["id"])
    for work in available:
        key = "api/catalog/" + work["id"] + "/content"
        if key not in files:
            raise ValueError("Missing advertised download: " + work["id"])
        content = json.loads((source / key).read_text())
        manifest = json.loads((source / ("api/catalog/" + work["id"] + "/manifest")).read_text())
        if content["work_id"] != work["id"] or not content["passages"]:
            raise ValueError("Invalid reader bundle")
        ids = [passage["id"] for passage in content["passages"]]
        if (content.get("content_completeness") != "complete"
                or content.get("passage_count") != len(ids)
                or work.get("catalog_passage_count", len(work["passages"])) != len(ids)
                or ids != [passage["id"] for passage in work["passages"]]
                or len(set(ids)) != len(ids)
                or any(not passage["text"].strip() for passage in content["passages"])):
            raise ValueError("Incomplete reader bundle: " + work["id"])
        bundle = manifest["bundles"][0]
        if manifest["work"].get("content_completeness") != "complete" or bundle["passages"] != ids:
            raise ValueError("Incomplete download manifest: " + work["id"])
        if bundle["checksum"] != files[key]["sha256"] or bundle["byte_size"] != files[key]["bytes"]:
            raise ValueError("Stale download manifest")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fingerprint = hashlib.sha256((source / "catalog.json").read_bytes()).hexdigest()[:12]
    release = timestamp + "-" + fingerprint
    remote_root = "/var/lib/ga-reader"
    destination = remote_root + "/releases/" + release
    run_remote(host, f"from pathlib import Path\nPath({destination!r}).mkdir(parents=True, exist_ok=False)\n")
    subprocess.run(["rsync", "-az", "-e", "ssh -o BatchMode=yes", str(source) + "/", host + ":" + destination + "/"], check=True)
    code = f"""import hashlib,json,os
from pathlib import Path
root=Path({remote_root!r})
destination=Path({destination!r})
files=json.loads({json.dumps(json.dumps(files))})
for relative,expected in files.items():
    path=destination/relative
    assert not path.is_symlink() and path.is_file(), relative
    data=path.read_bytes()
    assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256'], relative
    path.chmod(0o644)
for path in [destination,*destination.rglob('*')]:
    if path.is_dir(): path.chmod(0o755)
current=root/'current'
old=os.readlink(current) if current.is_symlink() else None
temporary=root/{('.current-' + release)!r}
os.symlink({('releases/' + release)!r},temporary)
os.replace(temporary,current)
print(json.dumps({{'release':{release!r},'previous':old,'verified_files':len(files)}}))
"""
    run_remote(host, code)
    if configure_nginx:
        snippet = (Path(__file__).resolve().parents[1] / "server/deploy/ga-reader.nginx.conf").read_text()
        code = f"""from pathlib import Path
import subprocess
site=Path('/etc/nginx/sites-enabled/fototausch.eu').resolve()
target=Path('/etc/nginx/snippets/ga-reader.conf')
before=site.read_text()
old_snippet=target.read_bytes() if target.exists() else None
include='include /etc/nginx/snippets/ga-reader.conf;'
anchor='include /etc/nginx/snippets/ga-library.conf;'
assert include in before or anchor in before, 'Expected existing GA route configuration'
site.with_name(site.name+{('.ga-reader-' + release + '.backup')!r}).write_text(before)
target.write_text({snippet!r})
if include not in before:
    site.write_text(before.replace(anchor,anchor+'\\n '+include,1))
result=subprocess.run(['nginx','-t'],capture_output=True,text=True)
if result.returncode:
    site.write_text(before)
    if old_snippet is None: target.unlink()
    else: target.write_bytes(old_snippet)
    raise RuntimeError(result.stderr)
subprocess.run(['systemctl','reload','nginx'],check=True)
print('Reader route installed; nginx configuration passed.')
"""
        run_remote(host, code)
    print(f"Published {len(catalog['works'])} entries and {len(available)} reader downloads as {release}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--host", default="photo-share-prod")
    parser.add_argument("--configure-nginx", action="store_true", help="Install the narrow reader route after nginx syntax validation")
    args = parser.parse_args()
    publish(args.source.resolve(), args.host, args.configure_nginx)
