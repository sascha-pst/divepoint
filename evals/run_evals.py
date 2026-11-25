"""Run deterministic acceptance checks against the bundled guide evidence."""

import argparse
import json
import os
from pathlib import Path
import sys
from collections import Counter
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

EVAL_DIR = Path(__file__).resolve().parent


def load_cases(filename):
    return [json.loads(line) for line in (EVAL_DIR / filename).read_text().splitlines() if line.strip()]


def reject_network(*args, **kwargs):
    raise RuntimeError("Offline guide eval attempted an external HTTP request")


def evaluate_guide(client, case, dive):
    body = {"question": case["question"]}
    if "aphia_id" in case:
        if not any(fish["aphia_id"] == case["aphia_id"] for fish in dive["species"]):
            raise ValueError(f"fixture species {case['aphia_id']} is missing from the manifest")
        body["aphia_id"] = case["aphia_id"]

    response = client.post(f"/v1/dives/{dive['id']}/ask", json=body)
    response.raise_for_status()
    result = response.json()
    if result["mode"] != "records":
        raise ValueError(f"expected offline record lookup, got {result['mode']!r}")

    expected = Counter(tuple(row) for row in case["evidence"])
    actual = Counter((doc["topic"], doc["url"], doc["text"]) for doc in result["evidence"])
    if actual != expected:
        missing = list((expected - actual).elements())
        unexpected = list((actual - expected).elements())
        raise ValueError(f"missing evidence {missing!r}; unexpected evidence {unexpected!r}")
    if expected and result["message"] is not None:
        raise ValueError(f"cited answer also returned a message: {result['message']!r}")
    if not expected and result["message"] != case["no_data_message"]:
        raise ValueError(f"expected an explicit no-data response, got {result['message']!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Run the current offline seed suite")
    parser.parse_args()

    places = load_cases("places.jsonl")
    if not places or not all(
        row["prompt"] and row["expected_type"] in {"dive", "clarify", "reject"} for row in places
    ):
        print("FAIL: invalid place seeds")
        return 1
    print(f"PASS: {len(places)} place seeds are well formed (format only).")

    cases = load_cases("guide.jsonl")
    if not cases or len({case["id"] for case in cases}) != len(cases):
        print("FAIL: guide cases must have unique IDs and the suite must be nonempty")
        return 1

    # Support the documented command from the repo root without installing the app package.
    sys.path.insert(0, str(EVAL_DIR.parent / "backend"))
    from app.main import app

    failures = 0
    dives = {}
    with (
        patch.dict(os.environ, {"DIVEPOINT_GUIDE_API_KEY": "", "DIVEPOINT_EARLIEST_RECORD_YEAR": "1970"}),
        patch.object(httpx.HTTPTransport, "handle_request", reject_network),
        patch.object(httpx.AsyncHTTPTransport, "handle_async_request", reject_network),
        TestClient(app) as client,
    ):
        for case in cases:
            try:
                place = case["place"]
                if place not in dives:
                    response = client.post("/v1/dives/plan", json={"text": place, "depth_m": 30})
                    response.raise_for_status()
                    dive = response.json()
                    if dive.get("source_mode") != "recorded":
                        raise ValueError(f"{place} did not resolve to a recorded dive")
                    dives[place] = dive
                evaluate_guide(client, case, dives[place])
            except Exception as error:
                print(f"FAIL [{case['id']}] {case['question']} — {error}")
                failures += 1
    print(f"Offline guide: {len(cases) - failures}/{len(cases)} passed.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
