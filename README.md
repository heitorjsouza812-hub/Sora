# Sora

**Sora** é uma plataforma de **agentes de IA criados por conversa**. Você descreve o que precisa ("crie uma campanha para lançar minha cafeteria…") e a Sora:

1. entende o pedido;
2. monta um **plano**;
3. reúne uma **equipe de especialistas** (Pesquisador, Redator, Designer, Verificador);
4. coordena o trabalho entre eles;
5. entrega o resultado para você **revisar e aprovar**.

> Sua ideia. Seus agentes. Tudo em uma conversa.

Projeto em PT-BR. Cada pessoa usa as **próprias chaves de API** (OpenAI, Anthropic, Groq…), guardadas cifradas no servidor.

## Estado (outubro de 2026)

| Parte | Estado |
|---|---|
| **App** (`app/`) | Pronto: navegador e desktop (Tauri). Ainda simulado no navegador; a ligação com o backend é o próximo passo. |
| **Backend** (`backend/`) | Fase 1 em andamento. **A fundação está pronta e testada**: contas e login, cifra das chaves, banco e migrações, eventos em tempo real, busca, seletor de modelos e Sistema 1. **Falta** a cadeia de ponta a ponta: planejador, especialistas em LangChain, entregas e anexos. |
| **Infra** (`infra/`) | Docker Compose da fase 1 (Caddy, API, worker, PostgreSQL com pgvector, Redis) e scripts de backup. Deploy ainda não feito. |

O plano completo está em [`docs/plano-de-implementacao/`](docs/plano-de-implementacao/README.md): fases, arquitetura, especificação do backend e prompts.

## Estrutura

```text
app/          front-end: React 19 + Vite + TypeScript, e o app de desktop em app/src-tauri (Tauri v2)
backend/      API FastAPI, worker ARQ e agentes em LangChain (Python 3.12, uv)
  app/        api, core, modelos, eventos, llm, seletor, sistema1, orquestrador,
              agentes (+ middleware), ferramentas, busca, revisor, memoria
  workers/    jobs da fila
  prompts/    um arquivo .md por prompt, com versão no nome
  config/     política de modelos, catálogo e flags
  migrations/ Alembic
  tests/      unitarios, integracao, contrato (o formato dos eventos combinado com o app), ponta_a_ponta
infra/        docker-compose.yml, Caddyfile, .env.exemplo e scripts de backup
docs/         plano de implementação
log/          diário da equipe (comece por log/ONDE-PARAMOS.md)
CLAUDE.md     guia do projeto para pessoas e agentes de IA (AGENTS.md é a cópia para o Codex)
```

## Como rodar

### App

Requisitos: Node.js 20+.

```bash
cd app
npm install
npm run dev            # http://localhost:5173
npm run desktop        # app de desktop (precisa de Rust)
```

Mais detalhes em [`app/README.md`](app/README.md).

### Backend

Requisitos: [uv](https://docs.astral.sh/uv/) e Docker Desktop. O Docker serve para os testes de integração e para subir PostgreSQL e Redis.

```bash
cd backend
uv sync --python 3.12
uv run ruff check .
uv run pytest -q       # com o Docker ligado, os testes de integração também rodam
uv run uvicorn app.main:app --reload
```

Para os serviços reais, copie `infra/.env.exemplo` para um `.env` e preencha os segredos. **Nunca** coloque chave, token ou senha no repositório. Mais detalhes em [`backend/README.md`](backend/README.md) e [`infra/README.md`](infra/README.md).

**Modelo falso:** com `SORA_MODELO_FALSO=1`, o backend responde com respostas prontas, para desenvolver sem gastar com as APIs. O servidor se recusa a subir assim em produção.

## Próximos passos

1. **Backend de ponta a ponta:** conexão das APIs do usuário, prompt da Sora, modo Cadeia na fila, especialistas em LangChain, entregas com versões, cartões de pergunta, agente independente e anexos.
2. **Ligar o app ao backend:** camada `src/api`, telas de login, onboarding "Conecte sua primeira API", Configurações reais e "Uso do mês". A simulação sai do app.
3. **Deploy** e testes no GitHub Actions. Isso fecha a fase 1.

Fases 2 a 4 (memória, conectores, computador na nuvem): veja o [plano](docs/plano-de-implementacao/01-plano.md).
