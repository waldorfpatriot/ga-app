#!/usr/bin/env python3
"""Prepare private Apple review collections; never submit them for review.

Read-only unless --apply. No submission, deletion, release or build-selection
operation is implemented. App items require the explicitly expected build.
"""
import argparse
import json
from pathlib import Path

from asc_client import ASCClient, APIError, relation
from app_config import (APP_ID, BUNDLE_ID, GROUP_ID, IOS_VERSION_ID, IOS_BUILD_ID,
                        MAC_VERSION_ID, MAC_BUILD_ID)

APPS = {
    "IOS": {"app": APP_ID, "version": IOS_VERSION_ID,
            "build": IOS_BUILD_ID, "group": GROUP_ID,
            "subscriptions": ["57c612f2-bc91-4316-a5ad-912a88acf6e7", "a37a5c43-4bf7-4cca-a2e6-8c0feab48d60"]},
    "MAC_OS": {"app": APP_ID, "version": MAC_VERSION_ID,
               "build": MAC_BUILD_ID, "group": None, "subscriptions": []},
}


def item_resources(items):
    return {(key, rel["data"]["id"]) for item in items
            for key, rel in item.get("relationships", {}).items()
            if rel.get("data") and isinstance(rel["data"], dict)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--include-app", action="store_true")
    p.add_argument("--platform", choices=["ios", "macos", "all"], default="all")
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    client = ASCClient(allow_writes=args.apply)
    reports = []

    def save():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")

    app = client.request("GET", f"/v1/apps/{APP_ID}")["data"]
    if app["attributes"].get("bundleId") != BUNDLE_ID:
        raise RuntimeError("Unexpected universal-purchase app record.")
    platforms = APPS if args.platform == "all" else {"IOS" if args.platform == "ios" else "MAC_OS": APPS["IOS" if args.platform == "ios" else "MAC_OS"]}
    for platform, config in platforms.items():
        private_drafts = [r for r in client.rows(f"/v1/apps/{config['app']}/reviewSubmissions", {"limit": 200})
                          if r["attributes"]["state"] == "READY_FOR_REVIEW"
                          and not r["attributes"].get("submittedDate")]
        drafts = [r for r in private_drafts if r["attributes"]["platform"] == platform]
        if any(r["attributes"]["platform"] not in APPS for r in private_drafts):
            raise RuntimeError("Unexpected platform in a private draft; inspect before creating another one")
        if len(drafts) > 1:
            raise RuntimeError("Multiple private drafts: inspect before choosing one")
        draft = drafts[0] if drafts else None
        if draft is None and args.apply:
            draft = client.write("POST", "reviewSubmissions", {"platform": platform},
                                 {"app": relation("apps", config["app"])})
            draft = client.request("GET", f"/v1/reviewSubmissions/{draft['id']}")["data"]
        report = {"appId": config["app"], "expectedPlatform": platform,
                  "platform": draft["attributes"]["platform"] if draft else None,
                  "platformVerified": bool(draft and draft["attributes"]["platform"] == platform),
                  "draftId": draft["id"] if draft else None,
                  "applied": args.apply, "appItemRequested": args.include_app,
                  "expectedBuild": config["build"], "expectedVersion": config["version"],
                  "added": [], "validationErrors": [], "submitted": False}
        reports.append(report)
        save()
        if draft is None:
            print(json.dumps(report), flush=True)
            continue
        if not report["platformVerified"]:
            raise RuntimeError("Apple readback platform differs from requested platform; inspect the private draft")
        draft_id = draft["id"]
        existing_items = client.rows(f"/v1/reviewSubmissions/{draft_id}/items", {
            "include": "appStoreVersion,subscriptionVersion,subscriptionGroupVersion", "limit": 200})
        existing = item_resources(existing_items)
        desired = []
        if config["group"]:
            group_versions = [r for r in client.rows(f"/v1/subscriptionGroups/{config['group']}/versions", {"limit": 200})
                              if r["attributes"]["state"] in ("PREPARE_FOR_SUBMISSION", "READY_FOR_REVIEW")]
            if len(group_versions) != 1:
                raise RuntimeError("Expected one editable shared subscription-group version")
            desired.append(("subscriptionGroupVersion", "subscriptionGroupVersions", group_versions[0]["id"]))
            desired.extend(("subscriptionVersion", "subscriptionVersions", sid) for sid in config["subscriptions"])
        elif any(key in {"subscriptionVersion", "subscriptionGroupVersion"} for key, _ in existing):
            raise RuntimeError("Shared products belong to the existing iOS review draft; refusing duplicate Mac review items.")
        if args.include_app:
            if not config["version"] or not config["build"]:
                report["validationErrors"].append({"resource": "appStoreVersion", "id": config["version"],
                                                   "detail": "Final shared version/build 3 is not yet confirmed; app item was not added."})
            else:
                version = client.request("GET", f"/v1/appStoreVersions/{config['version']}", params={"include": "build,app"})
                selected = version["data"]["relationships"]["build"]["data"]
                owner = version["data"]["relationships"]["app"]["data"]
                builds = [row for row in version.get("included", []) if row["type"] == "builds"]
                if (not selected or selected["id"] != config["build"] or owner["id"] != APP_ID
                        or version["data"]["attributes"]["platform"] != platform
                        or version["data"]["attributes"]["releaseType"] != "MANUAL"
                        or len(builds) != 1 or builds[0]["id"] != config["build"]
                        or builds[0]["attributes"].get("version") != "3"
                        or builds[0]["attributes"].get("processingState") != "VALID"):
                    raise RuntimeError("Expected confirmed platform build on shared app and manual release; refusing app addition")
                desired.append(("appStoreVersion", "appStoreVersions", config["version"]))
        for key, resource, identifier in desired:
            if (key, identifier) in existing or not args.apply:
                continue
            try:
                item = client.write("POST", "reviewSubmissionItems", relationships={
                    "reviewSubmission": relation("reviewSubmissions", draft_id),
                    key: relation(resource, identifier)})
                report["added"].append({"itemId": item["id"], "resource": key, "id": identifier})
                print(json.dumps({"platform": platform, "added": key, "id": identifier}), flush=True)
            except APIError as error:
                report["validationErrors"].append({"resource": key, "id": identifier, "detail": str(error)})
                print(json.dumps({"platform": platform, "blocked": key, "detail": str(error)}), flush=True)
            save()
        final_draft = client.request("GET", f"/v1/reviewSubmissions/{draft_id}")["data"]
        final_items = client.rows(f"/v1/reviewSubmissions/{draft_id}/items", {
            "include": "appStoreVersion,subscriptionVersion,subscriptionGroupVersion", "limit": 200})
        attrs = final_draft["attributes"]
        if attrs["platform"] != platform:
            raise RuntimeError("Private draft platform changed unexpectedly")
        if attrs["state"] != "READY_FOR_REVIEW" or attrs.get("submittedDate"):
            raise RuntimeError("Expected an unsubmitted private draft")
        report.update(platform=attrs["platform"], platformVerified=True,
                      state=attrs["state"], submittedDate=attrs.get("submittedDate"), items=final_items,
                      appItemPresent=("appStoreVersion", config["version"]) in item_resources(final_items),
                      desiredItemsPresent=not report["validationErrors"] and all((key, identifier) in item_resources(final_items) for key, _, identifier in desired))
        save()
        print(json.dumps({"platform": platform, "draftId": draft_id, "state": attrs["state"],
                          "items": len(final_items), "submittedDate": attrs.get("submittedDate"),
                          "desiredItemsPresent": report["desiredItemsPresent"]}), flush=True)


if __name__ == "__main__":
    main()
