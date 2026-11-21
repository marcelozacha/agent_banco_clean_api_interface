# Você pode expor as duas versões para alternar facilmente se quiser
from .graph import grafo as grafo_react
from .graph2 import grafo as grafo_roteador

__all__ = ["grafo_react", "grafo_roteador"]