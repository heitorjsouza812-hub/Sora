# Canais da empresa: a Sora aprende lendo o atendimento

> Dona: Ponte (backend). Código em `backend/app/canais_empresa/`, rotas em `backend/app/api/canais_empresa.py`,
> jobs em `backend/workers/canais_empresa.py`, migração `0012_canais_empresa`.
> Contrato das rotas e dos eventos para o app: `.maestri/contrato-etapa5.md`, seção "Ponte".

## O que é (e o que não é)

A Sora **lê** o atendimento da empresa no **WhatsApp Business** e em **canais do Slack** para:

1. montar a **ficha de cada cliente** (preferências, pedidos, promessas, prazos, reclamações, dados de contato), cada fato com o link da mensagem de origem;
2. aprender o **conhecimento da empresa** (perguntas frequentes e como os funcionários responderam bem, produtos, preços, políticas, processos, tom de voz, objeções);
3. **sugerir melhorias** para as instruções e habilidades dos bots, que o usuário aprova num cartão "Precisa de você".

**A Sora nunca envia nada por esses canais.** Não existe ferramenta de resposta ao cliente, nem cliente HTTP de envio, nem `chat.postMessage`, nem `/messages` da Graph API. O token do Slack não tem (e não deve ter) `chat:write`; o token do WhatsApp só serve para **testar a conexão**. Um teste automático (`test_nao_ha_caminho_de_envio_no_codigo`) falha se alguém acrescentar um caminho de envio.

## Como o dado anda

```
Slack (Events API)  ─┐                     ┌─ ficha do cliente (fatos tipados + origem)
                     ├─ webhook assinado ─▶ mensagem mascarada ─▶ worker (modelo) ─┤
WhatsApp (Cloud API)─┘   (idempotente)      (ce_mensagens)                         └─ conhecimento da empresa
                                                                                          │
                          sugestões semanais ◀── compara com instruções/habilidades ◀─────┘
                          cartão "Precisa de você": Aplicar · Editar · Descartar
```

1. **Webhook.** Confere a assinatura, ignora o que não é de um canal escolhido, **mascara a PII**, grava e responde 200 na hora. Enfileira o resumo (adiado 60 s para juntar a conversa); uma rotina de 5 em 5 minutos pega o que sobrar.
2. **Resumo (worker).** Agrupa por conversa (`fio`), troca nomes e telefones por apelidos (C1, F1…) antes de falar com o modelo e pede um JSON com fatos e conhecimento. Valida campo a campo, mascara de novo, tira e-mail, telefone e nomes do conhecimento e grava. Se o modelo falhar, a mensagem continua pendente e a próxima passada tenta de novo.
3. **Fusão do conhecimento.** Item repetido soma a contagem e a origem. Item com o mesmo assunto e **conteúdo diferente** (números diferentes, como "7 dias" e "30 dias", contam como contradição) fica marcado `contraditorio`: o mais recente vence e o anterior vai para `anteriores`. Item **editado** pelo usuário fica travado (só conta). Item **apagado** não volta sozinho.
4. **Sugestões.** Rotina por usuário (padrão **semanal**; `0` desliga): compara a base com as instruções e habilidades de cada bot autorizado e cria sugestões. Só roda se a base mudou desde a última análise.

## Como configurar

### 1. Uma URL pública para os webhooks

Slack e Meta precisam alcançar a API por **https**. Em produção, é o domínio da API. **Em desenvolvimento, use um túnel**:

```bash
# Cloudflare (sem conta): imprime uma URL https://xxxx.trycloudflare.com
cloudflared tunnel --url http://localhost:8200
# ou ngrok
ngrok http 8200
```

A URL do webhook é `<URL pública>` + o caminho que a Sora devolve em `webhook_caminho` (campo de `GET /v1/canais-empresa/conexoes`), por exemplo:

- Slack: `https://xxxx.trycloudflare.com/v1/canais-empresa/webhooks/slack/<id da conexão>`
- WhatsApp: `https://xxxx.trycloudflare.com/v1/canais-empresa/webhooks/whatsapp/<id da conexão>`

Túnel rápido muda de URL a cada execução: atualize o campo no Slack/Meta. O id da conexão vai no caminho para a Sora achar os segredos certos; **a segurança é a assinatura**, não o sigilo da URL.

### 2. Slack (app oficial, só leitura)

1. Em <https://api.slack.com/apps>, **Create New App → From scratch**, no workspace da empresa.
2. **OAuth & Permissions → Bot Token Scopes**: peça **só** estes (a Sora recusa token com permissão de escrita):
   `channels:history`, `groups:history`, `channels:read`, `users:read`.
   Opcional, também de leitura: `groups:read`, para listar canais privados no app. **Não** peça `chat:write`.
3. **Install to Workspace** e copie o **Bot User OAuth Token** (`xoxb-…`).
4. **Basic Information → App Credentials**: copie o **Signing Secret**.
5. Na Sora: `PUT /v1/canais-empresa/conexoes/slack` com `segredos: {bot_token, signing_secret}` (opcional em `config`: `dominio` do workspace, para links diretos, e `ids_funcionarios`, os ids `U…` de quem é da equipe: as mensagens deles viram "resposta de funcionário" em vez de cliente).
6. **Event Subscriptions → Enable Events**, **Request URL** = a URL do passo 1 (a Sora responde o desafio `url_verification` depois de conferir a assinatura). Em **Subscribe to bot events**: `message.channels` e, se for ler privados, `message.groups`.
7. No Slack, **convide o app** para cada canal (`/invite @nome-do-app`).
8. Na Sora: `POST …/conexoes/slack/testar` (reprova se o token tiver `chat:write`), `GET …/conexoes/slack/canais-disponiveis` e `PUT …/conexoes/slack/canais` com os ids que ela deve ler. **Canal que não está na lista é ignorado.**

### 3. WhatsApp Business (Cloud API oficial da Meta)

Só a **API oficial**. Nada de biblioteca não oficial nem WhatsApp Web.

1. Em <https://developers.facebook.com/apps>, crie um app do tipo **Business** e adicione o produto **WhatsApp**.
2. Em **WhatsApp → API Setup**, anote o **Phone number ID** do número da empresa.
3. Em **Configurações do app → Básico**, copie o **App Secret** (assina os webhooks).
4. Gere um **token de acesso** (de preferência de usuário do sistema, permanente). Ele é usado **só no teste de conexão**.
5. Escolha um **Verify Token** qualquer (uma frase longa e aleatória).
6. Na Sora: `PUT /v1/canais-empresa/conexoes/whatsapp` com `segredos: {access_token, app_secret, verify_token}` e `config: {phone_number_id}`.
7. Na Meta, **WhatsApp → Configuration → Webhook**: **Callback URL** = a URL do passo 1 e **Verify token** = o do passo 5 (a Sora responde ao `GET` de verificação com `hub.challenge`). Assine o campo **`messages`**.
8. `POST …/conexoes/whatsapp/testar` e `PUT …/conexoes/whatsapp/canais` com `{"canais": ["<phone_number_id>"]}`: **o número que a Sora lê**.

#### Modo de coexistência (o número continua no app do celular)

Se a equipe já atende pelo **app WhatsApp Business** no celular e quer **manter** o app, use o modo de **coexistência** da Meta: o mesmo número funciona no app e na Cloud API. Pontos a conferir na documentação atual da Meta, porque mudam:

- o número entra pelo fluxo de **Embedded Signup** (cadastro incorporado) escolhendo a coexistência, e não pelo cadastro direto de número novo;
- as mensagens que a equipe **envia pelo app do celular** chegam ao webhook no campo **`smb_message_echoes`** (assine esse campo além de `messages`). A Sora trata esses ecos como **respostas de funcionário** na mesma conversa do cliente, que é o que alimenta as "boas respostas" do conhecimento;
- há restrições de países e a Meta pede que o app do celular seja aberto com frequência para a conexão não cair (a documentação cita 13 dias);
- sem coexistência (número só na Cloud API), a equipe responde por outra ferramenta e a Sora só vê as mensagens dos clientes: a ficha funciona, mas o conhecimento "como responderam bem" fica pobre.

### 4. Quem pode ver

Nada é visível para os bots até o usuário autorizar. `PUT /v1/canais-empresa/autorizacoes` com `{alvo_tipo: "agente"|"grupo", alvo_id, escopos: ["clientes","conhecimento"]}`:

- `clientes` → ferramenta **`consultar_cliente`** (ficha);
- `conhecimento` → ferramenta **`consultar_conhecimento`** (base) **e** o bloco de contexto "o que a empresa mais repete" no prompt do bot, além de entrar na análise de sugestões.

Um bot **dentro de um grupo autorizado** só vale como autorizado naquele grupo; no chat 1:1 ele precisa da própria autorização. Ao autorizar, a Sora acrescenta a ferramenta à lista do bot (e tira ao revogar); no chat 1:1 a ferramenta já aparece para a Sora e para os bots, mas só devolve dado a quem está autorizado. A Sora, a chefe, também pode ser autorizada para consultar, mas não recebe sugestões de melhoria.

## Privacidade (LGPD)

- **Só os canais escolhidos.** O resto do workspace e outros números não entram.
- **Máscara antes de gravar.** CPF, CNPJ, cartão (confere o dígito verificador/Luhn), senhas, códigos de verificação e tokens/chaves viram `[CPF]`, `[CNPJ]`, `[cartão]`, `[senha]`, `[código]`, `[token]` **antes** de qualquer gravação, inclusive da mensagem crua, e de novo sobre o que o modelo extrai.
- **Conhecimento sem dado pessoal.** Além da máscara, e-mail, telefone e nomes de pessoas saem (`[e-mail]`, `[telefone]`, `[cliente]`). O modelo recebe apelidos (C1, F1…) no lugar do nome e do telefone do contato.
- **Retenção.** A mensagem crua fica só pelo prazo do usuário (`retencao_dias`, padrão **90**, 1 a 3650, contado do recebimento). Uma rotina de hora em hora apaga o **texto**; a linha fica sem texto (garante que o webhook repetido não regrave e mantém o link de origem dos fatos).
- **Apagar tudo deste cliente.** `DELETE /v1/canais-empresa/clientes/{id}` remove o contato, as mensagens e a ficha, e tira os rastros dele do conhecimento (origens e contagem; item que fica com zero ocorrências sai da base). Se o cliente voltar a escrever e o canal continuar escolhido, um contato novo nasce: para parar de vez, tire o canal/número da lista. Apagar a conexão (`DELETE …/conexoes/{canal}`) remove **tudo** que veio dela.
- **Isolamento.** Toda consulta filtra por `usuario_id`; o id de outra conta responde 404; o segredo cifrado usa o usuário no AAD (copiar a coluna entre contas não decifra).
- **Aviso ao cliente.** A Sora **não** manda aviso nenhum (ela não envia). Quem opera a empresa deve informar o cliente que o atendimento é registrado e analisado (política de privacidade, mensagem de saudação do WhatsApp Business, topo do canal do Slack). O app deve lembrar o usuário disso ao ligar o canal.
- **Texto de cliente é dado, não ordem.** Tudo que vem de mensagem entra no modelo e nos bots **cercado** como `<dado_externo>` com a instrução de não obedecer. Mesmo assim, o que o modelo concluiu só muda um bot depois do **Aplicar** do usuário.

## Rotas

Prefixo `/v1/canais-empresa`, todas com login, exceto os webhooks. Campos completos na seção "Ponte" do contrato.

| Método e caminho | Para quê |
|---|---|
| `GET /conexoes` | Slack e WhatsApp, configurados ou não (nunca devolve segredo) |
| `PUT /conexoes/{canal}` | cria/atualiza (segredo omitido é mantido) |
| `DELETE /conexoes/{canal}` | apaga a conexão e tudo que veio dela |
| `POST /conexoes/{canal}/testar` | testa; Slack reprova token com escrita |
| `GET /conexoes/slack/canais-disponiveis` | canais que o bot enxerga |
| `PUT /conexoes/{canal}/canais` | os canais/número que a Sora lê |
| `POST|GET /webhooks/slack/{id}` · `/webhooks/whatsapp/{id}` | entrada (assinatura obrigatória) |
| `GET /clientes` · `GET\|PATCH\|DELETE /clientes/{id}` | lista, ficha, edita nome/papel, **apaga tudo** |
| `PATCH\|DELETE /fatos/{id}` | edita ou apaga um fato |
| `GET\|PUT /autorizacoes` | quem vê o quê |
| `GET\|PUT /preferencias` | retenção e intervalo das sugestões |
| `GET /conhecimento` · `PATCH\|DELETE /conhecimento/{id}` | lista/busca, edita (trava), apaga |
| `GET /sugestoes` · `PATCH /sugestoes/{id}` | lista; edita o texto |
| `POST /sugestoes/{id}/aplicar\|descartar\|desfazer` | decide e desfaz |
| `POST /sugestoes/analisar` | pede uma análise agora (202) |

## Eventos SSE (`GET /v1/eventos`)

- `cliente.atualizado` `{contato_id, canal, novos_fatos, total_fatos, motivo: leitura|edicao|remocao|apagado}`
- `conhecimento.atualizado` `{motivo: leitura|edicao|remocao|sugestoes|aplicacao|desfeita, itens_novos, itens_atualizados, sugestoes_pendentes, sugestao_id?, agente_id?}`
- a sugestão pendente também move o estado do bot para `precisa_de_voce` (`precisa_de_voce.atualizado`).

## Sugestões de melhoria

- Cada sugestão tem `tipo` `instrucoes` (acrescenta um trecho às instruções do bot) ou `habilidade` (cria ou acrescenta a uma habilidade do usuário), `titulo`, `motivo`, `texto` (o que será acrescentado) e os itens de conhecimento que a motivaram.
- O cartão chega em `GET /v1/atencao` como `tipo: "aprovacao"`, `titulo: "Sugestão de melhoria"`, `acao: "sugestao_melhoria"` e opções **Aplicar** (`permitir`) / **Descartar** (`negar`) por `POST /v1/aprovacoes/{id}/decidir`. **Editar** é `PATCH /v1/canais-empresa/sugestoes/{id}` com o texto novo, antes do Aplicar (o app acha a sugestão pelo `aprovacao_id`). "Sempre permitir" é ignorado: sugestão nunca vira permissão permanente.
- **Só depois do Aplicar** a instrução ou habilidade do bot muda. A versão anterior fica na sugestão (`versao_anterior`) e `POST …/desfazer` volta a ela. Se o bot (ou a habilidade) mudou **depois** da aplicação, desfazer responde 409 em vez de apagar a mudança do usuário.
- Limites: até 3 sugestões por bot por rodada, até 5 pendentes por bot, instruções com no máximo 8.000 caracteres, repetição da mesma sugestão pendente ou já aplicada é descartada, e o que as instruções já cobrem não é sugerido.

## Limitações conhecidas

- Mensagens de mídia (áudio, imagem sem legenda) são ignoradas; só texto e legendas entram. Baixar mídia não foi implementado.
- Bots que entram num grupo autorizado **depois** da autorização só recebem a ferramenta quando o usuário salvar a autorização de novo (o acesso em si é conferido a cada chamada).
- O bloco de conhecimento no prompt vale para a Sora e para o bot em chat 1:1; nos turnos de grupo o bot usa a ferramenta `consultar_conhecimento`.
- A análise de sugestões usa a lista de **habilidades do usuário** (elas são compartilhadas entre os bots), então uma sugestão de habilidade vale para todos.
- Sem modelo real conectado, o desenvolvimento usa regras simples (`SORA_MODELO_FALSO=1`): perguntas seguidas de resposta viram FAQ, e política/preço viram conhecimento. Com modelo real, é o JSON do modelo.
