import { expect, test } from '@playwright/test';
// Login da conta de QA antes de cada teste (API, worker e Vite desta etapa precisam estar rodando).
import { entrarNoContexto } from '../../qa/entrar.mjs';

async function aguardarSessao(page: import('@playwright/test').Page) {
  await page.waitForLoadState('load');
  await page.waitForFunction(() => Boolean(window.__sora) && !window.__sora.lerEstado().carregando, null, { timeout: 20_000 });
}

async function limparEstado(page: import('@playwright/test').Page) {
  await page.goto('/');
  // Espera a renovação silenciosa terminar: navegar no meio dela gira o token sem o cookie novo chegar.
  // Não dá para usar 'networkidle': o app mantém o SSE agregado (/v1/eventos) sempre aberto.
  await aguardarSessao(page);
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.setItem('sora.chegou', '1');
  });
  await page.reload();
  await aguardarSessao(page);
  await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}.composer-beam canvas{display:none!important}' });
}

async function captura(page: import('@playwright/test').Page, nome: string) {
  await expect(page).toHaveScreenshot(nome, {
    fullPage: true,
    mask: [page.locator('canvas')],
  });
}

// Conta fixa (o cadastro tem limite de 5 por hora por IP). O login limpa conversas e bots; os grupos
// de rodadas anteriores são arquivados aqui para a barra lateral começar vazia.
test.beforeEach(async ({ page }) => {
  const sessao = await entrarNoContexto(page.context(), { limparConversas: true });
  const base = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
  const headers = { Authorization: `Bearer ${sessao.token_acesso}` };
  const grupos = await (await page.context().request.get(`${base}/v1/grupos`, { headers })).json() as { id: string }[];
  for (const grupo of grupos) await page.context().request.post(`${base}/v1/canais-equipe/${grupo.id}/arquivar`, { headers, failOnStatusCode: false });
  // Perfis do navegador sobram de outras sessões de QA: a baseline parte sempre da lista vazia.
  const perfis = await page.context().request.get(`${base}/v1/navegador/perfis`, { headers, failOnStatusCode: false });
  if (perfis.status() === 200) for (const perfil of await perfis.json() as { perfil_id: string }[]) await page.context().request.delete(`${base}/v1/navegador/perfis/${perfil.perfil_id}`, { headers, failOnStatusCode: false });
  await limparEstado(page);
});

// Etapa 5: Sora · Bots · Grupos · Configurações. Rotas antigas (projetos, revisão, canais) só redirecionam
// e são conferidas no qa/e2e.mjs.
for (const [rota, titulo, nome] of [
  ['/', 'Em que posso te ajudar hoje?', 'sora'],
  ['/bots', 'Nenhum bot ainda', 'bots'],
  ['/grupos', 'Grupos reúnem seus bots', 'grupos'],
  ['/configuracoes', 'Configurações', 'configuracoes'],
  ['/configuracoes?secao=memoria', 'Nada guardado ainda.', 'configuracoes-secao-memoria'],
  ['/configuracoes?secao=rotinas', 'Nenhuma rotina ainda.', 'configuracoes-secao-rotinas'],
  ['/configuracoes?secao=habilidades', 'Nenhuma habilidade ainda.', 'configuracoes-secao-habilidades'],
  ['/configuracoes?secao=conectores', 'Nenhum conector ainda.', 'configuracoes-secao-conectores'],
  ['/configuracoes?secao=navegador', 'Perfis com login salvo', 'configuracoes-secao-navegador'],
  ['/configuracoes?secao=telegram', 'não está ligado', 'configuracoes-secao-telegram'],
  ['/lab/ui', 'Componentes base', 'lab-ui'],
] as const) {
  test(`tela ${rota}`, async ({ page }) => {
    await page.goto(rota);
    await expect(page.getByText(titulo, { exact: false }).first()).toBeVisible();
    // A foto só sai com a lista pronta: "Carregando provedores e modelos…" sobreposto deixava a captura intermitente.
    await expect(page.getByText(/^Carregando/)).toHaveCount(0);
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await captura(page, `${nome}.png`);
  });
}
