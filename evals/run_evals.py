"""Runs every case in cases.py against the real graph and prints pass/fail.

Requires a working LLM key (see .env.example) since extract/sop_match/compose
all make real model calls. Weather is mocked for every case except the live
smoke test, which hits the real Open-Meteo API.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from evals.cases import CASES  # noqa: E402


async def main():
    results = []
    for case in CASES:
        print(f"[{case.name}] {case.description}")
        try:
            passed, detail = await case.run()
        except Exception as e:  # noqa: BLE001 - eval harness, want to surface any failure
            passed, detail = False, f"raised {type(e).__name__}: {e}"
        results.append((case, passed, detail))
        status = "PASS" if passed else "FAIL"
        print(f"  {status} — {detail}\n")

    passed_count = sum(1 for _, p, _ in results if p)
    print(f"{passed_count}/{len(results)} passed")

    print(
        "\nnote: the live_weather_smoke_test case depends on real conditions at run time. "
        "It doesn't assert against any specific hardcoded event, only that the response cites "
        "real pulled numbers and (when live conditions are genuinely elevated) leads with the "
        "severe_weather category. For a suite that needs to pass identically forever, that case "
        "should be replaced with a mocked Open-Meteo response like the other seven, and this one "
        "kept separately as a periodic smoke test rather than part of CI."
    )

    if passed_count != len(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
