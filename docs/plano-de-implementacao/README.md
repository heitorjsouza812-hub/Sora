# Sora: plano de implementação (versão 2)

Plano do backend da Sora e de como ele se liga ao app que já existe em `app/`. **Versão atual: 2.1** (agentes em LangChain). A versão 1 foi exportada do documento "Sora: plano de implementação" em 2026-10-11. A **versão 2** (2026-10-11, noite) corrige o que não fazia sentido diante do que já está no repositório.

| Parte | Arquivo |
|---|---|
| Plano: ponto de partida, arquitetura, fluxo, Sistema 1, cadeias, revisão, personalidade, memória, segurança, stack e fases | [01-plano.md](01-plano.md) |
| Especificação do backend (fase 1): banco, API, **contrato com o app**, ferramentas, modelos, execução, Laya, busca, contas, deploy, repositório e testes | [02-especificacao-do-backend.md](02-especificacao-do-backend.md) |
| Prompts da fase 1 | [03-prompts.md](03-prompts.md) |

Diagramas: [fluxo de um pedido](img/fluxo-de-um-pedido.png) · [estados de uma cadeia](img/estados-de-uma-cadeia.png). A arquitetura agora é um diagrama Mermaid dentro do `01-plano.md` (o GitHub desenha sozinho). Os PDFs da versão 1 não foram trazidos porque ficaram desatualizados.

## Versão 2.1 (2026-10-14): agentes em LangChain

27. **Decisão:** os agentes da Sora (a Sora, os especialistas e os agentes individuais) são feitos em **LangChain 1.x**, com `create_agent` sobre o LangGraph. Detalhes na nova seção **6.1** da especificação.
    - Os modelos continuam passando pelo LiteLLM, agora pelo `ChatLiteLLM` (pacote `langchain-litellm`).
    - As ferramentas da seção 4 viram `@tool` do LangChain, com o mesmo esquema Pydantic.
    - Pausa e retomada das etapas (cartões de pergunta, `criar_agente`, queda do worker) usam o checkpointer do LangGraph no próprio PostgreSQL.
    - As peças de engenharia viram middleware: os prontos do LangChain (troca de modelo, limites de chamadas, erro de ferramenta, resumo) e os nossos (lembretes, loop, orçamento, cancelamento, passos, cerca).
    - Continuam sendo código nosso: a fila ARQ, os estados da cadeia no banco, o seletor, o orçamento e os eventos SSE.
    - Sem LangSmith e sem Deep Agents na fase 1.
28. Atualizados para combinar: Stack, Arquitetura, Peças de engenharia e fase 1 em `01-plano.md`; seções 4, 6.1, 8.4 e 8.5 da especificação.

## O que mudou da versão 1 para a 2

### Busca e serviços

1. **SearXNG saiu da fase 1.** Vindo de um IP de nuvem, ele é bloqueado ou recebe captcha dos buscadores com frequência (risco de falhar na FEBRACE), a qualidade varia e raspar buscadores esbarra nos termos de uso. **Agora:** API de busca (Tavily ou Brave) com a chave da equipe, cache de 24 h e limites; o usuário continua sem precisar de chave. O SearXNG fica só como opção de desenvolvimento local. A interface `ProvedorBusca` continua, com um provedor falso para os testes.
2. **Qdrant saiu.** A memória é da fase 2 e cabe no próprio PostgreSQL com **pgvector**. Um serviço a menos.
3. **GrowthBook e Langfuse foram para a fase 4.** Na fase 1, flags num `config/flags.yaml` e Sentry opcional.
4. **Deploy da fase 1 com 5 serviços:** Caddy, API, worker, PostgreSQL (com pgvector) e Redis. O Caddy também serve o app web.

### Contas

5. **Login no app de desktop.** O cookie `SameSite=Lax` não chega do app Tauri, que roda em `http://tauri.localhost`, outro site. **Agora:** no desktop, o token de renovação vem no corpo e fica no cofre do sistema. Também foram definidos o CORS e o CSP.
6. **Confirmação de e-mail e recuperação de senha foram para a fase 2**, antes de abrir o cadastro ao público. Na fase 1, o cadastro é por convite. As tabelas já nascem prontas.

### Ligação com o app (o que faltava)

7. **Nova seção 3, "Contrato com o app".** A versão 1 pulava da seção 2 para a 4. A nova seção traz:
   - o modo real e o modo demonstração;
   - a tabela de nomes dos dois lados (projeto/conversa, tarefa/etapa, avulso/individual…);
   - o que muda em cada tela e no desktop.
8. **Projetos:** `conversas.tipo = chat | projeto | agente`. A pasta em CHATS é uma conversa `projeto`.
9. **Especialistas visíveis.** No app, a equipe tem nome, cor e movimento, e aparece na pasta e na Ilha. **Agora:**
   - os especialistas são linhas em `agentes` (tipo `especialista`), com a aparência escolhida por código;
   - a Sora continua sendo a única voz: mensagem a um especialista vira correção de rota;
   - "Salvar como agente" promove um especialista a agente individual.
10. **Agente individual básico entrou na fase 1.** O app já tem o seletor **Equipe | Agente independente**: criar a partir do pedido, ter chat próprio e respeitar o limite de 5. Memória e rotinas continuam na fase 2. Foi criado um prompt novo, "Perfil de agente a partir do pedido".
11. **Painel Trabalho:**
    - tabela `passos` e evento `passo`;
    - o backend monta o rótulo de cada chamada de ferramenta;
    - progresso por passos.
12. **Revisão e versões:**
    - tabela `entregas` por versão;
    - rotas Aprovar e Pedir ajuste;
    - job `ajustar`.
    
    "Aprovar e publicar" vira **Aprovar** até existirem conectores (fase 3).
13. **Ilha e barra lateral:** canal de eventos do usuário (`GET /v1/eventos`), além do canal por conversa.
14. **Anexos:** tabela e rotas `POST/GET /v1/anexos`. A versão 1 citava anexos, mas não tinha onde enviá-los.
15. **Agentes:** rotas de agentes (criar, editar, apagar, promover) na fase 1, com aparência (`funcao`, `cor`, `movimento`).

### Entregas da demonstração

16. **Imagens:**
    - novo especialista **Designer**, com `gerar_imagem`, usando o modelo de imagem do próprio usuário;
    - ele só entra se o usuário conectou um modelo de imagem; sem isso, as peças viram texto com o Redator.

    A versão 1 só tinha busca e texto, e a campanha da demonstração ficava sem peças visuais.
17. **Ferramentas simuladas:** Figma, Canva, Instagram e Notion ficam só no modo demonstração. Elas viram reais com os conectores da fase 3.
18. **Cartões de pergunta:** ficaram todos na fase 1. A versão 1 tinha a ferramenta e a tabela na fase 1, mas o cartão na fase 2.

### Créditos, modelos e coerência

19. **Créditos × chaves próprias:**
    - a fase 1 usa as chaves do usuário;
    - o medidor de créditos do app vira **Uso do mês** (`GET /v1/uso`);
    - créditos só existem no modo demonstração;
    - sem API conectada, o usuário pode usar o modo demonstração.
20. **Catálogo de modelos:**
    - removido o "GPT-6 Luna", que contradizia o resto do catálogo;
    - entraram os modelos de imagem, com nome a confirmar;
    - embeddings agora são para o pgvector.
21. **Stack da interface:** agora descreve o que existe de verdade (React 19, Vite, TypeScript, `marked` + DOMPurify, Tauri v2). KaTeX, Mermaid e Tiptap entram quando fizerem falta.
22. **Estrutura do repositório:** agora é a real. O app em `app/` (com `src-tauri/`), e `backend/` e `infra/` como pastas novas na raiz, ao lado de `docs/`, `log/` e `CLAUDE.md`.
23. **Laya:** marcado como opcional. A fase 1 só grava os dados de treino.
24. **Revisor de ações:** fica na fase 3, porque as ferramentas da fase 1 não têm efeito externo. O `criar_agente` usa um cartão fixo já na fase 1.
25. **Divisão da equipe:** cada pessoa também liga a sua parte no app (provedores e modelos; eventos e modo demonstração).
26. **Testes novos:**
    - contrato de eventos compartilhado entre backend e app (`backend/tests/contrato/*.json`);
    - login no desktop;
    - Revisão e versões;
    - limite de agentes;
    - busca falsa.

## Decisões que continuam abertas

- **Tavily ou Brave:** conferir o plano gratuito e o preço vigentes antes de escolher. Basta um na fase 1.
- **Nome:** "Sora" colide com o produto de vídeo da OpenAI. Decidir antes de publicar o app.
- **OneDrive:** mover o repositório para fora do OneDrive antes de começar o backend, porque a sincronização atrapalha o `node_modules`, o `target/` do Rust e os volumes do Docker.
- **Assinatura do instalador:** assinar o `.exe`/`.msi` do app de desktop para o Windows não mostrar o aviso do SmartScreen.
