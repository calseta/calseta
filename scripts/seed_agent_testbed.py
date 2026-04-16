#!/usr/bin/env python3
"""
Seed the Calseta instance with mock alerts for agent runtime testing.

Reads mock_alerts.json, ingests each alert via POST /v1/ingest/sentinel,
polls until enrichment completes, and prints a summary.

Usage:
    python scripts/seed_agent_testbed.py
    python scripts/seed_agent_testbed.py --api-url http://localhost:8000 --api-key cai_xxxx
    python scripts/seed_agent_testbed.py --skip-enrichment-wait
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "mock_alerts.json"

# Terminal colors (degrade gracefully if not a TTY)
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def _green(t: str) -> str:
    return _c("32", t)


def _yellow(t: str) -> str:
    return _c("33", t)


def _red(t: str) -> str:
    return _c("31", t)


def _bold(t: str) -> str:
    return _c("1", t)


def _dim(t: str) -> str:
    return _c("2", t)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed Calseta with mock alerts for agent runtime testing.",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("CALSETA_API_URL", "http://localhost:8000"),
        help="Calseta API base URL (default: $CALSETA_API_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CALSETA_API_KEY", ""),
        help="Calseta API key (default: $CALSETA_API_KEY)",
    )
    parser.add_argument(
        "--skip-enrichment-wait",
        action="store_true",
        help="Ingest alerts without waiting for enrichment to complete",
    )
    parser.add_argument(
        "--enrichment-timeout",
        type=int,
        default=120,
        help="Max seconds to wait for enrichment per alert (default: 120)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Only ingest alerts from a specific scenario (e.g. credential_stuffing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate fixtures without sending to API",
    )
    return parser.parse_args()


async def ingest_alert(
    client: httpx.AsyncClient,
    alert_payload: dict,
    index: int,
    scenario: str,
) -> dict | None:
    """POST a single alert to /v1/ingest/sentinel. Returns response data or None on failure."""
    try:
        resp = await client.post("/v1/ingest/sentinel", json=alert_payload)
    except httpx.RequestError as exc:
        print(f"  {_red('ERROR')} [{scenario}#{index}] Connection failed: {exc}")
        return None

    if resp.status_code == 202:
        data = resp.json().get("data", {})
        uuid = data.get("alert_uuid", "unknown")
        status = data.get("status", "unknown")
        is_dup = data.get("is_duplicate", False)
        dup_label = f" {_yellow('(duplicate)')}" if is_dup else ""
        print(f"  {_green('OK')} [{scenario}#{index}] {uuid} -> {status}{dup_label}")
        return data
    else:
        error = resp.json().get("error", {})
        msg = error.get("message", resp.text[:200])
        print(f"  {_red('FAIL')} [{scenario}#{index}] HTTP {resp.status_code}: {msg}")
        return None


async def wait_for_enrichment(
    client: httpx.AsyncClient,
    alert_uuid: str,
    timeout: int,
) -> dict | None:
    """Poll GET /v1/alerts/{uuid} until enrichment_status is not Pending."""
    start = time.monotonic()
    poll_interval = 2.0

    while time.monotonic() - start < timeout:
        try:
            resp = await client.get(f"/v1/alerts/{alert_uuid}")
        except httpx.RequestError:
            await asyncio.sleep(poll_interval)
            continue

        if resp.status_code != 200:
            await asyncio.sleep(poll_interval)
            continue

        alert_data = resp.json().get("data", {})
        enrichment_status = alert_data.get("enrichment_status", "Pending")

        if enrichment_status != "Pending":
            return alert_data

        await asyncio.sleep(poll_interval)

    return None  # timed out


async def main() -> None:
    args = parse_args()

    # Load fixtures
    if not FIXTURES_PATH.exists():
        print(f"{_red('ERROR')}: Fixture file not found: {FIXTURES_PATH}")
        sys.exit(1)

    with open(FIXTURES_PATH) as f:
        fixtures = json.load(f)

    # Filter by scenario if requested
    if args.scenario:
        fixtures = [fx for fx in fixtures if fx["scenario"] == args.scenario]
        if not fixtures:
            print(f"{_red('ERROR')}: No alerts found for scenario '{args.scenario}'")
            sys.exit(1)

    total = len(fixtures)
    scenarios = {}
    for fx in fixtures:
        s = fx["scenario"]
        scenarios[s] = scenarios.get(s, 0) + 1

    print(_bold(f"\nCalseta Agent Testbed Seeder"))
    print(f"{'='*50}")
    print(f"API URL:    {args.api_url}")
    print(f"Alerts:     {total}")
    print(f"Scenarios:  {', '.join(f'{k} ({v})' for k, v in scenarios.items())}")
    if args.dry_run:
        print(f"Mode:       {_yellow('DRY RUN')}")
    print()

    if args.dry_run:
        print(_bold("Fixture validation:"))
        for fx in fixtures:
            alert = fx["alert"]
            props = alert.get("properties", {})
            entities = alert.get("Entities", [])
            expected = fx["expected"]
            title = props.get("title", "???")[:60]
            print(
                f"  {_green('VALID')} [{fx['scenario']}#{fx['scenario_index']}] "
                f"{title} | {len(entities)} entities | "
                f"expect {expected['indicator_count']} indicators"
            )
        print(f"\n{_green('All')} {total} fixtures valid.")
        return

    # Validate API key
    if not args.api_key:
        print(
            f"{_red('ERROR')}: No API key provided. "
            "Set CALSETA_API_KEY env var or pass --api-key."
        )
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=args.api_url,
        headers=headers,
        timeout=30.0,
    ) as client:
        # Health check
        try:
            health = await client.get("/v1/health")
            if health.status_code != 200:
                print(f"{_yellow('WARN')}: Health check returned {health.status_code}")
        except httpx.RequestError as exc:
            print(f"{_red('ERROR')}: Cannot reach API at {args.api_url}: {exc}")
            sys.exit(1)

        # Phase 1: Ingest all alerts
        print(_bold("Phase 1: Ingesting alerts"))
        print(f"{'-'*50}")

        ingested: list[dict] = []
        failed = 0

        for fx in fixtures:
            result = await ingest_alert(
                client,
                fx["alert"],
                fx["scenario_index"],
                fx["scenario"],
            )
            if result:
                result["_scenario"] = fx["scenario"]
                result["_scenario_index"] = fx["scenario_index"]
                result["_expected"] = fx["expected"]
                ingested.append(result)
            else:
                failed += 1

        print(f"\nIngested: {_green(str(len(ingested)))} | Failed: {_red(str(failed))}")

        if not ingested:
            print(f"\n{_red('No alerts ingested. Exiting.')}")
            sys.exit(1)

        # Phase 2: Wait for enrichment
        if args.skip_enrichment_wait:
            print(f"\n{_dim('Skipping enrichment wait (--skip-enrichment-wait)')}")
        else:
            print(f"\n{_bold('Phase 2: Waiting for enrichment')}")
            print(f"{'-'*50}")

            enriched_count = 0
            enrichment_failed = 0
            enrichment_timeout = 0
            indicator_total = 0

            for item in ingested:
                uuid = item["alert_uuid"]
                scenario = item["_scenario"]
                idx = item["_scenario_index"]

                sys.stdout.write(
                    f"  Enriching [{scenario}#{idx}] {uuid}... "
                )
                sys.stdout.flush()

                alert_data = await wait_for_enrichment(
                    client, uuid, args.enrichment_timeout
                )

                if alert_data is None:
                    print(_yellow("TIMEOUT"))
                    enrichment_timeout += 1
                elif alert_data.get("enrichment_status") == "Enriched":
                    indicators = alert_data.get("indicators", [])
                    indicator_total += len(indicators)
                    print(_green(f"OK ({len(indicators)} indicators)"))
                    enriched_count += 1
                elif alert_data.get("enrichment_status") == "Failed":
                    print(_red("FAILED"))
                    enrichment_failed += 1
                else:
                    status = alert_data.get("enrichment_status", "unknown")
                    print(_yellow(f"({status})"))

            print(
                f"\nEnriched: {_green(str(enriched_count))} | "
                f"Failed: {_red(str(enrichment_failed))} | "
                f"Timeout: {_yellow(str(enrichment_timeout))}"
            )
            print(f"Total indicators extracted: {_bold(str(indicator_total))}")

        # Summary
        print(f"\n{'='*50}")
        print(_bold("Summary"))
        print(f"{'='*50}")
        print(f"Total alerts ingested:  {len(ingested)}/{total}")
        duplicates = sum(1 for i in ingested if i.get("is_duplicate"))
        if duplicates:
            print(f"Duplicates detected:    {duplicates}")
        print(f"Scenarios covered:      {len(scenarios)}")
        print()

        # Scenario breakdown
        print(_bold("Scenario breakdown:"))
        for scenario_name, count in scenarios.items():
            scenario_items = [
                i for i in ingested if i["_scenario"] == scenario_name
            ]
            expected = next(
                (
                    i["_expected"]["expected_classification"]
                    for i in scenario_items
                ),
                "N/A",
            )
            print(
                f"  {scenario_name:25s} {len(scenario_items):2d}/{count} ingested | "
                f"expected: {expected}"
            )

        print(f"\n{_green('Done.')} Alerts are ready for agent investigation.\n")


if __name__ == "__main__":
    asyncio.run(main())
