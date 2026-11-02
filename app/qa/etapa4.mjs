// Etapa 4 (passo 6): telas novas contra API + worker reais (modelo falso): Configurações (memória,
// rotinas, habilidades, conectores, Telegram), Canais de equipe e o painel do agente (contexto/fila).
// Uso: SORA_QA_BASE=http://localhost:5273 node qa/etapa4.mjs
import assert from 'node:assert/strict';
import { mkdir, readdir, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { chromium } from '@playwright/test';
import { BASE, QA_SENHA, entrarNoContexto } from './entrar.mjs';

const qaDir = dirname(fileURLToPath(import.meta.url));
const backendDir = join(qaDir, '..', '..', 'backend');
const shots = join(qaDir, 'shots');
await mkdir(shots, { recursive: true });
await Promise.all((await readdir(shots)).filter(a => a.startsWith('etapa4-') && a.endsWith('.png')).map(a => rm(join(shots, a))));

const EMAIL = process.env.SORA_QA_ETAPA4_EMAIL ?? 'qa-etapa4@sora.local';
const erros = [];
// microfone falso: o Chromium entrega um tom de teste, sem precisar de hardware
const browser = await chromium.launch({ headless: true, args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
let falha;
try {
  for (const [largura, altura] of [[1440, 900], [390, 844]]) {
    const vp = `${largura}x${altura}`;
    const contexto = await browser.newContext({ viewport: { width: largura, height: altura }, colorScheme: 'dark', permissions: ['microphone'] });
    await entrarNoContexto(contexto, { email: EMAIL });
    const { request } = contexto;
    const entrar = await (await request.post(`${BASE}/v1/auth/entrar`, { data: { email: EMAIL, senha: QA_SENHA } })).json();
    const H = { Authorization: `Bearer ${entrar.token_acesso}` };
    const api = async (metodo, caminho, data) => {
      const r = await request.fetch(`${BASE}${caminho}`, { method: metodo, headers: H, data, failOnStatusCode: false });
      if (r.status() >= 400) throw new Error(`${metodo} ${caminho} -> ${r.status()} ${await r.text()}`);
      return r.status() === 204 ? null : r.json();
    };
    // limpa o que sobrou de rodadas anteriores
    for (const c of await api('GET', '/v1/canais-equipe')) await api('POST', `/v1/canais-equipe/${c.canal_id}/arquivar`);
    for (const m of await api('GET', '/v1/memorias')) await api('DELETE', `/v1/memorias/${m.id}`);
    for (const r of await api('GET', '/v1/rotinas')) await api('DELETE', `/v1/rotinas/${r.id}`);
    for (const ab of await api('GET', '/v1/navegador/abas')) await api('DELETE', `/v1/navegador/abas/${ab.aba_id}`);
    for (const pf of await api('GET', '/v1/navegador/perfis')) await api('DELETE', `/v1/navegador/perfis/${pf.perfil_id}`);
    for (const h of await api('GET', '/v1/habilidades')) await api('DELETE', `/v1/habilidades/${h.id}`);
    for (const a of await api('GET', '/v1/agentes')) if (a.tipo !== 'sora') await api('DELETE', `/v1/agentes/${a.id}`);

    const mk = nome => api('POST', '/v1/agentes', { nome, funcao: 'Pesquisa', papel: `Você é ${nome}, especialista em pesquisa.`, cor: nome === 'Atlas' ? '#56A8FF' : '#46E8A8', movimento: 'vibracao', ferramentas: [] });
    const atlas = await mk('Atlas'); const nina = await mk('Nina');
    const canal = await api('POST', '/v1/canais-equipe', { nome: 'Lançamento', membros: [atlas.id, nina.id], lider_id: atlas.id });
    const canalId = canal.canal_id;
    await api('POST', `/v1/canais-equipe/${canalId}/mensagens`, { texto: 'Vamos montar o lançamento.' });
    await api('POST', '/v1/memorias', { conteudo: 'A cafeteria fecha às segundas.' });
    await api('POST', '/v1/rotinas', { titulo: 'Resumo da manhã', pedido: 'Resuma as novidades', daqui_segundos: 5 });
    await api('POST', '/v1/rotinas', { titulo: 'Revisão semanal', pedido: 'Revise as pendências', a_cada: 1, unidade: 'dias' });

    const page = await contexto.newPage();
    // o 422 do segredo na memória é provocado de propósito (uma vez por viewport)
    let esperado422 = 1; let esperado409 = 3; let esperado404 = 2; // 422 segredo, 409 limite, 404 voz (ditar + ouvir)
    page.on('console', m => {
      if (m.type() !== 'error') return;
      if (/status of 422/.test(m.text()) && esperado422-- > 0) return;
      if (/status of 409/.test(m.text()) && esperado409-- > 0) return;
      if (/status of 404/.test(m.text()) && esperado404-- > 0) return;
      erros.push(`${vp} console: ${m.text()}`);
    });
    page.on('pageerror', e => erros.push(`${vp} pageerror: ${e.message}`));
    const ver = async (nome) => page.screenshot({ path: join(shots, `etapa4-${nome}-${vp}.png`) });
    const ir = async (rota) => { await page.goto(`${BASE}${rota}`, { waitUntil: 'domcontentloaded' }); };

    // ── Memória ─────────────────────────────────────────────────────────────────────────
    await ir('/configuracoes?secao=memoria');
    await page.getByText('A cafeteria fecha às segundas.').waitFor({ timeout: 20_000 });
    await page.getByLabel('Nova lembrança').fill('Moro em Curitiba.');
    await page.getByRole('button', { name: 'Guardar' }).click();
    await page.getByText('Moro em Curitiba.').waitFor({ timeout: 10_000 });
    await ver('memoria');
    await page.getByRole('button', { name: 'Esquecer' }).first().click();
    await page.waitForFunction(() => document.querySelectorAll('.pc-lista > li').length === 1, null, { timeout: 10_000 });
    // o servidor recusa segredo e a tela mostra o motivo
    await page.getByLabel('Nova lembrança').fill('minha senha é hunter2 e a api_key=sk-abcdefghijklmnop');
    await page.getByRole('button', { name: 'Guardar' }).click();
    await page.getByRole('alert').first().waitFor({ timeout: 10_000 });

    // ── Rotinas (a rotina de 5 s roda no worker) ────────────────────────────────────────
    await ir('/configuracoes?secao=rotinas');
    await page.locator('.pc-lista').getByText('Resumo da manhã').waitFor({ timeout: 20_000 });
    const unica = page.locator('.pc-lista > li', { hasText: 'Resumo da manhã' });
    await unica.getByRole('button', { name: 'Histórico' }).click();
    await unica.locator('.pc-execs').getByText(/Enviada|Sem resposta/).waitFor({ timeout: 60_000 });
    await ver('rotinas');
    // a rotina de execução única se desativa depois de rodar; a recorrente pausa e retoma
    await unica.getByText(/pausada/).waitFor({ timeout: 15_000 });
    const semanal = page.locator('.pc-lista > li', { hasText: 'Revisão semanal' });
    await semanal.getByRole('button', { name: 'Pausar' }).click();
    await semanal.getByRole('button', { name: 'Retomar' }).waitFor({ timeout: 10_000 });
    await semanal.getByRole('button', { name: 'Retomar' }).click();
    await semanal.getByRole('button', { name: 'Pausar' }).waitFor({ timeout: 10_000 });

    // ── Habilidades ─────────────────────────────────────────────────────────────────────
    await ir('/configuracoes?secao=habilidades');
    await page.getByLabel('Nome', { exact: true }).fill('resumo-curto');
    await page.getByLabel('Para que serve').fill('Resume textos em três linhas.');
    await page.getByLabel('Instruções').fill('1. Leia o texto.\n2. Resuma em três linhas.');
    await page.getByRole('button', { name: 'Criar habilidade' }).click();
    await page.getByText('/resumo-curto').waitFor({ timeout: 10_000 });
    await ver('habilidades');

    // ── Conectores e Telegram ───────────────────────────────────────────────────────────
    await ir('/configuracoes?secao=conectores');
    await page.getByText('Nenhum conector ainda.').waitFor({ timeout: 15_000 });
    await ver('conectores');
    await ir('/configuracoes?secao=telegram');
    await page.getByText('O Telegram não está ligado neste servidor.').waitFor({ timeout: 15_000 });
    await ver('telegram');



    // ── Navegador: criar perfil, nome repetido (409) e abrir um site para entrar (aba assumida) ──
    await ir('/configuracoes?secao=navegador');
    await page.getByLabel('Novo perfil').fill('Pessoal');
    await page.getByRole('button', { name: 'Criar perfil' }).click();
    const pessoal = page.locator('.pc-lista > li', { hasText: 'Pessoal' });
    await pessoal.waitFor({ timeout: 15_000 });
    await page.getByLabel('Novo perfil').fill('Pessoal');
    await page.getByRole('button', { name: 'Criar perfil' }).click();
    await page.getByRole('alert').filter({ hasText: 'Já existe um perfil com esse nome' }).waitFor({ timeout: 10_000 });
    assert.equal((await api('GET', '/v1/navegador/perfis')).filter(pf => pf.nome === 'Pessoal').length, 1, 'o servidor não duplicou o perfil');
    await pessoal.getByLabel(/Site para entrar em/).fill('https://example.com/');
    await pessoal.getByRole('button', { name: 'Abrir para entrar' }).click();
    // O worker precisa lançar o Chromium. Se o ambiente não permite (ex.: worker no Windows), o servidor
    // responde 409 com o motivo e a tela deve mostrá-lo; o passo vira AVISO, salvo com SORA_QA_EXIGIR_NAVEGADOR=1.
    const abriu = pessoal.getByText('Aba aberta para você entrar');
    const recusou = pessoal.getByRole('alert');
    await abriu.or(recusou).first().waitFor({ timeout: 80_000 });
    if (await abriu.count()) {
      const abas = await api('GET', '/v1/navegador/abas');
      assert.equal(abas.length, 1); assert.equal(abas[0].assumida_pelo_usuario, true, 'a aba nasce assumida pelo usuário');
      await ver('navegador-login');
      await pessoal.getByRole('button', { name: 'Concluir e fechar' }).click();
      await abriu.waitFor({ state: 'detached', timeout: 10_000 });
      assert.equal((await api('GET', '/v1/navegador/abas')).length, 0, 'concluir fecha a aba');
    } else {
      assert.ok(!process.env.SORA_QA_EXIGIR_NAVEGADOR, 'SORA_QA_EXIGIR_NAVEGADOR=1: o navegador precisava abrir');
      const motivo = (await recusou.first().innerText()).trim();
      assert.ok(motivo.length > 5, 'a tela mostra o motivo do servidor');
      await ver('navegador-login-recusado');
      console.log(`AVISO: o worker não abriu o Chromium neste ambiente (${motivo}); "abrir para entrar" provado só até a recusa.`);
    }

    // ── Navegador: perfis com login salvo e domínios aprovados (semeados com o código do backend) ──
    const perfilId = execFileSync('uv', ['run', 'python', join(qaDir, 'semear_perfil.py'), EMAIL, 'Trabalho', 'banco.com', 'loja.com'],
      { cwd: backendDir, env: { ...process.env, AMBIENTE: process.env.AMBIENTE ?? 'desenvolvimento' }, shell: process.platform === 'win32' }).toString().trim().split(String.fromCharCode(10)).pop().trim();
    await ir('/configuracoes?secao=navegador');
    const cartao = page.locator('.pc-lista > li', { hasText: 'Trabalho' });
    await cartao.waitFor({ timeout: 20_000 });
    await cartao.getByText('Perfil nomeado').waitFor();
    await cartao.getByText('banco.com').waitFor(); await cartao.getByText('loja.com').waitFor();
    await ver('navegador');
    await page.getByRole('button', { name: 'Revogar loja.com em Trabalho' }).click();
    await cartao.getByText('loja.com').waitFor({ state: 'detached', timeout: 10_000 });
    const depois = (await api('GET', '/v1/navegador/perfis')).find(pf => pf.perfil_id === perfilId);
    assert.deepEqual(depois.dominios_aprovados, ['banco.com'], 'o servidor revogou só loja.com e manteve o login');
    await cartao.getByRole('button', { name: 'Apagar perfil' }).click();
    await page.getByText('Apagar este perfil?').waitFor();
    assert.ok((await api('GET', '/v1/navegador/perfis')).some(pf => pf.perfil_id === perfilId), 'nada some antes da confirmação');
    await page.waitForTimeout(500); // fim da animação do modal
    await ver('navegador-apagar');
    await page.getByRole('dialog').getByRole('button', { name: 'Apagar perfil' }).click();
    await cartao.waitFor({ state: 'detached', timeout: 10_000 });
    await page.locator('.pc-lista > li', { hasText: 'Pessoal' }).waitFor(); // o outro perfil segue
    assert.equal((await api('GET', '/v1/navegador/perfis')).some(pf => pf.perfil_id === perfilId), false);

    // ── Canais de equipe ────────────────────────────────────────────────────────────────
    await ir('/canais');
    await page.getByRole('button', { name: /Lançamento/ }).click();
    await page.getByText('Vamos montar o lançamento.').waitFor({ timeout: 15_000 });
    await page.getByLabel('Mensagem para o canal').fill('Atlas, pesquise concorrentes.');
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    await page.getByText('Atlas, pesquise concorrentes.').waitFor({ timeout: 15_000 });
    await ver('canais');
    await page.getByRole('button', { name: 'Reagir com 👍' }).first().click();
    await page.getByRole('button', { name: 'Reagir com 👍' }).first().filter({ hasText: '1' }).waitFor({ timeout: 10_000 });
    await page.getByRole('button', { name: 'Apagar' }).first().click();
    await page.getByRole('button', { name: 'Apagados' }).click();
    await page.getByRole('button', { name: /Lançamento/ }).first().waitFor({ timeout: 10_000 });


    // ── Voz: sem provedor de voz o servidor responde 404 e o app avisa em PT-BR ─────────────
    await ir(`/chat/${atlas.id}`);
    const campo = page.getByRole('textbox', { name: /Mensagem para Atlas/ });
    await campo.waitFor({ timeout: 20_000 });
    await page.getByRole('button', { name: 'Ativar microfone' }).click();
    await page.getByRole('button', { name: 'Parar microfone' }).waitFor({ timeout: 10_000 });
    await page.waitForTimeout(2500); // o tom de teste precisa render mais que 1,5 KB de áudio
    const transcricao = page.waitForResponse(r => r.url().includes('/v1/voz/transcrever'), { timeout: 20_000 });
    await page.getByRole('button', { name: 'Parar microfone' }).click();
    assert.equal((await transcricao).status(), 404, 'sem provedor de voz o servidor responde 404');
    await page.locator('.composer-notice.is-on').getByText('conecte uma chave da OpenAI em Configurações → Modelos de IA').waitFor({ timeout: 10_000 });
    assert.equal(await campo.inputValue(), '', 'o campo não recebe texto quando a voz falha');
    await ver('voz-sem-provedor');

    // ── "Ouvir" numa resposta: mesmo 404, com aviso em vez de falha ─────────────────────
    await campo.fill('oi, tudo bem?');
    await page.getByRole('button', { name: 'Enviar mensagem' }).click();
    const ouvir = page.locator('.msg-acoes button[aria-label="Ouvir"]').first(); // a barra só aparece no hover
    await ouvir.waitFor({ state: 'attached', timeout: 40_000 });
    const ultima = page.locator('.chat-msg.is-assistant').last();
    await ultima.hover();
    if (largura <= 600) await ultima.getByRole('button', { name: 'Mais ações' }).click(); // no celular as ações ficam atrás do "…"
    const [fala] = await Promise.all([page.waitForResponse(r => r.url().includes('/v1/voz/falar'), { timeout: 20_000 }), ouvir.click()]);
    assert.equal(fala.status(), 404);
    await page.getByText('conecte uma chave da OpenAI em Configurações → Modelos de IA').first().waitFor({ timeout: 10_000 });

    // ── Painel do agente: contexto e fila ───────────────────────────────────────────────
    await ir(`/chat/${atlas.id}`);
    if (largura <= 600) await page.locator('.work-pill').click(); // no celular o painel abre numa folha
    await page.getByRole('tab', { name: 'Perfil' }).click();
    await page.getByLabel('Contexto').first().waitFor({ state: 'attached', timeout: 15_000 });
    await ver('agente');

    // ── Perfil do navegador do agente (PUT/GET /v1/agentes/{id}/navegador) ──────────────
    const seletor = page.getByLabel('Perfil do navegador deste agente');
    await seletor.waitFor({ timeout: 15_000 });
    assert.equal((await api('GET', `/v1/agentes/${atlas.id}/navegador`)).tipo, 'compartilhado');
    await ver('agente-navegador');
    await seletor.selectOption({ label: 'Pessoal' });
    const noServidor = async (tipo) => { for (let i = 0; i < 40; i++) { const n = await api('GET', `/v1/agentes/${atlas.id}/navegador`); if (n.tipo === tipo) return n; await page.waitForTimeout(250); } throw new Error(`o servidor não passou o agente para ${tipo}`); };
    const comPerfil = await noServidor('perfil');
    assert.equal(comPerfil.tipo, 'perfil'); assert.equal(comPerfil.perfil_nome, 'Pessoal');
    await seletor.selectOption({ label: 'Sem login (aba descartável)' });
    await noServidor('efemero');
    await page.getByText(/sem login salvo e sem pedir aprovação/).waitFor();
    await ir(`/chat/${atlas.id}`);
    if (largura <= 600) await page.locator('.work-pill').click();
    await page.getByRole('tab', { name: 'Perfil' }).click();
    await page.waitForFunction(() => document.querySelector('[aria-label="Perfil do navegador deste agente"]')?.value === 'efemero', null, { timeout: 15_000 });

    // ── Pendências do agente (rotas da Âncora) ──────────────────────────────────────────
    await page.getByLabel('Nova pendência').fill('Ligar para o fornecedor');
    await page.locator('.eq-pend-novo').getByLabel('Notas (opcional)').fill('depois das 14h');
    await page.getByRole('button', { name: 'Adicionar pendência' }).click();
    const item = page.locator('.eq-pend', { hasText: 'Ligar para o fornecedor' });
    await item.waitFor({ timeout: 10_000 });
    await item.getByText('depois das 14h').waitFor();
    await page.getByLabel('Nova pendência').fill('Revisar o orçamento');
    await page.getByLabel('Criar como estacionada').check();
    await page.getByRole('button', { name: 'Adicionar pendência' }).click();
    await page.getByText('Estacionadas (1)').waitFor({ timeout: 10_000 });
    await ver('pendencias');
    await item.getByRole('button', { name: 'Editar' }).click();
    await page.getByRole('form', { name: /Editar pendência/ }).getByLabel('Título').fill('Ligar hoje para o fornecedor');
    await page.getByRole('form', { name: /Editar pendência/ }).getByRole('button', { name: 'Salvar' }).click();
    const editado = page.locator('.eq-pend', { hasText: 'Ligar hoje para o fornecedor' });
    await editado.waitFor({ timeout: 10_000 });
    await editado.getByLabel(/Status de/).selectOption('concluida');
    await page.getByText('Concluídas (1)').waitFor({ timeout: 10_000 });
    // o servidor guardou: confere pela API, não só pela tela
    const guardadas = await api('GET', `/v1/agentes/${atlas.id}/pendencias?incluir_concluidas=true`);
    assert.deepEqual(guardadas.map(p => [p.titulo, p.status]).sort(), [['Ligar hoje para o fornecedor', 'concluida'], ['Revisar o orçamento', 'estacionada']]);
    await page.locator('.eq-pend', { hasText: 'Revisar o orçamento' }).getByRole('button', { name: 'Apagar' }).click();
    await page.getByText('Estacionadas (1)').waitFor({ state: 'detached', timeout: 10_000 });

    // limite: com 100 abertas o servidor responde 409 e a tela explica em PT-BR
    for (let i = 0; i < 100; i++) await api('POST', `/v1/agentes/${nina.id}/pendencias`, { titulo: `Tarefa ${i}` });
    await ir(`/chat/${nina.id}`);
    if (largura <= 600) await page.locator('.work-pill').click();
    await page.getByRole('tab', { name: 'Perfil' }).click();
    await page.getByLabel('Nova pendência').fill('Uma a mais');
    await page.getByRole('button', { name: 'Adicionar pendência' }).click();
    await page.getByRole('alert').filter({ hasText: '100 pendências abertas' }).waitFor({ timeout: 10_000 });
    await ver('pendencias-limite');

    await contexto.close();
  }
} catch (e) { falha = e; }
await browser.close();
if (falha) { console.error(falha); process.exit(1); }
assert.deepEqual(erros, [], `console deve ficar limpo:\n${erros.join('\n')}`);
console.log('Etapa 4 aprovada: memória, rotinas (worker real), habilidades, conectores, navegador (perfis: criar, 409, abrir para entrar, revogar, apagar, perfil do agente), Telegram, canais e painel do agente em 1440/390; pendências (incl. limite 409) e voz pelo caminho 404 em 1440/390; console limpo.');
