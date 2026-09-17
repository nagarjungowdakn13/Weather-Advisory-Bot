"""Loads SOP yaml files from /policies into a typed structure."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"

SEVERITY_ORDER = {"advisory": 0, "caution": 1, "high": 2}

OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


@dataclass
class Condition:
    field: str
    operator: str
    value: float


@dataclass
class Trigger:
    conditions: list[Condition]
    applies_when: str
    match: str | int = "all"  # "all", "any", or an int minimum count


@dataclass
class SOP:
    id: str
    category: str
    severity: str
    trigger: Trigger
    guidance: str
    citation_note: str


def _parse_sop(raw: dict) -> SOP:
    trig = raw["trigger"]
    conditions = [Condition(**c) for c in trig.get("conditions", [])]
    trigger = Trigger(
        conditions=conditions,
        applies_when=trig["applies_when"].strip(),
        match=trig.get("match", "all"),
    )
    return SOP(
        id=raw["id"],
        category=raw["category"],
        severity=raw["severity"],
        trigger=trigger,
        guidance=raw["guidance"].strip(),
        citation_note=raw["citation_note"].strip(),
    )


def load_policies(directory: Path = POLICIES_DIR) -> list[SOP]:
    sops = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        sops.append(_parse_sop(raw))
    if not sops:
        raise RuntimeError(f"no policy files found in {directory}")
    return sops


def condition_matches(cond: Condition, facts: dict[str, Any]) -> bool:
    actual = facts.get(cond.field)
    if actual is None:
        return False
    return OPERATORS[cond.operator](actual, cond.value)


def sop_passes_numeric_filter(sop: SOP, facts: dict[str, Any]) -> bool:
    """SOPs with no numeric conditions (fuzzy ones) always pass — the LLM
    decides those on applies_when alone. Others need their match rule
    satisfied against live facts."""
    conditions = sop.trigger.conditions
    if not conditions:
        return True

    results = [condition_matches(c, facts) for c in conditions]
    match = sop.trigger.match
    if match == "all":
        return all(results)
    if match == "any":
        return any(results)
    if isinstance(match, int):
        return sum(results) >= match
    raise ValueError(f"unknown match mode: {match}")


def candidate_sops(sops: list[SOP], facts: dict[str, Any]) -> list[SOP]:
    return [s for s in sops if sop_passes_numeric_filter(s, facts)]
