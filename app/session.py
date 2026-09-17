"""In-memory session store. Dict keyed by session id, no persistence."""

from dataclasses import dataclass, field


@dataclass
class DecisionLog:
    """Compact structured memory of the last resolved turn, so follow-ups
    like "what about this evening" don't need to be re-derived from raw
    chat history alone."""

    location: dict | None = None
    weather_facts: dict | None = None
    matched_sop_ids: list[str] = field(default_factory=list)
    activity: str | None = None


@dataclass
class SessionState:
    turns: list[dict] = field(default_factory=list)
    decision_log: DecisionLog = field(default_factory=DecisionLog)


_SESSIONS: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = SessionState()
    return _SESSIONS[session_id]


def append_turn(session_id: str, role: str, content: str) -> None:
    session = get_session(session_id)
    session.turns.append({"role": role, "content": content})


def update_decision_log(session_id: str, **kwargs) -> None:
    session = get_session(session_id)
    for key, value in kwargs.items():
        setattr(session.decision_log, key, value)
