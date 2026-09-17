from dataclasses import asdict

from app.session import append_turn, get_session
from app.state import GraphState


async def intake(state: GraphState) -> dict:
    session_id = state["session_id"]
    append_turn(session_id, "user", state["message"])
    session = get_session(session_id)
    return {
        "turns": list(session.turns),
        "decision_log": asdict(session.decision_log),
    }
