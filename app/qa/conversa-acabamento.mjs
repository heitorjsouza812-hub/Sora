import assert from 'node:assert/strict';
import { expect } from '@playwright/test';

// Só chamado pelo E2E quando o .env confirma o modelo falso. Todas as rotas são reais.
export async function conferirConversa({ page, contexto, auth, bot }) {
  const campo = page.getByRole('textbox', { name: `Mensagem para ${bot.nome}…` });
  await campo.fill('Olá, responda brevemente.');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.getByRole('button', { name: 'Refazer resposta', exact: true }).waitFor({ timeout: 30_000 });
  const antes = await page.locator('.chat-item:has(.is-assistant)').last().getAttribute('data-chave');
  await page.getByRole('button', { name: 'Refazer resposta', exact: true }).click();
  await expect(page.locator(`.chat-item[data-chave="${antes}"]`)).toHaveCount(0);
  await page.getByRole('button', { name: 'Refazer resposta', exact: true }).waitFor({ timeout: 30_000 });
  assert.equal(await page.locator('.chat-msg.is-user').count(), 1, 'refazer substitui também o ID da pergunta');
  await page.getByRole('button', { name: 'Boa resposta', exact: true }).last().click();
  await expect(page.getByRole('button', { name: 'Boa resposta', exact: true }).last()).toHaveAttribute('aria-pressed', 'true');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('button', { name: 'Boa resposta', exact: true }).last()).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.chat-msg.is-user')).toHaveCount(1);
  await expect(page.locator(`.chat-item[data-chave="${antes}"]`)).toHaveCount(0);
  await page.getByRole('button', { name: 'Editar pergunta', exact: true }).click();
  await page.getByRole('textbox', { name: 'Editar pergunta' }).fill('Olá, pergunta editada.');
  await page.locator('.msg-edit').getByRole('button', { name: 'Enviar', exact: true }).click();
  await page.getByRole('button', { name: 'Refazer resposta', exact: true }).waitFor({ timeout: 30_000 });
  await expect(page.locator('.user-message')).toHaveText('Olá, pergunta editada.');

  // O falso responde rápido. O gatilho de aprovação deixa um turno suspenso de verdade.
  for (const escape of [false, true]) {
    await campo.fill('[aprovacao] ajuste suas instruções');
    const enviado = page.waitForResponse(r => r.request().method() === 'POST' && /\/mensagens$/.test(r.url()));
    await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
    await enviado;
    await page.getByRole('button', { name: 'Parar resposta', exact: true }).waitFor();
    const parada = page.waitForResponse(r => r.request().method() === 'POST' && /\/conversas\/[^/]+\/parar$/.test(r.url()));
    void parada.catch(() => {});
    if (escape) { await campo.focus(); await page.keyboard.press('Escape'); }
    else await page.getByRole('button', { name: 'Parar resposta', exact: true }).click();
    const resposta = await parada;
    assert.equal(resposta.status(), 202);
    await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).waitFor({ timeout: 30_000 });
    await page.getByText('Resposta interrompida', { exact: true }).last().waitFor();
    const url = resposta.url().replace(/\/parar$/, '/mensagens');
    const mensagens = await (await contexto.request.get(url, { headers: auth })).json();
    assert.ok(mensagens.some(m => m.estado === 'interrompida'), 'interrupção persistida pelo backend');
  }
  const urlBot = page.url();
  await page.getByRole('link', { name: 'Conversar com a Sora', exact: true }).click();
  const campoSora = page.getByRole('textbox', { name: 'Mensagem para a Sora…' });
  // A resposta direta do modelo falso termina antes de o botão aparecer; só a cadeia fica aberta tempo suficiente para Parar.
  for (const texto of ['Pesquise referências e escreva um relatório detalhado para minha campanha [pergunta]']) {
    await campoSora.fill(texto);
    const envio = page.waitForResponse(r => r.request().method() === 'POST' && /\/conversas(?:\/[^/]+\/mensagens)?$/.test(r.url()));
    await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
    assert.ok((await envio).ok());
    if (texto.includes('[pergunta]')) await page.waitForFunction(() => window.__sora.lerEstado().projetos.some(p => p.cadeiaId && ['planejando', 'executando', 'aguardando_usuario'].includes(p.cadeiaStatus)), { timeout: 30_000 });
    const parada = page.waitForResponse(r => r.request().method() === 'POST' && /\/parar$/.test(r.url()));
    void parada.catch(() => {});
    await page.getByRole('button', { name: 'Parar resposta', exact: true }).click();
    assert.equal((await parada).status(), 202);
    await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).waitFor({ timeout: 30_000 });
    await page.getByText('Resposta interrompida', { exact: true }).last().waitFor();
  }
  await page.goto(urlBot, { waitUntil: 'domcontentloaded' });
  console.log('Conversa: refazer, editar, avaliação após recarga, Parar/Esc no bot e Parar na Sora direta/em cadeia aprovados na API real com modelo falso.');
}
