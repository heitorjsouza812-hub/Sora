// Uso: node qa/ferramentas-live-cenarios.mjs <cenario> [...]   (veja CENARIOS)
import { sessao, http, turno, soraId, mensagens, API, dorme, novaConversa } from './ferramentas-live.mjs';
import { readFileSync, writeFileSync } from 'node:fs';

const { token, est } = await sessao();
const sora = await soraId(token);
const guardar = (k, v) => { est[k] = v; writeFileSync(new URL('./shots/ferramentas-live/estado.json', import.meta.url), JSON.stringify(est)); };

async function responder(ev, conv, valor) {
  const p = ev.eventos.find((e) => e.ev === 'pergunta');
  if (!p) return console.log('(sem pergunta)');
  console.log('responde pergunta', p.d.pergunta_id, valor ?? p.d.opcoes?.[0]?.valor);
  const r = await http(token, 'POST', `/v1/perguntas/${p.d.pergunta_id}/responder`, { valor: valor ?? p.d.opcoes?.[0]?.valor ?? 'sim' });
  console.log('status', r.status);
}

async function bot(descricao) {
  const r = await http(token, 'POST', '/v1/bots/criar-por-descricao', { descricao });
  if (r.status !== 201) throw new Error(`bot ${r.status} ${JSON.stringify(r.dados)}`);
  console.log('bot', r.dados.id, r.dados.nome, JSON.stringify(r.dados.ferramentas));
  return r.dados;
}

async function permitir(ev) {
  // aceita cartoes "Precisa de voce" pendentes (permitir uma vez)
  const lista = await http(token, 'GET', '/v1/atencao');
  console.log('atencao', JSON.stringify(lista.dados).slice(0, 400));
}

async function botQa(ferramentas) {
  if (est.botQa && !ferramentas) return est.botQa;
  const nome = 'Faro' + Math.random().toString(36).slice(2, 6);
  const r = await http(token, 'POST', '/v1/agentes', { nome, funcao: 'Testador de ferramentas', papel: 'Você é um bot de QA. Faça exatamente o que o usuário pedir usando as ferramentas e conte o resultado em poucas palavras.', ferramentas });
  if (r.status !== 201) throw new Error(`agente ${r.status} ${JSON.stringify(r.dados)}`);
  console.log('bot', r.dados.id, r.dados.nome, JSON.stringify(r.dados.ferramentas));
  guardar('botQa', r.dados.id);
  return r.dados.id;
}
const TOOLS_BOT = ['falar', 'perguntar', 'ler_anexo', 'buscar_web', 'ler_pagina', 'escrever_arquivo', 'navegador_abrir', 'navegador_observar', 'navegador_elemento', 'navegador_acao', 'navegador_esperar'];
async function anexo(nome, conteudo, tipo = 'text/plain') {
  const f = new FormData(); f.append('arquivo', new Blob([conteudo], { type: tipo }), nome);
  const r = await http(token, 'POST', '/v1/anexos', f);
  console.log('anexo', r.status, JSON.stringify(r.dados));
  return r.dados.anexo_id;
}

const CENARIOS = {
  async c4b() {
    const b = await botQa(['falar', 'perguntar', 'escrever_arquivo']);
    await turno(token, { agenteId: b, texto: 'Pesquise na web quem é o presidente do Brasil e cite a fonte.', titulo: '4a PATCH: bot SEM buscar_web', max: 240000 });
    const p = await http(token, 'PATCH', `/v1/agentes/${b}`, { ferramentas: ['falar', 'perguntar', 'escrever_arquivo', 'buscar_web', 'ler_pagina'] });
    console.log('PATCH', p.status, JSON.stringify(p.dados?.ferramentas));
    await turno(token, { agenteId: b, texto: 'Pesquise na web quem é o presidente do Brasil e cite a fonte.', titulo: '4b PATCH: bot COM buscar_web (nova conversa)', max: 240000 });
    const p2 = await http(token, 'PATCH', `/v1/agentes/${b}`, { ferramentas: ['falar', 'perguntar', 'computador_observar', 'computador_agir'] });
    console.log('PATCH computador', p2.status, JSON.stringify(p2.dados?.ferramentas));
    console.log('estado computador', JSON.stringify((await http(token, 'GET', `/v1/agentes/${b}/computador`)).dados));
    await turno(token, { agenteId: b, texto: 'Use o seu computador para abrir o navegador e me diga o que aparece na tela.', titulo: '3 computador virtual', max: 240000 });
  },
  async c5dup() {
    // resposta duplicada: bot individual, perguntas simples seguidas; conta mensagens do bot com texto igual
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    const a = await turno(token, { agenteId: b, texto: 'Qual é a capital da França? Responda curto.', titulo: '5-dup 1', max: 200000 });
    for (const t of ['E a da Itália?', 'Agora escreva o arquivo capitais.txt com as duas capitais.', 'Obrigado!']) {
      await turno(token, { conversaId: a.id, texto: t, titulo: '5-dup ' + t, max: 240000 });
    }
    const ms = await mensagens(token, a.id);
    const ag = ms.filter((m) => m.autor === 'agente');
    const iguais = ag.filter((m, i) => ag.findIndex((x) => x.conteudo.trim() === m.conteudo.trim()) !== i);
    console.log('MENSAGENS DO BOT:', ag.length, 'DUPLICADAS:', iguais.length, JSON.stringify(ag.map((m) => m.conteudo.slice(0, 80))));
  },
  async c5parar() {
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    const c = await novaConversa(token, b, 'Use o navegador (navegador_abrir) para abrir https://example.com, depois use navegador_esperar para esperar 30 segundos, e só então me diga o título. Não use ler_pagina.');
    const ouv = (await import('./ferramentas-live.mjs')).ouvir(token, c.id);
    const t0 = Date.now(); let parou = false;
    while (Date.now() - t0 < 150000 && !parou) {
      await dorme(1500);
      if (ouv.eventos.some((e) => (e.ev === 'passo' || e.ev === 'mensagem.fim') && (e.d.tipo === 'prompt' || e.d.ferramenta === 'falar' || e.ev === 'mensagem.fim'))) {
        const r = await http(token, 'POST', `/v1/conversas/${c.id}/parar`); console.log('PARAR', r.status, ((Date.now() - t0) / 1000).toFixed(1) + 's'); parou = true;
      }
    }
    console.log('parou?', parou);
    await dorme(20000);
    ouv.fechar();
    console.log((await import('./ferramentas-live.mjs')).resumo(ouv.eventos));
    await turno(token, { conversaId: c.id, texto: 'Pode me dizer o que você já tinha feito? Responda curto.', titulo: '5-parar: nova mensagem depois do Parar', max: 240000 });
  },
  async c4() {
    const b = await botQa(['falar', 'perguntar', 'escrever_arquivo']);
    const r0 = await http(token, 'GET', '/v1/agentes'); console.log('antes', JSON.stringify(r0.dados.find((a) => a.id === b).ferramentas));
    const a = await turno(token, { agenteId: b, texto: 'Me lembre daqui a 3 horas de ligar para o fornecedor (use a ferramenta agendar).', titulo: '4a bot SEM agendar', max: 240000 });
    const p = await http(token, 'PATCH', `/v1/agentes/${b}`, { ferramentas: ['falar', 'perguntar', 'escrever_arquivo', 'agendar', 'listar_agendamentos', 'cancelar_agendamento', 'gerar_grafico'] });
    console.log('PATCH', p.status, JSON.stringify(p.dados?.ferramentas));
    const g = await http(token, 'GET', '/v1/agentes'); console.log('depois', JSON.stringify(g.dados.find((x) => x.id === b).ferramentas));
    const c = await turno(token, { agenteId: b, texto: 'Me lembre daqui a 3 horas de ligar para o fornecedor.', titulo: '4b bot COM agendar (nova conversa)', max: 240000 });
    await turno(token, { conversaId: c.id, texto: 'Liste meus agendamentos.', titulo: '4c listar_agendamentos', max: 240000 });
    await turno(token, { conversaId: c.id, texto: 'Cancele o lembrete do fornecedor.', titulo: '4d cancelar_agendamento', max: 240000 });
    await turno(token, { agenteId: b, texto: 'Faça um gráfico de barras com vendas: jan 10, fev 20, mar 15.', titulo: '4e gerar_grafico', max: 240000 });
  },
  async c2a() {
    const b = await botQa(TOOLS_BOT);
    await turno(token, { agenteId: b, texto: 'Crie um arquivo chamado ola.txt com o texto "teste de ferramenta Faro" e me avise.', titulo: '2a bot escrever_arquivo', max: 240000 });
  },
  async c2b() {
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    const a = await anexo('lista.txt', 'Compras: 3 maçãs, 2 pães, 1 café. Código secreto: ZEBRA-42.');
    await turno(token, { agenteId: b, texto: 'Leia o anexo e me diga o código secreto.', anexos: [a], titulo: '2b bot ler_anexo', max: 240000 });
  },
  async c2c() {
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    await turno(token, { agenteId: b, texto: 'Pesquise na web: quem ganhou a Copa do Mundo de 2022? Cite a fonte.', titulo: '2c bot buscar_web', max: 240000 });
  },
  async c2d() {
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    await turno(token, { agenteId: b, texto: 'Leia a página https://example.com e diga em uma frase do que ela trata.', titulo: '2d bot ler_pagina', max: 240000 });
  },
  async c2e() {
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    await turno(token, { agenteId: b, texto: 'Abra https://example.com no navegador, observe a página e me diga qual é o título (cabeçalho) principal.', titulo: '2e bot navegador', max: 300000 });
  },
  async c5err() {
    const b = est.botQa ?? await botQa(TOOLS_BOT);
    await turno(token, { agenteId: b, texto: 'Leia a página https://este-dominio-nao-existe-faro3.invalid/x e me diga o que tem nela.', titulo: '5 ler_pagina URL inexistente', max: 300000 });
  },
  async c1g3() {
    const a = await turno(token, { agenteId: sora, texto: 'Use a ferramenta agendar para criar um lembrete único daqui a 3 horas com o título "ligar para o fornecedor". Em seguida use listar_agendamentos e me mostre o que aparece.', titulo: '1g3 agendar explicito', max: 240000 });
    await turno(token, { conversaId: a.id, texto: 'Agora use cancelar_agendamento para cancelar esse lembrete.', titulo: '1g3 cancelar explicito', max: 240000 });
  },
  async c1g2() {
    const a = await turno(token, { agenteId: sora, texto: 'Me lembre em 3 horas de ligar para o fornecedor.', titulo: '1g2 Sora agendar (lembrete)', max: 180000 });
    await turno(token, { conversaId: a.id, texto: 'Quais lembretes eu tenho agendados?', titulo: '1g2 listar_agendamentos', max: 180000 });
    await turno(token, { conversaId: a.id, texto: 'Cancele o lembrete do fornecedor.', titulo: '1g2 cancelar_agendamento', max: 180000 });
  },
  async c1a() { await turno(token, { agenteId: sora, texto: 'Oi, tudo bem? Responda em uma frase.', titulo: '1a Sora simples' }); },
  async c1b() { await turno(token, { agenteId: sora, texto: 'Qual a cotação do dólar hoje em reais? Pesquise na web e cite a fonte.', titulo: '1b Sora buscar_web', max: 180000 }); },
  async c1c() { await turno(token, { agenteId: sora, texto: 'Leia a página https://example.com e me diga em uma frase do que ela trata.', titulo: '1c Sora ler_pagina', max: 180000 }); },
  async c1d() {
    const a = await turno(token, { agenteId: sora, texto: 'Lembre-se disto: meu prato favorito é feijoada e eu moro em Curitiba.', titulo: '1d Sora lembrar' });
    await turno(token, { agenteId: sora, texto: 'Qual é o meu prato favorito e onde eu moro? Consulte sua memória.', titulo: '1d Sora buscar_memoria (nova conversa)' });
  },
  async c1e() { await turno(token, { agenteId: sora, texto: 'Crie um bot que toda manhã resuma as notícias de tecnologia para mim.', titulo: '1e Sora criar_agente', max: 180000 }); },
  async c1f() { await turno(token, { agenteId: sora, texto: 'Quero lançar uma campanha para minha cafeteria: pesquisa de referências, criação de peças e calendário de posts. Monte uma equipe (grupo) para isso.', titulo: '1f Sora propor_grupo', max: 180000 }); },
  async c1g() {
    const a = await turno(token, { agenteId: sora, texto: 'Agende um lembrete para daqui a 3 horas: "ligar para o fornecedor". Depois liste meus agendamentos.', titulo: '1g Sora agendar+listar', max: 180000 });
    await turno(token, { conversaId: a.id, texto: 'Agora cancele esse lembrete e confirme listando de novo.', titulo: '1g Sora cancelar_agendamento', max: 180000 });
  },
  async c1h() {
    const a = await turno(token, { agenteId: sora, texto: 'Adicione uma pendência: "renovar o domínio do site". Depois liste minhas pendências.', titulo: '1h Sora pendencias', max: 180000 });
  },
  async c1i() {
    const a = await turno(token, { agenteId: sora, texto: 'Eu quero uma ajuda para escolher um nome de empresa, mas antes pergunte-me, usando uma pergunta com opções, qual o setor: Comida, Moda ou Tecnologia.', titulo: '1i Sora perguntar', max: 120000 });
    await responder(a, a.id, 'Comida');
    const ouv = a.ouv; // stream fechado; reabre num novo turno vazio
    const { ouvir, esperar, resumo } = await import('./ferramentas-live.mjs');
    const o2 = ouvir(token, a.id); const ok = await esperar(o2, { max: 120000, quietoMs: 8000, desde: 0 }); o2.fechar();
    console.log('apos resposta:', ok ? 'concluiu' : 'TIMEOUT'); console.log(resumo(o2.eventos.slice(-25)));
  },
  async c1j() { await turno(token, { agenteId: sora, texto: 'Faça um gráfico de barras com vendas: jan 10, fev 20, mar 15.', titulo: '1j Sora gerar_grafico', max: 150000 }); },
};

for (const nome of process.argv.slice(2)) {
  if (!CENARIOS[nome]) { console.log('cenario desconhecido', nome); continue; }
  try { await CENARIOS[nome](); } catch (e) { console.log('ERRO no cenario', nome, e.message); }
}
process.exit(0);
