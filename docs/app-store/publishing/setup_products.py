#!/usr/bin/env python3
"""Inspect or configure GA draft subscriptions; never submits/publishes an app.

Uses Apple OpenAPI 4.5.1 subscription/group versions, v2 localizations and
UPFRONT plan availability. Defaults to read-only. --apply explicitly enables
draft creation/localization; existing conflicting prices/offers are never removed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from asc_client import ASCClient, relation
from app_config import APP_ID, BUNDLE_ID, GROUP_ID, PRODUCT_IDS

METADATA = Path(__file__).resolve().parents[1] / "metadata.de-DE.json"
BUNDLES = {"ios": BUNDLE_ID, "macos": BUNDLE_ID}
GROUP = "GA-App-Zugang"


def draft_version(client, parent_type, parent_id, version_type, apply):
    versions = client.rows(f"/v1/{parent_type}/{parent_id}/versions", {"limit": 200})
    drafts = [v for v in versions if v.get("attributes", {}).get("state") in {"PREPARE_FOR_SUBMISSION", "READY_FOR_REVIEW"}]
    if drafts:
        return max(drafts, key=lambda v: v["attributes"].get("version", 0))
    if not apply:
        return None
    if versions:
        raise RuntimeError(f"{parent_type} {parent_id} has no editable PREPARE_FOR_SUBMISSION version. Create/reopen an editable draft in Apple first; current versions are preserved.")
    rel_name = "subscriptionGroup" if parent_type == "subscriptionGroups" else "subscription"
    return client.write("POST", version_type, relationships={rel_name: relation(parent_type, parent_id)})


def localize(client, version, version_type, resource, attrs):
    existing = next((r for r in client.rows(f"/v1/{version_type}/{version['id']}/localizations", {"limit": 200}) if r["attributes"]["locale"] == "de-DE"), None)
    if existing:
        if all(existing["attributes"].get(k) == v for k, v in attrs.items()):
            return existing
        if version.get("attributes", {}).get("state") != "PREPARE_FOR_SUBMISSION":
            raise RuntimeError("Review-ready localization differs; preserve it and reopen an editable version deliberately.")
        return client.write("PATCH", resource, attrs, identifier=existing["id"], version="v2")
    if version.get("attributes", {}).get("state") != "PREPARE_FOR_SUBMISSION":
        raise RuntimeError("Cannot add localization to a review-ready version.")
    return client.write("POST", resource, {"locale": "de-DE", **attrs}, {"version": relation(version_type, version["id"])}, version="v2")


def price_point(client, subscription_id, price, territory):
    points = client.rows(f"/v1/subscriptions/{subscription_id}/pricePoints", {"filter[territory]": territory, "limit": 200})
    match = next((p for p in points if Decimal(p["attributes"]["customerPrice"]) == Decimal(price)), None)
    if not match:
        nearest = sorted({p["attributes"]["customerPrice"] for p in points}, key=lambda p: abs(Decimal(p) - Decimal(price)))[:6]
        raise RuntimeError(f"Exact price {price} EUR is not an Apple price point for {territory}. Nearby points: {', '.join(nearest)}. No substitute was selected; use --annual-price/--supporter-price only after the price decision.")
    return match


def current_prices(client, sid, territory):
    prices, included = client.collection(f"/v1/subscriptions/{sid}/prices", {"filter[territory]": territory, "filter[planType]": "UPFRONT", "include": "subscriptionPricePoint,territory", "limit": 200})
    result = []
    for price in prices:
        attrs = price.get("attributes", {})
        ref = price.get("relationships", {}).get("subscriptionPricePoint", {}).get("data", {})
        point = included.get(("subscriptionPricePoints", ref.get("id")))
        if point is None and ref.get("id"):
            point = client.request("GET", f"/v1/subscriptionPricePoints/{ref['id']}")["data"]
        result.append({"id": price["id"], "startDate": attrs.get("startDate"), "customerPrice": point.get("attributes", {}).get("customerPrice") if point else None})
    return result


def setup_price(client, sid, target, territory):
    point = price_point(client, sid, target, territory)
    existing = current_prices(client, sid, territory)
    if existing:
        if any(p["customerPrice"] is None or Decimal(p["customerPrice"]) != Decimal(target) for p in existing):
            raise RuntimeError(f"Subscription {sid} has a conflicting/unknown existing price schedule: {existing}. Preserved; change it deliberately in Apple.")
        return existing
    client.write("POST", "subscriptionPrices", {"startDate": None, "planType": "UPFRONT"}, {"subscription": relation("subscriptions", sid), "subscriptionPricePoint": relation("subscriptionPricePoints", point["id"]), "territory": relation("territories", territory)})
    return current_prices(client, sid, territory)


def setup_availability(client, sid, territory):
    plans = client.rows(f"/v1/subscriptions/{sid}/planAvailabilities", {"include": "availableTerritories", "limit": 200})
    plan = next((p for p in plans if p.get("attributes", {}).get("planType") == "UPFRONT"), None)
    if plan:
        regions = client.rows(f"/v1/subscriptionPlanAvailabilities/{plan['id']}/availableTerritories", {"limit": 200})
        if territory not in {r["id"] for r in regions}:
            raise RuntimeError(f"Existing plan {plan['id']} does not include {territory}; preserved. Set territories deliberately in Apple.")
        return plan
    return client.write("POST", "subscriptionPlanAvailabilities", {"planType": "UPFRONT", "availableInNewTerritories": False}, {"subscription": relation("subscriptions", sid), "availableTerritories": {"data": [{"type": "territories", "id": territory}]}})


def setup_intro(client, sid, territory):
    today = dt.date.today().isoformat()
    offers = client.rows(f"/v1/subscriptions/{sid}/introductoryOffers", {"filter[territory]": territory, "limit": 200})
    upcoming_or_active = [o for o in offers if not o["attributes"].get("endDate") or o["attributes"]["endDate"] >= today]
    for offer in upcoming_or_active:
        a = offer["attributes"]
        if a.get("offerMode") == "FREE_TRIAL" and a.get("duration") == "THREE_MONTHS" and a.get("numberOfPeriods") == 1 and (not a.get("startDate") or a["startDate"] <= today):
            return offer
    if upcoming_or_active:
        raise RuntimeError(f"Subscription {sid} has an existing conflicting/future introductory offer; preserved. Resolve its schedule in Apple.")
    return client.write("POST", "subscriptionIntroductoryOffers", {"duration": "THREE_MONTHS", "offerMode": "FREE_TRIAL", "numberOfPeriods": 1, "startDate": today, "targetSubscriptionPlanType": "UPFRONT"}, {"subscription": relation("subscriptions", sid), "territory": relation("territories", territory)})


def run(args):
    client = ASCClient(allow_writes=args.apply)
    bundle = BUNDLES[args.platform]
    if args.app_id:
        app = client.request("GET", f"/v1/apps/{args.app_id}")["data"]
        if app["attributes"]["bundleId"] != bundle:
            raise RuntimeError("The selected App Store record belongs to a different bundle ID; no changes made.")
    else:
        apps = client.rows("/v1/apps", {"filter[bundleId]": bundle, "limit": 200})
        if not apps:
            print(json.dumps({"platform": args.platform, "bundleId": bundle, "appRecord": "missing", "nextStep": "Create the draft app in App Store Connect. The public API cannot create app records.", "writesEnabled": args.apply}, indent=2))
            return 2
        if len(apps) != 1:
            raise RuntimeError("More than one matching Apple app record; pass an explicit --app-id.")
        app = apps[0]
    app_id = app["id"]
    if app_id != APP_ID:
        raise RuntimeError("Expected the shared universal-purchase app record; legacy Mac setup is disabled.")
    metadata = json.loads(METADATA.read_text())
    platform = "iOS" if args.platform == "ios" else "macOS"
    products = [p for p in metadata["subscriptions"] if platform in p.get("platforms", [])]
    if len(products) != 2 or {p["product_id"] for p in products} != set(PRODUCT_IDS):
        raise RuntimeError("Expected exactly two shared products for both platforms; duplicate platform products are refused.")
    groups = client.rows(f"/v1/apps/{app_id}/subscriptionGroups", {"limit": 200})
    matching = [g for g in groups if g["attributes"].get("referenceName") == GROUP]
    if len(matching) > 1:
        raise RuntimeError("Ambiguous duplicate GA subscription groups; no group was selected.")
    group = matching[0] if matching else None
    if group and group["id"] != GROUP_ID:
        raise RuntimeError("Unexpected subscription group; preserve it rather than selecting another one.")
    if not group and args.apply:
        if groups:
            raise RuntimeError("App already has a different subscription group; preserve it and resolve grouping before setup.")
        group = client.write("POST", "subscriptionGroups", {"referenceName": GROUP}, {"app": relation("apps", app_id)})
    report = {"appId": app_id, "bundleId": bundle, "requestedPlatform": platform,
              "sharedPlatforms": ["iOS", "macOS"], "writesEnabled": args.apply,
              "territory": args.territory, "groupId": group["id"] if group else None, "products": []}
    if not group:
        report["nextStep"] = "Run --apply to create GA-App-Zugang after reviewing the draft record."
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.apply:
        gv = draft_version(client, "subscriptionGroups", group["id"], "subscriptionGroupVersions", True)
        localize(client, gv, "subscriptionGroupVersions", "subscriptionGroupLocalizations", {"name": GROUP})
    subscriptions = client.rows(f"/v1/subscriptionGroups/{group['id']}/subscriptions", {"limit": 200})
    for product in products:
        sid = product["product_id"]
        sub = next((s for s in subscriptions if s["attributes"].get("productId") == sid), None)
        target = args.supporter_price if sid.endswith(".supporter") else args.annual_price
        if not sub and args.apply:
            sub = client.write("POST", "subscriptions", {"name": product["reference_name"], "productId": sid, "subscriptionPeriod": "ONE_YEAR", "groupLevel": 1, "reviewNote": "One year of GA app reading access. Annual and supporter products provide identical features. Eligible accounts: three-month Apple free introductory trial, then selected annual price. Separate free-year request is not an IAP and never converts to payment."}, {"group": relation("subscriptionGroups", group["id"])})
        if not sub:
            report["products"].append({"productId": sid, "state": "missing", "targetPrice": target})
            continue
        attrs = sub["attributes"]
        if attrs.get("subscriptionPeriod") != "ONE_YEAR" or attrs.get("groupLevel") != 1:
            raise RuntimeError(f"{sid} has a different period/group level; preserved. Resolve this before setup.")
        if args.apply:
            sv = draft_version(client, "subscriptions", sub["id"], "subscriptionVersions", True)
            localize(client, sv, "subscriptionVersions", "subscriptionLocalizations", {"name": product["display_name"], "description": product["description"]})
            # Resolve the exact point before making availability or intro changes.
            price_point(client, sub["id"], target, args.territory)
            setup_availability(client, sub["id"], args.territory)
            setup_price(client, sub["id"], target, args.territory)
            setup_intro(client, sub["id"], args.territory)
        versions = client.rows(f"/v1/subscriptions/{sub['id']}/versions", {"limit": 200})
        report["products"].append({"productId": sid, "subscriptionId": sub["id"], "period": attrs.get("subscriptionPeriod"), "groupLevel": attrs.get("groupLevel"), "versions": [{"id": v["id"], **v.get("attributes", {})} for v in versions], "prices": current_prices(client, sub["id"], args.territory), "introductoryOffers": [{"id": o["id"], **o["attributes"]} for o in client.rows(f"/v1/subscriptions/{sub['id']}/introductoryOffers", {"filter[territory]": args.territory, "limit": 200})]})
    report["remaining"] = "Review screenshots, app metadata, agreements, sandbox validation, signed build and review submission remain separate. No review submission or app publication was performed."
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=BUNDLES, required=True)
    parser.add_argument("--app-id")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Read-only inspection (default).")
    mode.add_argument("--apply", action="store_true", help="Create/configure editable draft resources; does not submit.")
    parser.add_argument("--territory", default="DEU")
    parser.add_argument("--annual-price", default="30.00")
    parser.add_argument("--supporter-price", default="90.00")
    args = parser.parse_args()
    for price in (args.annual_price, args.supporter_price):
        if Decimal(price) <= 0:
            parser.error("Subscription prices must be positive.")
    try:
        return run(args)
    except RuntimeError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
