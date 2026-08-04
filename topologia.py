import hashlib

ILHAS = [
    {"nome": "Ilha A", "host": "127.0.0.1", "porta": 9001},
    {"nome": "Ilha B", "host": "127.0.0.1", "porta": 9002},
]

def indice_ilha(usuario: str) -> int:
    digest = hashlib.sha256(usuario.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % len(ILHAS)