from app.session import append_turn, update_decision_log
from app.state import GraphState


async def update_session(state: GraphState) -> dict:
    session_id = state["session_id"]
    append_turn(session_id, "assistant", state["response"])

    log_updates = {}
    if state.get("location"):
        log_updates["location"] = state["location"]
    if state.get("facts"):
        log_updates["weather_facts"] = state["facts"]
    if "matched_ids" in state:
        log_updates["matched_sop_ids"] = state["matched_ids"]
    if state.get("activity"):
        log_updates["activity"] = state["activity"]

    if log_updates:
        update_decision_log(session_id, **log_updates)

    return {}
