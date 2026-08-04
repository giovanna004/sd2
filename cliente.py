import socket
import sys
import os
import base64
import hashlib
import threading
import uuid

from protocolo import (
    enviar_json,
    receber_json,
    TAMANHO_CHUNK,
    IDENTIFICACAO,
    ACK,
    ERRO,
    MSG_TEXTO,
    ENVIO_ARQUIVO,
    CHUNK_ARQUIVO,
    FIM_ARQUIVO,
    DESCONECTAR,
)

from seguranca import (
    criar_contexto_cliente,
    gerar_par_chaves,
    serializar_chave_publica,
    assinar,
    verificar,
    dados_para_assinar,
)
from relogio_vetorial import RelogioVetorial, ordenar_historico

PASTA_RECEBIDOS = "recebidos"

# id_transferencia -> {"remetente", "nome_arquivo", "num_chunks", "chunks": [...]}
transferencias_em_andamento: dict[str, dict] = {}

historico: list[dict] = []

relogio: "RelogioVetorial | None" = None
chave_privada = None
chave_publica_pem: str = ""

def novo_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------- recepção

def tratar_arquivo_inicio(cabecalho: dict, corpo: dict) -> None:
    id_transferencia = cabecalho["id_mensagem"]
    transferencias_em_andamento[id_transferencia] = {
        "remetente": cabecalho.get("remetente"),
        "nome_arquivo": corpo["nome_arquivo"],
        "num_chunks": corpo["num_chunks"],
        "chunks": [None] * corpo["num_chunks"],
    }
    print(f"\n[Recebendo arquivo '{corpo['nome_arquivo']}' de {cabecalho.get('remetente')}...]")


def tratar_arquivo_chunk(cabecalho: dict, corpo: dict) -> None:
    transferencia = transferencias_em_andamento.get(cabecalho["id_mensagem"])
    if transferencia is None:
        return
    transferencia["chunks"][corpo["seq"]] = base64.b64decode(corpo["dados_base64"])


def tratar_arquivo_fim(cabecalho: dict, corpo: dict) -> None:
    transferencia = transferencias_em_andamento.pop(cabecalho["id_mensagem"], None)
    if transferencia is None:
        return

    if any(pedaco is None for pedaco in transferencia["chunks"]):
        print(f"\n[Arquivo '{transferencia['nome_arquivo']}' incompleto — pedaços faltando.]")
        return

    conteudo = b"".join(transferencia["chunks"])
    hash_calculado = hashlib.sha256(conteudo).hexdigest()

    if hash_calculado != corpo["hash_sha256"]:
        print(f"\n[ERRO: hash de '{transferencia['nome_arquivo']}' não confere — arquivo descartado.]")
        return

    os.makedirs(PASTA_RECEBIDOS, exist_ok=True)
    caminho = os.path.join(PASTA_RECEBIDOS, transferencia["nome_arquivo"])
    with open(caminho, "wb") as arquivo:
        arquivo.write(conteudo)

    print(f"\n[Arquivo '{transferencia['nome_arquivo']}' recebido de {transferencia['remetente']} -> {caminho}]")

def tratar_texto_recebido(cabecalho: dict, corpo: dict) -> None:
    remetente = cabecalho.get("remetente")
    destinatario = cabecalho.get("destinatario")
    texto = corpo.get("texto")
    id_mensagem = cabecalho.get("id_mensagem")
 
    relogio_recebido = corpo.get("relogio_vetorial", {})
    relogio_local = relogio.marcar_recebimento(relogio_recebido)
 
    chave_publica_remetente = corpo.get("chave_publica")
    assinatura = corpo.get("assinatura")
    assinatura_ok = False
    if chave_publica_remetente and assinatura:
        dados = dados_para_assinar(remetente, destinatario, id_mensagem, texto)
        assinatura_ok = verificar(chave_publica_remetente, dados, assinatura)
 
    selo = "assinatura válida" if assinatura_ok else "SEM assinatura válida"
    historico.append({
        "remetente": remetente, "destinatario": destinatario, "texto": texto,
        "id_mensagem": id_mensagem, "relogio": relogio_local, "assinatura_ok": assinatura_ok,
    })
 
    print(f"\n[{remetente}]: {texto}  ({selo})\n> ", end="", flush=True)

def escutar_servidor(conexao) -> None:
    try:
        while True:
            mensagem = receber_json(conexao)
            cabecalho = mensagem.get("cabecalho", {})
            corpo = mensagem.get("corpo", {})
            tipo = cabecalho.get("tipo")
 
            if tipo == MSG_TEXTO:
                tratar_texto_recebido(cabecalho, corpo)
            elif tipo == ENVIO_ARQUIVO:
                tratar_arquivo_inicio(cabecalho, corpo)
            elif tipo == CHUNK_ARQUIVO:
                tratar_arquivo_chunk(cabecalho, corpo)
            elif tipo == FIM_ARQUIVO:
                tratar_arquivo_fim(cabecalho, corpo)
                print("> ", end="", flush=True)
            elif tipo == ERRO:
                print(f"\n[ERRO do servidor: {corpo.get('mensagem')}]\n> ", end="", flush=True)
            elif tipo == ACK:
                pass  # útil para depuração; omitido para não poluir o terminal
    except (ConnectionError, OSError):
        print("\n[Conexão com o servidor encerrada.]")
        os._exit(0)


# ------------------------------------------------------------------ envio

def enviar_texto(conexao, usuario: str, destinatario: str, texto: str) -> None:
    id_mensagem = novo_id()
    relogio_local = relogio.marcar_envio()
 
    dados = dados_para_assinar(usuario, destinatario, id_mensagem, texto)
    assinatura = assinar(chave_privada, dados)
 
    enviar_json(conexao, {
        "cabecalho": {"tipo": MSG_TEXTO, "remetente": usuario, "destinatario": destinatario, "id_mensagem": id_mensagem},
        "corpo": {
            "texto": texto,
            "relogio_vetorial": relogio_local,
            "assinatura": assinatura,
            "chave_publica": chave_publica_pem,
        },
    })
 
    historico.append({
        "remetente": usuario, "destinatario": destinatario, "texto": texto,
        "id_mensagem": id_mensagem, "relogio": relogio_local, "assinatura_ok": True,
    })


def enviar_arquivo(conexao, usuario: str, destinatario: str, caminho: str) -> None:
    if not os.path.isfile(caminho):
        print(f"[Arquivo '{caminho}' não encontrado.]")
        return
 
    with open(caminho, "rb") as arquivo:
        conteudo = arquivo.read()
 
    nome_arquivo = os.path.basename(caminho)
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()
    id_transferencia = novo_id()
 
    pedacos = [conteudo[i:i + TAMANHO_CHUNK] for i in range(0, len(conteudo), TAMANHO_CHUNK)] or [b""]
 
    enviar_json(conexao, {
        "cabecalho": {"tipo": ENVIO_ARQUIVO, "remetente": usuario, "destinatario": destinatario, "id_mensagem": id_transferencia},
        "corpo": {"nome_arquivo": nome_arquivo, "tamanho": len(conteudo), "num_chunks": len(pedacos)},
    })
 
    for seq, pedaco in enumerate(pedacos):
        enviar_json(conexao, {
            "cabecalho": {"tipo": CHUNK_ARQUIVO, "remetente": usuario, "destinatario": destinatario, "id_mensagem": id_transferencia},
            "corpo": {"seq": seq, "dados_base64": base64.b64encode(pedaco).decode("ascii")},
        })
 
    enviar_json(conexao, {
        "cabecalho": {"tipo": FIM_ARQUIVO, "remetente": usuario, "destinatario": destinatario, "id_mensagem": id_transferencia},
        "corpo": {"hash_sha256": hash_sha256},
    })
 
    print(f"[Arquivo '{nome_arquivo}' enviado para {destinatario} em {len(pedacos)} pedaço(s).]")

def mostrar_historico() -> None:
    if not historico:
        print("[Histórico vazio.]")
        return
    print("--- Histórico (ordem causal, via relógio vetorial) ---")
    for entrada in ordenar_historico(historico):
        selo = "OK" if entrada["assinatura_ok"] else "!!"
        print(f"[{selo}] {entrada['remetente']} -> {entrada['destinatario']}: {entrada['texto']}  {entrada['relogio']}")

# ------------------------------------------------------------------ main

def descobrir_broker(usuario: str, contexto_tls, gateway_host: str, gateway_porta: int) -> tuple[str, int, str]:
    """Consulta o gateway (via TLS) e devolve (host, porta, nome_da_ilha) do broker responsável."""
    bruta = socket.create_connection((gateway_host, gateway_porta))
    conexao_gateway = contexto_tls.wrap_socket(bruta)
 
    enviar_json(conexao_gateway, {
        "cabecalho": {"tipo": IDENTIFICACAO, "remetente": usuario, "destinatario": None, "id_mensagem": novo_id()},
        "corpo": {},
    })
    resposta = receber_json(conexao_gateway)
    conexao_gateway.close()
 
    if resposta.get("cabecalho", {}).get("tipo") == ERRO:
        raise RuntimeError(resposta.get("corpo", {}).get("mensagem", "erro desconhecido no gateway"))
 
    corpo = resposta["corpo"]
    return corpo["host"], corpo["porta"], corpo["ilha"]

def main() -> None:
    global relogio, chave_privada, chave_publica_pem
 
    if len(sys.argv) < 2:
        print("Uso: python cliente.py <usuario> [gateway_host] [gateway_porta]")
        sys.exit(1)
 
    usuario = sys.argv[1]
    gateway_host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    gateway_porta = int(sys.argv[3]) if len(sys.argv) > 3 else 8080
 
    relogio = RelogioVetorial(usuario)
    chave_privada, chave_publica = gerar_par_chaves()
    chave_publica_pem = serializar_chave_publica(chave_publica)
 
    contexto_tls = criar_contexto_cliente()
 
    try:
        broker_host, broker_porta, nome_ilha = descobrir_broker(usuario, contexto_tls, gateway_host, gateway_porta)
    except (RuntimeError, ConnectionError, OSError) as erro:
        print(f"[Não foi possível descobrir o broker via gateway: {erro}]")
        return
 
    print(f"Gateway direcionou '{usuario}' para {nome_ilha} ({broker_host}:{broker_porta})")
 
    bruta = socket.create_connection((broker_host, broker_porta))
    conexao = contexto_tls.wrap_socket(bruta)
 
    enviar_json(conexao, {
        "cabecalho": {"tipo": IDENTIFICACAO, "remetente": usuario, "destinatario": None, "id_mensagem": novo_id()},
        "corpo": {},
    })
    resposta = receber_json(conexao)
 
    if resposta.get("cabecalho", {}).get("tipo") == ERRO:
        print(f"[Falha na identificação: {resposta.get('corpo', {}).get('mensagem')}]")
        conexao.close()
        return
 
    print(f"Conectado como '{usuario}' (canal TLS estabelecido).")
    print("Comandos: /msg <usuario> <texto>  |  /arquivo <usuario> <caminho>  |  /historico  |  /sair")
 
    threading.Thread(target=escutar_servidor, args=(conexao,), daemon=True).start()
 
    while True:
        try:
            comando = input("> ")
        except EOFError:
            break
 
        if comando.startswith("/msg "):
            _, destinatario, texto = comando.split(" ", 2)
            enviar_texto(conexao, usuario, destinatario, texto)
 
        elif comando.startswith("/arquivo "):
            _, destinatario, caminho = comando.split(" ", 2)
            enviar_arquivo(conexao, usuario, destinatario, caminho)
 
        elif comando == "/historico":
            mostrar_historico()
 
        elif comando == "/sair":
            enviar_json(conexao, {
                "cabecalho": {"tipo": DESCONECTAR, "remetente": usuario, "destinatario": None, "id_mensagem": novo_id()},
                "corpo": {},
            })
            break
 
        else:
            print("Comando não reconhecido. Use /msg, /arquivo, /historico ou /sair.")
 
    conexao.close()

if __name__ == "__main__":
    main()
