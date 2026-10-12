#!/usr/bin/env python3
"""Secret-safe staged checks of already initialized isolated author backends.

Run as root on the deployment host. Each initially inactive author is started
for the check and stopped afterward. Original GA services are never managed.
"""
import argparse
import datetime
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import uuid


def command(args, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("Protected operational command failed: " + args[0])
    return result.stdout.strip()


def request(url, method="GET", data=None, token=None, expected=200):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    if response.status != expected:
        raise RuntimeError("Unexpected HTTP result on " + method + " " + urlparse(url).path)
    return body, {key.lower():value for key,value in response.headers.items()}


def api(author, route, **kwargs):
    body, headers = request(author["access_base_url"] + "/api/access/" + route, **kwargs)
    if "no-store" not in headers.get("cache-control", ""):
        raise RuntimeError("Access response permits caching")
    return json.loads(body) if body else None


def database_count(author, table, identifier):
    uuid.UUID(identifier)
    if table not in {"access_installations", "access_free_requests", "access_selections"}:
        raise ValueError("Unsupported validation table")
    column = "id" if table == "access_installations" else "installation_id"
    return int(command(["runuser", "-u", "postgres", "--", "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", author["database"]],
        "SELECT count(*) FROM " + table + " WHERE " + column + "='" + identifier + "';"))


def verify(author, stage, foreign_token):
    service = author["service_name"]
    initially_active = subprocess.run(["systemctl", "is-active", "--quiet", service]).returncode == 0
    if not initially_active:
        command(["systemctl", "start", service])
    credentials = None
    current_token = None
    outcome = {"slug": author["slug"]}
    try:
        for attempt in range(30):
            try:
                health, _ = request(author["access_base_url"] + "/api/health")
                if not json.loads(health).get("ok"):
                    raise RuntimeError("Health not healthy")
                break
            except Exception:
                if attempt == 29:
                    raise RuntimeError("Author health unavailable")
                time.sleep(1)
        inventory = json.loads((stage / author["slug"] / "reader-inventory.json").read_text())
        for name, info in inventory["files"].items():
            body, _ = request(author["reader_base_url"] + "/" + name)
            if len(body) != info["bytes"] or hashlib.sha256(body).hexdigest() != info["sha256"]:
                raise RuntimeError("Public reader integrity failure")
        for name in ["index.html", "privacy.html", "support.html"]:
            body, _ = request(author["access_base_url"] + "/" + name)
            if body != (stage / author["slug"] / "web" / name).read_bytes():
                raise RuntimeError("Public app page integrity failure")
        request(author["access_base_url"] + "/api/catalog", expected=404)
        request(author["access_base_url"] + "/api/developer/catalog", expected=404)
        if foreign_token:
            api(author, "status", token=foreign_token, expected=401)
        credentials = api(author, "installations", method="POST", data={}, expected=201)
        identifier = credentials["installation_id"]
        current_token = credentials["access_token"]
        if api(author, "status", token=current_token)["active"]:
            raise RuntimeError("New installation unexpectedly has access")
        message = "Deployment verification: temporary test request; delete immediately."
        grant = api(author, "free-requests", method="POST", data={"request_id":str(uuid.uuid4()), "message":message}, token=current_token, expected=201)
        if not grant["active"] or grant["grant_kind"] != "free":
            raise RuntimeError("Free-year request not granted")
        starts = datetime.datetime.fromisoformat(grant["starts_at"].replace("Z", "+00:00"))
        expires = datetime.datetime.fromisoformat(grant["expires_at"].replace("Z", "+00:00"))
        if not 364 <= (expires - starts).days <= 366:
            raise RuntimeError("Free grant does not span a calendar year")
        if database_count(author, "access_free_requests", identifier) != 1:
            raise RuntimeError("Free request row missing")
        query = "SELECT count(*) FROM access_free_requests WHERE installation_id='" + identifier + "' AND octet_length(message_ciphertext)>octet_length('" + message + "') AND position(convert_to('" + message + "','UTF8') in message_ciphertext)=0;"
        if command(["runuser", "-u", "postgres", "--", "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", author["database"]], query) != "1":
            raise RuntimeError("Request message encryption check failed")
        recovered = api(author, "recover", method="POST", data={"installation_id":identifier, "recovery_code":credentials["recovery_code"]})
        old_token = current_token
        current_token = recovered["access_token"]
        api(author, "status", token=old_token, expected=401)
        if not api(author, "status", token=current_token)["active"]:
            raise RuntimeError("Recovery did not preserve grant")
        api(author, "installation", method="DELETE", token=current_token, expected=204)
        api(author, "status", token=current_token, expected=401)
        for table in ["access_installations", "access_free_requests", "access_selections"]:
            if database_count(author, table, identifier):
                raise RuntimeError("Deletion did not cascade")
        log = command(["journalctl", "-u", service, "--since", "1 hour ago", "--no-pager", "-o", "cat"])
        if any(value in log for value in [credentials["access_token"],credentials["recovery_code"],current_token,message]):
            raise RuntimeError("Sensitive request data appeared in service logs")
        properties=dict(line.split("=",1) for line in command(["systemctl","show",service,"-p","MemoryCurrent","-p","MemoryPeak"]).splitlines())
        outcome.update({"health":True, "public_reader_files":len(inventory["files"]), "public_downloads":inventory["downloads"], "public_pages":3,
            "other_api_routes_blocked":True,"foreign_token_rejected":bool(foreign_token),"free_calendar_year":True,"message_encrypted":True,
            "recovery_rotates_token":True,"installation_deletion_cascades":True,"request_secrets_absent_from_logs":True,
            "post_access_flow_memory_bytes":int(properties["MemoryCurrent"]),"peak_memory_bytes":int(properties["MemoryPeak"])})
    finally:
        if credentials and current_token:
            try:
                api(author, "installation", method="DELETE", token=current_token, expected=204)
            except Exception:
                pass
        if not initially_active:
            command(["systemctl", "stop", service])
    command(["systemctl", "enable", "--now", service + "-backup.timer"])
    command(["systemctl", "start", service + "-backup.service"])
    archives = sorted(Path("/var/backups",service).glob("*/backup.tar.enc"))
    if not archives:
        raise RuntimeError("Encrypted backup missing")
    archive = archives[-1]
    key = Path("/etc",service,"backup-key").read_bytes().strip()
    actual = hmac.new(key, (service+"-backup-v1:").encode() + archive.read_bytes(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(actual, archive.with_name("backup.tar.enc.hmac").read_text().strip()):
        raise RuntimeError("Backup authentication failure")
    with tempfile.TemporaryDirectory(prefix="author-backup-check-") as temporary:
        import tarfile
        clear = Path(temporary)/"contents.tar"
        command(["openssl","enc","-d","-aes-256-cbc","-pbkdf2","-iter","200000","-pass","file:/etc/"+service+"/backup-key","-in",str(archive),"-out",str(clear)])
        with tarfile.open(clear) as contents:
            if set(contents.getnames())!={"database.dump","environment"}:
                raise RuntimeError("Unexpected backup inventory")
            dump=Path(temporary)/"database.dump"
            dump.write_bytes(contents.extractfile("database.dump").read())
        command(["pg_restore","--list",str(dump)])
    outcome.update({"daily_backup_timer":True,"encrypted_backup_authenticated_and_readable":True,"active_after_check":initially_active})
    return outcome


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    authors=json.loads((args.stage/"authors.json").read_text())["authors"]
    # One real credential from the staged active author proves rejection by the
    # other ten independent databases, then is erased before any backup.
    first=authors[0]
    foreign=api(first,"installations",method="POST",data={},expected=201)
    outcomes=[]
    try:
        for author in authors:
            try:
                outcome=verify(author,args.stage,foreign["access_token"] if author!=first else None)
            except Exception as error:
                outcome={"slug":author["slug"],"passed":False,"error":str(error)}
                outcomes.append(outcome)
                args.report.write_text(json.dumps({"authors":outcomes},indent=2)+"\n")
                print(json.dumps(outcome),flush=True)
                raise SystemExit(1)
            outcome["passed"]=True
            outcomes.append(outcome)
            print(json.dumps(outcome),flush=True)
            args.report.write_text(json.dumps({"authors":outcomes},indent=2)+"\n")
        last=authors[-1]
        last_active=subprocess.run(["systemctl","is-active","--quiet",last["service_name"]]).returncode==0
        if not last_active:
            command(["systemctl","start",last["service_name"]])
            time.sleep(2)
        reverse=None
        try:
            reverse=api(last,"installations",method="POST",data={},expected=201)
            api(first,"status",token=reverse["access_token"],expected=401)
            outcomes[0]["foreign_token_rejected"]=True
            args.report.write_text(json.dumps({"authors":outcomes},indent=2)+"\n")
        finally:
            if reverse:
                api(last,"installation",method="DELETE",token=reverse["access_token"],expected=204)
            if not last_active:
                command(["systemctl","stop",last["service_name"]])
            # Backup names have one-second resolution; avoid a duplicate name
            # immediately after the last author's first successful check.
            time.sleep(1.1)
            command(["systemctl","start",last["service_name"]+"-backup.service"])
    finally:
        api(first,"installation",method="DELETE",token=foreign["access_token"],expected=204)
        command(["systemctl","start",first["service_name"]+"-backup.service"])


if __name__=="__main__":
    main()
