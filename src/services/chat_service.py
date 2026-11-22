# src/services/chat_service.py
import asyncio
from typing import Any
from langchain_core.messages import HumanMessage, ToolMessage

from src.agents import grafo_react as grafo
from src.core import obter_usuario_logado
from src.security import aplicar_todos_guardrails
from src.utils import registrar_observabilidade_llm


def _extrair_resposta_assistente(mensagens: list[Any]) -> str:
    """Extrai a última resposta textual do assistente sem retornar ToolMessage crua."""
    for msg in reversed(mensagens):
        tipo = getattr(msg, "type", "")
        conteudo = getattr(msg, "content", "")
        if tipo == "ai" and isinstance(conteudo, str) and conteudo.strip():
            return conteudo.strip()

    for msg in reversed(mensagens):
        tipo = getattr(msg, "type", "")
        conteudo = getattr(msg, "content", "")
        if tipo != "tool" and isinstance(conteudo, str) and conteudo.strip():
            return conteudo.strip()

    if mensagens:
        ultimo_conteudo = getattr(mensagens[-1], "content", "")
        if isinstance(ultimo_conteudo, str) and ultimo_conteudo.strip():
            return ultimo_conteudo.strip()

    return "Operação concluída."


def _registrar_snapshot_grafo(config: dict[str, Any], evento: str) -> Any:
    """Registra no log de observabilidade o estado atual do grafo e eventuais tool_calls."""
    state = grafo.get_state(config)
    mensagens = state.values.get("messages", []) if state.values else []
    ultima_msg = mensagens[-1] if mensagens else None

    registrar_observabilidade_llm(
        evento,
        {
            "thread_id": config.get("configurable", {}).get("thread_id"),
            "next_nodes": list(state.next) if state.next else [],
            "messages_count": len(mensagens),
            "last_msg_type": getattr(ultima_msg, "type", None),
            "tool_calls": getattr(ultima_msg, "tool_calls", None),
            "last_content_preview": str(getattr(ultima_msg, "content", ""))[:250],
        },
    )
    return state


def _executar_grafo_sync(
    config: dict[str, Any],
    mensagem: str | None = None,
    aprovar: bool | None = None,
) -> dict[str, Any]:
    """Executa ou retoma o grafo em thread dedicada e inspeciona interrupções HITL."""
    if aprovar is False:
        state_antes = grafo.get_state(config)
        mensagens_antes = state_antes.values.get("messages", []) if state_antes.values else []
        ultima_msg = mensagens_antes[-1] if mensagens_antes else None
        tool_calls = getattr(ultima_msg, "tool_calls", None) or []

        if tool_calls:
            cancel_msgs = [
                ToolMessage(
                    content="Operação cancelada pelo usuário.",
                    tool_call_id=tc.get("id", f"cancel_{idx}"),
                    name=tc.get("name", "tool"),
                )
                for idx, tc in enumerate(tool_calls)
            ]
            grafo.update_state(config, {"messages": cancel_msgs}, as_node="tools")
            grafo.invoke(None, config=config)

        state_pos = _registrar_snapshot_grafo(config, "HITL_CANCELLED")
        mensagens_pos = state_pos.values.get("messages", []) if state_pos.values else []
        resposta_cancel = _extrair_resposta_assistente(mensagens_pos) or "Operação cancelada pelo usuário."

        return {
            "status": "cancelled",
            "agent_response": resposta_cancel,
            "pending_actions": [],
        }

    if aprovar is True:
        grafo.invoke(None, config=config)
    elif mensagem is not None:
        grafo.invoke({"messages": [HumanMessage(content=mensagem)]}, config=config)

    state = _registrar_snapshot_grafo(config, "GRAPH_STEP_END")

    if state.next and "tools" in state.next:
        mensagens = state.values.get("messages", []) if state.values else []
        ultima_msg = mensagens[-1] if mensagens else None
        acoes = [
            {"name": tc["name"], "args": tc["args"], "id": tc.get("id")}
            for tc in getattr(ultima_msg, "tool_calls", []) or []
        ]
        registrar_observabilidade_llm(
            "HITL_PENDING_APPROVAL",
            {
                "thread_id": config.get("configurable", {}).get("thread_id"),
                "pending_actions": acoes,
            },
        )
        return {
            "status": "pending_approval",
            "agent_response": "Confirmação necessária antes de executar a operação bancária.",
            "pending_actions": acoes,
        }

    mensagens = state.values.get("messages", []) if state.values else []
    resposta = _extrair_resposta_assistente(mensagens)

    return {
        "status": "completed",
        "agent_response": resposta,
        "pending_actions": [],
    }


async def processar_mensagem_chat(user_message: str, thread_id: str) -> dict[str, Any]:
    user_info = obter_usuario_logado()
    user_name = user_info.get("nome", "Usuário")

    aprovado, mensagem_erro = aplicar_todos_guardrails(user_message)
    if not aprovado:
        registrar_observabilidade_llm(
            "GUARDRAIL_BLOCK",
            {"input": user_message, "motivo": mensagem_erro, "usuario": user_name},
        )
        return {
            "status": "blocked",
            "agent_response": mensagem_erro,
            "pending_actions": [],
        }

    registrar_observabilidade_llm(
        "PROMPT_USER",
        {"input": user_message, "usuario": user_name, "thread_id": thread_id},
    )

    config = {"configurable": {"thread_id": thread_id}}
    return await asyncio.to_thread(_executar_grafo_sync, config, user_message, None)


async def confirmar_acao_hitl(thread_id: str, aprovar: bool) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    registrar_observabilidade_llm(
        "HITL_DECISION",
        {"thread_id": thread_id, "aprovar": aprovar},
    )
    return await asyncio.to_thread(_executar_grafo_sync, config, None, aprovar)