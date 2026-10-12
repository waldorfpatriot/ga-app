"""Upload GA marketing/review screenshots to editable App Store drafts.

Default is read-only. Apple JWTs and signed upload URLs are never printed.
Uses Apple's OpenAPI 4.5.1 screenshot resources and upload-reserve/commit flow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from asc_client import APIError, ASCClient, relation
from app_config import APP_ID, IOS_LOCALIZATION_ID, MAC_LOCALIZATION_ID

ROOT = Path(__file__).resolve().parents[3]
SCREENSHOTS = ROOT / "docs/app-store/screenshots"
CONFIG = {
    "ios": {
        "app": APP_ID, "localization": IOS_LOCALIZATION_ID, "platform": "IOS",
        "sets": [
            ("APP_IPHONE_67", "iphone-6.9", (1320, 2868), 8),
            ("APP_IPHONE_61", "iphone-medium", (1206, 2622), 8),
            ("APP_IPAD_PRO_3GEN_129", "ipad-13", (2064, 2752), 8),
        ],
        "reviews": [
            ("annual", "6820967918", "57c612f2-bc91-4316-a5ad-912a88acf6e7", "com.jonathankutscher.ga.annual", "review/iphone-6.9/AppStore-04-Solidarischer-Zugang.png"),
            ("supporter", "6820968113", "a37a5c43-4bf7-4cca-a2e6-8c0feab48d60", "com.jonathankutscher.ga.supporter", "review/iphone-6.9/AppStore-05-Kostenloses-Jahr.png"),
        ],
    },
    "macos": {
        "app": APP_ID, "localization": MAC_LOCALIZATION_ID, "platform": "MAC_OS",
        "sets": [("APP_DESKTOP", "mac", (2560, 1600), 4)],
        # Universal purchase reuses the iOS product review assets. Never create
        # a second review asset or resurrect separate Mac products.
        "reviews": [],
    },
}
PURCHASE_MARKETING_FILES = (
    "AppStore-04-Solidarischer-Zugang.png",
    "AppStore-05-Kostenloses-Jahr.png",
)
PURCHASE_MARKETING_DIRECTORIES = {"iphone-6.9", "iphone-medium", "ipad-13"}


def image_dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        width, height, depth, color = struct.unpack(">IIBB", data[16:26])
        if depth != 8 or color != 2 or b"tRNS" in data:
            raise RuntimeError("Expected an opaque, 8-bit RGB screenshot PNG.")
        return width, height
    if data.startswith(b"\xff\xd8"):
        offset = 2
        while offset < len(data):
            if data[offset] != 0xff:
                raise RuntimeError("Invalid JPEG screenshot.")
            while data[offset] == 0xff:
                offset += 1
            marker = data[offset]
            offset += 1
            if marker in (0xd8, 0xd9):
                continue
            length = struct.unpack(">H", data[offset:offset + 2])[0]
            if marker in (0xc0, 0xc1, 0xc2):
                depth, height, width, channels = struct.unpack(">BHHB", data[offset + 2:offset + 8])
                if depth != 8 or channels != 3:
                    raise RuntimeError("Expected an opaque, 8-bit RGB screenshot JPEG.")
                return width, height
            offset += length
    raise RuntimeError("Expected a PNG or JPEG screenshot.")


def manifest(config):
    result = {}
    for display, directory, expected, count in config["sets"]:
        if not 1 <= count <= 10:
            raise RuntimeError("Expected 1 to 10 configured screenshots per display.")
        files = sorted((SCREENSHOTS / directory).glob("AppStore-*.png")) + sorted((SCREENSHOTS / directory).glob("AppStore-*.jpg"))
        if len(files) != count:
            raise RuntimeError(f"{directory}: expected {count} store screenshots, found {len(files)}.")
        entries = []
        for path in files:
            data = path.read_bytes()
            if image_dimensions(data) != expected:
                raise RuntimeError(f"{directory}/{path.name}: screenshot dimensions differ from the verified set.")
            entries.append({"path": path, "name": path.name, "size": len(data), "checksum": hashlib.md5(data).hexdigest()})
        result[display] = entries
    return result


def validate_draft(client, config):
    if not config.get("localization"):
        raise RuntimeError("Shared Mac localization is not confirmed yet; legacy Mac uploads are disabled.")
    localization = config["localization"]
    response = client.request("GET", f"/v1/appStoreVersionLocalizations/{localization}", params={"include": "appStoreVersion"})
    if response["data"]["attributes"].get("locale") != "de-DE":
        raise RuntimeError("Refusing a localization other than the expected de-DE draft.")
    versions = [row for row in response.get("included", []) if row["type"] == "appStoreVersions"]
    if len(versions) != 1:
        raise RuntimeError("Cannot verify the screenshot localization's version.")
    version = client.request("GET", f"/v1/appStoreVersions/{versions[0]['id']}", params={"include": "app"})
    apps = [row for row in version.get("included", []) if row["type"] == "apps"]
    attributes = version["data"]["attributes"]
    if len(apps) != 1 or apps[0]["id"] != config["app"] or attributes.get("platform") != config["platform"]:
        raise RuntimeError("Refusing screenshots for an unexpected Apple app/platform.")
    if attributes.get("versionString") != "1.0" or attributes.get("appVersionState", attributes.get("appStoreState")) != "PREPARE_FOR_SUBMISSION":
        raise RuntimeError("Screenshots may only be changed on the expected version 1.0 preparation draft.")
    return version["data"]["id"]


def inventory(client, config):
    rows = client.rows(f"/v1/appStoreVersionLocalizations/{config['localization']}/appScreenshotSets", params={"limit": 200})
    result = {}
    for row in rows:
        display = row["attributes"]["screenshotDisplayType"]
        if display in result:
            raise RuntimeError(f"Multiple sets for {display}; refusing ambiguous changes.")
        assets = client.rows(f"/v1/appScreenshotSets/{row['id']}/appScreenshots", params={"limit": 200})
        result[display] = {"id": row["id"], "assets": assets}
    return result


def state(asset):
    return asset.get("attributes", {}).get("assetDeliveryState", {}).get("state", "UNKNOWN")


def plan(entries, existing, journal):
    wanted = {entry["name"]: entry for entry in entries}
    if len(wanted) != len(entries):
        raise RuntimeError("Duplicate names in the desired screenshot manifest.")
    matched = {}
    for asset in existing:
        attributes = asset.get("attributes", {})
        name = attributes.get("fileName")
        entry = wanted.get(name)
        if entry is None or name in matched or attributes.get("fileSize") != entry["size"]:
            raise RuntimeError("Existing screenshot differs from the verified manifest; nothing will be overwritten or deleted.")
        checksum = attributes.get("sourceFileChecksum")
        if checksum is not None and checksum.lower() != entry["checksum"]:
            raise RuntimeError("Existing screenshot checksum differs; refusing a replacement.")
        if state(asset) != "COMPLETE":
            if journal.get(asset["id"]) != entry["checksum"]:
                raise RuntimeError("Unfinished screenshot is not an upload owned by this script; refusing to change it.")
            if state(asset) == "FAILED":
                raise RuntimeError("An owned screenshot failed Apple processing; no asset has been deleted. Inspect Apple first.")
        elif checksum is None:
            raise RuntimeError("Cannot confirm an existing screenshot checksum; refusing to change it.")
        matched[name] = asset
    return matched


def purchase_marketing_sources(config):
    """Resolve removable fingerprints exclusively from retained review originals."""
    result = {}
    for display, directory, expected, _ in config["sets"]:
        if directory not in PURCHASE_MARKETING_DIRECTORIES:
            continue
        originals = {}
        for name in PURCHASE_MARKETING_FILES:
            source = SCREENSHOTS / "review" / directory / name
            data = source.read_bytes()
            if image_dimensions(data) != expected:
                raise RuntimeError("Retained purchase original has unexpected screenshot dimensions.")
            originals[name] = {"path": source, "name": name, "size": len(data),
                               "checksum": hashlib.md5(data).hexdigest()}
        result[display] = originals
    return result


def marketing_plan(entries, existing, journal, removable=None):
    """Separate only exact known purchase originals; protect every other asset."""
    removable = removable or {}
    if {entry["name"] for entry in entries} & set(removable):
        raise RuntimeError("Move purchase screenshots out of the marketing manifest before removal.")
    remaining, stale, names, identifiers = [], [], set(), set()
    for asset in existing:
        identifier = asset["id"]
        if identifier in identifiers:
            raise RuntimeError("Duplicate remote screenshot IDs; refusing ambiguous changes.")
        identifiers.add(identifier)
        attrs = asset.get("attributes", {})
        name = attrs.get("fileName")
        original = removable.get(name)
        if original is None:
            remaining.append(asset)
            continue
        checksum = attrs.get("sourceFileChecksum")
        if (name in names or attrs.get("fileSize") != original["size"]
                or not isinstance(checksum, str) or checksum.lower() != original["checksum"]
                or state(asset) != "COMPLETE"):
            raise RuntimeError("Purchase marketing asset does not exactly match its retained original; refusing removal.")
        names.add(name)
        stale.append(asset)
    matched = plan(entries, remaining, journal)
    if len(entries) + len(stale) > 10:
        raise RuntimeError("Upload-before-removal would exceed Apple's 10 screenshots per display.")
    return matched, stale


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upload_parts(asset, entry):
    operations = asset.get("attributes", {}).get("uploadOperations") or []
    if not operations:
        raise RuntimeError("Apple returned no upload operations for the reserved screenshot.")
    ranges = []
    for operation in operations:
        url = urllib.parse.urlsplit(operation.get("url", ""))
        offset, length = operation.get("offset"), operation.get("length")
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment or not url.hostname.endswith(".apple.com"):
            raise RuntimeError("Refusing an upload destination outside Apple's HTTPS asset hosts.")
        if operation.get("method") != "PUT" or not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length <= 0 or offset + length > entry["size"]:
            raise RuntimeError("Apple returned an invalid screenshot upload byte range.")
        ranges.append((offset, offset + length))
    boundary = 0
    for start, end in sorted(ranges):
        if start != boundary:
            raise RuntimeError("Screenshot upload ranges do not cover the entire file exactly once.")
        boundary = end
    if boundary != entry["size"]:
        raise RuntimeError("Screenshot upload ranges are incomplete.")
    opener = urllib.request.build_opener(NoRedirect())
    with entry["path"].open("rb") as source:
        for operation in operations:
            source.seek(operation["offset"])
            body = source.read(operation["length"])
            headers = {header["name"]: header["value"] for header in operation.get("requestHeaders", [])}
            # Use only Apple's reservation headers. Never attach the ASC JWT.
            request = urllib.request.Request(operation["url"], data=body, headers=headers, method="PUT")
            try:
                with opener.open(request, timeout=60) as response:
                    if not 200 <= response.status < 300:
                        raise RuntimeError("Screenshot part upload did not succeed.")
            except urllib.error.HTTPError as error:
                raise RuntimeError(f"Screenshot part upload failed (HTTP {error.code}); signed URL omitted.") from None
            except urllib.error.URLError:
                raise RuntimeError("Screenshot part upload connection failed; signed URL omitted.") from None


def save_journal(path, journal):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(journal, indent=2) + "\n")
    temporary.replace(path)


def wait_complete(client, identifier, timeout, expected_checksum, resource="appScreenshots"):
    deadline = time.monotonic() + timeout
    while True:
        asset = client.request("GET", f"/v1/{resource}/{identifier}", params={f"fields[{resource}]": "fileName,fileSize,sourceFileChecksum,assetDeliveryState,imageAsset"})["data"]
        current = state(asset)
        checksum = asset.get("attributes", {}).get("sourceFileChecksum")
        if current == "COMPLETE" and checksum:
            if checksum.lower() != expected_checksum:
                raise RuntimeError("Apple's completed screenshot checksum does not match the source.")
            return asset
        if current == "FAILED":
            codes = [str(error.get("code", "unknown")) for error in asset.get("attributes", {}).get("assetDeliveryState", {}).get("errors", [])]
            raise RuntimeError("Apple screenshot processing failed: " + ", ".join(codes))
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Screenshot processing is still {current}; rerun --status or --apply later. No asset was deleted.")
        time.sleep(3)


def run_platform(client, platform, apply, journal, journal_path, timeout, remove_purchase_marketing=False):
    config = CONFIG[platform]
    entries_by_display = manifest(config)
    removable_by_display = purchase_marketing_sources(config) if remove_purchase_marketing else {}
    version = validate_draft(client, config)
    sets = inventory(client, config)
    # Preflight every display before reserving any asset.
    for display, entries in entries_by_display.items():
        marketing_plan(entries, sets.get(display, {}).get("assets", []), journal,
                       removable_by_display.get(display))
    report = {"platform": platform, "app": config["app"], "version": version, "locale": "de-DE",
              "writesEnabled": apply, "removePurchaseMarketing": remove_purchase_marketing, "sets": []}
    prepared = []
    for display, entries in entries_by_display.items():
        current = sets.get(display)
        if current is None and apply:
            created = client.write("POST", "appScreenshotSets", {"screenshotDisplayType": display}, {"appStoreVersionLocalization": relation("appStoreVersionLocalizations", config["localization"])})
            current = {"id": created["id"], "assets": []}
        existing = current["assets"] if current else []
        matched, stale = marketing_plan(entries, existing, journal, removable_by_display.get(display))
        prepared.append({"display": display, "entries": entries, "current": current,
                         "existingCount": len(existing), "matched": matched, "stale": stale})
        if apply:
            # Commit all displays sequentially before waiting. Apple can process
            # these uploads concurrently; no old asset or order changes here.
            for entry in entries:
                asset = matched.get(entry["name"])
                if asset is None:
                    asset = client.write("POST", "appScreenshots", {"fileName": entry["name"], "fileSize": entry["size"]}, {"appScreenshotSet": relation("appScreenshotSets", current["id"])})
                    journal[asset["id"]] = entry["checksum"]
                    save_journal(journal_path, journal)
                if state(asset) == "AWAITING_UPLOAD":
                    upload_parts(asset, entry)
                    asset = client.write("PATCH", "appScreenshots", {"uploaded": True, "sourceFileChecksum": entry["checksum"]}, identifier=asset["id"])
                matched[entry["name"]] = asset
    if apply:
        # A failure/timeout anywhere preserves every old purchase asset and all
        # ordering. Already committed reservations remain resumable in journal.
        for item in prepared:
            for entry in item["entries"]:
                asset = item["matched"][entry["name"]]
                asset = wait_complete(client, asset["id"], timeout, entry["checksum"])
                item["matched"][entry["name"]] = asset
                print(f"{platform} {item['display']} {entry['name']}: COMPLETE", flush=True)
        # Freshly verify ALL displays before the first deletion or reordering.
        for item in prepared:
            latest = client.rows(f"/v1/appScreenshotSets/{item['current']['id']}/appScreenshots", params={"limit": 200})
            final, verified_stale = marketing_plan(item["entries"], latest, journal,
                                                   removable_by_display.get(item["display"]))
            if (len(final) != len(item["entries"]) or any(state(asset) != "COMPLETE" for asset in final.values())
                    or {asset["id"] for asset in verified_stale} != {asset["id"] for asset in item["stale"]}):
                raise RuntimeError("Screenshot set changed during upload; refusing removal/reordering.")
            item.update(latest=latest, final=final, verifiedStale=verified_stale)
        validate_draft(client, config)
    for item in prepared:
        display, entries, current = item["display"], item["entries"], item["current"]
        stale, matched = item["stale"], item["matched"]
        removed = []
        count_after = item["existingCount"]
        order_verified = False
        if apply:
            latest, final = item["latest"], item["final"]
            for old in item["verifiedStale"]:
                # Subscription review assets are a separate resource and never
                # appear in this exact-known-marketing-only operation.
                client.request("DELETE", f"/v1/appScreenshots/{old['id']}")
                removed.append(old["id"])
            if item["verifiedStale"]:
                latest = client.rows(f"/v1/appScreenshotSets/{current['id']}/appScreenshots", params={"limit": 200})
                final = plan(entries, latest, journal)
                if len(final) != len(entries):
                    raise RuntimeError("Post-removal screenshot inventory differs from desired manifest.")
            desired = [final[entry["name"]]["id"] for entry in entries]
            if [asset["id"] for asset in latest] != desired:
                client.request("PATCH", f"/v1/appScreenshotSets/{current['id']}/relationships/appScreenshots", {"data": [{"type": "appScreenshots", "id": identifier} for identifier in desired]})
            readback = client.rows(f"/v1/appScreenshotSets/{current['id']}/appScreenshots", params={"limit": 200})
            checked = plan(entries, readback, journal)
            if ([asset["id"] for asset in readback] != desired or len(checked) != len(entries)
                    or any(state(asset) != "COMPLETE" for asset in checked.values())):
                raise RuntimeError("Final screenshot order/content readback differs from the verified manifest.")
            count_after = len(readback)
            order_verified = True
        rows = [{"file": entry["name"], "id": matched[entry["name"]]["id"] if entry["name"] in matched else None,
                 "state": state(matched[entry["name"]]) if entry["name"] in matched else "NOT_UPLOADED",
                 "checksumMatches": bool(entry["name"] in matched and matched[entry["name"]].get("attributes", {}).get("sourceFileChecksum", "") == entry["checksum"])}
                for entry in entries]
        report["sets"].append({"display": display, "id": current["id"] if current else None,
                              "inventoryCountBefore": item["existingCount"], "desiredCount": len(entries),
                              "inventoryCountAfter": count_after, "orderVerified": order_verified,
                              "temporaryCount": len(entries) + len(stale),
                              "plannedPurchaseRemovals": [{"id": asset["id"], "file": asset["attributes"]["fileName"],
                                                           "checksum": asset["attributes"]["sourceFileChecksum"]} for asset in stale],
                              "removedPurchaseIds": removed, "screenshots": rows})
    return report


def run_review(client, platform, apply, journal, journal_path, timeout, overrides):
    config = CONFIG[platform]
    if not config["reviews"]:
        return {"platform": platform, "app": config["app"], "writesEnabled": False,
                "reviewScreenshots": [], "sharedReviewAssetsPlatform": "ios"}
    version_id = validate_draft(client, config)
    resource = "subscriptionAppStoreReviewScreenshots"
    prepared = []
    for option, subscription, version, product, relative in config["reviews"]:
        sub = client.request("GET", f"/v1/subscriptions/{subscription}")["data"]
        draft = client.request("GET", f"/v1/subscriptionVersions/{version}")["data"]
        if sub["attributes"].get("productId") != product or draft["attributes"].get("state") not in {"PREPARE_FOR_SUBMISSION", "READY_FOR_REVIEW"}:
            raise RuntimeError("Refusing a review screenshot for an unexpected product or non-editable subscription version.")
        versions = client.rows(f"/v1/subscriptions/{subscription}/versions", params={"limit": 200})
        if not any(row["id"] == version for row in versions):
            raise RuntimeError("Subscription version does not belong to the expected product.")
        try:
            existing = client.request("GET", f"/v1/subscriptions/{subscription}/appStoreReviewScreenshot").get("data")
        except APIError as error:
            if error.status != 404:
                raise
            existing = None
        source = overrides.get(option) if platform == "macos" else None
        source = source or SCREENSHOTS / relative
        entry = None
        if source.exists():
            data = source.read_bytes()
            width, height = image_dimensions(data)
            if width < 640 or height < 640:
                raise RuntimeError("Review screenshot is too small; use a genuine full-size app capture.")
            entry = {"path": source, "name": source.name, "size": len(data), "checksum": hashlib.md5(data).hexdigest()}
            # The subscription relationship returns Apple's canonical SOURCE
            # label after processing. Preserve that completed asset only when
            # its exact size and returned checksum match the original file.
            if existing:
                attributes = existing.get("attributes", {})
                if (attributes.get("fileName") == "SOURCE"
                        and attributes.get("fileSize") == entry["size"]
                        and attributes.get("sourceFileChecksum") == entry["checksum"]
                        and state(existing) == "COMPLETE"):
                    existing = {**existing, "attributes": {**attributes, "fileName": entry["name"]}}
            plan([entry], [existing] if existing else [], journal)
        elif apply:
            raise RuntimeError(f"Missing genuine {platform} {option} review screenshot: {source}")
        if apply and draft["attributes"].get("state") != "PREPARE_FOR_SUBMISSION" and (not existing or state(existing) != "COMPLETE"):
            raise RuntimeError("Refusing to create or change a review asset on a review-ready subscription version.")
        prepared.append((option, subscription, product, entry, existing))
    rows = []
    for option, subscription, product, entry, asset in prepared:
        if apply:
            if asset is None:
                asset = client.write("POST", resource, {"fileName": entry["name"], "fileSize": entry["size"]}, {"subscription": relation("subscriptions", subscription)})
                journal[asset["id"]] = entry["checksum"]
                save_journal(journal_path, journal)
            if state(asset) == "AWAITING_UPLOAD":
                upload_parts(asset, entry)
                asset = client.write("PATCH", resource, {"uploaded": True, "sourceFileChecksum": entry["checksum"]}, identifier=asset["id"])
            asset = wait_complete(client, asset["id"], timeout, entry["checksum"], resource)
            print(f"{platform} {product} App Review screenshot: COMPLETE", flush=True)
        sub = client.request("GET", f"/v1/subscriptions/{subscription}")["data"]
        rows.append({"productId": product, "subscriptionId": subscription, "productState": sub["attributes"].get("state"), "sourceExists": entry is not None, "file": entry["name"] if entry else None, "reviewScreenshotId": asset["id"] if asset else None, "state": state(asset) if asset else "NOT_UPLOADED", "checksumMatches": bool(entry and asset and asset.get("attributes", {}).get("sourceFileChecksum") == entry["checksum"])})
    return {"platform": platform, "app": config["app"], "version": version_id, "writesEnabled": apply, "reviewScreenshots": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["ios", "macos", "all"], default="all")
    parser.add_argument("--kind", choices=["marketing", "review"], default="marketing")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Read-only inventory (default).")
    mode.add_argument("--apply", action="store_true", help="Upload/reorder matching screenshots on draft versions only.")
    parser.add_argument("--processing-timeout", type=int, default=180)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--remove-purchase-marketing", action="store_true",
                        help="Plan removal of exact retained mobile purchase marketing originals; requires --apply to write.")
    parser.add_argument("--mac-annual-review", type=Path)
    parser.add_argument("--mac-supporter-review", type=Path)
    args = parser.parse_args()
    if args.mac_annual_review or args.mac_supporter_review:
        parser.error("Universal purchase reuses the two iOS product review assets; separate Mac review overrides are disabled.")
    if args.remove_purchase_marketing and args.kind != "marketing":
        parser.error("--remove-purchase-marketing is restricted to marketing screenshot sets")
    if args.processing_timeout < 1 or args.processing_timeout > 600:
        parser.error("processing timeout must be between 1 and 600 seconds")
    try:
        journal_path = args.journal or ROOT / f"artifacts/app-store/{args.kind}-screenshot-upload-state.json"
        # Preserve reservations from the initial marketing upload invocation.
        if args.kind == "marketing" and args.journal is None:
            journal_path = ROOT / "artifacts/app-store/screenshot-upload-state.json"
        journal = json.loads(journal_path.read_text()) if journal_path.exists() else {}
        client = ASCClient(allow_writes=args.apply)
        platforms = list(CONFIG) if args.platform == "all" else [args.platform]
        if args.kind == "review":
            overrides = {"annual": args.mac_annual_review, "supporter": args.mac_supporter_review}
            reports = [run_review(client, platform, args.apply, journal, journal_path, args.processing_timeout, overrides) for platform in platforms]
        else:
            reports = [run_platform(client, platform, args.apply, journal, journal_path,
                                    args.processing_timeout, args.remove_purchase_marketing) for platform in platforms]
        print(json.dumps({"reports": reports}, indent=2), flush=True)
    except (RuntimeError, APIError, OSError, ValueError, KeyError) as error:
        print(f"Screenshot upload stopped: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
