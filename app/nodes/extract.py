from app.llm import get_llm_client, parse_json_response
from app.state import GraphState

SYSTEM_PROMPT = """You extract structured intent from a message sent to a weather-safety \
assistant. Look at the current message plus the recent conversation and the assistant's \
last remembered decision (location, activity, weather facts) to judge whether this message \
is a follow-up to that context.

Respond with JSON only, no prose, no markdown fences:
{
  "location": "<city/place mentioned in THIS message, or null if none was mentioned>",
  "activity": "<short phrase for the activity or category being asked about, e.g. \
'cycling', 'picnic', 'traveling', or null if unclear>",
  "time_window": "<'today', 'this evening', 'tomorrow', etc if stated, else null>",
  "is_followup": <true if this message leans on earlier context instead of restating it>
}"""


def _build_user_prompt(state: GraphState) -> str:
    turns = state.get("turns", [])
    decision_log = state.get("decision_log", {})
    recent = turns[-6:-1]  # exclude the current message, already appended by intake
    history_lines = [f"{t['role']}: {t['content']}" for t in recent]
    history_block = "\n".join(history_lines) if history_lines else "(no prior turns)"

    log_lines = []
    if decision_log.get("location"):
        log_lines.append(f"last location: {decision_log['location']}")
    if decision_log.get("activity"):
        log_lines.append(f"last activity: {decision_log['activity']}")
    log_block = "\n".join(log_lines) if log_lines else "(nothing remembered yet)"

    return (
        f"Recent conversation:\n{history_block}\n\n"
        f"Remembered decision log:\n{log_block}\n\n"
        f"Current message: {state['message']}"
    )


async def extract(state: GraphState) -> dict:
    client = get_llm_client()
    raw = await client.complete(SYSTEM_PROMPT, _build_user_prompt(state), max_tokens=300)

    try:
        parsed = parse_json_response(raw)
    except (ValueError, KeyError):
        parsed = {"location": None, "activity": None, "time_window": None, "is_followup": False}

    decision_log = state.get("decision_log", {})
    is_followup = bool(parsed.get("is_followup"))

    location_query = parsed.get("location")
    if not location_query and is_followup:
        last_location = decision_log.get("location")
        if last_location:
            location_query = last_location.get("name")

    activity = parsed.get("activity")
    if not activity and is_followup:
        activity = decision_log.get("activity")

    return {
        "location_query": location_query,
        "activity": activity,
        "is_followup": is_followup,
    }
