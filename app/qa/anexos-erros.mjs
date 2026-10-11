// Itens 43 e 47 · QA dos anexos no composer e dos estados de erro (dev server em :5173).
// Uso: node qa/anexos-erros.mjs  → screenshots em qa/shots/forja-*.png; sai com 1 se algo falhar.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = 'http://localhost:5173';
const shots = join(dirname(fileURLToPath(import.meta.url)), 'shots');
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');

const browser = await chromium.launch();
const erros = [];
try {
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const ctx = await browser.newContext({ viewport: vp, colorScheme: 'dark' });
    const page = await ctx.newPage();
    page.on('pageerror', e => erros.push(`${vp.width}: ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') erros.push(`${vp.width}: ${m.text()}`); });
    await page.goto(BASE + '/?simularErro=');
    await page.evaluate(() => { localStorage.clear(); sessionStorage.setItem('sora.chegou', '1'); });
    await page.goto(BASE + '/');
    await page.waitForTimeout(800);

    // 43 · "+" abre o seletor; chips com nome, tamanho e tipo; remover
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.getByRole('button', { name: 'Anexar arquivos' }).click()]);
    await chooser.setFiles([
      { name: 'referencia.png', mimeType: 'image/png', buffer: PNG },
      { name: 'briefing.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(2048) },
    ]);
    await page.getByText('briefing.pdf').waitFor();
    assert.equal(await page.locator('.anx-chip').count(), 2);
    assert.ok(await page.locator('.anx-chip img').count() === 1, 'imagem deve ter miniatura');
    assert.match(await page.locator('.anx-chip').nth(1).innerText(), /2 KB · PDF/);
    await page.screenshot({ path: join(shots, `forja-anexos-${vp.width}.png`) });
    await page.getByRole('button', { name: 'Remover briefing.pdf' }).click();
    assert.equal(await page.locator('.anx-chip').count(), 1);

    // limite de tamanho → erro
    const [c2] = await Promise.all([page.waitForEvent('filechooser'), page.getByRole('button', { name: 'Anexar arquivos' }).click()]);
    await c2.setFiles([{ name: 'video.mov', mimeType: 'video/quicktime', buffer: Buffer.alloc(21 * 1024 * 1024) }]);
    await page.getByText(/passa de 20 MB/).waitFor();

    // soltar arquivo sobre a área (evento de drop sintético no composer não existe: usa a ponte)
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('sora:anexar', { detail: [new File(['oi'], 'nota.txt', { type: 'text/plain' })] })));
    await page.getByText('nota.txt').waitFor();

    // colar imagem
    await page.getByRole('textbox').first().focus();
    await page.evaluate(() => {
      const dt = new DataTransfer();
      dt.items.add(new File([new Uint8Array([137, 80, 78, 71])], '', { type: 'image/png' }));
      document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    });
    await page.getByText(/imagem-colada\.png/).waitFor();
    assert.equal(await page.locator('.anx-chip').count(), 3);

    // 47 · sem conexão (simulado) → faixa? (a faixa fica no AppShell) e composer bloqueado
    await page.evaluate(() => window.__soraErro.definir('conexao'));
    await page.getByText(/Sem conexão: dá para escrever/).waitFor();
    assert.ok(await page.getByRole('button', { name: 'Enviar mensagem' }).isDisabled());
    await page.screenshot({ path: join(shots, `forja-sem-conexao-${vp.width}.png`) });
    await page.getByRole('button', { name: 'Tentar de novo' }).first().click();
    await page.getByText(/Sem conexão: dá para escrever/).waitFor({ state: 'detached' });

    // offline de verdade (eventos do navegador)
    await ctx.setOffline(true);
    await page.getByText(/Sem conexão: dá para escrever/).waitFor();
    await ctx.setOffline(false);
    await page.getByText(/Sem conexão: dá para escrever/).waitFor({ state: 'detached' });

    // créditos esgotados → bloqueio suave com "Ver planos"
    await page.evaluate(() => window.__soraErro.definir('creditos'));
    await page.getByText('Seus créditos acabaram.').waitFor();
    assert.ok(await page.getByRole('button', { name: 'Enviar mensagem' }).isDisabled());
    await page.screenshot({ path: join(shots, `forja-sem-creditos-${vp.width}.png`) });
    await page.getByRole('link', { name: 'Ver planos' }).click();
    await page.waitForURL(/configuracoes\?secao=conta/);
    await page.getByRole('heading', { name: 'Plano Pro' }).waitFor();
    await page.screenshot({ path: join(shots, `forja-plano-${vp.width}.png`), fullPage: true });
    await page.evaluate(() => window.__soraErro.definir(null));
    await ctx.close();
  }
} finally {
  await browser.close();
}
if (erros.length) { console.error('erros de console:\n' + erros.join('\n')); process.exitCode = 1; }
else console.log('anexos/erros OK (1440 e 390)');
