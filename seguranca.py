import base64
import ssl
 
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
 
CERTIFICADO_PADRAO = "certificado.pem"
CHAVE_PADRAO = "chave.pem"
 
 
# ------------------------------------------------------------------ TLS
 
def criar_contexto_servidor(certfile: str = CERTIFICADO_PADRAO, keyfile: str = CHAVE_PADRAO) -> ssl.SSLContext:
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return contexto
 
 
def criar_contexto_cliente(certfile: str = CERTIFICADO_PADRAO) -> ssl.SSLContext:
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.load_verify_locations(cafile=certfile)
    # Certificado autoassinado sem DNS real (usamos IP/localhost) — desligamos
    # a checagem de hostname mas MANTEMOS a validação da cadeia do certificado.
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_REQUIRED
    return contexto
 
 
# ------------------------------------------------------- assinatura digital
 
def gerar_par_chaves():
    chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return chave_privada, chave_privada.public_key()
 
 
def serializar_chave_publica(chave_publica) -> str:
    return chave_publica.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
 
 
def carregar_chave_publica(pem_texto: str):
    return serialization.load_pem_public_key(pem_texto.encode("ascii"))
 
 
def assinar(chave_privada, dados: bytes) -> str:
    assinatura = chave_privada.sign(
        dados,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(assinatura).decode("ascii")
 
 
def verificar(chave_publica_pem: str, dados: bytes, assinatura_base64: str) -> bool:
    try:
        chave_publica = carregar_chave_publica(chave_publica_pem)
        chave_publica.verify(
            base64.b64decode(assinatura_base64),
            dados,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False
 
 
def dados_para_assinar(remetente: str, destinatario: str, id_mensagem: str, texto: str) -> bytes:
    """Monta de forma determinística os bytes que são assinados/verificados."""
    return f"{remetente}|{destinatario}|{id_mensagem}|{texto}".encode("utf-8")