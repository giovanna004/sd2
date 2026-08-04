import socket
import threading

from protocolo import (
    enviar_json,
    receber_json,
    IDENTIFICACAO,
    ACK,
    ERRO,
    DESCONECTAR,
    CHUNK_ARQUIVO,
    TIPOS_ENCAMINHAVEIS,
)

HOST = "0.0.0.0"
PORTA = 8080

clientes: dict[str, socket.socket] = {}
clientes_lock = threading.Lock()


def registrar_usuario(usuario: str, conexao: socket.socket) -> None:
    with clientes_lock:
        if usuario in clientes:
            raise ValueError("Usuário já conectado")
        clientes[usuario] = conexao


def remover_usuario(usuario: str | None) -> None:
    if usuario is None:
        return
    with clientes_lock:
        clientes.pop(usuario, None)


def encaminhar_mensagem(mensagem: dict) -> bool:
    destinatario = mensagem.get("cabecalho", {}).get("destinatario")

    with clientes_lock:
        conexao_destino = clientes.get(destinatario)

    if conexao_destino is None:
        return False

    enviar_json(conexao_destino, mensagem)
    return True


def enviar_ack(conexao: socket.socket, id_mensagem: str | None, status: str) -> None:
    enviar_json(conexao, {
        "cabecalho": {"tipo": ACK, "remetente": None, "destinatario": None, "id_mensagem": id_mensagem},
        "corpo": {"status": status},
    })


def enviar_erro(conexao: socket.socket, motivo: str) -> None:
    enviar_json(conexao, {
        "cabecalho": {"tipo": ERRO, "remetente": None, "destinatario": None, "id_mensagem": None},
        "corpo": {"mensagem": motivo},
    })


def atender_cliente(conexao: socket.socket, endereco: tuple[str, int]) -> None:
    usuario: str | None = None
    print(f"Cliente conectado: {endereco}")

    try:
        while True:
            mensagem = receber_json(conexao)
            cabecalho = mensagem.get("cabecalho", {})
            tipo = cabecalho.get("tipo")
            id_mensagem = cabecalho.get("id_mensagem")

            if tipo == IDENTIFICACAO:
                usuario_recebido = cabecalho.get("remetente")

                if not usuario_recebido:
                    enviar_erro(conexao, "Identificação inválida")
                    continue

                try:
                    registrar_usuario(usuario_recebido, conexao)
                except ValueError as erro:
                    enviar_erro(conexao, str(erro))
                    continue

                usuario = usuario_recebido
                enviar_ack(conexao, id_mensagem, "IDENTIFICADO")

            elif tipo in TIPOS_ENCAMINHAVEIS:
                if usuario is None:
                    enviar_erro(conexao, "Cliente não identificado")
                    continue

                entregue = encaminhar_mensagem(mensagem)

                # Chunks não geram ACK individual (evita sobrecarregar o canal com um arquivo grande); só confirmamos o início e o fim da transferência, e a entrega de mensagens de texto.
                if tipo != CHUNK_ARQUIVO:
                    enviar_ack(conexao, id_mensagem, "ENTREGUE" if entregue else "DESTINATARIO_OFFLINE")

            elif tipo == DESCONECTAR:
                break

            else:
                enviar_erro(conexao, f"Tipo não reconhecido: {tipo}")

    except Exception as erro:
        # captura ConnectionError, JSON malformado, ou qualquer outra falha da conexão
        print(f"Conexão encerrada ({endereco}): {erro}")

    finally:
        remover_usuario(usuario)
        conexao.close()
        print(f"Cliente desconectado: {endereco}")


def iniciar_servidor() -> None:
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((HOST, PORTA))
    servidor.listen()

    print(f"Servidor escutando em {HOST}:{PORTA}")

    try:
        while True:
            conexao, endereco = servidor.accept()
            thread = threading.Thread(target=atender_cliente, args=(conexao, endereco), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\nEncerrando servidor.")
    finally:
        servidor.close()


if __name__ == "__main__":
    iniciar_servidor()
