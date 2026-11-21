# graph.py
# Este arquivo define o grafo de estados do agente bancário, integrando o modelo LLM (Ollama) com as ferramentas (tools) e a lógica de fluxo.

from typing import Literal, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver # checkpointer para salvar o estado do grafo em memória para HIL (Human-in-the-Loop)

from src.tools.bank_tools import ALL_TOOLS  # <-- importa o arquivo de tools.py que contém todas as ferramentas bancárias
from src.core.database import obter_usuario_logado # <-- importa a função para obter o usuário logado

#para logar prompts, chains, tool calls e parâmetros
from src.utils.logger import registrar_observabilidade_llm  # <--- Importação do logger

# 1. Definir o Estado do Agente
class EstadoAgente(TypedDict):
    messages: list[BaseMessage]

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
        f"Você é um assistente bancário inteligente. "
        f"O usuário atualmente logado é: {user['nome']} (ID: {user['id']}). "
        f"Ajude-o a consultar saldo, sacar, depositar ou transferir dinheiro com segurança."
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
    if last_message.tool_calls:
        return "tools"
    return END

# 5. Função para salvar o grafo em formato Mermaid localmente
def salvar_mermaid_local(graph_compiled, filename="grafo_arquitetura.mmd"):
    """Gera e salva a representação em texto do Mermaid localmente."""
    try:
        # Obtém o código estruturado do grafo em texto puro
        mermaid_code = graph_compiled.get_graph().draw_mermaid()
        
        # Salva em um arquivo .mmd compatível com editores de texto e viewers
        with open(filename, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
            
        print(f"📊 Código Mermaid exportado com sucesso para '{filename}'")
        print("💡 Dica: Abra este arquivo no VS Code com a extensão 'Markdown Preview Mermaid Support'")
        print("   ou cole o conteúdo gerado em: https://mermaid.live/")
        
    except Exception as e:
        print(f"⚠️ Não foi possível gerar o código Mermaid: {e}")


# 6. Construir o Grafo
workflow = StateGraph(EstadoAgente)

workflow.add_node("assistente", chamar_modelo) # Nó do assistente que chama o modelo LLM e já classifica a intenção e roteia para tools se necessário
workflow.add_node("tools", ToolNode(ALL_TOOLS))  

workflow.add_edge(START, "assistente")
workflow.add_conditional_edges("assistente", deve_continuar, {"tools": "tools", END: END})
workflow.add_edge("tools", "assistente")

memory = MemorySaver()
grafo = workflow.compile(checkpointer=memory, interrupt_before=["tools"])


# Executa a função de salvamento local
#salvar_mermaid_local(grafo)