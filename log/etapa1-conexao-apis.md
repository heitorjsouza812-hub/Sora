# Etapa 1 — Conexão das APIs do usuário (backend)

_Combinado em 2026-10-15 pelo orquestrador. Especificação de base: `docs/plano-de-implementacao/02-especificacao-do-backend.md` §1 (tabelas `provedores` e `modelos_disponiveis`), §2 (rotas) e §5 (como conectar, catálogo, seletor)._

Escopo: **só backend**. O app continua como está (ligar o app é a etapa seguinte). Nada de migração nova: as tabelas já existem (0001).

## O que já existe (não reescrever)

- `app/llm/provedores.py`: `ConfigProvedor`, `validar_base_url`, `listar_modelos` (teste da chave, com SSRF), `ChaveInvalida`, `ErroProvedor`, `DestinoBloqueado`, `politica_de_rede`.
- `app/core/seguranca.py`: `cifrar_segredo`, `decifrar_segredo`, `precisa_recifrar`, `recifrar_segredo`.
- `app/seletor/catalogo.py`: `obter_catalogo().classificar(nome) -> ClassificacaoModelo`.
- `app/seletor/tipos.py`: `ContextoSeletor`, `ModeloCandidato`, `ProvedorSeletor`.
- `app/llm/custo.py`: `gasto_do_mes_por_provedor(sessao, usuario_id)`.
- `app/modelos/esquemas.py`: `ProvedorCriacao`, `ProvedorAtualizacao`, `ProvedorSaida`, `ProvedorConexaoSaida`, `ModeloAtualizacao`, `ModeloSaida`, `PreferenciasAtualizacao`.
- `app/core/contas.py`: padrão `_limitar` (Redis) e `ErroConta`/`ErroLimite` (o `main.py` já converte `ErroConta` em resposta).

## Regras decididas

1. **Teste antes de salvar.** `POST /v1/provedores` valida `base_url`, chama `listar_modelos` e só grava se der certo. Falha → **422** com mensagem em PT-BR, sem a chave, e nada no banco.
   - `DestinoBloqueado`, `ChaveInvalida` e `ErroProvedor` viram 422 (mensagem da própria exceção).
   - Provedor que responde com lista vazia → 422 "O provedor não devolveu nenhum modelo."
   - Guardar no máximo **500 modelos** por provedor (os primeiros em ordem alfabética).
2. **Chave.** `chave` com espaços nas pontas é limpa. Obrigatória para groq, openai, anthropic, google e openrouter (falta → 422). Opcional para `compativel_openai` e `ollama`.
   - Cifra: `cifrar_segredo(chave, usuario_id=..., provedor=str(provedor.id))` — o **id da linha** é o AAD (gere o `uuid4` antes de cifrar). Mesma coisa ao decifrar.
   - `chave_final` = 4 últimos caracteres **só se a chave tiver 12 ou mais**; senão `None`.
   - A chave nunca aparece em resposta, log, exceção ou `repr`.
3. **Duplicado.** Já existe provedor ativo (não apagado) do mesmo usuário com o mesmo `tipo` e o mesmo `base_url` normalizado → **409** "Essa API já está conectada."
4. **Limites.** No máximo **10 provedores ativos** por usuário (o 11º → 409). Testes de chave (POST e PATCH com `chave`) limitados a **10 por hora por usuário** → 429 (reaproveitar o padrão `_limitar`/`ErroLimite`; chave Redis `provedor:teste:{usuario_id}`). Conta tentativa, não só falha.
5. **Cruzamento com o catálogo.** Cada modelo listado vira uma linha de `modelos_disponiveis` com `obter_catalogo().classificar(nome)` (nível, capacidades, contexto, preços, velocidade, `origem="catalogo"`). Modelo com `somente_se_escolhido` entra com `ativo=False`.
6. **`GET /v1/provedores`.** Só os não apagados do usuário, ordenados por `criado_em`, com `gasto_mes_usd` de `gasto_do_mes_por_provedor`. Sem chave.
7. **`PATCH /v1/provedores/{id}`.** Campos opcionais; use `model_fields_set` para separar "não enviado" de `null`.
   - `chave` enviada: testa de novo (mesmo tipo e `base_url`), recifra, atualiza `chave_final` e `validado_em`, zera `falhas_seguidas` e `pausado_ate`, e **sincroniza os modelos**: insere os novos; os que sumiram ficam `ativo=False`; os que já existiam **mantêm** `nivel`/`ativo` escolhidos pelo usuário. Falha no teste → 422 e nada muda.
   - `teto_mensal_usd`: `null` remove o teto; valor entre 0 e 100000 (fora → 422).
8. **`DELETE /v1/provedores/{id}`.** Apagado lógico: `apagado_em=now`, `chave_cifrada=None`, `chave_final=None`, e todos os modelos dele `ativo=False`. 204.
9. **Dono.** Provedor ou modelo de outro usuário (ou apagado) → **404** (igual a inexistente; não revelar).
10. **`GET /v1/modelos`.** Modelos dos provedores não apagados do usuário, ordenados por provedor (criado_em) e nome.
11. **`PATCH /v1/modelos/{id}`.** `nivel` ∈ {N1, N2, N3, especial} (outro → 422); `ativo` bool. Mudar o `nivel` grava `origem="usuario"`.
12. **`PATCH /v1/preferencias`.** Atualiza `usuarios.prioridade`. 204.
13. **`tem_provedor`** (em `/v1/eu`) passa a exigir `validado_em IS NOT NULL` e `apagado_em IS NULL`.
14. **412.** Nova dependência `exigir_provedor_validado` em `app/core/dependencias.py`: levanta 412 "Conecte uma API de modelos antes de fazer pedidos." quando o usuário não tem provedor validado. Ainda não é usada nas rotas de conversa (elas são esqueleto); só deixar pronta e testada.
15. **Injeção nos testes.** A rota não chama `listar_modelos` direto: usa a dependência `obter_listador()` de `app/api/provedores.py`, que devolve um `Callable[[ConfigProvedor], Awaitable[list[str]]]` (padrão: `app.llm.provedores.listar_modelos`). Os testes trocam com `app.dependency_overrides[obter_listador]`. **Nenhum teste chama a internet.**

## Divisão

| Quem | Arquivos (só estes) |
| --- | --- |
| **Conector** (Codex) | `app/core/conexoes.py` (novo: regras 1–9, funções `conectar`, `listar`, `atualizar`, `apagar`), `app/api/provedores.py`, `tests/unitarios/test_provedores_api.py` |
| **Catálogo** (Claude Code) | `app/api/modelos.py`, `app/api/preferencias.py`, `app/seletor/repositorio.py` (novo, ver abaixo), `app/core/dependencias.py` (regra 14), `app/core/contas.py` (só a regra 13), `tests/unitarios/test_modelos_api.py` |
| **Ensaio** (Hermes) | `tests/integracao/test_provedores.py` (novo): o fluxo inteiro com PostgreSQL e Redis reais (fixtures de `tests/integracao/conftest.py`) e o listador falso |
| **Vigia** (Codex, validador) | não edita produção; roda tudo e reporta |

`app/seletor/repositorio.py` (Catálogo):

- `async def contexto_do_usuario(sessao, usuario_id, *, conversa_privada=False) -> ContextoSeletor` — monta os candidatos a partir do banco (modelos de provedores não apagados e validados, `ProvedorSeletor` com `pausado_ate`, `teto_mensal_usd` e `gasto_mes_usd`; prioridade do usuário).
- `async def config_do_provedor(sessao, usuario_id, provedor_id) -> ConfigProvedor` — decifra a chave (AAD = id do provedor) e, se `precisa_recifrar`, regrava cifrado com a chave atual. Outro usuário ou apagado → `LookupError`.

## Pronto quando

- `uv run ruff check .` e `uv run ruff format --check .` limpos.
- `uv run pytest -q` verde (com o Docker ligado, os de integração também).
- Nenhum `NotImplementedError` sobrando em `provedores.py`, `modelos.py` e `preferencias.py`.
- Nenhuma chave em resposta, log ou mensagem de erro (os testes conferem com uma chave marcadora tipo `sk-TESTE-NAO-VAZAR-1234567890`).
