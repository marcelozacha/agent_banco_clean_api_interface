# src/API/api.py
import sys
from pathlib import Path

# Garante que a raiz do projeto esteja no sys.path mesmo se rodar o arquivo direto
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.services.chat_service import confirmar_acao_hitl, processar_mensagem_chat


# Adicione logo após criar o objeto `app = FastAPI(...)`
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="API do Agente Bancário",
    description="API HTTP para interagir com o agente bancário com HITL e guardrails.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja às origens da sua interface web
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_message: str = Field(..., min_length=1)
    thread_id: str = Field(default="sessao_banco_default", min_length=1)


class ConfirmRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    aprovar: bool


class PendingAction(BaseModel):
    name: str
    args: dict
    id: str | None = None


class ChatResponse(BaseModel):
    status: str  # "completed" | "pending_approval" | "blocked" | "cancelled"
    agent_response: str
    tool_calls_required: bool
    pending_actions: list[PendingAction] = []


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    resultado = await processar_mensagem_chat(
        user_message=request.user_message.strip(),
        thread_id=request.thread_id,
    )
    return ChatResponse(
        status=resultado["status"],
        agent_response=resultado["agent_response"],
        tool_calls_required=resultado["status"] == "pending_approval",
        pending_actions=resultado["pending_actions"],
    )


@app.post("/chat/confirm", response_model=ChatResponse)
async def confirm_endpoint(request: ConfirmRequest):
    resultado = await confirmar_acao_hitl(
        thread_id=request.thread_id,
        aprovar=request.aprovar,
    )
    return ChatResponse(
        status=resultado["status"],
        agent_response=resultado["agent_response"],
        tool_calls_required=resultado["status"] == "pending_approval",
        pending_actions=resultado["pending_actions"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.API.api:app", host="127.0.0.1", port=8000, reload=True)