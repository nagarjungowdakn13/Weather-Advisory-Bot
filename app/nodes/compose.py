import re

from app.llm import get_llm_client
from app.policies import SEVERITY_ORDER, load_policies
from app.state import GraphState

_SOPS = {s.id: s for s in load_policies()}

SYSTEM_PROMPT = """You write the advice paragraph of a reply for a weather-safety assistant. \
You are only allowed to handle phrasing and tone. The facts block and policy guidance given to \
you below are the complete and final set of numbers and advice — do not add, remove, round \
differently, or invent any number, and do not reference any policy not listed. Lead with the \
primary policy's guidance; mention secondary policies briefly afterward if there are any. Keep \
it to a short, direct paragraph or two, like a person texting back a straight answer, not a \
report. Do not add a citation or source list yourself — that gets appended separately."""


def _facts_summary(facts: dict) -> str:
    parts = []
    if facts.get("temperature_2m") is not None:
        parts.append(f"currently {facts['temperature_2m']}°C")
    if facts.get("wind_speed_10m") is not None:
        parts.append(f"wind {facts['wind_speed_10m']} km/h")
    if facts.get("wind_gusts_10m") is not None:
        parts.append(f"gusts {facts['wind_gusts_10m']} km/h")
    if facts.get("precipitation") is not None:
        parts.append(f"precipitation {facts['precipitation']} mm")
    if facts.get("uv_index") is not None:
        parts.append(f"UV index {facts['uv_index']}")
    if facts.get("precipitation_probability_max") is not None:
        parts.append(f"rain chance today {facts['precipitation_probability_max']}%")
    if facts.get("temperature_2m_max") is not None and facts.get("temperature_2m_min") is not None:
        parts.append(f"today's range {facts['temperature_2m_min']}-{facts['temperature_2m_max']}°C")
    return ", ".join(parts)


def _extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"-?\d+\.?\d*", text))


def _source_numbers(facts: dict, ranked_sops) -> set[str]:
    """Numbers the LLM is allowed to use: live facts, plus any numbers
    already present in the matched policies' own guidance/citation text
    (thresholds a policy explains itself with aren't drift)."""
    numbers = set()
    for v in facts.values():
        if isinstance(v, (int, float)):
            numbers.add(str(v))
            numbers.add(str(int(v)) if float(v).is_integer() else str(v))
            numbers.add(f"{v:.0f}")
    for s in ranked_sops:
        numbers |= _extract_numbers(s.guidance)
        numbers |= _extract_numbers(s.citation_note)
    return numbers


def _deterministic_body(location_name: str, facts_summary: str, ranked_sops) -> str:
    primary = ranked_sops[0]
    lines = [f"For {location_name}: {facts_summary}.", "", primary.guidance]
    if len(ranked_sops) > 1:
        lines.append("")
        lines.append("Also worth noting:")
        for s in ranked_sops[1:]:
            lines.append(f"- {s.guidance}")
    return "\n".join(lines)


def _citation_footer(ranked_sops) -> str:
    """Built entirely in code so SOP citation is guaranteed to appear in
    the visible reply regardless of what the LLM did with phrasing — same
    reasoning as never trusting the LLM to restate facts."""
    primary = ranked_sops[0]
    lines = [f"Source: {primary.id} ({primary.severity}) — {primary.citation_note}"]
    for s in ranked_sops[1:]:
        lines.append(f"Also: {s.id} ({s.severity}) — {s.citation_note}")
    return "\n".join(lines)


async def compose(state: GraphState) -> dict:
    matched_ids = state.get("matched_ids", [])
    ranked_sops = sorted(
        (_SOPS[i] for i in matched_ids if i in _SOPS),
        key=lambda s: SEVERITY_ORDER[s.severity],
        reverse=True,
    )

    facts = state["facts"]
    location = state["location"]
    location_name = f"{location['name']}, {location['country']}" if location.get("country") else location["name"]
    facts_summary = _facts_summary(facts)

    deterministic_body = _deterministic_body(location_name, facts_summary, ranked_sops)
    citation_footer = _citation_footer(ranked_sops)

    policy_block = "\n\n".join(
        f"[{'PRIMARY' if s is ranked_sops[0] else 'secondary'}] {s.id} (severity: {s.severity})\n"
        f"guidance: {s.guidance}\n"
        f"citation: {s.citation_note}"
        for s in ranked_sops
    )
    user_prompt = (
        f"User's question: {state['message']}\n"
        f"Location: {location_name}\n"
        f"Facts block (the only numbers you may use): {facts_summary}\n\n"
        f"Matched policies:\n{policy_block}"
    )

    client = get_llm_client()
    phrased = await client.complete(SYSTEM_PROMPT, user_prompt, max_tokens=500)

    source_numbers = _source_numbers(facts, ranked_sops)
    phrased_numbers = _extract_numbers(phrased)
    drifted = phrased_numbers - source_numbers
    # allow small integers that are likely not measurements (e.g. "30 minutes", list markers)
    drifted = {n for n in drifted if len(n) > 1 or n not in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}}

    body = phrased.strip() if not drifted else deterministic_body

    return {"response": f"{body}\n\n{citation_footer}"}


# --- evaluated-but-not-triggered path -------------------------------------
# A topically relevant SOP exists and was checked against real numbers, but
# conditions are safely under its threshold. Distinct from "no policy covers
# this at all" (no_guidance) - see fallback.py and the sop_match status.

FIELD_LABELS = {
    "temperature_2m": "temperature",
    "wind_speed_10m": "wind speed",
    "wind_gusts_10m": "wind gusts",
    "precipitation": "precipitation",
    "uv_index": "UV index",
    "relative_humidity_2m": "humidity",
    "temperature_2m_max": "today's high",
    "temperature_2m_min": "today's low",
    "precipitation_probability_max": "rain chance today",
    "uv_index_max": "today's peak UV index",
    "wind_speed_10m_max": "today's peak wind speed",
}
FIELD_UNITS = {
    "temperature_2m": "°C",
    "wind_speed_10m": "km/h",
    "wind_gusts_10m": "km/h",
    "precipitation": "mm",
    "uv_index": "",
    "relative_humidity_2m": "%",
    "temperature_2m_max": "°C",
    "temperature_2m_min": "°C",
    "precipitation_probability_max": "%",
    "uv_index_max": "",
    "wind_speed_10m_max": "km/h",
}
OP_WORDS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below", "==": "equal to"}


def _condition_clause(cond, facts: dict) -> str:
    label = FIELD_LABELS.get(cond.field, cond.field)
    unit = FIELD_UNITS.get(cond.field, "")
    actual = facts.get(cond.field)
    return f"{label} is {actual}{unit} (threshold to trigger: {OP_WORDS.get(cond.operator, cond.operator)} {cond.value}{unit})"


SYSTEM_PROMPT_NO_TRIGGER = """You write the advice paragraph of a reply for a weather-safety \
assistant, for the specific case where a real policy exists and was checked, but current \
conditions are safely under its threshold — so no advisory applies. You are only allowed to \
handle phrasing and tone. The facts and threshold comparison given to you below are the \
complete and final set of numbers — do not add, remove, round differently, or invent any \
number, and do not reference any policy not listed. State plainly that conditions are within \
the safe range and no advisory applies right now. Do not say there's no policy or no coverage \
for this topic — there is a policy, it simply isn't triggered by today's numbers. Keep it to \
one short, direct paragraph, like a person texting back a straight answer. Do not add a \
citation or source list yourself — that gets appended separately."""


def _deterministic_no_trigger_body(location_name: str, primary, clause_text: str) -> str:
    topic = primary.category.replace("_", " ")
    return (
        f"For {location_name}: {clause_text}. Conditions are within the safe range for "
        f"{topic} — no {primary.severity} advisory applies right now."
    )


async def compose_no_trigger(state: GraphState) -> dict:
    relevant_ids = state.get("relevant_not_triggered_ids", [])
    ranked_sops = sorted(
        (_SOPS[i] for i in relevant_ids if i in _SOPS),
        key=lambda s: SEVERITY_ORDER[s.severity],
        reverse=True,
    )

    facts = state["facts"]
    location = state["location"]
    location_name = f"{location['name']}, {location['country']}" if location.get("country") else location["name"]
    primary = ranked_sops[0]
    clause_text = "; ".join(_condition_clause(c, facts) for c in primary.trigger.conditions)

    deterministic_body = _deterministic_no_trigger_body(location_name, primary, clause_text)
    citation_footer = _citation_footer(ranked_sops)

    user_prompt = (
        f"User's question: {state['message']}\n"
        f"Location: {location_name}\n"
        f"Policy evaluated: {primary.id} (category: {primary.category}, severity: {primary.severity})\n"
        f"Condition check: {clause_text}\n"
        f"This policy's guidance if it had triggered (context only, do not present as current advice): "
        f"{primary.guidance}"
    )

    client = get_llm_client()
    phrased = await client.complete(SYSTEM_PROMPT_NO_TRIGGER, user_prompt, max_tokens=400)

    source_numbers = _source_numbers(facts, ranked_sops)
    phrased_numbers = _extract_numbers(phrased)
    drifted = phrased_numbers - source_numbers
    drifted = {n for n in drifted if len(n) > 1 or n not in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}}

    body = phrased.strip() if not drifted else deterministic_body

    return {"response": f"{body}\n\n{citation_footer}"}
