from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from app.graph import run_turn  # noqa: E402 (must load env before importing graph -> llm)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="weather advisory bot")


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    response = await run_turn(req.session_id, req.message)
    return ChatResponse(response=response)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
