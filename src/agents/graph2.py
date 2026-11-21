# graph2.py
# plug-n-play: Roteamento explícito com Classificador + Executor de Tools
# Retorna o mesmo tipo de estado (messages) e mantem a mesma assinatura de interrupção (interrupt_before=["tools"])
'''
Abordagem com Nó Explícito de Classificação (Router / Classifier Pattern)
O que faz: Você cria um nó separado no grafo onde um prompt restrito categoriza a intenção do usuário em categorias rígidas (SALDO, SAQUE, DEPOSITO, TRANSFERENCIA, OUTROS) antes de enviar para o agente executor.

Quando se torna uma BOA PRÁTICA OBRIGATÓRIA (Arquitetura Corporativa):

Governança e Segurança Rígida: Em ambientes bancários reais, você muitas vezes quer garantir que determinadas intenções passem por fluxos de validação estritos ou guardrails específicos antes de tocar no agente de IA principal.

Modelos Locais Menores (como o Gemma de 2B/7B): Modelos locais menores às vezes "se perdem" quando têm muitas ferramentas complexas disponíveis ao mesmo tempo. Separar a classificação (fazer o modelo menor focar só em classificar a intenção primeiro) aumenta drasticamente a acurácia do sistema.

Multi-Agentes / Escalonamento: Se o seu projeto crescer e você tiver um "Agente de Atendimento", um "Agente de Investimentos" e um "Agente de Cartões", o nó classificador funciona como um Router que direciona o usuário para o micro-agente correto.



'''

# Para usar precisa importar o grafo no main.py e substituir o grafo original
# Troque:
# from graph import grafo

# Por:
#from graph2 import grafo



from typing import Literal, TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, AIMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from src.tools.bank_tools import consultar_saldo, realizar_saque, realizar_deposito, transferir_valor, ALL_TOOLS
from src.core.database import obter_usuario_logado
from src.utils.logger import registrar_observabilidade_llm

# 1. Schema Pydantic para forçar o LLM a classificar estritamente em uma das categorias
# No prompt_roteador do graph2.py, adicione:
class ClassificacaoIntencao(BaseModel):
    intencao: Literal["SALDO", "EXTRATO", "SAQUE", "DEPOSITO", "TRANSFERENCIA", "CONVERSA_GERAL"] = Field(
        description="A intenção identificada na fala do usuário."
    )
    justificativa: str = Field(
          description="Breve motivo técnico da classificação."
    )

# 2. Definir o Estado estendido (incluindo o campo de intenção classificada)
class EstadoAgenteRoteado(TypedDict):
    messages: list[BaseMessage]
    intencao_atual: str

# 3. Modelos Ollama locais (ajuste o nome do modelo conforme instalado no seu Ollama)
MODELO_OLLAMA = "gemma4:e4b"
llm_base = ChatOllama(model=MODELO_OLLAMA, temperature=0)

# Classificador estruturado (focado exclusivamente em roteamento)
llm_classificador = llm_base.with_structured_output(ClassificacaoIntencao)

# Executor com ferramentas vinculadas
llm_executor = llm_base.bind_tools(ALL_TOOLS)

# --- NÓ 1: CLASSIFICADOR DE INTENÇÃO EXPLÍCITO ---
def classificador_intencao(state: EstadoAgenteRoteado):
    ultima_msg = state["messages"][-1].content
    
    prompt_roteador = (
        "Você é um roteador bancário. Classifique a intenção do usuário estritamente em:\n"
        "- SALDO: consultar saldo, extrato ou dados da conta.\n"
        "- SAQUE: retirar ou sacar dinheiro.\n"
        "- DEPOSITO: depositar ou adicionar dinheiro na conta.\n"
        "- TRANSFERENCIA: transferir, enviar ou fazer PIX/TED para outra pessoa.\n"
        "- CONVERSA_GERAL: saudações, dúvidas gerais ou assuntos fora das operações acima."
    )
    
    resultado: ClassificacaoIntencao = llm_classificador.invoke([
        {"role": "system", "content": prompt_roteador},
        {"role": "user", "content": ultima_msg}
    ])
    
    registrar_observabilidade_llm("ROUTER_CLASSIFICATION", {
        "input": ultima_msg,
        "intencao": resultado.intencao,
        "justificativa": resultado.justificativa
    })
    
    return {"intencao_atual": resultado.intencao}

# --- FUNÇÃO DE ROTEAMENTO CONDICIONAL ---
def rotear_por_intencao(state: EstadoAgenteRoteado) -> Literal["agente_transacional", "agente_conversacional"]:
    intencao = state.get("intencao_atual", "CONVERSA_GERAL")
    if intencao in ["SALDO", "EXTRATO", "SAQUE", "DEPOSITO", "TRANSFERENCIA"]:
        return "agente_transacional"
    return "agente_conversacional"

# --- NÓ 2A: AGENTE CONVERSACIONAL (Sem acesso a tools financeiras) ---
def agente_conversacional(state: EstadoAgenteRoteado):
    user = obter_usuario_logado()
    sistema_prompt = (
        f"Você é o atendimento inicial do Banco Digital IA. O cliente logado é {user['nome']}. "
        f"Responda de forma cordial e informe que você pode ajudar com saldo, saques, depósitos e transferências."
    )
    messages = [{"role": "system", "content": sistema_prompt}] + state["messages"]
    response = llm_base.invoke(messages)
    return {"messages": [response]}

# --- NÓ 2B: AGENTE TRANSACIONAL (Prepara a chamada de tool específica) ---
def agente_transacional(state: EstadoAgenteRoteado):
    user = obter_usuario_logado()
    intencao = state["intencao_atual"]
    
    sistema_prompt = (
        f"Você é o módulo de execução bancária. O cliente logado é {user['nome']} (ID: {user['id']}).\n"
        f"O roteador identificou que a intenção do cliente é: **{intencao}**.\n"
        f"Acione a ferramenta correspondente usando os dados fornecidos pelo usuário. "
        f"Se faltar algum dado obrigatório (como valor, nome, agência, conta ou dígito na transferência), "
        f"peça ao usuário antes de chamar a ferramenta."
    )
    
    messages = [{"role": "system", "content": sistema_prompt}] + state["messages"]
    response = llm_executor.invoke(messages)
    return {"messages": [response]}

# --- DECISÃO PÓS-TRANSACIONAL ---
def verificar_tool_call(state: EstadoAgenteRoteado) -> Literal["tools", END]:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# --- CONSTRUÇÃO DO GRAFO ---
workflow = StateGraph(EstadoAgenteRoteado)

# Adicionando os nós explícitos
workflow.add_node("classificador", classificador_intencao)
workflow.add_node("agente_conversacional", agente_conversacional)
workflow.add_node("agente_transacional", agente_transacional)
workflow.add_node("tools", ToolNode(ALL_TOOLS))

# Fluxo de entrada -> Classificador
workflow.add_edge(START, "classificador")

# Roteamento condicional baseado na classificação explícita
workflow.add_conditional_edges(
    "classificador",
    rotear_por_intencao,
    {
        "agente_transacional": "agente_transacional",
        "agente_conversacional": "agente_conversacional"
    }
)

# Saídas dos agentes
workflow.add_edge("agente_conversacional", END)
workflow.add_conditional_edges("agente_transacional", verificar_tool_call, {"tools": "tools", END: END})
workflow.add_edge("tools", "agente_transacional")

# Compilação com Human-in-the-Loop antes de executar qualquer tool
memory = MemorySaver()
grafo = workflow.compile(checkpointer=memory, interrupt_before=["tools"])