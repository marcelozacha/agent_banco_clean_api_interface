# database.py
# Este arquivo gerencia a persistência dos dados do banco em um arquivo JSON, incluindo contas de usuários e saldos.

import json
import os
from typing import Dict

ARQUIVO_DB = "banco.json"

# Dados padrão caso o arquivo ainda não exista
DADOS_INICIAIS: Dict[str, dict] = {
    "user_marcelo": {
        "id": "user_marcelo",
        "nome": "Marcelo",
        "agencia": "0001",
        "conta": "12345",
        "digito": "6",
        "codigo": "M01",
        "saldo": 5000.00
    },
    "user_daiane": {
        "id": "user_daiane",
        "nome": "Daiane",
        "agencia": "0001",
        "conta": "54321",
        "digito": "0",
        "codigo": "D02",
        "saldo": 3500.00
    }
}

def carregar_banco() -> Dict[str, dict]:
    """Carrega o banco de dados do arquivo JSON ou cria com os dados padrão."""
    if os.path.exists(ARQUIVO_DB):
        try:
            with open(ARQUIVO_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DADOS_INICIAIS
    return DADOS_INICIAIS

def salvar_banco():
    """Salva o estado atual do banco de dados no arquivo JSON."""
    with open(ARQUIVO_DB, "w", encoding="utf-8") as f:
        json.dump(CONTAS_DB, f, indent=4, ensure_ascii=False)

# Inicializa a base de dados em memória a partir do arquivo JSON
CONTAS_DB: Dict[str, dict] = carregar_banco()

# Estado da sessão simulando o usuário logado atualmente
class SessaoUsuario:
    usuario_atual_id: str = "user_marcelo"  # Começa logado como Marcelo

def obter_usuario_logado() -> dict:
    return CONTAS_DB[SessaoUsuario.usuario_atual_id]

def alternar_usuario(user_id: str):
    if user_id in CONTAS_DB:
        SessaoUsuario.usuario_atual_id = user_id
        return True
    return False