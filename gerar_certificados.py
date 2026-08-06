import datetime

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def gerar_certificado(caminho_chave: str = "chave.pem", caminho_certificado: str = "certificado.pem") -> None:
    chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    nome = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Federacao Ficticia"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    agora = datetime.datetime.now(datetime.timezone.utc)

    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)  # autoassinado: emissor == titular
        .public_key(chave_privada.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora)
        .not_valid_after(agora + datetime.timedelta(days=365))
        .sign(chave_privada, hashes.SHA256())
    )

    with open(caminho_chave, "wb") as arquivo:
        arquivo.write(chave_privada.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(caminho_certificado, "wb") as arquivo:
        arquivo.write(certificado.public_bytes(serialization.Encoding.PEM))

    print(f"Gerado: {caminho_certificado} (público) e {caminho_chave} (privado, não compartilhar).")


if __name__ == "__main__":
    gerar_certificado()