# agent-desktop → navegador da Sora

O [agent-desktop](https://github.com/vercel-labs/agent-desktop) (Vercel Labs, Rust, Apache 2.0) é uma ferramenta de linha de comando para agentes de IA usarem **apps de desktop** (macOS, Windows, Linux) pela árvore de acessibilidade do sistema: o agente tira uma "foto" da árvore, recebe uma ref para cada elemento acionável, age numa ref e confere de novo. Sem pixels e sem adivinhar coordenadas.

Em 2026-11-01 o Heitor pediu para trazer isso para a parte de **navegador** da Sora. Olhamos o código (commit `9eb9b29`, 2026-10-31), a documentação e as habilidades deles e escrevemos a nossa versão: o mesmo modelo de trabalho, com o Chromium da Sora como alvo no lugar dos apps do sistema.

## Licença

Apache 2.0: permite copiar, adaptar e usar comercialmente, desde que o aviso de licença vá junto e que se diga o que mudou. Por isso:

- a licença deles está em [`agent-desktop-LICENSE.txt`](agent-desktop-LICENSE.txt);
- todo arquivo derivado diz no topo que é ideia do agent-desktop, com o link;
- esta página lista o que foi trazido e o que mudou.

**Nada foi copiado literalmente.** O original é Rust falando com as APIs de acessibilidade do sistema; o nosso é Python + JavaScript falando com o DOM pelo Playwright. A documentação e o prompt dos agentes foram escritos em PT-BR por nós. Conferido em 2026-11-01: nenhum trecho de 60 caracteres dos arquivos novos aparece nos fontes (`.rs`, `.md`, `.ts`, `.js`) do agent-desktop.

## O que entrou na Sora (`backend/app/navegador/arvore/`)

| Ideia no agent-desktop | Na Sora | Como ficou |
|---|---|---|
| Snapshot da árvore de acessibilidade, com ref só no que dá para acionar | `pagina.js` (`observar`), `motor.py` (`observar`) | Papel (ARIA), nome acessível, valor e estados calculados no DOM, inclusive shadow DOM aberto. Ref para controles, rolagem e elementos clicáveis sem papel; foco sozinho não ganha ref. Títulos ficam como contexto. |
| Refs qualificadas pelo snapshot (`@s8f3k2p9:e8`); ref solta é recusada | `refs.py` | `@sXXXXXXX:eN`. `@e7` → `ARGUMENTOS_INVALIDOS`. Cada aba guarda as 8 últimas leituras; leitura velha → `LEITURA_NAO_ENCONTRADA`. |
| `-i`, `--compact`, `--skeleton`, `--root` (drill-down) e `--max-depth` | `navegador_observar` (`somente_interativos`, `compacto`, `esqueleto`, `raiz`, `profundidade_max`) | Esqueleto = 3 níveis com a contagem do que ficou dentro e uma ref para perfurar. Perfurar troca só as refs daquela região. |
| Wrappers sem significado não gastam profundidade | `pagina.js` | `div`/`span` sem papel, sem nome e sem ação viram transparentes; páginas cheias de camadas cabem no limite. |
| Leitura parcial quando o orçamento acaba | `observar` | Limite de 1.500 nós ou 3 s: devolve o que viu com `completa: false` e marca onde cortou. Perfurar exige leitura completa. |
| Resolução estrita da ref, em camadas | `identidade.py` | Memória (o mesmo objeto do DOM) → id do desenvolvedor (`id`, `data-testid`, `name`) → caminho no DOM → busca pelo papel. Cada camada só localiza; a confirmação exige papel igual, id igual quando existe e nome estável igual. Sem identidade, só a posição exata e única. Dois confirmados → `ALVO_AMBIGUO`. Nenhum → `REF_VELHA`. |
| Objeto nativo retido para uma linha removida não cair na que sobrou | `identidade.py` + `pagina.js` | A ref guarda uma `WeakRef` do elemento. Se ele foi **removido** da página, só o id do desenvolvedor pode reencontrá-lo; caminho e busca são proibidos (cairiam no vizinho). |
| Bateria de acionabilidade com auto-espera | `acionabilidade.py` | Visível, estável (dois quadros), habilitado e recebe eventos (5 pontos: centro e quadrantes) esperam até 5 s (+30 ms por caractere ao digitar). Suporta a ação, política e editável falham na hora. Rola até o elemento uma vez antes. |
| Teste de clique que diz quem está por cima | `acionabilidade.py` | Falha só com prova de que outro elemento tapa todos os pontos e diz qual (papel, nome, posição). Sem evidência, segue. |
| Disposição de entrega (`delivery` / `retry`) | `resposta.py` | `nao_entregue` (repetir: seguro), `incerta`, `entregue_sem_confirmar`, `entregue_confirmada`. O erro só traz `recuperacao` quando repetir é seguro. |
| Envelope JSON com códigos de erro | `resposta.py` | `REF_VELHA`, `ALVO_AMBIGUO`, `LEITURA_NAO_ENCONTRADA`, `POLITICA_NEGADA`, `ACAO_FALHOU`, `ACAO_NAO_SUPORTADA`, `PRAZO_ESGOTADO`, `ARGUMENTOS_INVALIDOS`, `ABA_NAO_ENCONTRADA`, `PAGINA_SEM_RESPOSTA`, `INTERNO`… |
| Verificação depois de ações com estado | `motor.py` | Definir valor, limpar, digitar, marcar, desmarcar, alternar, expandir, recolher, selecionar e focar releem o elemento. Contradição legível → `ACAO_FALHOU` (`verificacao_pos_acao`); sem evidência → sucesso sem confirmar. `marcar` já marcado não faz nada. |
| Campo secreto | `pagina.js`, `motor.py`, `rastro.py` | Senha nunca sai: nem na árvore, nem em `navegador_elemento`, nem no estado depois, nem no rastro. A escrita funciona e volta como `entregue_sem_confirmar` (`campo_secreto`). |
| Headless × headed | `Politica` | `fisica` (padrão): mouse e teclado do Playwright, eventos `isTrusted`. O Chromium da Sora é isolado no servidor, então isso não atrapalha ninguém. `semantica`: só pelo DOM; arrastar, passar o mouse, clique duplo e teclas → `POLITICA_NEGADA`. |
| Cadeia de ações com passos registrados | `motor.py` (`passos`) | Clique: ponteiro no ponto conferido; sem ponto conferível, `click()` do DOM. Cada passo diz rótulo, resultado e mecanismo. |
| Trava de interação (uma ação por vez) | `motor.py` (`_trava`) | Uma trava por aba. A espera fica fora dela; dentro, a ref é resolvida e conferida de novo antes de agir. |
| `wait` com predicados, `--wait-for` / `--wait-for-gone` | `navegador_esperar`, `esperar_por`/`esperar_sumir` | Tempo, elemento (existe, visível, habilitado, acionável, valor), `papel:texto` aparecer ou sumir (com contagem), URL e eventos (navegou, diálogo nativo, sobreposição abriu/fechou). |
| `find` | `navegador_procurar` | Papel, nome, valor, texto, id; `exato`, `primeiro`, `contar`, `limite`, `raiz`. Papel que não existe → lista os papéis presentes. Busca por texto sobe até quem tem ref (o link em volta do texto). |
| `get` / `is` | `navegador_elemento` | Texto, valor, título, posição, papel, estados; e sim/não com `aplicavel` quando o estado não existe. |
| `batch` | `navegador_lote` | Até 20 passos em ordem, sem lote dentro de lote, campos desconhecidos recusados, `parar_no_erro` marca o resto como `nao_iniciado`. |
| Sobreposições (`surfaces`) | `superficies` | Depois de agir, a resposta lista diálogos, alertas, menus e listas abertos. `alert`/`confirm` nativos são dispensados e aparecem em `dialogos_nativos`. |
| Traces JSONL | `rastro.py` | Rastro por aba em memória, redigido, com esquema que só ganha campos. Base para o painel Trabalho. |
| Cursor do agente (só apresentação) | `CursorAgente` + `pagina.js` (`cursor`) | Seta na **cor do agente** com o nome dele, que vai até o ponto antes da ação e faz uma onda no clique. Fica num shadow DOM fechado e `pointer-events: none`, fora da árvore e dos testes de clique. Desligado por padrão. |
| Habilidade que ensina o ciclo ao agente | `backend/prompts/navegador_arvore.v1.md` | Escrito por nós: observar → agir → conferir, quando repetir, o que fazer com cada erro. |

### Ferramentas novas dos agentes

`navegador_observar`, `navegador_procurar`, `navegador_elemento`, `navegador_esperar` (livres: só leem), `navegador_acao`, `navegador_tecla`, `navegador_lote` (passam pelo revisor). Estão em `esquemas_das_proximas_fases()` com rótulo no painel Trabalho (o texto digitado nunca aparece no rótulo). `ServicoArvore` liga as ferramentas às abas do navegador persistente (`app/navegador/abas.py`): sem `aba_id`, usa a última aba do agente; aba que o usuário **assumiu** → `POLITICA_NEGADA`.

As ferramentas antigas `navegador_ler` e `navegador_agir` (do Rakazo) continuam lá; quando o worker for ligado, a ideia é oferecer as novas no lugar delas.

## O que ficou de fora, e por quê

- **Controle do sistema operacional** (janelas, apps, área de transferência, notificações, telas, AT-SPI/UIA/AX): a Sora usa o navegador isolado no servidor, não o computador do usuário.
- **Biblioteca C (FFI), comandos de CLI, sessões em disco e daemon**: o navegador da Sora roda dentro do worker; o estado fica em memória por aba.
- **Iframes**: só a página principal é lida (iframes aparecem como nó `iframe`). Iframes da mesma origem podem entrar depois.
- **Arrastar entre apps, teclas seguradas, mouse por coordenadas soltas**: sem uso para os agentes da Sora agora.

## Antes de ligar em produção

- No worker: criar o `ServicoArvore(gerente, motor.pagina)` com o `MotorPlaywright` e trocar `navegador_ler`/`navegador_agir` pelas ferramentas novas.
- Juntar `prompts/navegador_arvore.v1.md` ao prompt dos agentes que recebem o navegador.
- Mandar o rastro (`Rastro`) para o painel Trabalho e o cursor colorido para a transmissão da aba.
- Rodar `tests/unitarios/test_navegador_arvore.py` onde houver Chromium (`SORA_CHROMIUM` aponta para o executável; sem ele, os testes de navegador pulam).
