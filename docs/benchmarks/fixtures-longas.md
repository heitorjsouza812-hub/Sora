# Fixtures das tarefas longas L01–L10 (sem tela)

Tarefa 0.5 do plano de correções (§3.5, item 2). Dez tarefas com **10 ou mais etapas dependentes**, sem tela, rodadas pelo backend real (API + worker, `SORA_RASTRO=1`) com o modelo fixo do `baseline.md`. A prova é sempre conferida **fora do bot**: arquivo baixado pela API, linhas no Postgres e o registro do servidor MCP de bancada. Resposta do modelo sozinha não é prova.

## Como cada execução começa (estado inicial comum)

| Item | Valor |
|---|---|
| Conta | conta de QA própria do baseline (`baseline-05-…@bancada.local`), só com o provedor Groq e só o modelo fixo ativo |
| Bot | um bot **novo por execução** (`POST /v1/agentes`): nome `Bancada<Lnn>r<n><hora>`, função "Bot de bancada (baseline 0.5)", ferramentas `ler_anexo`, `ler_pagina`, `escrever_arquivo` (o produto soma `falar`, `perguntar` e as ferramentas de memória, pendências, agenda, habilidades e histórico do papel `individual`) |
| Instrução do bot | "Você é um bot de bancada de testes. Faça exatamente o que o usuário pedir, na ordem pedida, usando as ferramentas. Nunca invente um resultado: se uma ferramenta falhar, diga qual falhou e o motivo." |
| Modelo | `PATCH /v1/agentes/{id}`: `provedor_id` da Groq, `modelo = groq/qwen/qwen3.8-27b`, `raciocinio = auto`, `permissao = perguntar` |
| Conversa | nova a cada execução (`POST /v1/conversas` com o 1º turno e os anexos) |
| MCP de bancada | conector `bancada` da conta → `http://127.0.0.1:8765/mcp` com `Authorization: Bearer bancada-local`. O executor sobe o servidor (`ferramentas/mcp_bancada.py`) **zerado** em cada execução, com estado na pasta da execução |
| Páginas fixture | `docs/benchmarks/paginas/*.md`, servidas pelo raw do GitHub **fixado no commit `54cd737`** (o `ler_pagina` recusa 127.0.0.1 por SSRF, de propósito). A página `L04_promocoes.md` **não existe** (404) de propósito |
| Anexos | `docs/benchmarks/dados/*` (gerados por `ferramentas/dados_longas.py gerar`) |
| Cartões e perguntas | o executor age como o usuário: responde a pergunta com o valor da fixture e decide cada cartão "Precisa de você" com a decisão da fixture (padrão **Permitir uma vez**; L07 **Recusar**), 2 s depois de o cartão aparecer |
| Fim do turno | `mensagem.fim` de mensagem do bot + 8 s sem evento + bot fora de "trabalhando". Prazo do executor por turno: 900 s (o job tem 360 s; a folga cobre esperas de 429 e retomadas por cartão) |

O gabarito de cada tarefa é **calculado** pelo mesmo código que confere (`ferramentas/dados_longas.py gabarito`), nunca escrito à mão.

## Cobertura e prova

| ID | O que exercita | Etapas | Prova conferida fora do bot | Resultado esperado (gabarito) |
|---|---|---|---|---|
| L01 | ler anexo CSV → normalizar → filtrar → agregar → ordenar → escrever JSON → memória | 11 | `resumo_L01.json` baixado e comparado; linha em `memorias` do bot | Praia 1005,60 · Centro 975,30 · Norte 812,70 · Serra 697,90; média 872,88; 3 devoluções |
| L02 | memória em 2 turnos; apagar com **cartão fixo** (`esquecer_memoria`) e retomar; conta de datas; arquivo | 5 + 7 | `memorias` do bot: 5 fatos do Ipê, com Bianca e sem Caio; cartão em `aprovacoes`; `ipe_L02.md` | responsável Bianca; 56 dias de 15/01/2027 a 12/03/2027 |
| L03 | página fixture + anexo JSON; regra condicional; CSV | 8 por pedido × 8 pedidos | `fretes_L03.csv` linha a linha | total 172,07; maior frete pedido 305 |
| L04 | duas páginas encadeadas + **erro de ferramenta** (404) sem parar; junção; JSON; memória | 10 | `estoque_L04.json`; `memorias`; resposta diz que as promoções não foram lidas | Bebidas 128,00 · Mercearia 540,00 · Limpeza 179,40; sem estoque A2, A6 |
| L05 | **MCP**: leitura, **erro temporário** com nova tentativa, escrita com efeito (`registrar_pedido_compra`), conferência, CSV | 7 + 3 por item | `pedidos.json` do servidor MCP (exatamente P-02×17, P-03×10, P-05×9, sem repetição); `chamadas.jsonl` (P-03 consultado 2×); `compras_L05.csv` | total 270,75 |
| L06 | **MCP com erro permanente**: não inventar valor; nova tentativa; pendência | 5 consultas + 7 | `fretes_L06.json` com `69900-000 = INDISPONIVEL`; `chamadas.jsonl` (2 tentativas no CEP que falha); `pendencias` | soma 84,55; mais caro 80010-000 |
| L07 | **aprovação recusada**: envio (`enviar_relatorio`) → cartão → **Recusar** → salvar local + pendência | 9 | `enviados.json` do MCP **vazio**; cartão em `aprovacoes`; `relatorio_L07.md`; `pendencias` | sexta (29); média 24,0 |
| L08 | **pergunta e retomada** (`perguntar` → resposta "domingo") + 5 pendências criadas/anotadas/concluídas/removidas + arquivo | 1 + 7 | `pendencias` do bot (abertas, notas, status); `mudanca_L08.md` | abertas: Avisar clientes, Contratar caminhão (nota "domingo"), Ligar internet nova |
| L09 | agenda: criar 4, listar, cancelar, recriar, listar, memória, arquivo | 11 | `rotinas` do bot (ativa, `proxima_execucao`, `expressao`); `memorias`; `agenda_L09.md` | 4 ativos; módulo 2 em 01/03/2027 09:00; "Revisão geral" com cron `30 8 29 2 *` (próxima em 2028, não dispara durante a medição) |
| L10 | planilha xlsx de 3 abas; 2 turnos com **correção**; memória trocada (cartão fixo); **habilidade** com cartão fixo | 8 + 5 | `saldo_L10.csv` e `saldo_L10_v2.csv`; `memorias`; `habilidades`; 2 cartões em `aprovacoes` | v1: pior fev (1 500); v2: fev 3 900, pior **mar** (3 800) |

Critério de resultado por execução: **ok** = todos os critérios da tarefa passaram; **parcial** = pelo menos um passou; **falhou** = nenhum; **não executado** = o executor não conseguiu rodar ou o provedor recusou por cota (429/413 da Groq: não é falha do produto, regra do plano). Os critérios exatos estão em `ferramentas/rodar_longas.py` (`conferir`).

## Como rodar

```bash
# de dentro de C:/dev/sora-claude/backend, com Docker (Postgres e Redis de dev), API em 8000 e:
SORA_RASTRO=1 uv run python -m workers > "$LOCALAPPDATA/sora-baseline/logs/worker.log" 2>&1 &
uv run python ../docs/benchmarks/ferramentas/rodar_longas.py preparar        # 1 vez: conta, modelo fixo, conector
uv run python ../docs/benchmarks/ferramentas/rodar_longas.py rodar --vezes 3 --log-worker "$LOCALAPPDATA/sora-baseline/logs/worker.log"
uv run python ../docs/benchmarks/ferramentas/rodar_longas.py resumo          # tabela para o baseline.md
```

Cada execução grava `docs/benchmarks/execucoes/<Lnn>-r<n>-<hora>/registro.json` (resultado, classe, duração, chamadas, tokens, custo, esperas de 429) e `prova.json` (mensagens, arquivos, linhas do banco, registro do MCP).

## Pedidos exatos

Gerados por `rodar_longas.py pedidos` (o executor envia exatamente este texto). `{P}` nas URLs = `https://raw.githubusercontent.com/heitorjsouza812-hub/Sora/54cd737395d79ea4f08b3667fe4e008eaaec8c60/docs/benchmarks/paginas`.

### L01 — Vendas por loja: CSV → JSON + memória

Anexos: `docs/benchmarks/dados/vendas_L01.csv`

**Turno 1:**

> Anexei vendas_L01.csv. Faça nesta ordem: 1) leia o arquivo; 2) normalize o nome da loja (sem espaços nas pontas, só a primeira letra maiúscula); 3) descarte as linhas com quantidade negativa (são devoluções) e conte quantas descartou; 4) calcule o faturamento de cada linha (quantidade × preço unitário); 5) some o faturamento por loja; 6) arredonde cada total para 2 casas; 7) ordene as lojas do maior para o menor total; 8) calcule a média dos totais das lojas, com 2 casas; 9) salve o arquivo resumo_L01.json exatamente neste formato: {"lojas":[{"loja":"Nome","total":0.00}],"media":0.00,"devolucoes_descartadas":0}; 10) guarde na memória o fato "Loja campeã de vendas (L01): <nome da loja>"; 11) responda só com o nome da loja campeã e o total dela.


### L02 — Memória em dois turnos com troca aprovada

**Turno 1:**

> Guarde na memória, um fato por vez, estes 5 fatos do projeto Ipê: (a) O cliente do projeto Ipê é a Padaria Aurora. (b) O orçamento do projeto Ipê é R$ 18.400. (c) O prazo do projeto Ipê é 12/03/2027. (d) A cor principal do projeto Ipê é verde-musgo. (e) O responsável do projeto Ipê é o Caio. Depois me diga quantos fatos guardou.

**Turno 2:**

> Mudou uma coisa: o responsável do projeto Ipê agora é a Bianca. Faça nesta ordem: 1) busque na memória os fatos do projeto Ipê; 2) apague a memória antiga do responsável (isso vai pedir minha aprovação); 3) guarde o fato novo do responsável; 4) busque de novo para conferir; 5) calcule quantos dias faltam de 15/01/2027 até o prazo do projeto; 6) salve ipe_L02.md com uma linha por item no formato 'campo: valor', com os campos cliente, orcamento, prazo, cor, responsavel e dias_ate_prazo; 7) responda só com o nome do responsável atual.

Cartão/pergunta esperado: esquecer_memoria (cartão fixo) → Permitir uma vez.


### L03 — Página de frete + pedidos anexos → CSV

Anexos: `docs/benchmarks/dados/pedidos_L03.json`

**Turno 1:**

> Leia a tabela de frete em {P}/L03_frete.md e os pedidos do anexo pedidos_L03.json. Para cada pedido: 1) ache a região da UF pela tabela; 2) calcule frete = base + por_kg × peso; 3) se o valor do pedido passar de 300, aplique 50% de desconto no frete; 4) arredonde para 2 casas. Depois: 5) some o frete de todos os pedidos; 6) ache o pedido de maior frete; 7) salve fretes_L03.csv com o cabeçalho id,uf,regiao,frete e uma linha por pedido em ordem de id; 8) responda com o frete total e o id do pedido de maior frete.


### L04 — Duas páginas encadeadas + uma que não existe

**Turno 1:**

> 1) Leia o catálogo em {P}/L04_catalogo.md; 2) leia preços e estoque em {P}/L04_precos.md; 3) tente ler as promoções em {P}/L04_promocoes.md — se falhar, siga sem promoção e diga isso na resposta; 4) junte catálogo e preços pelo código; 5) separe os itens com estoque 0; 6) para os outros, calcule valor em estoque = preço × estoque; 7) some por categoria, com 2 casas; 8) salve estoque_L04.json exatamente no formato {"categorias":{"Categoria":0.00},"itens_sem_estoque":["código"]}; 9) guarde na memória o fato "Categoria de maior valor em estoque (L04): <categoria>"; 10) responda com a categoria de maior valor e se as promoções foram lidas ou não.


### L05 — MCP: reposição com erro temporário e registro com efeito

**Turno 1:**

> Use as ferramentas do conector bancada: 1) leia o estoque; 2) para cada item com quantidade abaixo do mínimo, calcule quanto falta para chegar ao DOBRO do mínimo; 3) consulte o preço de cada um desses itens (se der erro temporário, tente de novo uma vez); 4) registre um pedido de compra por item com a quantidade calculada; 5) leia os pedidos registrados para conferir que não ficou nada repetido nem faltando; 6) salve compras_L05.csv com o cabeçalho sku,quantidade,preco_unitario,subtotal, uma linha por item e uma última linha TOTAL com a soma no subtotal; 7) responda com o total da compra.

Cartão/pergunta esperado: registrar_pedido_compra (revisor) → se abrir cartão, Permitir uma vez.


### L06 — MCP: erro permanente sem inventar valor

**Turno 1:**

> Calcule o frete destes 5 CEPs com a ferramenta de frete do conector bancada: 01310-100, 20040-002, 30130-010, 69900-000, 80010-000. 1) consulte cada CEP; 2) se algum falhar, tente mais uma vez; 3) se continuar falhando, marque como INDISPONIVEL (não estime nenhum valor); 4) some só os fretes que deram certo, com 2 casas; 5) ache o CEP de frete mais caro; 6) salve fretes_L06.json exatamente no formato {"fretes":{"CEP":0.00 ou "INDISPONIVEL"},"soma":0.00,"mais_caro":"CEP"}; 7) adicione a pendência "Refazer frete do CEP 69900-000"; 8) responda com a soma e qual CEP ficou indisponível.


### L07 — Envio recusado → salvar local e pendência

Anexos: `docs/benchmarks/dados/relatorio_L07.csv`

**Turno 1:**

> Monte o relatório semanal a partir do anexo relatorio_L07.csv: 1) leia o arquivo; 2) some os atendimentos por dia; 3) ache o dia com mais atendimentos; 4) calcule a média diária com 1 casa; 5) escreva um texto curto com esses números; 6) envie o texto pela ferramenta enviar_relatorio do conector bancada para financeiro@exemplo.com.br com o assunto 'Relatório semanal L07'; 7) se o envio for recusado, NÃO envie de outro jeito: salve o texto em relatorio_L07.md e me avise que ficou salvo; 8) adicione a pendência "Enviar relatório L07 depois"; 9) responda com o dia de mais atendimentos.

Cartão "Precisa de você" → **negar**.

Cartão/pergunta esperado: enviar_relatorio (envio) → cartão obrigatório → Recusar.


### L08 — Pergunta no meio + pendências

**Turno 1:**

> Organize as tarefas da mudança de escritório. Antes de começar, me pergunte (com a ferramenta de pergunta) se a mudança é no sábado ou no domingo. Depois: 1) crie estas 5 pendências: 'Contratar caminhão', 'Embalar arquivos', 'Desligar internet antiga', 'Ligar internet nova', 'Avisar clientes'; 2) nas notas da pendência 'Contratar caminhão', anote o dia que eu escolhi; 3) conclua 'Embalar arquivos'; 4) remova 'Desligar internet antiga' (não precisa mais); 5) liste as pendências abertas; 6) salve mudanca_L08.md com as pendências abertas, uma por linha, em ordem alfabética; 7) responda quantas ficaram abertas.

Pergunta do bot → responder **domingo**.

Cartão/pergunta esperado: perguntar → responder 'domingo'.


### L09 — Agenda: criar, cancelar, recriar e conferir

**Turno 1:**

> Crie estes lembretes (fuso de São Paulo): 1) 'Treinamento módulo 1' em 08/02/2027 às 09:00; 2) 'Treinamento módulo 2' em 15/02/2027 às 09:00; 3) 'Treinamento módulo 3' em 22/02/2027 às 09:00; 4) 'Revisão geral' recorrente todo ano em 29 de fevereiro às 08:30 (cron 30 8 29 2 *); 5) liste os agendamentos; 6) cancele o 'Treinamento módulo 2' (foi adiado); 7) crie 'Treinamento módulo 2' de novo em 01/03/2027 às 09:00; 8) liste de novo para conferir; 9) guarde na memória o fato 'Treinamento L09 termina em 01/03/2027'; 10) salve agenda_L09.md com os agendamentos ativos, um por linha; 11) responda quantos agendamentos ativos ficaram.


### L10 — Planilha de 3 abas, correção no 2º turno, habilidade aprovada

Anexos: `docs/benchmarks/dados/orcamento_L10.xlsx`

**Turno 1:**

> Anexei orcamento_L10.xlsx (abas Receitas, Despesas e Metas). 1) leia a planilha; 2) some as receitas de cada mês (jan, fev, mar); 3) some as despesas de cada mês; 4) calcule o saldo de cada mês (receitas − despesas); 5) compare com a meta de saldo do mês (aba Metas); 6) salve saldo_L10.csv com o cabeçalho mes,receitas,despesas,saldo,meta,atingiu (atingiu = sim se saldo ≥ meta, senão nao), uma linha por mês; 7) guarde na memória o fato 'Pior mês de saldo (L10): <mês>'; 8) responda com o pior mês.

**Turno 2:**

> Correção: o Aluguel de fevereiro foi lançado em dobro; considere só a metade dele. 1) refaça as contas de fevereiro; 2) salve saldo_L10_v2.csv no mesmo formato, com os três meses; 3) se o pior mês mudou, apague a memória antiga do pior mês e guarde a nova; 4) crie uma habilidade chamada saldo-mensal com o passo a passo que você usou (isso vai pedir minha aprovação); 5) responda com o saldo corrigido de fevereiro e o pior mês agora.

Cartão/pergunta esperado: esquecer_memoria e criar_habilidade (cartões fixos) → Permitir uma vez.

