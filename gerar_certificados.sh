#!/bin/bash
# Gera um certificado autoassinado (o mesmo par serve para todos os
# processos locais: gateway e brokers de todas as ilhas). Em um cenário
# real, cada nó teria seu próprio par de chaves emitido por uma AC da
# federação; aqui simplificamos para fins de demonstração acadêmica.
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout chave.pem -out certificado.pem \
  -subj "/C=BR/O=Federacao Fictícia/CN=localhost"
echo "Gerado: certificado.pem (público) e chave.pem (privado, não versionar)."
