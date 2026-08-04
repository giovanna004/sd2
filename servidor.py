import socket
import threading
import sys

from protocolo import (
    enviar_json,
    receber_json,
    IDENTIFICACAO,
    ACK,
    ERRO,
    DESCONECTAR,
    CHUNK_ARQUIVO,
    ENCAMINHAR_ENTRE_ILHAS,
    TIPOS_ENCAMINHAVEIS,
)

from topologia import ILHAS, indice_ilha
from seguranca import criar_contexto_servidor, criar_contexto_cliente

HOST = "0.0.0.0"
PORTA = 8080

clientes: dict[str, tuple[socket.socket, threading.Lock]] = {}
clientes_lock = threading.Lock()

meu_indice: int = 0  # definido em main() a partir do argumento de linha de comando

conexoes_peer: dict[int, tuple[socket.socket, threading.Lock]] = {}
conexoes_peer_lock = threading.Lock()

def registrar_usuario(usuario: str, conexao: socket.socket, lock: threading.Lock) -> None:
    with clientes_lock:
        if usuario in clientes:
            raise ValueError("Usuário já conectado")
        clientes[usuario] = (conexao, lock)


def remover_usuario(usuario: str | None) -> None:
    if usuario is None:
        return
    with clientes_lock:
        clientes.pop(usuario, None)


def entregar_localmente(mensagem: dict) -> bool:
    """Tenta entregar para um usuário conectado NESTA ilha."""
    destinatario = mensagem.get("cabecalho", {}).get("destinatario")
    with clientes_lock:
        entrada = clientes.get(destinatario)
    if entrada is None:
        return False
    conexao_destino, lock_envio = entrada
    with lock_envio:  # serializa envios concorrentes para o mesmo socket
        enviar_json(conexao_destino, mensagem)
    return True

def obter_conexao_peer(indice_destino: int) -> tuple[socket.socket, threading.Lock] | None:
    """Devolve a conexão persistente com o broker da ilha indicada, abrindo uma nova se preciso."""
    with conexoes_peer_lock:
        entrada = conexoes_peer.get(indice_destino)
        if entrada is not None:
            return entrada
 
        ilha = ILHAS[indice_destino]
        try:
            bruta = socket.create_connection((ilha["host"], ilha["porta"]), timeout=5)
            conexao = criar_contexto_cliente().wrap_socket(bruta)
        except OSError as erro:
            print(f"Falha ao conectar com {ilha['nome']}: {erro}")
            return None
 
        entrada = (conexao, threading.Lock())
        conexoes_peer[indice_destino] = entrada
        return entrada


def repassar_para_ilha_remota(mensagem: dict, indice_destino: int, ilha_destino: dict) -> bool:
    entrada = obter_conexao_peer(indice_destino)
    if entrada is None:
        return False
 
    conexao_peer, lock_peer = entrada
    try:
        with lock_peer:
            enviar_json(conexao_peer, {
                "cabecalho": {"tipo": ENCAMINHAR_ENTRE_ILHAS, "remetente": None, "destinatario": None, "id_mensagem": None},
                "corpo": {"mensagem": mensagem},
            })
        return True
    except OSError as erro:
        print(f"Conexão com {ilha_destino['nome']} caiu ({erro}); será reaberta na próxima tentativa.")
        with conexoes_peer_lock:
            conexoes_peer.pop(indice_destino, None)
        return False
 

def encaminhar_ou_repassar(mensagem: dict) -> str:
    """Entrega local se possível; senão repassa para a ilha correta. Devolve um status para o ACK."""
    if entregar_localmente(mensagem):
        return "ENTREGUE"
 
    destinatario = mensagem.get("cabecalho", {}).get("destinatario")
    indice_destino = indice_ilha(destinatario)
 
    if indice_destino == meu_indice:
        return "DESTINATARIO_OFFLINE"
 
    ilha_destino = ILHAS[indice_destino]
    if repassar_para_ilha_remota(mensagem, indice_destino, ilha_destino):
        return "REPASSADO_ILHA_REMOTA"
    return "ILHA_REMOTA_INDISPONIVEL"


def enviar_ack(conexao: socket.socket, lock: threading.Lock, id_mensagem: str | None, status: str) -> None:
    with lock:
        enviar_json(conexao, {
            "cabecalho": {"tipo": ACK, "remetente": None, "destinatario": None, "id_mensagem": id_mensagem},
            "corpo": {"status": status},
        })


def enviar_erro(conexao: socket.socket, lock: threading.Lock, motivo: str) -> None:
    with lock:
        enviar_json(conexao, {
            "cabecalho": {"tipo": ERRO, "remetente": None, "destinatario": None, "id_mensagem": None},
            "corpo": {"mensagem": motivo},
        })


def atender_cliente(conexao: socket.socket, endereco: tuple[str, int]) -> None:
    usuario: str | None = None
    # Lock próprio desta conexão: usado tanto para o que ESTA thread escreve
    # diretamente (ACKs, erros) quanto pelo que outras threads escrevem via
    # entregar_localmente — garante que nunca duas escritas se intercalem.
    lock_conexao = threading.Lock()
    print(f"Conexão recebida: {endereco}")
 
    try:
        while True:
            mensagem = receber_json(conexao)
            cabecalho = mensagem.get("cabecalho", {})
            tipo = cabecalho.get("tipo")
            id_mensagem = cabecalho.get("id_mensagem")
 
            if tipo == ENCAMINHAR_ENTRE_ILHAS:
                mensagem_original = mensagem.get("corpo", {}).get("mensagem")
                if mensagem_original:
                    entregar_localmente(mensagem_original)
                # Não fazemos break: esta conexão é o link persistente com o broker
                # de origem e continuará recebendo repasses futuros nesta mesma conexão.
                continue
 
            if tipo == IDENTIFICACAO:
                usuario_recebido = cabecalho.get("remetente")
 
                if not usuario_recebido:
                    enviar_erro(conexao, lock_conexao, "Identificação inválida")
                    continue
 
                try:
                    registrar_usuario(usuario_recebido, conexao, lock_conexao)
                except ValueError as erro:
                    enviar_erro(conexao, lock_conexao, str(erro))
                    continue
 
                usuario = usuario_recebido
                enviar_ack(conexao, lock_conexao, id_mensagem, "IDENTIFICADO")
 
            elif tipo in TIPOS_ENCAMINHAVEIS:
                if usuario is None:
                    enviar_erro(conexao, lock_conexao, "Cliente não identificado")
                    continue
 
                status = encaminhar_ou_repassar(mensagem)
 
                if tipo != CHUNK_ARQUIVO:
                    enviar_ack(conexao, lock_conexao, id_mensagem, status)
 
            elif tipo == DESCONECTAR:
                break
 
            else:
                enviar_erro(conexao, lock_conexao, f"Tipo não reconhecido: {tipo}")
 
    except Exception as erro:
        print(f"Conexão encerrada ({endereco}): {erro}")
 
    finally:
        remover_usuario(usuario)
        conexao.close()
        print(f"Conexão finalizada: {endereco}")
 

def iniciar_servidor(porta: int) -> None:
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((HOST, porta))
    servidor.listen()
    servidor_tls = criar_contexto_servidor().wrap_socket(servidor, server_side=True)
 
    print(f"Broker '{ILHAS[meu_indice]['nome']}' escutando em {HOST}:{porta} (TLS)")
 
    try:
        while True:
            conexao, endereco = servidor_tls.accept()
            thread = threading.Thread(target=atender_cliente, args=(conexao, endereco), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\nEncerrando broker.")
    finally:
        servidor_tls.close()
 
 
def main() -> None:
    global meu_indice
 
    if len(sys.argv) < 2:
        print("Uso: python3 servidor.py <indice_da_ilha>")
        print(f"Ilhas disponíveis: {[(i, ILHAS[i]['nome']) for i in range(len(ILHAS))]}")
        sys.exit(1)
 
    meu_indice = int(sys.argv[1])
    porta = ILHAS[meu_indice]["porta"]
    iniciar_servidor(porta)
 

if __name__ == "__main__":
    iniciar_servidor()
