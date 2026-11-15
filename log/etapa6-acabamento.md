# Etapa 6: acabamento até o nível do Grok Bot (e além)

Pedido do Heitor em 2026-11-14: terminar a Sora com todas as funcionalidades, "igual ou melhor que o Grok Bot", usando quantos agentes forem necessários. Continua no ramo `etapa5-interface`, worktree `C:\dev\sora-e5` (base `cad9457`). Referência de experiência só: nada de texto, código, ícone ou marca da xAI.

Análise completa da Lupa (Claude Fable): `.maestri/relatorios/lupa-grok.md` (pasta ignorada pelo git). A lista abaixo é a cópia de trabalho.

## Lista (Lupa, 2026-11-14)

**P0 — o que engana ou trava**
1. Parar funciona no bot e na Sora (rota `POST /v1/conversas/{id}/parar` + app). *ambos*
2. Grupo com o mesmo chat do 1:1 (markdown, compositor completo, avatares `SoraOrb`). *app*
3. Sem botão que não faz nada ("Compartilhar" e 👍/👎 somem até haver rota). *app*
4. Bolha na hora (otimista, "Tentar de novo") e carga das mensagens sob demanda. *app*
5. Streaming sem puxar a rolagem ("Ir para o fim"; render no máximo 1x por quadro). *app*
6. Cartão de rascunho sem termo técnico (chips de ferramenta, rotina "Todo dia/Dias úteis/Toda semana + hora", amostras de cor). *app*
7. Central "Precisa de você" na barra lateral + cartão único (Permitir uma vez · Sempre permitir · Recusar). *app*
8. Imagens do test:visual atuais e com telas cheias. *app (validador, no fim)*

**P1 — alcança o Grok na conversa**
9. Fontes citadas na resposta (chips numerados, persistem). *ambos*
10. Imagem e arquivo dentro da resposta; visão de imagem anexada. *ambos*
11. Editar pergunta, refazer resposta, avaliação 👍/👎 guardada. *ambos*
12. Primeiro uso "crie seu primeiro bot" e estados vazios com um CTA. *app*
13. Notificação do sistema quando o app está fora de foco ("(N) Sora" no título). *app/Tauri*
14. Rotinas e Memória editáveis dentro do bot; chip "guardei isto" com Desfazer. *ambos*
15. Gerir o grupo (membros 2–5, arquivar, Reatribuir/Cancelar, menções com teclado, celular em duas telas). *app*
16. Conversa por voz contínua no bot. *app*
17. Busca nas mensagens na paleta Ctrl+K. *ambos*

**P2 — vantagem**
18. Navegador do bot ao vivo (imagem ≥1/s, Assumir clicando na imagem). *ambos*
19. Código realçado sob demanda, tabela rolável, pacote inicial < 500 kB. *app*
20. Vocabulário e limpeza (sem "agente"/"projeto" visível, sem cafeteria, `/plugins` → `/`, telas mortas apagadas, contraste 4,5:1). *app*

Também abertos da etapa 5: B1, B2, B3, B5, B7 e a renovação da sessão (decisão 8) — com a Âncora-2.

## Computador e navegador por bot (pedido do Heitor, 2026-11-14)

- **C1 Navegador próprio por bot:** perfil "do agente" (`TipoPerfil.AGENTE`) vira o padrão de bot novo; a tela do bot mostra qual navegador usa; dois bots navegam em paralelo sem se atrapalhar (teste).
- **C2 Computador virtual por bot:** cada bot ganha um computador isolado com tela (contêiner Linux com área de trabalho, navegador e arquivos), ferramentas de captura, mouse, teclado e arquivos; tela ao vivo no painel Trabalho; roda em paralelo. Mesmas regras do sandbox (host separado em produção, fora de rotina sem supervisão).
- **C3 Controle do PC do usuário (só app desktop):** ponte local no Tauri com árvore de acessibilidade do Windows (UI Automation), captura, mouse e teclado; **um bot por vez** (vez/fila); desligado por padrão, ligado por bot em Configurações; borda acesa enquanto controla, **Parar** sempre visível, mexer no mouse pausa; primeira ação em cada programa vira cartão "Precisa de você"; nunca digita senha. Não controla o servidor.

## Canais da empresa (pedido do Heitor, 2026-11-14)

- **D1 Ler e virar memória:** canais escolhidos pelo usuário (Slack via app oficial; WhatsApp só pela API oficial do WhatsApp Business num número da empresa; nada de WhatsApp pessoal nem biblioteca não oficial) → fila → resumo → **ficha por cliente** (preferências, pedidos, promessas, prazos, reclamações, com link para a mensagem de origem) na memória, consultável pelos bots e pela busca.
- ~~D2 Responder~~ e ~~D3 Resumo do dia~~: **removidos (Heitor, 2026-11-14)**. Os canais são **só leitura**; a Sora nunca envia nada por eles (Slack sem `chat:write`).
- **D4 Aprendizado da empresa (autoaperfeiçoamento):** das conversas sai uma **base de conhecimento** (FAQ e boas respostas dos funcionários, produtos/preços/termos, políticas e processos, tom de voz, objeções), sem dado pessoal, consultável pelos bots autorizados; uma rotina semanal compara o aprendido com as instruções/habilidades de cada bot e gera **sugestões de melhoria** em cartão "Precisa de você" (Aplicar · Editar · Descartar), com versão anterior para desfazer.
- **LGPD:** só canais escolhidos, aviso ao cliente, mascarar CPF/cartão/senha antes de guardar, retenção configurável, "apagar tudo deste cliente", ficha visível só para bots/grupos autorizados.
- App: tela **Clientes** com as fichas; Configurações → Canais da empresa. Depois: e-mail e Teams pelo mesmo encaixe. Telegram já existe.
- **Decidido (Heitor, 2026-11-14):** atendimento pelo número WhatsApp Business da empresa → Cloud API oficial (verificar modo de coexistência com o app do celular ao conectar).

## Ondas e donos

Regra de modelo (Heitor): tarefa simples → modelo leve; só segurança, arquitetura e bug difícil → modelo forte.

| Onda | Dono | Modelo | Escopo |
|---|---|---|---|
| A | Âncora-2 | Codex gpt-6.1-sol high | backend: B1–B7, decisão 8 |
| A | Leme-2 | Codex gpt-6-astra medium | app conversa: 3, 4, 5, 19, parte da 20 (rotas mortas, `/plugins`) |
| A | Mosaico-2 | Claude Sonnet 5.5 high | app grupos/pendências: 2, 7, 15, B3 na tela |
| A | Brisa-2 | Claude Sonnet 5.5 medium | app rascunho/primeiro uso/textos: 6, 12, 20 (textos) |
| A | Vela-2 | Codex gpt-6.1-terra medium | desktop: 13 |
| B | Âncora-3 | backend | 1, 9, 10, 11, 14, 17 (rotas) e depois app delas |
| C | a definir | | C1, C2, C3, 16, 18 |
| fim | Prumo-2 | validador | 8 + validação completa + modelo real |

## Regras para todo o time

As de `log/etapa5-interface.md` (portas 8200/5383, bancos `sora-e5-*`, PT-BR, sem demonstração, mascote e cores intocados, Plugins escondido), mais:
- Cada agente só edita os caminhos do seu escopo. Arquivo de outro dono: só **consumir** (importar); se precisar de mudança, edição mínima e aditiva registrada em `.maestri/contrato-etapa5.md`.
- Antes de commitar no app: `npm run build`, `npx oxlint`, `npm test`. Commit só dos seus caminhos (`git commit -- caminhos`), em PT-BR. Sem push.
- Relatório em `.maestri/relatorios/<nome>.md` ao terminar.

## Teste com modelo real (decisão do Heitor, 2026-11-15)

- O app e o worker do ambiente de testes passam a rodar com **modelo real (Groq)**, não com `SORA_MODELO_FALSO`. A chave do Heitor está em `backend/.env` como `SORA_QA_GROQ_CHAVE` (arquivo ignorado pelo git; **nunca** copiar para commit, log, relatório ou contrato). O QA cadastra a chave na conta de teste pela rota `/v1/provedores` lendo a variável.
- Limite grátis da Groq: ao bater 429, esperar e continuar (o backend já respeita o limite por minuto; scripts de QA com espera e nova tentativa).
- O modelo falso continua só nas suítes automáticas (unitários e integração com testcontainers), que não podem gastar o limite nem depender de rede.
