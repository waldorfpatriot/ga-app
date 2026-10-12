#!/usr/bin/env python3
"""Summarize existing author setup evidence without changing provider state."""
import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]


def read(relative, default=None):
    path=ROOT/relative
    return json.loads(path.read_text()) if path.exists() else default


def by_slug(value):
    if isinstance(value,dict):
        value=value.get("authors",[])
    return {item["slug"]:item for item in value or []}


def main():
    authors=read("editions/authors.json")["authors"]
    provisioning=by_slug(read("editions/apple-provisioning-state.json",{}))
    cloudkit=by_slug(read("editions/cloudkit-readback-verification.json",{}))
    rc_setup=by_slug(read("editions/revenuecat-setup-state.json",[]))
    rc_public=by_slug(read("editions/revenuecat-public-verification.json",{}))
    backend_report=read("editions/backend-deployment-verification.json",{})
    backend=by_slug(backend_report)
    live=by_slug(backend_report.get("last_health_recheck",[]))
    baseline=read("editions/ga-baseline.json",{})
    mismatches=[name for name,digest in baseline.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    rows=[]
    for author in authors:
        slug=author["slug"]
        expected_products={author["bundle_id"]+".annual",author["bundle_id"]+".supporter"}
        apple_path=f"editions/{slug}/app-store/apple-setup-state.json"
        apple=read(apple_path,{})
        products=apple.get("subscriptions",{}).get("products",[])
        platform_metadata=apple.get("platformMetadata",[])
        metadata_ok={row.get("platform") for row in platform_metadata if row.get("verified") and row.get("bundleId")==author["bundle_id"]}=={"IOS","MAC_OS"}
        apple_prices={product["productId"]:[float(price["customerPrice"]) for price in product.get("prices",[]) if price.get("startDate") is None] for product in products}
        prices_ok=30.0 in apple_prices.get(author["bundle_id"]+".annual",[]) and 90.0 in apple_prices.get(author["bundle_id"]+".supporter",[])
        trials_ok=len(products)==2 and all(any(offer.get("attributes",{}).get("offerMode")=="FREE_TRIAL" and offer.get("attributes",{}).get("duration")=="THREE_MONTHS" for offer in product.get("introductoryOffers",[])) for product in products)
        apple_ok=(apple.get("bundleId")==author["bundle_id"] and bool(apple.get("appId")) and provisioning.get(slug,{}).get("bundleRegistered") is True and metadata_ok and prices_ok and trials_ok and {row.get("productId") for row in products}==expected_products and apple.get("pricePrerequisitesMissing") is False)
        ck=cloudkit.get(slug,{})
        ck_ok=ck.get("verified") is True and ck.get("containerId")==author["cloudkit_container"] and ck.get("productionExportPresent") is True and ck.get("bothStoreProfilesVerified") is True
        management=rc_setup.get(slug,{})
        public=rc_public.get(slug,{})
        mapping_ok=management.get("productsImported") is True and management.get("entitlement")==author["entitlement_id"] and management.get("offering")=="default"
        rc_ok=public.get("status")=="verified" and set(public.get("productIds",[]))==expected_products and public.get("entitlementIdentifier")==author["entitlement_id"] and public.get("projectId")==management.get("projectId") and mapping_ok and public.get("localConfigurationWritten") is True and public.get("localConfigurationIgnored") is True
        deployed=backend.get(slug,{})
        current=live.get(slug,{})
        backend_ok=deployed.get("passed") is True and deployed.get("active_after_check") is True and current.get("health") is True and current.get("active") is True and current.get("backup_timer_active") is True
        rows.append({"slug":slug,"author_name":author["author_name"],
            "apple":{"verified":apple_ok,"app_id":apple.get("appId"),"ios_and_mac_draft_metadata_verified":metadata_ok,"own_annual_and_supporter_products":{row.get("productId") for row in products}==expected_products,"germany_prices_30_and_90_eur_verified":prices_ok,"three_month_introductory_trials_verified":trials_ok,"source":apple_path},
            "cloudkit":{"verified":ck_ok,"container_id":ck.get("containerId"),"production_schema_readback_verified":ck.get("verified") is True,"ios_and_mac_store_profiles_verified":ck.get("bothStoreProfilesVerified") is True,"source":"editions/cloudkit-readback-verification.json"},
            "revenuecat":{"verified":rc_ok,"project_id":management.get("projectId"),"management_setup_recorded":mapping_ok,"own_public_offering_verified":public.get("status")=="verified","public_configuration_written":public.get("localConfigurationWritten") is True,"source":"editions/revenuecat-public-verification.json"},
            "backend":{"verified":backend_ok,"access_url":author["access_base_url"],"reader_url":author["reader_base_url"],"end_to_end_checks_passed":deployed.get("passed") is True,"last_public_health_verified":current.get("health") is True,"source":"editions/backend-deployment-verification.json"},
            "requested_setup_evidence_complete":bool(apple_ok and ck_ok and rc_ok and backend_ok)})
    counts={name:sum(row[name]["verified"] for row in rows) for name in ["apple","cloudkit","revenuecat","backend"]}
    remaining=["Signed distribution build uploads and screenshots.","Real StoreKit purchase/restore and iCloud sync checks on signed devices.","App privacy, content-rights and age-rating declarations before review.","App Store review and publication."]
    status={"checked_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"author_count":len(rows),"verified_counts":counts,"requested_setup_evidence_complete":all(row["requested_setup_evidence_complete"] for row in rows),
        "ga":{"baseline_file_count":len(baseline),"local_files_unchanged":bool(baseline) and not mismatches,"live_process_and_protected_files_preserved":backend_report.get("ga_process_and_protected_files_rechecked") is True},
        "backend_latest_health_check_at":backend_report.get("last_health_recheck_at"),"backend_fleet_memory_bytes":backend_report.get("fleet_memory_bytes"),"backend_fleet_swap_bytes":backend_report.get("fleet_swap_bytes"),"host_available_memory_MiB":backend_report.get("host_memory_available_MiB"),
        "publication_performed":False,"release_verification_remaining":remaining,"authors":rows}
    (ROOT/"editions/setup-status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n")
    date=datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo("Europe/Berlin")).strftime("%d %B %Y, %H:%M %Z")
    lines=["# Author setup status", "",f"Evidence snapshot: {date}. Refresh with `python3 tools/summarize_author_setup.py` as setup progresses.","",
        f"Verified setup: Apple draft configuration {counts['apple']}/11, CloudKit production and store profiles {counts['cloudkit']}/11, RevenueCat {counts['revenuecat']}/11, live backends {counts['backend']}/11.","",
        "| Author | Apple drafts and products | CloudKit production | RevenueCat | Backend |","| --- | --- | --- | --- | --- |"]
    for row in rows:
        labels=["Verified" if row[key]["verified"] else "Pending" for key in ["apple","cloudkit","revenuecat","backend"]]
        lines.append("| "+row["author_name"]+" | "+" | ".join(labels)+" |")
    lines.extend(["",f"The original GA app's {len(baseline)} baseline files are {'unchanged' if not mismatches else 'NOT all unchanged'}. The live GA process, protected configuration and release are {'preserved' if status['ga']['live_process_and_protected_files_preserved'] else 'not yet verified'}. Backend verification is recorded at `{status['backend_latest_health_check_at']}`.","",
        "Each verified Apple draft has its own app record, iOS/Mac metadata, €30/€90 products and three-month introductory trials. CloudKit evidence covers the production schema and author-specific store profile entitlements; it does not establish real-device sync. RevenueCat verification covers the independent project, management entitlement mapping, public offering and ignored local SDK configuration; it does not establish a real Apple purchase.","",
        "All live backends have isolated databases/secrets and daily authenticated encrypted backups. Complete access-flow checks and catalog/page integrity results are in [the backend report](author-backend-deployment.md).", "",
        "Before App Store release:",""])
    lines.extend("- "+item for item in remaining)
    lines.extend(["","Detailed evidence: [setup JSON](../editions/setup-status.json), [Apple drafts](author-apple-setup.md), [CloudKit readback](../editions/cloudkit-readback-verification.json), [RevenueCat public verification](../editions/revenuecat-public-verification.json), [backend verification](../editions/backend-deployment-verification.json).",""])
    (ROOT/"docs/author-setup-status.md").write_text("\n".join(lines))
    print(json.dumps({"verified_counts":counts,"requested_setup_evidence_complete":status["requested_setup_evidence_complete"],"ga_files_unchanged":status["ga"]["local_files_unchanged"]}))


if __name__=="__main__":
    main()
