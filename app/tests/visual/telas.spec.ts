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
  await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}.composer-beam canvas{display:none!important}' });
}

async function captura(page: import('@playwright/test').Page, nome: string) {
  await expect(page).toHaveScreenshot(nome, {
    fullPage: true,
    mask: [page.locator('canvas')],
  });
}

// Contas fixas (o cadastro tem limite de 5 por hora por IP): as telas usam a conta que nunca cria projeto;
// o "projeto pronto" usa uma conta por tamanho de tela (especialista não pode ser apagado pela API, então o
// teste exige a conta sem projetos: para regenerar as baselines, zere o banco de QA antes).
const contaDoProjeto = () => `qa-projeto-${test.info().project.name}@sora.local`;
test.beforeEach(async ({ page }) => {
  await entrarNoContexto(page.context(), {
    ...(test.info().title.startsWith('projeto pronto') ? { email: contaDoProjeto() } : {}),
    limparConversas: true,
  });
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
  expect(await page.evaluate(() => window.__sora.lerEstado().projetos.length), 'o harness deve limpar os projetos antes do teste').toBe(0);
  await page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i }).fill(pedido);
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//);
  await expect(page.getByRole('button', { name: 'Revisar', exact: true })).toBeVisible({ timeout: 90_000 });
  // A equipe acabou de terminar: a ilha abre sozinha (alerta). Dispensa, como o usuário faria.
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Ilha da Sora', exact: true })).toHaveCount(0);
  // Tira o foco do campo: com foco o beam (canvas) aparece e a máscara esconderia o campo inteiro.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForTimeout(500);
  await captura(page, 'projeto-pronto.png');

  // V1: projeto pronto de antes + armazenamento limpo (navegador novo) NÃO abre a ilha sobre a tela.
  // O app só trata como "acabou de terminar" o que concluiu há menos de 60 s; aqui o relógio da página
  // anda 2 min para simular um projeto pronto de antes.
  await page.evaluate(() => localStorage.clear());
  await page.addInitScript(() => { const real = Date.now.bind(Date); Date.now = () => real() + 120_000; });
  await page.goto('/');
  await aguardarSessao(page);
  await page.waitForTimeout(1_500);
  await expect(page.getByRole('dialog', { name: 'Ilha da Sora', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Ilha da Sora:/i })).toBeVisible();

});
