# Fixtures de tela G01–G10 (e reproduções R1, R3)

Tarefa 0.5 do plano de correções (§3.5, item 1). Tarefas genéricas no Windows real, pelo **app de desktop** deste worktree em **modo dev** (`npm run desktop`, Vite 5173 → API 8000; o instalador do `desktop:build` não fala com o backend local: sem `VITE_API_URL` e com o CSP de produção no domínio de exemplo), com o bot no **PC do usuário** e o modelo fixo do `baseline.md`. Quem executa é o **Heitor** (o Claude não opera o PC dele); o roteiro passo a passo está em `roteiro-sessao-heitor.md`.

**Prova é estado conferido fora do bot**: UI Automation, COM do Excel (só leitura), arquivo salvo e janela em primeiro plano por HWND/processo. A resposta do bot ou um screenshot sozinho **não** contam.

## Ferramentas (todas em `docs/benchmarks/ferramentas/`)

| Arquivo | Para quê |
|---|---|
| `fixtures_gui.py preparar` | cria `C:\bancada-g\` com os arquivos de cada tarefa, cópias em `originais\` e `manifesto.json` (sha256) |
| `fixtures_gui.py conferir G02\|G05\|G07\|G08\|G09\|G10` | confere arquivo salvo / formulário: imprime JSON com cada critério |
| `fixtures_gui.py formulario` | servidor local do formulário da G09 (`http://127.0.0.1:8766/`) e da G10 (`/g10`); grava `G09_envios.json` / `G10_envios.json` |
| `conferir_g.ps1 notepad-texto [-Titulo x]` | texto do documento ativo de cada janela do Bloco de Notas (TextPattern), normalizado `\n`, com sha256 |
| `conferir_g.ps1 calc-valor` | visor da Calculadora (`AutomationId = CalculatorResults`) |
| `conferir_g.ps1 frente` / `vigiar-frente -Saida x.csv` | janela em primeiro plano agora / registro de cada troca de primeiro plano (200 ms) durante a execução |
| `conferir_g.ps1 excel-tabela` | Excel aberto (COM, só leitura): área usada, valores, sublinhado, negrito, cor de fundo |
| `conferir_g.ps1 intruso -Atraso N` | G10: abre a janela intrusa (Bloco de Notas com `G10_intruso.txt`) depois de N s |
| `rodar_longas.py nova-g <ID> --primeira-rodada <n>` | cria um **bot novo** para a execução (conversa e memória limpas, modelo fixo, permissão `perguntar`, ferramentas `computador_observar` + `computador_agir` + `computador_abrir_programa`) e copia o pedido exato para a área de transferência |
| `rodar_longas.py registrar-g <ID> --primeira-rodada <n> --resultado … --classe … --prova "…"` | grava `execucoes/<ID>-r<n>-…/registro.json` com duração, chamadas de modelo e de ferramenta, tokens, custo, 429 e cartões, lidos do banco e do log do worker (só leitura) |

## Estado inicial comum

- 1 monitor 1920×1080, escala 100 % (conferir antes de começar; anotar se mudar).
- Fechar ou minimizar **toda janela com "Sora" no título** que não seja o app (T3 Code, VS Code com a pasta `sora`, abas do navegador): o título com "sora" é bloqueado e aparece tarjado para o bot.
- Bloco de Notas configurado para **abrir uma nova janela** ao iniciar (Configurações do Bloco de Notas → Ao iniciar → Abrir nova janela), sem sessão anterior.
- Antes de cada execução: `fixtures_gui.py preparar` (restaura todos os arquivos), fechar Bloco de Notas, Paint, Calculadora, Excel, Word e o navegador de teste **sem salvar**, depois abrir só o que a tarefa pede.
- Em cada execução, `vigiar-frente` gravando `C:\bancada-g\<ID>-r<n>-frente.csv` do envio do pedido até a resposta final.
- Cartões "Precisa de você": **Permitir uma vez** quando for o programa da tarefa; **Recusar** se for qualquer outro programa (e anotar como falha `executor` ou `modelo`).

## Tarefas

Os pedidos abaixo são **exatamente** os de `fixtures_gui.py` (`PEDIDOS_G`), que o `nova-g` copia.

### G01 — Bloco de Notas: escrever três linhas
- **Estado inicial:** Bloco de Notas fechado.
- **Pedido:** "No meu computador, abra o Bloco de Notas em um documento novo e escreva exatamente estas três linhas, uma embaixo da outra: 'Linha um da bancada', 'Linha dois: 2 + 2 = 4' e 'Linha três termina aqui.' (sem as aspas). Não salve e deixe a janela aberta."
- **Prova obrigatória:** o texto do documento é exatamente `Linha um da bancada⏎Linha dois: 2 + 2 = 4⏎Linha três termina aqui.` (aceita uma quebra de linha no fim).
- **Conferir:** `conferir_g.ps1 notepad-texto` → campo `texto` da janela nova.
- **ok** texto exato · **parcial** as três linhas com diferença de espaço/pontuação ou só parte delas · **falhou** nada escrito, texto em outro programa ou bot diz que fez sem o texto estar lá.

### G02 — Editar, salvar (Ctrl+S) e reabrir
- **Estado inicial:** `C:\bancada-g\G02_lista.txt` aberto no Bloco de Notas (duplo clique no arquivo), única aba.
- **Pedido:** "No meu computador, no Bloco de Notas que está aberto com o arquivo G02_lista.txt, troque a linha 'quantidade: 10' por 'quantidade: 25' sem mudar mais nada e salve com Ctrl+S. Depois feche a aba do arquivo com Ctrl+W, reabra o mesmo arquivo com Ctrl+O digitando C:\bancada-g\G02_lista.txt e Enter, e confira que a mudança ficou salva. Deixe o arquivo aberto."
- **Prova obrigatória:** o arquivo no disco tem `quantidade: 25` e o resto igual; o arquivo está aberto de novo com o conteúdo novo.
- **Conferir:** `fixtures_gui.py conferir G02` (disco) e `conferir_g.ps1 notepad-texto -Titulo G02_lista` (reaberto).
- **ok** disco e reaberto conferem · **parcial** disco certo mas não reabriu (ou reabriu outro) · **falhou** disco sem a mudança ou com outra linha alterada.

### G03 — Calculadora: operação definida
- **Estado inicial:** Calculadora aberta no modo **Padrão**, visor em 0 (Esc). A Calculadora **não** está na lista de programas que o bot abre pelo nome (`regras::PROGRAMAS_ABRIVEIS`), por isso começa aberta.
- **Pedido:** "No meu computador, na Calculadora que está aberta, calcule (1234 + 5678) × 3 − 99 e me diga o resultado que aparece no visor."
- **Prova obrigatória:** visor = **20.637** e o bot diz 20637.
- **Conferir:** `conferir_g.ps1 calc-valor` → `visor`/`numero`.
- **ok** visor e resposta conferem · **parcial** visor certo e resposta errada (ou o contrário) · **falhou** visor errado.

### G04 — Alternar entre duas janelas e voltar
- **Estado inicial:** `C:\bancada-g\G04_a.txt` aberto no Bloco de Notas e o **Paint** aberto vazio; o app (chat do bot) em primeiro plano no envio.
- **Pedido:** "No meu computador, traga a janela do Paint para a frente; depois volte para o Bloco de Notas com o arquivo G04_a.txt e deixe ele em primeiro plano. Não digite nada em nenhum dos dois."
- **Prova obrigatória:** no `vigiar-frente` aparece `mspaint.exe` em primeiro plano e **depois** `notepad.exe` com `G04_a.txt` no título, e este é o último primeiro plano antes de o app voltar; `G04_a.txt` sem mudança (sha256 do `manifesto.json`) e sem `*` de alteração no título.
- **Conferir:** CSV do `vigiar-frente` + `conferir_g.ps1 frente` logo ao fim + `notepad-texto -Titulo G04_a`.
- **ok** sequência certa e nada digitado · **parcial** foi ao Paint mas não voltou (ou voltou sem passar pelo Paint) · **falhou** digitou algo ou focou outro programa.

### G05 — Ler um valor exibido
- **Estado inicial:** `C:\bancada-g\G05_valores.xlsx` aberto no Excel.
- **Pedido:** "No meu computador, no Excel aberto com G05_valores.xlsx, leia e me diga o valor exato do 'Saldo final' da loja Bairro Alto. Não altere a planilha."
- **Prova obrigatória:** o valor dito é **48.317,26** (aceita 48317,26 / 48317.26), igual ao lido do arquivo pelo conferidor; a planilha não foi alterada (`salvo = true` no `excel-tabela`, arquivo com o mesmo sha256).
- **Conferir:** `fixtures_gui.py conferir G05` + `conferir_g.ps1 excel-tabela`.
- **ok** valor exato e planilha intacta · **parcial** valor de outra coluna/loja vizinha ou formato truncado · **falhou** valor inventado ou planilha alterada.

### G06 — 15 ações dependentes num editor
- **Estado inicial:** Bloco de Notas aberto com documento novo vazio.
- **Pedido:** "No meu computador, no Bloco de Notas aberto (documento novo e vazio), faça estas 15 ações em ordem: 1) escreva 'alfa beta gama'; 2) tecle Enter; 3) escreva 'delta'; 4) tecle Enter; 5) escreva 'epsilon zeta'; 6) tecle Ctrl+Home; 7) escreva 'Lista: ' (com o espaço no fim); 8) tecle End; 9) escreva ' (1)'; 10) tecle seta para baixo e depois End; 11) escreva ' (2)'; 12) tecle seta para baixo e depois End; 13) apague ' zeta' com 5 Backspace; 14) escreva ' (3)'; 15) tecle Ctrl+End, depois Enter, e escreva 'fim'. Escreva sem as aspas e não salve. No fim, confira o texto e me diga como ficou."
- **Prova obrigatória:** texto exato:
  ```
  Lista: alfa beta gama (1)
  delta (2)
  epsilon (3)
  fim
  ```
- **Conferir:** `conferir_g.ps1 notepad-texto`.
- **ok** exato · **parcial** 3 das 4 linhas certas · **falhou** 2 ou menos, ou o bot diz que ficou certo sem estar ("fiz" sem prova).

### G07 — Grade densa: achar e alterar valores
- **Estado inicial:** `C:\bancada-g\G07_grade.xlsx` aberto no Excel (20 filiais × 12 meses).
- **Pedido:** "No meu computador, no Excel aberto com G07_grade.xlsx, mude só estas três células: Março da 'Filial 07' para 1500, Agosto da 'Filial 13' para 2750 e Dezembro da 'Filial 19' para 980. Não mude mais nada e salve com Ctrl+S."
- **Prova obrigatória:** no arquivo salvo, `D8 = 1500`, `I14 = 2750`, `M20 = 980` e as outras 237 células iguais às originais.
- **Conferir:** `fixtures_gui.py conferir G07` (lista as diferenças).
- **ok** 3/3 e nada mais mudou · **parcial** 1–2 certas, sem outra célula alterada · **falhou** nenhuma certa, ou alguma célula não pedida mudou, ou não salvou.

### G08 — Inserir e modificar objeto/estilo num app de conteúdo
- **Estado inicial:** `C:\bancada-g\G08_documento.docx` aberto no Word (título em parágrafo normal, sem negrito; 3 parágrafos).
- **Pedido:** "No meu computador, no Word aberto com G08_documento.docx: 1) deixe a primeira linha, 'Relatório de bancada', em negrito; 2) insira uma tabela de 2 linhas e 2 colunas logo depois do segundo parágrafo, com 'Item' e 'Valor' na primeira linha e 'Café' e '12' na segunda; 3) sublinhe só a palavra 'urgente' no terceiro parágrafo; 4) salve com Ctrl+S, sem mudar o nome nem o formato do arquivo."
- **Prova obrigatória (arquivo salvo, `python-docx`):** título em negrito; tabela 2×2 exata entre o 2º e o 3º parágrafo; só "urgente" sublinhada; textos originais preservados.
- **Conferir:** `fixtures_gui.py conferir G08`.
- **ok** 5/5 critérios · **parcial** 2–4 · **falhou** 0–1 ou não salvou.

### G09 — Formulário local de teste
- **Estado inicial:** `fixtures_gui.py formulario` rodando; Edge aberto **só** com `http://127.0.0.1:8766/` ("Cadastro de bancada G09"); `G09_envios.json` inexistente.
- **Pedido:** "No meu computador, no navegador aberto na página 'Cadastro de bancada G09', preencha: Nome 'Marina Duarte', E-mail 'marina@exemplo.com.br', Cidade 'Curitiba', Quantidade 7, marque 'Aceito os termos' e clique em Enviar. Depois me diga o número de protocolo que aparecer na tela."
- **Prova obrigatória:** `G09_envios.json` com **exatamente 1** envio com os 5 campos exatos; protocolo dito pelo bot = `protocolo` do arquivo.
- **Conferir:** `fixtures_gui.py conferir G09`.
- **ok** 1 envio exato e protocolo certo · **parcial** 1 envio com 1–2 campos errados, ou protocolo errado · **falhou** nenhum envio, 2+ envios ou 3+ campos errados.

### G10 — Foco muda e controle aparece tarde; recuperar
- **Estado inicial:** formulário rodando; Edge aberto **só** com `http://127.0.0.1:8766/g10`, **recarregado (F5) logo antes do envio** (mostra "Carregando o formulário…" por 5 s). Logo antes do envio do pedido, rodar `conferir_g.ps1 intruso -Atraso 40` e enviar em até 10 s (abre na frente o Bloco de Notas com `G10_intruso.txt` ~30 s depois do envio). Ao clicar em Enviar pela 1ª vez, o campo "Código de confirmação" só aparece 3 s depois.
- **Pedido:** "No meu computador, no navegador aberto na página 'Cadastro de bancada G10', espere o formulário carregar e preencha: Nome 'Otávio Lins', E-mail 'otavio@exemplo.com.br', Cidade 'Londrina', Quantidade 3, marque 'Aceito os termos' e clique em Enviar. Depois de clicar, vai aparecer o campo 'Código de confirmação': preencha 'K7-42' e clique em Enviar de novo. Se outra janela aparecer na frente, não mexa nela: volte para o navegador. No fim, me diga o protocolo."
- **Prova obrigatória:** `G10_envios.json` com 1 envio exato (inclui `codigo = K7-42`); `G10_intruso.txt` intacto no disco **e** no Bloco de Notas intruso (`notepad-texto -Titulo G10_intruso` igual ao original, sem `*`); nenhuma ação no app errado.
- **Conferir:** `fixtures_gui.py conferir G10` + `conferir_g.ps1 notepad-texto -Titulo G10_intruso` + CSV do `vigiar-frente`.
- **ok** envio exato e intruso intocado · **parcial** envio com campo errado/sem código, intruso intocado · **falhou** qualquer digitação/clique no intruso, ou nenhum envio.

## Reproduções das falhas reais (com o Heitor)

### R1 — Excel "pensando para sempre" (log/2026-11-21.md)
- **Estado inicial:** Excel fechado. Bot novo (`nova-g R1`).
- **Pedido (texto original do Heitor):** "acesse meu computador e monte uma tabela simples no meu Excel com cores e títulos sublinhados"
- **Falha original:** o bot ficava em "pensando" sem agir. Causa: chamada ao `gemini-3.8-flash` sem prazo, provedor sobrecarregado (503) e reservas todas do Google; corrigido em 21/11 (prazo de 45 s, troca para reserva de outro provedor, pausa de provedor), commit `75434fd`. **Classe original: `transporte`** (provedor travado sem prazo; a UI ficou pensando).
- **Prova do pedido:** `conferir_g.ps1 excel-tabela`: ≥ 2 linhas × 2 colunas com valor, **todas** as células de título (1ª linha da tabela) sublinhadas e ≥ 1 célula com cor de fundo; o bot não diz "pronto" sem isso.
- **Anotar também:** se ficou "pensando" > 2 min sem passo novo (UI/estado), se trocou de modelo (não pode: modelo fixo).

### R3 — Bloco de Notas "Teste da Sora" (log/2026-11-22.md)
- **Estado inicial:** Bloco de Notas aberto com `G04_a.txt` (um documento já aberto, para conferir o "preserve"). Bot novo (`nova-g R3`).
- **Pedido (texto original):** "No meu computador, abra o Bloco de Notas e escreva ‘Teste da Sora’. Deixe a janela aberta para eu conferir. Use um documento novo e preserve qualquer documento já aberto."
- **Falhas originais:** (1) digitação parcial ("Teste dSora": letras perdidas no WinUI) → classe **`executor`**; (2) o Windows pôs a 1ª linha no título da aba, a palavra "Sora" acionou a proteção da janela do próprio produto e o bot não conseguiu confirmar → classe **`executor`** (bloqueio por pedaço do título, plano §1). Corrigido em parte no `081bdfd` (Bloco de Notas oficial identificado pelo pacote, 28 ms por caractere).
- **Prova:** `conferir_g.ps1 notepad-texto` → existe documento com texto **exatamente** `Teste da Sora`; `G04_a.txt` intacto (aba e disco); o bot só diz que fez se o texto conferir.

## Classes de falha (como anotar)

Use as classes do plano (§3.5): `modelo` (escolheu mal, alucinou sucesso), `schema` (chamada de ferramenta inválida), `orcamento` (bateu 40/64 ou 20/30), `prazo` (285 s / 360 s: "o tempo deste turno acabou"), `contexto` (perdeu instrução), `aprovacao` (cartão não abriu, abriu 2×, retomou errado), `transporte` (ponte do desktop, Redis, long-poll, app desconectado), `executor` (clique no lugar errado, captura ruim, árvore incompleta, foco/DPI, janela tarjada indevidamente), `estado` (linha presa, "pensando" sem fim), `ui` (app mostrou errado). **Cota do provedor** (429/413 do provedor; hoje o Google, plano grátis) não é falha do produto: a execução vira "não executado (cota)" e é repetida depois.
