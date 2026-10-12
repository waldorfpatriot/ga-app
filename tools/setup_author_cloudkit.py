#!/usr/bin/env python3
"""Inspect/prepare isolated author CloudKit schemas; default is read-only.

Uses cktool's Keychain token or CLOUDKIT_MANAGEMENT_TOKEN; never accepts or
prints a token. Container creation/association and Production deployment happen
in Apple's portal/Console. --apply-development only imports additive Development
changes after --registered-author confirms that author's provisioning is ready.
The original Steiner container is rejected unconditionally.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEAM_ID = "ER7U6R25KM"
GA_BUNDLE = "com.jonathankutscher.ga"
GA_CONTAINER = "iCloud." + GA_BUNDLE
REQUIRED_FIELDS = {"payload": "ASSET", "schemaVersion": "INT64"}
FRAGMENT = "RECORD TYPE GAReadingState (\n    payload ASSET,\n    schemaVersion INT64\n);\n"


def checked_authors(manifest: dict, slugs: list[str] | None) -> list[dict]:
    authors = manifest["authors"]
    if len({a["slug"] for a in authors}) != len(authors):
        raise ValueError("Duplicate author slugs")
    if slugs and set(slugs) - {a["slug"] for a in authors}:
        raise ValueError("Unknown author slug")
    selected = [a for a in authors if not slugs or a["slug"] in slugs]
    seen_containers = set()
    for author in selected:
        slug, bundle, container = (author[k] for k in ("slug", "bundle_id", "cloudkit_container"))
        if not re.fullmatch(r"[a-z][a-z0-9-]*", slug) or slug == "steiner":
            raise ValueError("Invalid or protected author slug")
        if bundle == GA_BUNDLE or container == GA_CONTAINER:
            raise ValueError("Original GA provisioning is protected")
        if not re.fullmatch(r"com\.jonathankutscher\.[a-z][a-z0-9]+", bundle):
            raise ValueError("Unexpected author bundle ID")
        if container != "iCloud." + bundle or container in seen_containers:
            raise ValueError("Author container must match its unique bundle ID")
        seen_containers.add(container)
    if not selected:
        raise ValueError("No authors selected")
    return selected


def mask_comments(schema: str) -> str:
    """Keep all offsets stable while hiding the three CKDB comment forms."""
    out = list(schema)
    i, quoted = 0, False
    while i < len(schema):
        if schema[i] == '"':
            quoted = not quoted
            i += 1
            continue
        if not quoted and schema[i:i + 2] in ("//", "--", "/*"):
            if schema[i:i + 2] == "/*":
                end = schema.find("*/", i + 2)
                if end < 0:
                    raise ValueError("Unterminated schema comment")
                end += 2
            else:
                end = schema.find("\n", i + 2)
                if end < 0:
                    end = len(schema)
            for j in range(i, end):
                if schema[j] != "\n":
                    out[j] = " "
            i = end
        else:
            i += 1
    if quoted:
        raise ValueError("Unterminated quoted schema identifier")
    return "".join(out)


def reading_type(schema: str):
    masked = mask_comments(schema)
    if not re.match(r"\s*DEFINE\s+SCHEMA\b", masked, flags=re.I):
        raise ValueError("Expected a complete exported CKDB schema")
    matches = list(re.finditer(r'\bRECORD\s+TYPE\s+(?:GAReadingState|"GAReadingState")\s*\(', masked))
    if len(matches) > 1:
        raise ValueError("Duplicate GAReadingState record type")
    if not matches:
        return None, {}, False
    start = matches[0].end()
    end = masked.find(")", start)
    if end < 0 or not re.match(r"\s*;", masked[end + 1:]):
        raise ValueError("Malformed GAReadingState record type")
    body = masked[start:end]
    fields = {}
    for name in REQUIRED_FIELDS:
        entries = list(re.finditer(r'(?:^|,)\s*(?:' + name + r'|"' + name + r'")\s+([^,]+)', body))
        if len(entries) > 1:
            raise ValueError("Duplicate reading-state field: " + name)
        if entries:
            declaration = " ".join(entries[0].group(1).split())
            fields[name] = re.sub(r"\s+(QUERYABLE|SORTABLE|SEARCHABLE)\b", "", declaration)
    return (start, end), fields, bool(re.search(r"\bGRANT\b", body))


def schema_status(schema: str) -> dict:
    _, fields, grants = reading_type(schema)
    conflicts = {name: actual for name, actual in fields.items()
                 if actual not in (REQUIRED_FIELDS[name], "NUMBER PREFERRED AS INT64" if name == "schemaVersion" else "ASSET")}
    return {"ready": fields.keys() >= REQUIRED_FIELDS.keys() and not conflicts,
            "fields": fields, "conflictingFields": conflicts, "publicGrantsPresent": grants}


def additive_schema(schema: str) -> str:
    """Preserve every existing byte and only insert missing record/fields."""
    bounds, fields, _ = reading_type(schema)
    status = schema_status(schema)
    if status["conflictingFields"]:
        raise ValueError("Existing reading-state field types conflict; manual review required")
    if bounds is None:
        return schema + ("" if schema.endswith("\n") else "\n") + "\n" + FRAGMENT
    missing = [name + " " + datatype for name, datatype in REQUIRED_FIELDS.items() if name not in fields]
    if not missing:
        return schema
    start, end = bounds
    existing_body = bool(mask_comments(schema[start:end]).strip())
    insert = "\n    " + ",\n    ".join(missing) + ("," if existing_body else "") + "\n"
    return schema[:start] + insert + schema[start:]


class CKToolError(RuntimeError):
    def __init__(self, status: str, code: int):
        self.status, self.code = status, code
        super().__init__(status)


def cktool(arguments: list[str]) -> None:
    # Never include --token in argv. Capture both streams without printing them;
    # diagnostics are mapped to fixed labels so credentials cannot enter reports.
    result = subprocess.run(["xcrun", "cktool", *arguments], capture_output=True, text=True, timeout=60)
    if result.returncode:
        output = (result.stdout + result.stderr).lower()
        if "no management token" in output:
            status = "blocked_missing_management_token"
        elif any(word in output for word in ("unauthorized", "authentication", "invalid token", "expired token")):
            status = "blocked_management_authentication"
        elif any(word in output for word in ("container not found", "unknown container", "does not exist")):
            status = "blocked_container_registration"
        else:
            status = "cktool_command_failed"
        raise CKToolError(status, result.returncode)


def base_report(author: dict) -> dict:
    return {"slug": author["slug"], "author": author["author_name"], "teamId": TEAM_ID,
            "bundleId": author["bundle_id"], "containerId": author["cloudkit_container"],
            "database": "private", "recordType": "GAReadingState", "recordId": "personal-reading-state-v1",
            "requiredFields": REQUIRED_FIELDS,
            "portalSteps": ["Register the author bundle ID for iOS and macOS.",
                            "Enable iCloud/CloudKit and register this author's iCloud container.",
                            "Associate only this author container with this author bundle ID.",
                            "Regenerate author iOS/macOS provisioning profiles after capability changes."],
            "productionStep": "After Development is ready, deploy schema changes in CloudKit Console and export Production again.",
            "deviceCheck": "Verify position, note, highlight and deletion sync on two signed devices using the same iCloud account."}


def write_status(directory: Path, report: dict) -> None:
    """A CLI authentication failure must not erase verified Console evidence."""
    (directory / "cktool-status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    status_path = directory / "status.json"
    previous = json.loads(status_path.read_text()) if status_path.exists() else {}
    if previous.get("productionSchemaVerified") and report["status"] in (
        "blocked_missing_management_token", "blocked_management_authentication"
    ):
        previous["lastCKToolStatus"] = report["status"]
        previous["lastCKToolCheckedAt"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
    else:
        status_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def inspect(author: dict, *, apply: bool, registered: bool) -> dict:
    report = base_report(author)
    if apply and not registered:
        raise ValueError("Development import requires --registered-author " + author["slug"])
    directory = ROOT / "editions" / author["slug"] / "cloudkit"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        with tempfile.TemporaryDirectory(prefix="author-cloudkit-") as temporary:
            scratch = Path(temporary)
            for environment in ("development", "production"):
                cktool(["export-schema", "--team-id", TEAM_ID, "--container-id", author["cloudkit_container"],
                        "--environment", environment, "--output-file", str(scratch / (environment + ".ckdb"))])
            development = (scratch / "development.ckdb").read_text()
            production = (scratch / "production.ckdb").read_text()
            report["development"] = schema_status(development)
            report["production"] = schema_status(production)
            merged = additive_schema(development)
            snapshots = directory / "snapshots" / stamp
            snapshots.mkdir(parents=True)
            shutil.copyfile(scratch / "development.ckdb", snapshots / "development.before.ckdb")
            shutil.copyfile(scratch / "production.ckdb", snapshots / "production.before.ckdb")
            prepared = snapshots / "development.prepared.ckdb"
            prepared.write_text(merged)
            report["snapshotDirectory"] = str(snapshots.relative_to(ROOT))
            report["developmentChangeNeeded"] = merged != development
            if report["production"]["conflictingFields"]:
                report["status"] = "blocked_production_field_conflict"
            elif report["production"]["ready"] and report["development"]["ready"]:
                report["status"] = "production_schema_verified"
            elif merged != development:
                cktool(["validate-schema", "--team-id", TEAM_ID, "--container-id", author["cloudkit_container"],
                        "--environment", "development", "--file", str(prepared)])
                report["status"] = "development_change_validated"
                if apply:
                    # Only Development may be mutated. Production deploy is a separate Console operation.
                    cktool(["import-schema", "--validate", "--team-id", TEAM_ID,
                            "--container-id", author["cloudkit_container"], "--environment", "development",
                            "--file", str(prepared)])
                    after = snapshots / "development.after.ckdb"
                    cktool(["export-schema", "--team-id", TEAM_ID, "--container-id", author["cloudkit_container"],
                            "--environment", "development", "--output-file", str(after)])
                    report["development"] = schema_status(after.read_text())
                    if not report["development"]["ready"]:
                        raise ValueError("Development readback did not confirm required fields")
                    report["status"] = "development_ready_production_deploy_required"
            else:
                report["status"] = "development_ready_production_deploy_required"
    except CKToolError as error:
        report.update(status=error.status, cktoolExitCode=error.code)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        report["status"] = "blocked_schema_or_tool_review_required"
    write_status(directory, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", action="append", help="Author slug; omitted means all eleven.")
    parser.add_argument("--plan", action="store_true", help="Offline plan; never reads credentials or contacts Apple.")
    parser.add_argument("--write-plan", action="store_true", help="Save the offline plan under editions/.")
    parser.add_argument("--apply-development", action="store_true", help="Import only the additive Development change.")
    parser.add_argument("--registered-author", action="append", default=[], help="Explicit author provisioning confirmation before import.")
    args = parser.parse_args()
    if args.plan and args.apply_development:
        parser.error("Plan and apply cannot be combined")
    if args.write_plan and not args.plan:
        parser.error("--write-plan requires --plan")
    try:
        authors = checked_authors(json.loads((ROOT / "editions/authors.json").read_text()), args.author)
        if args.apply_development and set(a["slug"] for a in authors) - set(args.registered_author):
            parser.error("Confirm every selected author with --registered-author before Development import")
        reports = [dict(base_report(a), status="portal_provisioning_then_schema_setup_required") for a in authors] if args.plan else [
            inspect(a, apply=args.apply_development, registered=a["slug"] in args.registered_author) for a in authors]
    except ValueError as error:
        parser.error(str(error))
    if args.write_plan:
        (ROOT / "editions/cloudkit-setup-plan.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    if not args.plan and any(r["status"].startswith(("blocked_", "cktool_")) for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
