# graph.py
# Este arquivo define o grafo de estados do agente bancário, integrando o modelo LLM (Ollama) com as ferramentas (tools) e a lógica de fluxo.

from typing import Literal, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver # checkpointer para salvar o estado do grafo em memória para HIL (Human-in-the-Loop)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from src.core import obter_usuario_logado
from src.tools import ALL_TOOLS # <-- importa o arquivo de tools.py que contém todas as ferramentas bancárias
from src.utils import registrar_observabilidade_llm

# 1. Definir o Estado do Agente e reducer
#Sem Annotated[list[BaseMessage], add_messages], cada nó que retorna {"messages": [...]} sobrescreve a lista inteira em vez de concatenar (append) ao histórico
class EstadoAgente(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# 2. Inicializar o modelo Ollama local (ex: gemma2 ou gemma4)
# Tool Calling Nativo / Roteamento Implícito
# Nos LLMs modernos integrados com LangChain/LangGraph (via .bind_tools(ALL_TOOLS)), 
# o modelo faz a classificação de intenção e o roteamento de forma nativa e automática dentro do nó 
# assistente
llm = ChatOllama(model="gemma4:e4b", temperature=0).bind_tools(ALL_TOOLS)

# 3. Nó do Assistente (Classificador e Gerador de Resposta)
def chamar_modelo(state: EstadoAgente):
    user = obter_usuario_logado()
    sistema_prompt = (
        f"Você é um assistente bancário objetivo e seguro. "
        f"Usuário logado: {user['nome']} (ID: {user['id']}). "
        "Regras:\n"
        "- Quando o usuário pedir saldo, extrato, saque, depósito ou transferência, chame a ferramenta correspondente.\n"
        "- Quando já houver o resultado de uma ferramenta (ToolMessage) no histórico, responda diretamente ao usuário com base nesse resultado, sem repetir menus.\n"
        "- Só mostre o menu de opções se o usuário fizer uma saudação genérica sem pedir operação."
    )

    messages = [{"role": "system", "content": sistema_prompt}] + state["messages"]
    
    # [OBSERVABILIDADE] Opcional: registrar o prompt/chain enviado ao LLM aqui se desejar
    registrar_observabilidade_llm("LLM_INPUT", {"messages_count": len(messages), "usuario_atual": user['nome']})
    
    response = llm.invoke(messages)
    return {"messages": [response]}

# 4. Condição para decidir se chama tools ou encerra
def deve_continuar(state: EstadoAgente) -> Literal["tools", END]:
    messages = state["messages"]
    last_message = messages[-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


workflow = StateGraph(EstadoAgente)

workflow.add_node("assistente", chamar_modelo) # Nó do assistente que chama o modelo LLM e já classifica a intenção e roteia para tools se necessário
workflow.add_node("tools", ToolNode(ALL_TOOLS))  

workflow.add_edge(START, "assistente")
workflow.add_conditional_edges("assistente", deve_continuar, {"tools": "tools", END: END})
workflow.add_edge("tools", "assistente")

memory = MemorySaver()
grafo = workflow.compile(checkpointer=memory, interrupt_before=["tools"])