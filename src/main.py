# main.py
# Este arquivo é o ponto de entrada do sistema, integrando o grafo de estados do agente bancário com a interface de linha de comando (CLI) para interação com o usuário. Ele gerencia a execução do grafo, a entrada do usuário e a observabilidade das operações.

# main.py (Exemplo de imports limpos)
from src.agents.graph import   grafo  # <-- importa o grafo de estados do agente bancário
from src.core import obter_usuario_logado, alternar_usuario, salvar_banco
from src.security import aplicar_guardrails, aplicar_guardrail_ia, aplicar_todos_guardrails # <-- importa as funções de guardrails do arquivo guardrails.py
from src.utils import registrar_observabilidade_llm #para logar prompts, chains, tool calls e parâmetros 

from langchain_core.messages import HumanMessage


def rodar_chat():
    '''Função principal que gerencia a interação do usuário com o agente bancário via CLI, incluindo a execução do grafo, aplicação de guardrails e registro de observabilidade.'''

    config = {"configurable": {"thread_id": "sessao_banco_1"}}
    
    print("=== BANCO DIGITAL IA (Ollama + LangGraph) ===")
    print(f"Logado inicialmente como: {obter_usuario_logado()['nome']}")
    print("Comandos especiais: /usuario (trocar usuário), /sair")
    
    while True:
        user_input = input("\n> ").strip()
        
        if user_input.lower() == "/sair":
            salvar_banco()
            print("💾 Dados salvos com sucesso. Até logo!")
            break
            
        if user_input.lower() == "/usuario":
            print("\nEscolha o usuário:")
            print("1. Marcelo (user_marcelo)")
            print("2. Daiane (user_daiane)")
            escolha = input("Opção: ").strip()
            if escolha == "1":
                alternar_usuario("user_marcelo")
            elif escolha == "2":
                alternar_usuario("user_daiane")
            print(f"-> Usuário alterado para: {obter_usuario_logado()['nome']}")
            continue


       # 🛑 2. APLICAR O GUARDRAIL AQUI (Antes de qualquer processamento)
        aprovado, mensagem_erro = aplicar_todos_guardrails(user_input)
        if not aprovado:
            print(f"\nAgente: {mensagem_erro}")
            # Registra no log de observabilidade que uma tentativa foi bloqueada
            registrar_observabilidade_llm("GUARDRAIL_BLOCK", {"input": user_input, "motivo": mensagem_erro})
            continue  # Descarta a entrada e pede o próximo input

        # 🎯 3. Log de prompt normal (se passou no guardrail)
        registrar_observabilidade_llm("PROMPT_USER", {"input": user_input, "usuario": obter_usuario_logado()['nome']})
        
        # Inserir a mensagem do usuário no estado do grafo
        inputs = {"messages": [HumanMessage(content=user_input)]}
        
        # Executar o grafo até encontrar uma interrupção (Human-in-the-Loop antes das tools)
        events = grafo.stream(inputs, config, stream_mode="values")
        for event in events:
            if "messages" in event:
                latest_msg = event["messages"][-1]
                # Se houver tool_calls, significa que o agente quer executar uma transação sensível
                if hasattr(latest_msg, "tool_calls") and latest_msg.tool_calls:
                    print("\n--- 🛑 HUMAN-IN-THE-LOOP: CONFIRMAÇÃO NECESSÁRIA ---")
                    for tc in latest_msg.tool_calls:
                        print(f"Operação solicitada: {tc['name'].upper()}")
                        print(f"Detalhes/Parâmetros: {tc['args']}")

                        #ENTRADA 2: Ao detectar a tool call e seus parâmetros gerados pelo agente
                        registrar_observabilidade_llm("TOOL_CALL", {"tool": tc["name"], "args": tc["args"]})
                    
                    
                    confirmacao = input("\nDeseja aprovar e executar esta operação? (s/n): ").strip().lower()
                    if confirmacao != 's':
                        print("❌ Operação cancelada pelo usuário.")
                        #ENTRADA 3: Ao detectar CANCELAMENTO da tool call e seus parâmetros gerados pelo agente
                        registrar_observabilidade_llm("TOOL_CALL_CANCELADA", {"tool": tc["name"], "args": tc["args"]})
                        break
                else:
                    if latest_msg.content:
                        print(f"\nAgente: {latest_msg.content}")

        # Se o grafo parou na interrupção e o usuário aprovou ('s'), continuamos a execução do grafo
        state = grafo.get_state(config)
        if state.next: 
            if 'confirmacao' in locals() and confirmacao == 's':
                print("\n🔄 Executando operação aprovada...")
                resumi_eventos = grafo.stream(None, config, stream_mode="values")
                for event in resumi_eventos:
                    if "messages" in event:
                        latest_msg = event["messages"][-1]
                        if latest_msg.content and not hasattr(latest_msg, "tool_calls"):
                            print(f"\nAgente: {latest_msg.content}")

if __name__ == "__main__":
    rodar_chat()