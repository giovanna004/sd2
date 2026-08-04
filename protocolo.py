import socket
import struct
import json
from typing import Any

TAMANHO_MAX_MENSAGEM = 10 * 1024 * 1024  # 10 MB — protege contra JSON malformado/absurdo
TAMANHO_CHUNK = 60_000  # bytes brutos por pedaço de arquivo, antes da codificação em base64

# ---- tipos de mensagem do protocolo de aplicação ----
IDENTIFICACAO = "IDENTIFICACAO"
ACK = "ACK"
ERRO = "ERRO"
MSG_TEXTO = "MSG_TEXTO"
ENVIO_ARQUIVO = "ENVIO_ARQUIVO"
CHUNK_ARQUIVO = "CHUNK_ARQUIVO"
FIM_ARQUIVO = "FIM_ARQUIVO"
DESCONECTAR = "DESCONECTAR"

REDIRECIONAMENTO = "REDIRECIONAMENTO"        # gateway -> cliente: para qual broker ir
ENCAMINHAR_ENTRE_ILHAS = "ENCAMINHAR_ENTRE_ILHAS"  # broker -> broker: repasse de mensagem
 
# Tipos que o servidor apenas encaminha para o destinatário, sem interpretar o corpo
TIPOS_ENCAMINHAVEIS = {MSG_TEXTO, ENVIO_ARQUIVO, CHUNK_ARQUIVO, FIM_ARQUIVO}

def ler_exato(conexao: socket.socket, tamanho: int) -> bytes:
    """Lê exatamente `tamanho` bytes do socket, mesmo que recv() retorne em pedaços."""
    dados = bytearray()
    while len(dados) < tamanho:
        parte = conexao.recv(tamanho - len(dados))
        if not parte:
            raise ConnectionError("Conexão encerrada pelo outro lado.")
        dados.extend(parte)
    return bytes(dados)


def enviar_json(conexao: socket.socket, mensagem: dict[str, Any]) -> None:
    dados = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    conexao.sendall(struct.pack("!I", len(dados)))
    conexao.sendall(dados)


def receber_json(conexao: socket.socket) -> dict[str, Any]:
    cabecalho_tamanho = ler_exato(conexao, 4)
    tamanho = struct.unpack("!I", cabecalho_tamanho)[0]

    if tamanho > TAMANHO_MAX_MENSAGEM:
        raise ValueError("Mensagem acima do limite permitido.")

    dados = ler_exato(conexao, tamanho)
    return json.loads(dados.decode("utf-8"))
