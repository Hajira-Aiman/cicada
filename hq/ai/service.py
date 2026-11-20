"""Head-office AI service. Run: python -m uvicorn hq.ai.service:app --port 8010
Sahiti's hq-api proxies POST /api/ai/chat here with the tenant taken from the login."""
from fastapi import FastAPI
from pydantic import BaseModel
from hq.ai.assistant import ask

app = FastAPI(title="Airlock head-office AI")


class Chat(BaseModel):
    tenant_id: str
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: Chat):
    return ask(req.tenant_id, req.question)   # {"answer": str, "evidence_ids": [str]}
