import { expect, test } from '@playwright/test';
// Login da conta de QA antes de cada teste (backend local precisa estar rodando).
import { entrarNoContexto } from '../../qa/entrar.mjs';

const pedido = 'Crie uma campanha para lançar minha cafeteria';

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
  await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}' });
}

async function captura(page: import('@playwright/test').Page, nome: string) {
  await expect(page).toHaveScreenshot(nome, {
    fullPage: true,
    mask: [page.locator('canvas')],
  });
}

test.beforeEach(async ({ page }) => {
  await entrarNoContexto(page.context());
  await limparEstado(page);
});

test('home vazia', async ({ page }) => {
  await captura(page, 'home.png');
});

for (const [rota, titulo] of [
  ['/projetos', 'Seus projetos'],
  ['/agentes', 'Seus agentes'],
  ['/agentes/novo', 'Criar agente'],
  ['/configuracoes', 'Configurações'],
  ['/lab/ui', 'Componentes base'],
] as const) {
  test(`tela ${rota}`, async ({ page }) => {
    await page.goto(rota);
    await expect(page.getByText(titulo, { exact: false }).first()).toBeVisible();
    await captura(page, `${rota.slice(1).replaceAll('/', '-')}.png`);
  });
}

test('projeto pronto', async ({ page }) => {
  // Backend real (modelo falso): cria o projeto pela própria interface e espera a equipe terminar.
  test.setTimeout(120_000);
  await page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i }).fill(pedido);
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//);
  await expect(page.getByRole('button', { name: 'Revisar', exact: true })).toBeVisible({ timeout: 90_000 });
  await captura(page, 'projeto-pronto.png');
});
