# Protótipo — Chat corporativo

## Dependências

- Python 3.10+
- OpenSSL (linha de comando, para gerar o certificado — já vem instalado na maioria dos sistemas Linux/macOS)
- Biblioteca `cryptography`: `pip install cryptography`
- Demais bibliotecas usadas são da biblioteca padrão do Python (`socket`, `ssl`, `threading`, `json`, `struct`, `base64`, `hashlib`, `uuid`)

## Arquivos

- `protocolo.py` — framing por tamanho e definição dos tipos de mensagem (compartilhado)
- `topologia.py` — lista de ilhas e função de particionamento (hash determinístico usuário → ilha)
- `seguranca.py` — contextos TLS e assinatura digital (RSA) das mensagens de texto
- `relogio_vetorial.py` — relógio vetorial para ordenação causal do histórico
- `gateway.py` — ponto de entrada único: identifica o usuário e devolve o broker correto
- `servidor.py` — broker de uma ilha: conexões concorrentes, entrega local ou repasse para a ilha correta (via link TLS persistente entre brokers)
- `cliente.py` — cliente CLI: descobre o broker via gateway, troca texto (assinado) e arquivos, mantém histórico causal local
- `gerar_certificados.sh` — gera o certificado autoassinado usado por todos os processos

## Arquitetura

```
Cliente -> Gateway (TLS; identifica, devolve endereço do broker) -> [conexão encerrada]
Cliente -> Broker da sua ilha (TLS, conexão direta e persistente; texto assinado/arquivos)
Broker A <-> Broker B (link TLS persistente, repasse automático entre ilhas)
```

## Como rodar

1. **Gere o certificado uma única vez** (na raiz do projeto, antes de subir qualquer processo):
   ```
   ./gerar_certificados.sh
   ```
   Isso cria `certificado.pem` (público, usado por todos) e `chave.pem` (privado — não compartilhar/versionar). Todos os processos abaixo devem rodar na mesma pasta onde esses dois arquivos foram gerados.

2. Suba o gateway:
   ```
   python3 gateway.py
   ```

3. Suba cada ilha em um terminal separado (índice conforme `topologia.py`):
   ```
   python3 servidor.py 0   # Ilha A
   python3 servidor.py 1   # Ilha B
   ```

4. Em outros terminais, um por usuário simulado:
   ```
   python3 cliente.py alice
   python3 cliente.py bob
   ```
   (opcionalmente informe host/porta do gateway: `python3 cliente.py alice 127.0.0.1 8080`)

5. Comandos disponíveis no cliente:
   ```
   /msg <usuario_destino> <texto>
   /arquivo <usuario_destino> <caminho_do_arquivo>
   /historico
   /sair
   ```
   `/historico` mostra as mensagens de texto trocadas (enviadas e recebidas), reordenadas
   pela ordem causal do relógio vetorial, com um selo indicando se a assinatura digital
   de cada mensagem foi verificada com sucesso.

Funciona tanto se os dois usuários caírem na mesma ilha quanto em ilhas
diferentes — nesse segundo caso a mensagem passa pelo repasse broker-a-broker
automaticamente, de forma transparente para o cliente.

Arquivos recebidos são salvos na pasta `recebidos/`, criada automaticamente
ao lado de onde o cliente é executado. A integridade é verificada por hash
SHA-256 antes de gravar o arquivo em disco.

## Segurança implementada

- **Confidencialidade (transporte):** todas as conexões (cliente↔gateway,
  cliente↔broker, broker↔broker) usam TLS com um certificado autoassinado.
- **Autenticidade e não repúdio (aplicação):** cada cliente gera seu próprio
  par de chaves RSA ao iniciar e assina digitalmente (RSA-PSS/SHA-256) cada
  mensagem de texto. Quem recebe verifica a assinatura com a chave pública
  embutida na própria mensagem.
- **Limitação conhecida (documentar como trabalho futuro):** não há uma
  Autoridade Certificadora validando que uma chave pública realmente
  pertence ao usuário que se identificou com aquele nome (confiança no
  primeiro uso). Uma versão de produção exigiria uma PKI completa da
  federação.

## Ordem causal

Cada cliente mantém um relógio vetorial próprio (`relogio_vetorial.py`).
Toda mensagem de texto carrega o vetor do remetente no momento do envio; o
receptor funde esse vetor com o seu. O comando `/historico` usa esses
vetores para reordenar as mensagens pela relação de causalidade
(happened-before), em vez de confiar no horário local de cada máquina —
resolvendo o problema de dispositivos com relógios diferentes.

## Limitação conhecida (repasse entre ilhas)

O ACK de "REPASSADO_ILHA_REMOTA" confirma que o broker de origem entregou a
mensagem ao broker de destino, mas não confirma que o destinatário
realmente a recebeu (não há um ACK de volta do broker remoto). Para o MVP
isso é aceitável; uma versão mais robusta faria o broker remoto devolver
uma confirmação final ao broker de origem, que repassaria ao cliente
original.
