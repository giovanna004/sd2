import functools
from typing import Dict, List
 
 
class RelogioVetorial:
    def __init__(self, meu_id: str):
        self.meu_id = meu_id
        self._relogio: Dict[str, int] = {}
 
    def marcar_envio(self) -> Dict[str, int]:
        self._relogio[self.meu_id] = self._relogio.get(self.meu_id, 0) + 1
        return dict(self._relogio)
 
    def marcar_recebimento(self, relogio_recebido: Dict[str, int]) -> Dict[str, int]:
        for usuario, contador in relogio_recebido.items():
            self._relogio[usuario] = max(self._relogio.get(usuario, 0), contador)
        self._relogio[self.meu_id] = self._relogio.get(self.meu_id, 0) + 1
        return dict(self._relogio)
 
 
def precede_causalmente(a: Dict[str, int], b: Dict[str, int]) -> bool:
    """True se o evento `a` aconteceu-antes de `b` (a -> b)."""
    chaves = set(a) | set(b)
    menor_ou_igual = all(a.get(k, 0) <= b.get(k, 0) for k in chaves)
    estritamente_menor = any(a.get(k, 0) < b.get(k, 0) for k in chaves)
    return menor_ou_igual and estritamente_menor
 
 
def ordenar_historico(historico: List[dict]) -> List[dict]:
    """
    Ordena entradas no formato {"relogio": {...}, ...} respeitando a ordem
    causal. Quando dois eventos são concorrentes (nenhum precede o outro),
    o desempate é pela ordem de chegada na lista original.
    """
    def comparar(x, y):
        if precede_causalmente(x["relogio"], y["relogio"]):
            return -1
        if precede_causalmente(y["relogio"], x["relogio"]):
            return 1
        return 0
 
    return sorted(historico, key=functools.cmp_to_key(comparar))