#!/usr/bin/env python3
"""Update one author's validated static library and pages without backend changes."""
import argparse
from concurrent.futures import as_completed, ThreadPoolExecutor
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

from generate_author_infrastructure import ROOT, generate_files, load_authors


def remote(host, code):
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "python3 -"],
                            input=code, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def write_report(path, report):
    """Persist recovery information atomically before any remote mutation."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".library-deployment-", delete=False) as output:
            temporary = Path(output.name)
            output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish(slug, host):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", host):
        raise ValueError("Expected a configured SSH host")
    author = next((a for a in load_authors(ROOT / "editions/authors.json") if a["slug"] == slug), None)
    if author is None:
        raise ValueError("Unknown author")
    edition = ROOT / "editions" / slug
    expected = generate_files(author, edition)
    trees = {}
    for tree in ("reader", "web"):
        inventory_bytes = expected[tree + "-inventory.json"]
        inventory = json.loads(inventory_bytes)
        source = edition / "deploy" / tree
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
            raise ValueError("Symlink in static snapshot")
        actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
        if actual != set(inventory["files"]):
            raise ValueError("Static file set differs from inventory")
        for name in actual:
            if (source / name).read_bytes() != expected[tree + "/" + name]:
                raise ValueError("Regenerate the static snapshot before publishing")
        fingerprint = hashlib.sha256(inventory_bytes).hexdigest()[:16]
        trees[tree] = {"root": author[tree + "_root"], "fingerprint": fingerprint,
                       "destination": author[tree + "_root"] + "/releases/" + fingerprint,
                       "files": inventory["files"]}

    # Capture the old targets without changing the server. A lost activation
    # response must not be the only place where the rollback targets were stored.
    snapshot = remote(host, "from pathlib import Path\nimport json,os\n" +
        f"trees=json.loads({json.dumps(trees)!r})\n" +
        "previous={}\n"
        "for name,tree in trees.items():\n"
        " root=Path(tree['root']); current=root/'current'\n"
        " assert current.is_symlink(), 'Expected initialized author library'\n"
        " assert current.resolve().is_dir(), 'Current snapshot is missing'\n"
        " assert not Path(tree['destination']).is_symlink()\n"
        " previous[name]=os.readlink(current)\n"
        "print(json.dumps({'previous':previous}))\n")
    previous = snapshot["previous"]
    if set(previous) != set(trees) or not all(isinstance(value, str) and value for value in previous.values()):
        raise ValueError("Invalid previous snapshot targets")
    releases = {name: tree["destination"] for name, tree in trees.items()}
    catalog = json.loads(expected["reader/catalog.json"])
    report_path = edition / "library-deployment.json"
    report = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "slug": slug,
              "host": host, "status": "preparing", "works": len(catalog["works"]),
              "reader_base_url": author["reader_base_url"], "backend_changes": False,
              "previous": previous, "releases": releases,
              "roots": {name: tree["root"] for name, tree in trees.items()}}
    write_report(report_path, report)

    def verify_file(item):
        tree, name, info = item
        base = author["reader_base_url" if tree == "reader" else "access_base_url"]
        req = urllib.request.Request(base + "/" + name, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
        if len(body) != info["bytes"] or hashlib.sha256(body).hexdigest() != info["sha256"]:
            raise ValueError("Public file integrity mismatch: " + tree + "/" + name)
        return tree + "/" + name

    activation_attempted = False
    try:
        remote(host, "from pathlib import Path\nimport json\n" +
            f"trees=json.loads({json.dumps(trees)!r})\n" +
            "for tree in trees.values():\n"
            " destination=Path(tree['destination'])\n"
            " assert not destination.is_symlink()\n"
            " destination.mkdir(parents=True,exist_ok=True)\n"
            "print(json.dumps({'prepared':True}))\n")
        for tree, info in trees.items():
            subprocess.run(["rsync", "-az", "-e", "ssh -o BatchMode=yes", "--",
                            str(edition / "deploy" / tree) + "/", host + ":" + info["destination"] + "/"], check=True)
        report["status"] = "activating"
        write_report(report_path, report)
        activation_attempted = True
        remote(host, "import hashlib,json,os\nfrom pathlib import Path\n" +
            f"trees=json.loads({json.dumps(trees)!r});previous=json.loads({json.dumps(previous)!r})\n" +
            "for name,tree in trees.items():\n"
            " current=Path(tree['root'])/'current'\n"
            " assert current.is_symlink() and os.readlink(current)==previous[name], 'Current snapshot changed during preparation'\n"
            " dest=Path(tree['destination'])\n"
            " assert not dest.is_symlink() and not any(p.is_symlink() for p in dest.rglob('*'))\n"
            " assert {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()}==set(tree['files'])\n"
            " for name,expected in tree['files'].items():\n"
            "  body=(dest/name).read_bytes()\n"
            "  assert len(body)==expected['bytes'] and hashlib.sha256(body).hexdigest()==expected['sha256'],name\n"
            "for tree in trees.values():\n"
            " dest=Path(tree['destination']);dest.chmod(0o755)\n"
            " for path in dest.rglob('*'):\n"
            "  if path.is_dir():path.chmod(0o755)\n"
            "  elif path.is_file():path.chmod(0o644)\n"
            "activated=[]\n"
            "try:\n"
            " for name,tree in trees.items():\n"
            "  root=Path(tree['root']); temp=root/('.current-'+tree['fingerprint'])\n"
            "  temp.unlink(missing_ok=True);temp.symlink_to(tree['destination']);os.replace(temp,root/'current');activated.append(name)\n"
            "except BaseException:\n"
            " for name in activated:\n"
            "  root=Path(trees[name]['root']);temp=root/'.current-rollback';temp.unlink(missing_ok=True);temp.symlink_to(previous[name]);os.replace(temp,root/'current')\n"
            " raise\n"
            "print(json.dumps({'activated':True}))\n")
        report["status"] = "verifying"
        write_report(report_path, report)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(verify_file, (tree, name, info))
                       for tree, data in trees.items() for name, info in data["files"].items()]
            try:
                checked = [future.result() for future in as_completed(futures)]
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
        request = urllib.request.Request(author["reader_base_url"] + "/api/catalog",
                                         headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.read() != expected["reader/api/catalog/index.json"]:
                raise ValueError("Public catalog route integrity mismatch")
        report.update({"status": "published", "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "verified_public_files": len(checked), "catalog_route_verified": True})
        write_report(report_path, report)
    except BaseException as error:
        recovery = {"status": "not_required", "reason": "Activation was not attempted"}
        if activation_attempted:
            try:
                # Restore only this publication's target. Never replace a newer,
                # unrelated live target after concurrent server changes.
                recovery = remote(host, "import json,os\nfrom pathlib import Path\n" +
                    f"trees=json.loads({json.dumps(trees)!r});previous=json.loads({json.dumps(previous)!r})\n" +
                    "results={}\n"
                    "for name,tree in trees.items():\n"
                    " root=Path(tree['root']);current=root/'current'\n"
                    " result={'previous':previous[name],'release':tree['destination']}\n"
                    " try:\n"
                    "  observed=os.readlink(current) if current.is_symlink() else None\n"
                    "  result['observed']=observed\n"
                    "  if observed==previous[name]:\n"
                    "   result['status']='unchanged'\n"
                    "  elif observed==tree['destination']:\n"
                    "   temp=root/'.current-rollback';temp.unlink(missing_ok=True);temp.symlink_to(previous[name]);os.replace(temp,current)\n"
                    "   result['status']='restored';result['current']=os.readlink(current)\n"
                    "  else:\n"
                    "   result['status']='manual_review_required'\n"
                    " except BaseException as error:\n"
                    "  result['status']='unknown';result['error']=str(error)\n"
                    " results[name]=result\n"
                    "complete=all(result['status'] in ('restored','unchanged') for result in results.values())\n"
                    "print(json.dumps({'status':'restored' if complete else 'manual_review_required','trees':results}))\n")
            except BaseException as rollback_error:
                recovery = {"status": "unknown", "error": f"{type(rollback_error).__name__}: {rollback_error}"}
        report.update({"status": "failed", "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       "error": f"{type(error).__name__}: {error}", "recovery": recovery})
        try:
            write_report(report_path, report)
        except BaseException as report_error:
            print(f"Could not update recovery report: {report_error}")
        print(f"Publication failed; recovery status: {recovery['status']}. Recovery report: {report_path}")
        if recovery["status"] not in ("restored", "not_required"):
            for name, tree in trees.items():
                print(f"{name}: current={tree['root']}/current; previous={previous[name]}; release={tree['destination']}")
            print(json.dumps(recovery, ensure_ascii=False, indent=2))
        raise
    print(f"Published {slug}: {report['works']} reader volumes, {len(checked)} verified public files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--host", default="photo-share-prod")
    args = parser.parse_args()
    publish(args.slug, args.host)
