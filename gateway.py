import socket
import threading
 
from protocolo import enviar_json, receber_json, IDENTIFICACAO, ERRO, REDIRECIONAMENTO
from topologia import ILHAS, indice_ilha
from seguranca import criar_contexto_servidor

HOST = "0.0.0.0"
PORTA = 8080
 
 
def enviar_erro(conexao: socket.socket, motivo: str) -> None:
    enviar_json(conexao, {
        "cabecalho": {"tipo": ERRO, "remetente": None, "destinatario": None, "id_mensagem": None},
        "corpo": {"mensagem": motivo},
    })
 
 
def atender_cliente(conexao: socket.socket, endereco: tuple[str, int]) -> None:
    try:
        mensagem = receber_json(conexao)
        cabecalho = mensagem.get("cabecalho", {})
 
        if cabecalho.get("tipo") != IDENTIFICACAO:
            enviar_erro(conexao, "Gateway espera uma mensagem IDENTIFICACAO")
            return
 
        usuario = cabecalho.get("remetente")
        if not usuario:
            enviar_erro(conexao, "Identificação inválida")
            return
 
        ilha = ILHAS[indice_ilha(usuario)]
        print(f"{usuario} -> {ilha['nome']} ({ilha['host']}:{ilha['porta']})")
 
        enviar_json(conexao, {
            "cabecalho": {
                "tipo": REDIRECIONAMENTO,
                "remetente": None,
                "destinatario": usuario,
                "id_mensagem": cabecalho.get("id_mensagem"),
            },
            "corpo": {"host": ilha["host"], "porta": ilha["porta"], "ilha": ilha["nome"]},
        })
 
    except Exception as erro:
        print(f"Erro atendendo {endereco}: {erro}")
    finally:
        conexao.close()
 
 
def iniciar_gateway() -> None:
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind((HOST, PORTA))
    servidor.listen()
    servidor_tls = criar_contexto_servidor().wrap_socket(servidor, server_side=True)
 
    print(f"Gateway escutando em {HOST}:{PORTA} (TLS)")
    print(f"Ilhas conhecidas: {[i['nome'] for i in ILHAS]}")
 
    try:
        while True:
            conexao, endereco = servidor_tls.accept()
            threading.Thread(target=atender_cliente, args=(conexao, endereco), daemon=True).start()
    except KeyboardInterrupt:
        print("\nEncerrando gateway.")
    finally:
        servidor_tls.close()
 
 
if __name__ == "__main__":
    iniciar_gateway()