import { expect, test } from '@playwright/test';

const pedido = 'Crie uma campanha para lançar minha cafeteria';

async function limparEstado(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.setItem('sora.chegou', '1');
  });
  await page.reload();
  await page.waitForFunction(() => Boolean(window.__sora));
  await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}' });
}

async function captura(page: import('@playwright/test').Page, nome: string) {
  await expect(page).toHaveScreenshot(nome, {
    fullPage: true,
    mask: [page.locator('canvas')],
  });
}

test.beforeEach(async ({ page }) => {
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
  const projeto = await page.evaluate((texto) => {
    const p = window.__sora.criarProjeto(texto, Date.now() - 300_000);
    return { id: p.id };
  }, pedido);

  await page.goto(`/projeto/${projeto.id}`);
  await expect(page.getByRole('button', { name: 'Revisar', exact: true })).toBeVisible();
  await captura(page, 'projeto-pronto.png');
});
