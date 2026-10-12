"""Apply prepared German metadata to an editable Apple draft; never submits review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from asc_client import ASCClient, APIError, relation
from app_config import APP_ID, BUNDLE_ID

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {"ios": ("IOS", "iOS", BUNDLE_ID),
             "macos": ("MAC_OS", "macOS", BUNDLE_ID)}
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED"}


def update_localization(client, resource, path, attrs, parent_type, parent_id):
    rows = client.rows(path, {"limit": 200})
    localized = next((row for row in rows if row["attributes"].get("locale") == "de-DE"), None)
    if localized:
        changes = {key: value for key, value in attrs.items()
                   if localized["attributes"].get(key) != value}
        if changes:
            return client.write("PATCH", resource, changes, identifier=localized["id"])
        return localized
    return client.write("POST", resource, {"locale": "de-DE", **attrs},
                        {parent_type: relation(parent_type + "s", parent_id)})


def run(args):
    platform, display_platform, bundle = PLATFORMS[args.platform]
    client = ASCClient(allow_writes=args.apply)
    metadata = json.loads((ROOT / "metadata.de-DE.json").read_text())
    apps = client.rows("/v1/apps", {"filter[bundleId]": bundle, "limit": 200})
    app = next((row for row in apps if not args.app_id or row["id"] == args.app_id), None)
    if not app:
        print(json.dumps({"platform": platform, "bundleId": bundle, "appFound": False,
                          "writesEnabled": args.apply}, ensure_ascii=False, indent=2))
        return 2
    app_id = app["id"]
    if app_id != APP_ID:
        raise RuntimeError("Expected the shared universal-purchase app record; legacy Mac setup is disabled.")
    infos = client.rows(f"/v1/apps/{app_id}/appInfos", {"limit": 200})
    editable_infos = [row for row in infos
                      if row["attributes"].get("state", row["attributes"].get("appStoreState")) in EDITABLE]
    versions = client.rows(f"/v1/apps/{app_id}/appStoreVersions",
                           {"filter[platform]": platform, "limit": 200})
    versions = [row for row in versions if row["attributes"].get("versionString") == args.version]
    version = next((row for row in versions
                    if row["attributes"].get("appVersionState", row["attributes"].get("appStoreState")) in EDITABLE), None)
    categories = metadata.get("platform_categories", {}).get(display_platform, {})
    primary = categories.get("primary_category", metadata["primary_category"])
    secondary = categories.get("secondary_category", metadata["secondary_category"])
    if primary != "Books" or secondary != "Reference":
        raise RuntimeError("Shared appInfo requires Books / Reference on both platforms.")
    summary = {"platform": platform, "bundleId": bundle, "appId": app_id,
               "writesEnabled": args.apply, "editableAppInfoIds": [row["id"] for row in editable_infos],
               "versionId": version["id"] if version else None,
               "versionString": args.version, "primaryCategory": primary, "secondaryCategory": secondary}
    if not args.apply:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if len(editable_infos) != 1:
        raise RuntimeError("Expected exactly one editable appInfo; refusing an ambiguous or submitted app record.")
    info = editable_infos[0]
    if versions and version is None:
        raise RuntimeError("Requested version exists but is not editable; refusing to change a submitted version.")
    if version is None:
        version = client.write("POST", "appStoreVersions",
                               {"platform": platform, "versionString": args.version,
                                "copyright": metadata["copyright"], "releaseType": "MANUAL"},
                               {"app": relation("apps", app_id)})
    else:
        # Manual release prevents an eventual approval from automatically publishing the app.
        client.write("PATCH", "appStoreVersions",
                     {"copyright": metadata["copyright"], "releaseType": "MANUAL"}, identifier=version["id"])
    for category in (primary, secondary):
        available = client.rows("/v1/appCategories", {"filter[platforms]": platform,
                                                       "exists[parent]": "false", "limit": 200})
        if category.upper() not in {row["id"] for row in available}:
            raise RuntimeError(f"Category {category} is unavailable for {platform}.")
    client.write("PATCH", "appInfos", relationships={
        "primaryCategory": relation("appCategories", primary.upper()),
        "secondaryCategory": relation("appCategories", secondary.upper())}, identifier=info["id"])
    name = metadata["name"]
    info_attrs = {"name": name, "subtitle": metadata["subtitle"], "privacyPolicyUrl": metadata["privacy_policy_url"]}
    version_attrs = {"description": metadata["description"], "keywords": metadata["keywords"],
                     "promotionalText": metadata["promotional_text"], "supportUrl": metadata["support_url"],
                     "marketingUrl": metadata["marketing_url"]}
    info_local = update_localization(client, "appInfoLocalizations",
        f"/v1/appInfos/{info['id']}/appInfoLocalizations",
        info_attrs,
        "appInfo", info["id"])
    version_local = update_localization(client, "appStoreVersionLocalizations",
        f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations",
        version_attrs, "appStoreVersion", version["id"])
    contact = metadata["review_contact"]
    notes = (ROOT / "review-notes.en.md").read_text()
    notes = notes[notes.index("The app is an independent"):].strip()
    review_attrs = {"contactFirstName": contact["first_name"], "contactLastName": contact["last_name"],
                    "contactEmail": contact["email"], "contactPhone": contact["phone"],
                    "demoAccountRequired": False, "notes": notes}
    try:
        review = client.request("GET", f"/v1/appStoreVersions/{version['id']}/appStoreReviewDetail").get("data")
    except APIError as error:
        if error.status != 404:
            raise
        review = None
    if review:
        client.write("PATCH", "appStoreReviewDetails", review_attrs, identifier=review["id"])
    else:
        client.write("POST", "appStoreReviewDetails", review_attrs,
                     {"appStoreVersion": relation("appStoreVersions", version["id"])})
    # Read the resulting resources rather than treating accepted writes as final verification.
    info_check = client.request("GET", f"/v1/appInfoLocalizations/{info_local['id']}")["data"]["attributes"]
    version_check = client.request("GET", f"/v1/appStoreVersionLocalizations/{version_local['id']}")["data"]["attributes"]
    if any(info_check.get(key) != value for key, value in info_attrs.items()):
        raise RuntimeError("Apple app-info verification did not match the prepared metadata.")
    if any(version_check.get(key) != value for key, value in version_attrs.items()):
        raise RuntimeError("Apple version-localization verification did not match the prepared metadata.")
    summary.update({"versionId": version["id"], "appInfoLocalizationId": info_local["id"],
                    "versionLocalizationId": version_local["id"], "verified": True,
                    "releaseType": "MANUAL", "submitted": False, "buildUploadPerformed": False})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=PLATFORMS)
    parser.add_argument("--app-id")
    parser.add_argument("--version", default="1.0")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Read-only status (default).")
    mode.add_argument("--apply", action="store_true", help="Write prepared metadata to an editable draft.")
    arguments = parser.parse_args()
    try:
        raise SystemExit(run(arguments))
    except (RuntimeError, APIError) as error:
        parser.exit(1, f"{error}\n")
