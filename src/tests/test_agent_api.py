import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

# Garante que a raiz do projeto (onde fica a pasta 'src') esteja no sys.path
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from langchain_core.messages import HumanMessage

from src.agents.graph import grafo
from src.core import obter_usuario_logado
from src.security import aplicar_todos_guardrails


def _consumir_stream_sync(
    inputs: dict[str, Any] | None,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Consome o generator do LangGraph integralmente dentro da worker thread."""
    eventos: list[dict[str, Any]] = []
    for evento in grafo.stream(inputs, config, stream_mode="values"):
        eventos.append(evento)
    return eventos


def _extrair_resposta_final(mensagens: list[Any]) -> str:
    """Retorna a última resposta textual do assistente, com fallback para ToolMessage."""
    for msg in reversed(mensagens):
        tipo = getattr(msg, "type", "")
        conteudo = getattr(msg, "content", "")
        if tipo == "ai" and isinstance(conteudo, str) and conteudo.strip():
            return conteudo.strip()

    for msg in reversed(mensagens):
        conteudo = getattr(msg, "content", "")
        if isinstance(conteudo, str) and conteudo.strip():
            return conteudo.strip()

    return "(Nenhuma resposta textual encontrada)"


async def test_agent_logic(auto_confirm_hitl: bool = True) -> None:
    user_message = "Qual o saldo da minha conta?"
    thread_id = f"teste_api_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    usuario = obter_usuario_logado()
    print(f"Usuário logado: {usuario.get('nome')} | Thread: {thread_id}")

    # 1. Guardrails
    aprovado, mensagem_erro = aplicar_todos_guardrails(user_message)
    if not aprovado:
        print(f"Guardrail bloqueou: {mensagem_erro}")
        return

    # 2. Primeira etapa do grafo (até eventual interrupção HITL antes de 'tools')
    inputs: dict[str, Any] | None = {"messages": [HumanMessage(content=user_message)]}

    try:
        eventos_etapa_1 = await asyncio.to_thread(_consumir_stream_sync, inputs, config)
        print(f"Etapa 1 concluída. Snapshots: {len(eventos_etapa_1)}")

        estado = grafo.get_state(config)
        print(f"Próximos nós após etapa 1: {estado.next}")

        if estado.next and "tools" in estado.next:
            ultima_msg = estado.values["messages"][-1] if estado.values.get("messages") else None
            tool_calls = getattr(ultima_msg, "tool_calls", None) or []
            print(f"HITL acionado para tools: {[tc.get('name') for tc in tool_calls]}")

            if auto_confirm_hitl:
                print("Confirmando HITL automaticamente e retomando o grafo...")
                eventos_etapa_2 = await asyncio.to_thread(_consumir_stream_sync, None, config)
                print(f"Etapa 2 concluída. Snapshots: {len(eventos_etapa_2)}")
                estado = grafo.get_state(config)
                print(f"Próximos nós após retomada: {estado.next}")
            else:
                print("HITL pendente e auto_confirm_hitl=False. Encerrando sem executar tools.")
                return

        mensagens = estado.values.get("messages", []) if estado.values else []
        print(f"Total de mensagens no estado final: {len(mensagens)}")

        for msg in mensagens:
            if getattr(msg, "type", "") == "tool":
                print(f"[ToolMessage - {getattr(msg, 'name', 'tool')}]: {msg.content}")

        resposta_final = _extrair_resposta_final(mensagens)
        print("\n--- Resposta Final do Agente ---")
        print(resposta_final)

    except Exception as e:
        print(f"ERRO CRÍTICO AO RODAR O GRAFO: {repr(e)}")


if __name__ == "__main__":
    asyncio.run(test_agent_logic(auto_confirm_hitl=True))