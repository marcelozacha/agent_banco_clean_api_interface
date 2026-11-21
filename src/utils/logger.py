# logger.py
# Este arquivo gerencia a observabilidade do sistema, registrando operações bancárias e eventos do agente em arquivos de log separados.

# logger.py
import json
import os
from datetime import datetime

ARQUIVO_LOG_OPERACAO = "extrato_operacoes.log"
ARQUIVO_LOG_OBSERVABILIDADE = "agent_observabilidade.log"

def registrar_operacao_bancaria(tipo_operacao: str, usuario_nome: str, valor: float, detalhes: str = ""):
    """Registra operações bancárias (saque, depósito, transferência) em arquivo em formato JSON por linha para facilitar a consulta no extrato."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    registro = {
        "timestamp": timestamp,
        "usuario": usuario_nome,
        "operacao": tipo_operacao.upper(),
        "valor": valor,
        "detalhes": detalhes
    }
    
    #linha_log = f"[{timestamp}] | USUÁRIO: {usuario_nome} | OP: {tipo_operacao.upper()} | VALOR: R$ {valor:.2f} | DETALHES: {detalhes}\n"
    try:
        with open(ARQUIVO_LOG_OPERACAO, "a", encoding="utf-8") as f:
            #f.write(linha_log)
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Erro ao gravar log de operação: {e}")

def obter_extrato_usuario(usuario_nome: str, limite: int = 5) -> list[dict]:
    """Lê o arquivo de log e retorna as últimas operações do usuário especificado."""
    #to-do: Implementar paginação ou filtros adicionais se necessário, como data inicial/final, tipo de operação, etc.
    #limite: número máximo de operações a retornar (padrão 5), mas poderia ser ultima semana, ultumo mês, etc.
    if not os.path.exists(ARQUIVO_LOG_OPERACAO):
        return []
    
    operacoes = []
    try:
        with open(ARQUIVO_LOG_OPERACAO, "r", encoding="utf-8") as f:
            for linha in f:
                if linha.strip():
                    dados = json.loads(linha)
                    if dados.get("usuario", "").lower() == usuario_nome.lower():
                        operacoes.append(dados)
    except Exception:
        return []
        
    # Retorna as últimas operações (do mais recente para o mais antigo, limitado ao parâmetro)
    return operacoes[-limite:][::-1]


def registrar_observabilidade_llm(tipo_evento: str, dados: dict):
    """Registra eventos de observabilidade do agente em arquivo em formato JSON por linha para facilitar a análise posterior."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {"timestamp": timestamp,
               "tipo_evento": tipo_evento, 
               "dados": dados}
    try:
        with open(ARQUIVO_LOG_OBSERVABILIDADE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Erro ao gravar log de observabilidade: {e}")