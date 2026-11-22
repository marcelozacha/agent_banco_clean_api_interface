# src/core/database.py
# Este arquivo gerencia a persistência dos dados do banco em um arquivo JSON, incluindo contas de usuários e saldos.

import json
from pathlib import Path
from typing import Dict

PASTA_CORE = Path(__file__).resolve().parent
ARQUIVO_DB = PASTA_CORE / "banco.json"

# Dados padrão caso o arquivo ainda não exista
DADOS_INICIAIS: Dict[str, dict] = {
    "user_marcelo": {
        "id": "user_marcelo",
        "nome": "Marcelo",
        "agencia": "0001",
        "conta": "12345",
        "digito": "6",
        "codigo": "M01",
        "saldo": 5000.00,
    },
    "user_daiane": {
        "id": "user_daiane",
        "nome": "Daiane",
        "agencia": "0001",
        "conta": "54321",
        "digito": "0",
        "codigo": "D02",
        "saldo": 3500.00,
    },
}


def carregar_banco() -> Dict[str, dict]:
    """Carrega o banco de dados de src/core/banco.json ou cria com os dados padrão."""
    if ARQUIVO_DB.exists():
        try:
            with open(ARQUIVO_DB, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, dict) and dados:
                    return dados
        except Exception:
            pass

    salvar_banco(DADOS_INICIAIS)
    return {k: dict(v) for k, v in DADOS_INICIAIS.items()}


def salvar_banco(dados: Dict[str, dict] | None = None) -> None:
    """Salva o estado atual do banco de dados em src/core/banco.json."""
    alvo = dados if dados is not None else CONTAS_DB
    ARQUIVO_DB.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_DB, "w", encoding="utf-8") as f:
        json.dump(alvo, f, indent=4, ensure_ascii=False)


# Inicializa a base de dados em memória a partir de src/core/banco.json
CONTAS_DB: Dict[str, dict] = carregar_banco()


# Estado da sessão simulando o usuário logado atualmente
class SessaoUsuario:
    usuario_atual_id: str = "user_marcelo"  # Começa logado como Marcelo


def obter_usuario_logado() -> dict:
    return CONTAS_DB[SessaoUsuario.usuario_atual_id]


def alternar_usuario(user_id: str) -> bool:
    if user_id in CONTAS_DB:
        SessaoUsuario.usuario_atual_id = user_id
        return True
    return False