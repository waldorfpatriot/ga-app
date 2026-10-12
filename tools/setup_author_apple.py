#!/usr/bin/env python3
"""Inspect or configure allowlisted author Apple drafts, preserving Steiner GA.

Default is read-only. --apply creates/configures author subscription products and
editable iOS/macOS metadata only. It never uploads a build, selects a build,
submits review, changes privacy/content-rights attestations, or publishes.
Credentials are supplied through ASC_KEY_ID, ASC_KEY_PATH and ASC_ISSUER_ID.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "docs/app-store/publishing"))
from asc_client import ASCClient, APIError, relation
from upload_metadata import update_localization
from setup_author_products import run as setup_products
from complete_subscription_pricing import price_rows, verify_availability

PROTECTED_APP_IDS = {"6820947669", "6820968413"}
PROTECTED_BUNDLES = {"com.jonathankutscher.ga", "com.jonathankutscher.ga.mac"}
EDITABLE = {"PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED"}
PLATFORMS = {"ios": "IOS", "macos": "MAC_OS"}
RESOURCE_PARENTS = {
    "subscriptionGroups": "app",
    "subscriptionGroupVersions": "subscriptionGroup",
    "subscriptionGroupLocalizations": "version",
    "subscriptions": "group",
    "subscriptionVersions": "subscription",
    "subscriptionLocalizations": "version",
    "subscriptionPrices": "subscription",
    "subscriptionPlanAvailabilities": "subscription",
    "subscriptionIntroductoryOffers": "subscription",
    "appStoreVersions": "app",
    "appInfoLocalizations": "appInfo",
    "appStoreVersionLocalizations": "appStoreVersion",
    "appStoreReviewDetails": "appStoreVersion",
}
WRITABLE_TYPES = set(RESOURCE_PARENTS) | {"appInfos"}
RELATION_TYPES = {
    "app": {"apps"}, "subscriptionGroup": {"subscriptionGroups"},
    "group": {"subscriptionGroups"}, "subscription": {"subscriptions"},
    "version": {"subscriptionVersions", "subscriptionGroupVersions"},
    "appInfo": {"appInfos"}, "appStoreVersion": {"appStoreVersions"},
}
AUTHOR_LOCK_DIRECTORY = Path(tempfile.gettempdir()) / "ga-author-apple-setup-locks"


def serialize_author_writes(operation):
    """Keep one local provisioning writer per author, across resumable runs."""
    @functools.wraps(operation)
    def guarded(author, *args, **kwargs):
        if not kwargs.get("apply"):
            return operation(author, *args, **kwargs)
        import fcntl
        AUTHOR_LOCK_DIRECTORY.mkdir(parents=True, exist_ok=True)
        identifier = hashlib.sha256(author["bundle_id"].encode()).hexdigest()
        descriptor = os.open(AUTHOR_LOCK_DIRECTORY / (identifier + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                return operation(author, *args, **kwargs)
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    return guarded


def load_authors():
    manifest = json.loads((ROOT / "editions/authors.json").read_text())
    authors = manifest["authors"]
    bundles = [a["bundle_id"] for a in authors]
    if len(bundles) != len(set(bundles)) or any(b in PROTECTED_BUNDLES for b in bundles):
        raise RuntimeError("Author manifest contains duplicate or protected bundle identities.")
    if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", a["slug"]) for a in authors):
        raise RuntimeError("Invalid author slug.")
    return authors


class AuthorClient(ASCClient):
    """Only resources descended from the selected author app may be written."""

    def __init__(self, author, *, allow_writes=False):
        if author["bundle_id"] in PROTECTED_BUNDLES:
            raise RuntimeError("Steiner GA is excluded from author setup.")
        self.author = author
        self.owned = {}
        self._price_point_cache = {}
        super().__init__(allow_writes=allow_writes)

    def owns(self, resource, identifier):
        return bool(identifier) and identifier in self.owned.get(resource, set())

    def rows(self, path, params=None):
        parts = urlsplit(path).path.strip("/").split("/")
        # Price-point catalogues are immutable Apple choices. The two exact-price
        # checks reuse this catalogue, while schedules/offers/availability must
        # always be fetched again to verify the result of author mutations.
        cacheable = (len(parts) == 4 and parts[0:2] == ["v1", "subscriptions"]
                     and parts[3] == "pricePoints" and self.owns("subscriptions", parts[2]))
        if not cacheable:
            return super().rows(path, params)
        key = (path, json.dumps(params or {}, sort_keys=True))
        if key not in self._price_point_cache:
            self._price_point_cache[key] = super().rows(path, params)
        return copy.deepcopy(self._price_point_cache[key])

    def _remember(self, rows):
        rows = rows if isinstance(rows, list) else [rows] if rows else []
        for row in rows:
            resource, identifier = row.get("type"), row.get("id")
            if resource and identifier:
                if resource == "apps":
                    if (identifier in PROTECTED_APP_IDS
                            or row.get("attributes", {}).get("bundleId") != self.author["bundle_id"]):
                        raise RuntimeError("Apple returned an app outside this author's allowlist.")
                self.owned.setdefault(resource, set()).add(identifier)
                if resource == "subscriptionPrices":
                    point = row.get("relationships", {}).get("subscriptionPricePoint", {}).get("data", {})
                    if point.get("type") == "subscriptionPricePoints" and point.get("id"):
                        self.owned.setdefault("subscriptionPricePoints", set()).add(point["id"])

    def _write_allowed(self, method, path, body):
        parts = urlsplit(path).path.strip("/").split("/")
        if len(parts) not in (2, 3) or parts[0] not in {"v1", "v2"}:
            raise RuntimeError("Unsupported author mutation endpoint.")
        resource = parts[1]
        if resource not in WRITABLE_TYPES or method not in {"POST", "PATCH"}:
            raise RuntimeError("Only author draft configuration writes are allowed.")
        data = body.get("data", {}) if isinstance(body, dict) else {}
        if data.get("type") != resource:
            raise RuntimeError("Apple mutation resource type mismatch.")
        if method == "PATCH":
            if len(parts) != 3 or data.get("id") != parts[2] or not self.owns(resource, parts[2]):
                raise RuntimeError("Cannot modify a resource outside the selected author app.")
            parent_name = RESOURCE_PARENTS.get(resource)
            relationships = data.get("relationships", {})
            if parent_name in relationships:
                parent = relationships[parent_name].get("data", {})
                if (parent.get("type") not in RELATION_TYPES[parent_name]
                        or not self.owns(parent.get("type"), parent.get("id"))):
                    raise RuntimeError("Cannot move an author resource to an unrelated parent.")
        else:
            if len(parts) != 2 or resource not in RESOURCE_PARENTS:
                raise RuntimeError("Unsupported author resource creation.")
            parent_name = RESOURCE_PARENTS[resource]
            parent = data.get("relationships", {}).get(parent_name, {}).get("data", {})
            if (parent.get("type") not in RELATION_TYPES[parent_name]
                    or not self.owns(parent.get("type"), parent.get("id"))):
                raise RuntimeError("New resource must belong to the selected author app.")
        attributes = data.get("attributes", {})
        if resource == "subscriptions" and "productId" in attributes:
            expected = {self.author["bundle_id"] + ".annual", self.author["bundle_id"] + ".supporter"}
            if attributes["productId"] not in expected:
                raise RuntimeError("Subscription product is outside this author's allowlist.")
        if resource == "appStoreVersions" and any(k in attributes for k in ("releaseType",)):
            if attributes.get("releaseType") != "MANUAL":
                raise RuntimeError("Author app versions must retain manual release.")
        if any(k in attributes for k in ("contentRightsDeclaration", "appStoreState", "appVersionState")):
            raise RuntimeError("Legal attestations and submission state are outside this setup command.")
        if "build" in data.get("relationships", {}):
            raise RuntimeError("Build selection is outside this command.")
        if body.get("included"):
            self._price_graph_allowed(resource, data, body["included"])

    def _price_graph_allowed(self, resource, data, included):
        """Permit only additive price rows for the already verified subscription."""
        if resource != "subscriptions" or data.get("attributes") or set(data.get("relationships", {})) != {"prices"}:
            raise RuntimeError("Only an author subscription's additive price graph is allowed.")
        sid = data["id"]
        references = data["relationships"]["prices"].get("data", [])
        if len(references) != len(included) or not included:
            raise RuntimeError("Subscription price graph is incomplete.")
        expected = {r.get("id") for r in references if r.get("type") == "subscriptionPrices"}
        if len(expected) != len(included) or expected != {r.get("id") for r in included}:
            raise RuntimeError("Subscription price graph references differ.")
        for row in included:
            if row.get("type") != "subscriptionPrices" or not re.fullmatch(r"\$\{price-[A-Z]{3}\}", row.get("id", "")):
                raise RuntimeError("Only new additive price rows are permitted.")
            if row.get("attributes") != {"startDate": None, "planType": "UPFRONT"}:
                raise RuntimeError("Unexpected author subscription price attributes.")
            relations = row.get("relationships", {})
            if set(relations) != {"subscription", "subscriptionPricePoint", "territory"}:
                raise RuntimeError("Unexpected author price relationships.")
            if relations["subscription"] != relation("subscriptions", sid):
                raise RuntimeError("Inline price belongs to a different subscription.")
            point = relations["subscriptionPricePoint"].get("data", {})
            territory = relations["territory"].get("data", {})
            if point.get("type") != "subscriptionPricePoints" or not self.owns("subscriptionPricePoints", point.get("id")):
                raise RuntimeError("Price point was not obtained from Apple's author price mapping.")
            if territory.get("type") != "territories" or row["id"] != "${price-" + territory.get("id", "") + "}":
                raise RuntimeError("Inline author price territory mismatch.")

    def request(self, method, path, body=None, params=None):
        parsed = urlsplit(path)
        parts = parsed.path.strip("/").split("/")
        if method != "GET":
            self._write_allowed(method, path, body)
        result = super().request(method, path, body=body, params=params)
        # Register only resources reached through an already verified parent,
        # or the filtered app lookup. Global category/price-point GETs cannot
        # make an unrelated app, version or subscription writable.
        if method != "GET" or (len(parts) >= 3 and self.owns(parts[1], parts[2])):
            self._remember(result.get("data"))
            self._remember([r for r in result.get("included", []) if r.get("type") == "subscriptionPricePoints"])
        elif parts == ["v1", "apps"]:
            self._remember(result.get("data"))
        return result


def find_app(client, author, requested_id=None):
    apps = client.rows("/v1/apps", {"filter[bundleId]": author["bundle_id"], "limit": 200})
    if not apps:
        return None
    if len(apps) != 1:
        raise RuntimeError("Expected exactly one Apple app for " + author["slug"])
    app = apps[0]
    if requested_id and app["id"] != requested_id:
        raise RuntimeError("Requested app ID does not match the selected author's bundle.")
    if app["id"] in PROTECTED_APP_IDS or app["attributes"].get("bundleId") != author["bundle_id"]:
        raise RuntimeError("Steiner or another author's Apple record cannot be selected.")
    return app


def prepared_metadata(author):
    metadata = json.loads((ROOT / "editions" / author["slug"] / "app-store/metadata.de-DE.json").read_text())
    if metadata.get("bundle_id") != author["bundle_id"]:
        raise RuntimeError("Prepared metadata bundle differs from the author manifest.")
    for key, limit in {"name": 30, "subtitle": 30, "description": 4000, "keywords": 100, "promotional_text": 170}.items():
        value = metadata.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            raise RuntimeError("Prepared metadata exceeds Apple's field limit: " + key)
    if metadata["primary_category"] != "Books" or metadata["secondary_category"] != "Reference":
        raise RuntimeError("Expected Books / Reference author categories.")
    for key in ("privacy_policy_url", "support_url", "marketing_url"):
        if not metadata[key].startswith(author["access_base_url"] + "/"):
            raise RuntimeError("Prepared metadata URL is outside the selected author's app pages.")
    return metadata


def review_notes(author, metadata):
    return (f"This is an independent original-language reading edition of {author['author_name']}. "
            f"Its {metadata['starter_works']} complete starter texts are bundled for offline reading; "
            "this starter selection is not the author's complete collected works. Source and collation "
            "notes are shown with the works. Reading, search, annotations and EPUB export require active access.\n\n"
            "The annual and supporter subscriptions unlock identical features in this author app on "
            "iPhone, iPad and Mac. Their German annual prices are EUR 30 and EUR 90. Eligible Apple "
            "accounts receive a three-month introductory free trial, followed by the selected annual price.\n\n"
            "The separate free-year request is not an in-app purchase and never converts to payment. "
            "A short confidential request immediately grants twelve calendar months without an income "
            "check, login account or demo credentials. Apple purchases can be restored separately. "
            "Each author's subscriptions, access service and private CloudKit container are independent. "
            "No access in the Steiner GA app or another author app is required.")


def metadata_status(client, app, author, metadata, platform, version_string, apply):
    apple_platform = PLATFORMS[platform]
    infos = client.rows(f"/v1/apps/{app['id']}/appInfos", {"limit": 200})
    editable_infos = [r for r in infos if r["attributes"].get("state", r["attributes"].get("appStoreState")) in EDITABLE]
    versions = client.rows(f"/v1/apps/{app['id']}/appStoreVersions", {"filter[platform]": apple_platform, "limit": 200})
    matching = [r for r in versions if r["attributes"].get("versionString") == version_string]
    editable = [r for r in matching if r["attributes"].get("appVersionState", r["attributes"].get("appStoreState")) in EDITABLE]
    summary = {"platform": apple_platform, "appId": app["id"], "bundleId": author["bundle_id"],
               "versionString": version_string, "editableAppInfoIds": [r["id"] for r in editable_infos],
               "editableVersionIds": [r["id"] for r in editable], "applied": apply}
    if not apply:
        return summary
    if len(editable_infos) != 1 or len(editable) > 1 or (matching and not editable):
        raise RuntimeError("Expected unambiguous editable author metadata drafts; existing records preserved.")
    categories = client.rows("/v1/appCategories", {"filter[platforms]": apple_platform, "exists[parent]": "false", "limit": 200})
    if not {"BOOKS", "REFERENCE"} <= {r["id"] for r in categories}:
        raise RuntimeError("Books / Reference is unavailable for " + apple_platform)
    info = editable_infos[0]
    attributes = {"copyright": metadata["copyright"], "releaseType": "MANUAL"}
    if editable:
        version = client.write("PATCH", "appStoreVersions", attributes, identifier=editable[0]["id"])
    else:
        version = client.write("POST", "appStoreVersions", {"platform": apple_platform, "versionString": version_string, **attributes}, {"app": relation("apps", app["id"])})
    client.write("PATCH", "appInfos", relationships={"primaryCategory": relation("appCategories", "BOOKS"), "secondaryCategory": relation("appCategories", "REFERENCE")}, identifier=info["id"])
    info_attrs = {"name": metadata["name"], "subtitle": metadata["subtitle"], "privacyPolicyUrl": metadata["privacy_policy_url"]}
    version_attrs = {"description": metadata["description"], "keywords": metadata["keywords"], "supportUrl": metadata["support_url"], "marketingUrl": metadata["marketing_url"]}
    if "promotional_text" in metadata:
        version_attrs["promotionalText"] = metadata["promotional_text"]
    info_local = update_localization(client, "appInfoLocalizations", f"/v1/appInfos/{info['id']}/appInfoLocalizations", info_attrs, "appInfo", info["id"])
    version_local = update_localization(client, "appStoreVersionLocalizations", f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations", version_attrs, "appStoreVersion", version["id"])
    contact = metadata["review_contact"]
    review_attrs = {"contactFirstName": contact["first_name"], "contactLastName": contact["last_name"], "contactEmail": contact["email"], "contactPhone": contact["phone"], "demoAccountRequired": False, "notes": review_notes(author, metadata)}
    try:
        review = client.request("GET", f"/v1/appStoreVersions/{version['id']}/appStoreReviewDetail").get("data")
    except APIError as error:
        if error.status != 404:
            raise
        review = None
    if review:
        review = client.write("PATCH", "appStoreReviewDetails", review_attrs, identifier=review["id"])
    else:
        review = client.write("POST", "appStoreReviewDetails", review_attrs, {"appStoreVersion": relation("appStoreVersions", version["id"])})
    for resource, row, expected in (("appInfoLocalizations", info_local, info_attrs), ("appStoreVersionLocalizations", version_local, version_attrs), ("appStoreReviewDetails", review, review_attrs)):
        actual = client.request("GET", f"/v1/{resource}/{row['id']}")["data"]["attributes"]
        if any(actual.get(key) != value for key, value in expected.items()):
            raise RuntimeError("Author metadata readback differs: " + resource)
    verified_version = client.request("GET", f"/v1/appStoreVersions/{version['id']}")["data"]
    if verified_version["attributes"].get("releaseType") != "MANUAL":
        raise RuntimeError("Author version manual release readback failed.")
    summary.update(versionId=version["id"], appInfoLocalizationId=info_local["id"], versionLocalizationId=version_local["id"], reviewDetailId=review["id"], verified=True, releaseType="MANUAL")
    return summary


def complete_prices(client, subscription_id, apply):
    if not client.owns("subscriptions", subscription_id):
        raise RuntimeError("Price setup requires a verified author subscription.")
    before_availability = verify_availability(client, subscription_id)
    territories = {r["id"] for r in client.rows("/v1/territories", {"limit": 200})}
    existing = price_rows(client, subscription_id)
    bases = existing.get("DEU", [])
    if len(bases) != 1 or Decimal(bases[0]["price"]) not in {Decimal(30), Decimal(90)}:
        raise RuntimeError("Expected one exact German EUR 30/90 base price.")
    base = bases[0]
    equalizations = client.rows(f"/v1/subscriptionPricePoints/{base['pointId']}/equalizations", {"filter[planType]": "UPFRONT", "include": "territory", "limit": 8000})
    mapping = {r["relationships"]["territory"]["data"]["id"]: {"pointId": r["id"], "price": r["attributes"]["customerPrice"]} for r in equalizations}
    mapping["DEU"] = {"pointId": base["pointId"], "price": base["price"]}
    if set(mapping) != territories:
        raise RuntimeError("Apple's price equalizations do not cover all official territories.")
    for territory, schedules in existing.items():
        if territory not in mapping or any(Decimal(r["price"]) != Decimal(mapping[territory]["price"]) for r in schedules):
            raise RuntimeError("Existing conflicting author price preserved: " + territory)
    missing = sorted(territories - set(existing))
    if apply and missing:
        references, included = [], []
        for territory in missing:
            identifier = "${price-" + territory + "}"
            references.append({"type": "subscriptionPrices", "id": identifier})
            included.append({"type": "subscriptionPrices", "id": identifier, "attributes": {"startDate": None, "planType": "UPFRONT"},
                             "relationships": {"subscription": relation("subscriptions", subscription_id), "subscriptionPricePoint": relation("subscriptionPricePoints", mapping[territory]["pointId"]), "territory": relation("territories", territory)}})
        client.request("PATCH", f"/v1/subscriptions/{subscription_id}", {"data": {"type": "subscriptions", "id": subscription_id, "relationships": {"prices": {"data": references}}}, "included": included})
    final = price_rows(client, subscription_id)
    old_ids = {r["priceId"] for schedules in existing.values() for r in schedules}
    final_ids = {r["priceId"] for schedules in final.values() for r in schedules}
    availability = verify_availability(client, subscription_id)
    if old_ids - final_ids or availability != before_availability:
        raise RuntimeError("Existing price schedules or Germany-only availability changed.")
    if apply and (set(final) != territories or Decimal(final["DEU"][0]["price"]) != Decimal(base["price"])):
        raise RuntimeError("Author price coverage readback failed.")
    return {"subscriptionId": subscription_id, "baseTerritory": "DEU", "basePrice": base["price"], "territoryCount": len(territories),
            "missingBefore": missing, "coverageAfter": len(final), "missingAfter": sorted(territories - set(final)),
            "availability": availability, "existingPriceIdsPreserved": True, "applied": apply}


@serialize_author_writes
def run_author(author, *, apply, step, platforms, version_string, requested_id=None):
    metadata = prepared_metadata(author)
    client = AuthorClient(author, allow_writes=apply)
    app = find_app(client, author, requested_id)
    report = {"slug": author["slug"], "bundleId": author["bundle_id"], "writesEnabled": apply}
    if app is None:
        report.update(status="app_record_missing", nextStep="Create one Apple app record for this bundle, then rerun this command.")
        return report
    report["appId"] = app["id"]
    if step in {"products", "prices", "all"}:
        report["subscriptions"] = setup_products(author, client, apply and step != "prices")
    if step in {"prices", "all"}:
        products = report["subscriptions"]["products"]
        configured = [p for p in products if p.get("subscriptionId") and p.get("prices")]
        report["pricePrerequisitesMissing"] = len(configured) != 2
        if apply and report["pricePrerequisitesMissing"]:
            raise RuntimeError("Both author products and their German base prices are required before price setup.")
        report["requiredPrices"] = [complete_prices(client, p["subscriptionId"], apply) for p in configured]
    if step in {"metadata", "all"}:
        report["platformMetadata"] = [metadata_status(client, app, author, metadata, platform, version_string, apply) for platform in platforms]
    report["status"] = "author_draft_configuration_applied" if apply else "author_draft_status"
    report["remaining"] = "Signed builds, screenshots, CloudKit production schema, privacy/content-rights attestations, real purchase/sync checks and review remain separate. No review submission or publication performed."
    if step != "all":
        report["remaining"] = "Other setup steps (products, required prices or platform metadata) remain separate. " + report["remaining"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", action="append", help="Allowlisted slug; repeat, or omit for all eleven.")
    parser.add_argument("--app-id", help="Optional verified app ID for a single selected author.")
    parser.add_argument("--step", choices=("all", "products", "prices", "metadata"), default="all")
    parser.add_argument("--platform", choices=("both", "ios", "macos"), default="both")
    parser.add_argument("--version", default="1.0")
    parser.add_argument("--apply", action="store_true", help="Configure author drafts; default is GET-only.")
    parser.add_argument("--plan", action="store_true", help="Print the author-only plan without reading credentials or contacting Apple.")
    parser.add_argument("--report", type=Path, help="Save credential-free results to this local file.")
    args = parser.parse_args()
    try:
        available = load_authors()
        authors = [a for a in available if not args.author or a["slug"] in args.author]
        if not authors or (args.author and set(args.author) - {a["slug"] for a in authors}):
            parser.error("Unknown author slug.")
        if args.app_id and (len(authors) != 1 or args.app_id in PROTECTED_APP_IDS):
            parser.error("--app-id requires one author and cannot select a Steiner record.")
        if args.plan and args.apply:
            parser.error("--plan and --apply cannot be combined.")
        platforms = ["ios", "macos"] if args.platform == "both" else [args.platform]
        reports = []
        for author in authors:
            report = ({"slug": author["slug"], "bundleId": author["bundle_id"], "appName": author["app_name"], "step": args.step, "platforms": [PLATFORMS[p] for p in platforms], "writesEnabled": False, "products": [author["bundle_id"] + ".annual", author["bundle_id"] + ".supporter"], "releaseType": "MANUAL"}
                      if args.plan else run_author(author, apply=args.apply, step=args.step, platforms=platforms, version_string=args.version, requested_id=args.app_id))
            reports.append(report)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 2 if any(r.get("status") == "app_record_missing" for r in reports) else 0
    except (OSError, ValueError, RuntimeError, APIError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
