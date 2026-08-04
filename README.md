# Protótipo — Chat corporativo

Requer apenas Python 3.10+ (usa apenas biblioteca padrão: `socket`, `threading`,
`json`, `struct`, `base64`, `hashlib`, `uuid`).

## Arquivos

- `protocolo.py` — framing por tamanho e definição dos tipos de mensagem (compartilhado)
- `servidor.py` — broker: aceita conexões concorrentes e encaminha mensagens por usuário
- `cliente.py` — cliente CLI: identificação, mensagens de texto e envio/recebimento de arquivos

## Como rodar

1. Em um terminal, inicie o servidor:
   ```
   python3 servidor.py
   ```

2. Em outros terminais, um para cada usuário simulado:
   ```
   python3 cliente.py alice
   python3 cliente.py bob
   ```
   (opcionalmente informe host/porta: `python3 cliente.py alice 127.0.0.1 8080`)

3. Comandos disponíveis no cliente:
   ```
   /msg <usuario_destino> <texto>
   /arquivo <usuario_destino> <caminho_do_arquivo>
   /sair
   ```

Arquivos recebidos são salvos na pasta `recebidos/`, criada automaticamente
ao lado de onde o cliente é executado. A integridade é verificada por hash
SHA-256 antes de gravar o arquivo em disco.
