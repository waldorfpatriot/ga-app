#!/usr/bin/env python3
"""Complete Apple's required global pricing without expanding availability.

Read-only unless --apply. Uses only Apple's equalizations of an already configured
exact German price. Existing schedules are preserved and conflicts stop the run.
"""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from asc_client import ASCClient, relation


def price_rows(client, sid):
    rows, included = client.collection(f"/v1/subscriptions/{sid}/prices", {
        "filter[planType]": "UPFRONT", "include": "territory,subscriptionPricePoint", "limit": 200})
    result = {}
    for row in rows:
        territory = row["relationships"]["territory"]["data"]["id"]
        point_id = row["relationships"]["subscriptionPricePoint"]["data"]["id"]
        point = included.get(("subscriptionPricePoints", point_id))
        if point is None:
            point = client.request("GET", f"/v1/subscriptionPricePoints/{point_id}")["data"]
        result.setdefault(territory, []).append({
            "priceId": row["id"], "pointId": point_id,
            "price": point["attributes"]["customerPrice"],
            "startDate": row["attributes"].get("startDate")})
    return result


def verify_availability(client, sid):
    plans = client.rows(f"/v1/subscriptions/{sid}/planAvailabilities", {"limit": 200})
    plan = next(p for p in plans if p["attributes"]["planType"] == "UPFRONT")
    territories = sorted(r["id"] for r in client.rows(
        f"/v1/subscriptionPlanAvailabilities/{plan['id']}/availableTerritories", {"limit": 200}))
    if territories != ["DEU"] or plan["attributes"]["availableInNewTerritories"]:
        raise RuntimeError("Expected Germany-only availability with future territories disabled")
    return {"availableTerritories": territories, "availableInNewTerritories": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    client = ASCClient(allow_writes=args.apply)
    all_territories = {r["id"] for r in client.rows("/v1/territories", {"limit": 200})}
    reports = []
    for sid in args.subscription_id:
        before_availability = verify_availability(client, sid)
        existing = price_rows(client, sid)
        bases = existing.get("DEU", [])
        if len(bases) != 1 or Decimal(bases[0]["price"]) not in (Decimal(30), Decimal(90)):
            raise RuntimeError("Expected one existing exact German EUR 30/90 base")
        base = bases[0]
        equalizations = client.rows(f"/v1/subscriptionPricePoints/{base['pointId']}/equalizations", {
            "filter[planType]": "UPFRONT", "include": "territory", "limit": 8000})
        mapping = {r["relationships"]["territory"]["data"]["id"]: {
            "pointId": r["id"], "price": r["attributes"]["customerPrice"]} for r in equalizations}
        mapping["DEU"] = {"pointId": base["pointId"], "price": base["price"]}
        if set(mapping) != all_territories:
            raise RuntimeError("Apple's equalization mapping does not cover all official territories")
        for territory, schedules in existing.items():
            if territory not in mapping or any(Decimal(r["price"]) != Decimal(mapping[territory]["price"]) for r in schedules):
                raise RuntimeError(f"Existing conflicting price in {territory}; preserved")
        missing = sorted(all_territories - set(existing))
        report = {"subscriptionId": sid, "baseTerritory": "DEU", "basePrice": base["price"],
                  "basePointId": base["pointId"], "appleEqualizations": mapping,
                  "territoryCount": len(all_territories), "missingBefore": missing,
                  "availability": before_availability, "applied": args.apply}
        reports.append(report)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"subscriptionId": sid, "basePrice": base["price"],
                          "mappingCount": len(mapping), "missing": len(missing), "apply": args.apply}), flush=True)
        if args.apply and missing:
            # Apple's SubscriptionUpdateRequest supports inline price creation.
            # This relationship creates the supplied inline rows additively.
            # Existing IDs must not be included as bare references: Apple treats
            # each entry as a creation request requiring an inline price point.
            references = []
            included = []
            for territory in missing:
                identifier = "${price-" + territory + "}"
                references.append({"type": "subscriptionPrices", "id": identifier})
                included.append({"type": "subscriptionPrices", "id": identifier,
                    "attributes": {"startDate": None, "planType": "UPFRONT"},
                    "relationships": {"subscription": relation("subscriptions", sid),
                        "subscriptionPricePoint": relation("subscriptionPricePoints", mapping[territory]["pointId"]),
                        "territory": relation("territories", territory)}})
            client.request("PATCH", f"/v1/subscriptions/{sid}", {"data": {
                "type": "subscriptions", "id": sid,
                "relationships": {"prices": {"data": references}}}, "included": included})
            print(json.dumps({"subscriptionId": sid, "created": len(missing), "batch": True}), flush=True)
        final = price_rows(client, sid)
        old_ids = {row["priceId"] for schedules in existing.values() for row in schedules}
        final_ids = {row["priceId"] for schedules in final.values() for row in schedules}
        report.update(coverageAfter=len(final), missingAfter=sorted(all_territories - set(final)),
                      availability=verify_availability(client, sid),
                      allExistingPriceIdsPreserved=old_ids <= final_ids)
        if args.apply and (report["missingAfter"] or Decimal(final["DEU"][0]["price"]) != Decimal(base["price"])):
            raise RuntimeError("Post-write full coverage/German price invariant failed")
        if not report["allExistingPriceIdsPreserved"]:
            raise RuntimeError("An existing price schedule changed unexpectedly")
        args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"subscriptionId": sid, "coverageAfter": len(final),
                          "missingAfter": len(report["missingAfter"]), "availability": report["availability"]}), flush=True)


if __name__ == "__main__":
    main()
