#!/usr/bin/env python3
"""Register only manifest author identifiers and their CloudKit capabilities.

Default is read-only. Requires a team API key; individual keys cannot use
provisioning endpoints. No existing identifiers or capabilities are modified.
The public Apple API cannot create or associate iCloud containers, so enabling
ICLOUD here does not claim that CloudKit container provisioning is complete.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_author_apple import ROOT, ASCClient, APIError, load_authors, relation, PROTECTED_BUNDLES

ICLOUD_SETTINGS = [{"key": "ICLOUD_VERSION", "options": [{"key": "XCODE_6", "enabled": True}]}]


def bundle_name(author):
    # Developer identifier descriptions reject App Store punctuation such as ':'.
    return " ".join(re.sub(r"[^A-Za-z0-9 ]", " ", author["app_name"]).split())


class AuthorProvisioningClient(ASCClient):
    """Creation-only scope; existing GA and foreign provisioning cannot change."""

    def __init__(self, author, *, allow_writes=False):
        listed = {row["slug"]: row for row in load_authors()}
        if (author.get("slug") not in listed
                or author.get("bundle_id") != listed[author["slug"]]["bundle_id"]
                or author["bundle_id"] in PROTECTED_BUNDLES):
            raise RuntimeError("Only an allowlisted author bundle may be provisioned.")
        if not os.environ.get("ASC_ISSUER_ID"):
            raise RuntimeError("Author provisioning requires ASC_ISSUER_ID and a team API key.")
        self.author = author
        self.bundle_resource_id = None
        super().__init__(allow_writes=allow_writes)

    def _validate_bundle(self, row):
        attrs = row.get("attributes", {})
        if row.get("type") != "bundleIds" or attrs.get("identifier") != self.author["bundle_id"]:
            raise RuntimeError("Apple returned a bundle outside this author's allowlist.")
        if attrs.get("platform") not in {"IOS", "UNIVERSAL"}:
            raise RuntimeError("Existing author identifier has an incompatible platform; preserved.")
        self.bundle_resource_id = row["id"]

    def request(self, method, path, body=None, params=None):
        parts = urlsplit(path).path.strip("/").split("/")
        data = body.get("data", {}) if isinstance(body, dict) else {}
        if method != "GET":
            if method != "POST" or len(parts) != 2 or parts[0] != "v1" or body.get("included"):
                raise RuntimeError("Provisioning allows creation only; existing records are preserved.")
            if parts[1] == "bundleIds":
                if data != {"type": "bundleIds", "attributes": {
                        "identifier": self.author["bundle_id"], "name": bundle_name(self.author), "platform": "IOS"}}:
                    raise RuntimeError("Bundle creation is outside the selected author's allowlist.")
            elif parts[1] == "bundleIdCapabilities":
                expected = {"type": "bundleIdCapabilities", "attributes": {
                    "capabilityType": "ICLOUD", "settings": ICLOUD_SETTINGS},
                    "relationships": {"bundleId": relation("bundleIds", self.bundle_resource_id)}}
                if not self.bundle_resource_id or data != expected:
                    raise RuntimeError("Only this verified author's CloudKit capability may be created.")
            else:
                raise RuntimeError("Unsupported author provisioning resource.")
        else:
            if parts == ["v1", "bundleIds"]:
                if not params or params.get("filter[identifier]") != self.author["bundle_id"]:
                    raise RuntimeError("Bundle reads must filter this author explicitly.")
            elif parts != ["v1", "bundleIds", self.bundle_resource_id, "bundleIdCapabilities"]:
                raise RuntimeError("Only the verified author's capabilities may be read.")
        result = super().request(method, path, body=body, params=params)
        if parts == ["v1", "bundleIds"]:
            rows = result.get("data", [])
            for row in rows if isinstance(rows, list) else [rows]:
                self._validate_bundle(row)
        return result


def cloudkit_enabled(capability):
    attrs = capability.get("attributes", {})
    # Apple returns the selected option keys and omits the optional enabled flag.
    return attrs.get("capabilityType") == "ICLOUD" and any(
        setting.get("key") == "ICLOUD_VERSION" and any(
            option.get("key") == "XCODE_6" and option.get("enabled") is not False
            for option in setting.get("options", []))
        for setting in (attrs.get("settings") or []))


def provision(author, apply):
    client = AuthorProvisioningClient(author, allow_writes=apply)
    bundles = client.rows("/v1/bundleIds", {"filter[identifier]": author["bundle_id"], "limit": 200})
    if len(bundles) > 1:
        raise RuntimeError("Ambiguous author bundle registration; existing identifiers preserved.")
    created = False
    if not bundles and apply:
        bundle = client.write("POST", "bundleIds", {
            "identifier": author["bundle_id"], "name": bundle_name(author), "platform": "IOS"})
        # Re-read Apple's stored identity before any dependent provisioning.
        bundles = client.rows("/v1/bundleIds", {"filter[identifier]": author["bundle_id"], "limit": 200})
        if len(bundles) != 1 or bundle["id"] != bundles[0]["id"]:
            raise RuntimeError("Created author identifier could not be verified.")
        created = True
    result = {"slug": author["slug"], "bundleId": author["bundle_id"],
              "expectedCloudKitContainer": author["cloudkit_container"],
              "bundleRegistered": bool(bundles), "bundleCreated": created,
              "cloudkitEnabled": False, "containerAssociationVerified": False,
              "remaining": ["Create/associate this author's private iCloud container in Developer portal or Xcode.",
                            "Initialize and deploy this author's CloudKit production schema.",
                            "Create signed author provisioning profiles and verify real-device sync."]}
    if not bundles:
        return result
    bundle = bundles[0]
    result.update(bundleResourceId=bundle["id"], platform=bundle["attributes"]["platform"])
    endpoint = f"/v1/bundleIds/{bundle['id']}/bundleIdCapabilities"
    capabilities = client.rows(endpoint)
    cloud = [r for r in capabilities if r["attributes"]["capabilityType"] == "ICLOUD"]
    if len(cloud) > 1 or (cloud and not cloudkit_enabled(cloud[0])):
        raise RuntimeError("Existing iCloud settings conflict with CloudKit; preserved for inspection.")
    if not cloud and apply:
        client.write("POST", "bundleIdCapabilities", {"capabilityType": "ICLOUD", "settings": ICLOUD_SETTINGS},
                     {"bundleId": relation("bundleIds", bundle["id"])})
        capabilities = client.rows(endpoint)
        cloud = [r for r in capabilities if r["attributes"]["capabilityType"] == "ICLOUD"]
    result["cloudkitEnabled"] = len(cloud) == 1 and cloudkit_enabled(cloud[0])
    result["capabilityResourceId"] = cloud[0]["id"] if cloud else None
    result["inAppPurchaseEnabled"] = any(r["attributes"]["capabilityType"] == "IN_APP_PURCHASE" for r in capabilities)
    if apply and not result["cloudkitEnabled"]:
        raise RuntimeError("Apple's stored CloudKit capability could not be verified.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", action="store_true", help="Show expected identifiers without credentials or network")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.plan and args.apply:
        parser.error("--plan and --apply cannot be combined")
    authors = load_authors()
    known = {row["slug"] for row in authors}
    if set(args.author) - known:
        parser.error("Unknown author slug")
    selected = [row for row in authors if not args.author or row["slug"] in args.author]
    if args.plan:
        print(json.dumps([{"slug": a["slug"], "bundleId": a["bundle_id"], "platform": "IOS",
                           "capability": "ICLOUD", "cloudKitContainer": a["cloudkit_container"],
                           "containerAssociationRequired": True} for a in selected], indent=2))
        return
    results = []
    for author in selected:
        try:
            result = provision(author, args.apply)
        except (APIError, RuntimeError) as error:
            # Apple errors can contain request IDs and public resource attributes,
            # but no credential material. Do not include environment or key paths.
            result = {"slug": author["slug"], "bundleId": author["bundle_id"], "error": str(error)}
        results.append(result)
        print(json.dumps(result), flush=True)
        if args.report:
            old = json.loads(args.report.read_text()) if args.report.exists() else {"authors": []}
            merged = {row["slug"]: row for row in old["authors"]}
            merged.update({row["slug"]: row for row in results})
            report = {"checkedAt": datetime.now(timezone.utc).isoformat(), "applied": args.apply,
                      "authors": [merged[a["slug"]] for a in authors if a["slug"] in merged]}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
    if any("error" in row for row in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
