import { chromium } from '@playwright/test';
import { logarTodoContexto } from './entrar.mjs';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE_URL = 'http://localhost:5173';
// Rotas de agentes são dinâmicas: @1, @2… = n-ésimo agente do projeto semeado; @projeto = id do projeto.
const DEFAULT_ROUTES = [
  '/',
  '/projetos',
  '/agentes',
  '/projeto/@projeto',
  '/chat/@1',
  '/chat/@2',
  '/revisao/@projeto',
  '/configuracoes',
  '/plugins',
  '/celular',
  '/lab/orb',
];
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
];
const FLOW_MESSAGE =
  'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.';
const FLOW_INTERVAL_MS = 3_000;
const FLOW_DURATION_MS = 51_000;
const AGENT_DESCRIPTION = 'Um agente chamado Pipa que escreve legendas divertidas para o Instagram';

const qaDir = dirname(fileURLToPath(import.meta.url));
const shotsDir = join(qaDir, 'shots');

function parseArgs(argv) {
  let waitMs = 1_000;
  let flow = false;
  let agentes = false;
  const routes = [];

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];

    if (argument === '--flow') {
      flow = true;
      continue;
    }

    if (argument === '--agentes') {
      agentes = true;
      continue;
    }

    if (argument === '--wait') {
      const rawWait = argv[index + 1];
      if (rawWait === undefined || !/^\d+$/.test(rawWait)) {
        throw new Error('--wait exige um valor inteiro em milissegundos.');
      }
      waitMs = Number(rawWait);
      index += 1;
      continue;
    }

    if (argument.startsWith('--')) {
      throw new Error(`Argumento desconhecido: ${argument}`);
    }

    routes.push(...argument.split(',').filter(Boolean));
  }

  const normalizedRoutes = routes.map((route) => {
    const normalized = route.startsWith('/') ? route : `/${route}`;
    const parsed = new URL(normalized, BASE_URL);
    if (parsed.origin !== BASE_URL) {
      throw new Error(`Rota fora do app local não é permitida: ${route}`);
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  });

  return {
    flow,
    agentes,
    waitMs,
    routes: normalizedRoutes.length > 0 ? normalizedRoutes : DEFAULT_ROUTES,
  };
}

function routeSlug(route) {
  const pathname = new URL(route, BASE_URL).pathname;
  if (pathname === '/') return 'root';
  return (
    pathname
      .replace(/^\/+|\/+$/g, '')
      .replace(/[^a-zA-Z0-9_-]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'root'
  );
}

function serializeError(error) {
  if (error instanceof Error) {
    return { message: error.message, stack: error.stack ?? null };
  }
  return { message: String(error), stack: null };
}

function attachDiagnostics(page, entries, viewportLabel) {
  page.on('console', (message) => {
    if (!['warning', 'error'].includes(message.type())) return;
    const location = message.location();
    entries.push({
      timestamp: new Date().toISOString(),
      type: 'console',
      level: message.type(),
      text: message.text(),
      url: page.url(),
      viewport: viewportLabel,
      location: {
        url: location.url || null,
        lineNumber: location.lineNumber ?? null,
        columnNumber: location.columnNumber ?? null,
      },
    });
  });

  page.on('pageerror', (error) => {
    const serialized = serializeError(error);
    entries.push({
      timestamp: new Date().toISOString(),
      type: 'pageerror',
      level: 'error',
      text: serialized.message,
      stack: serialized.stack,
      url: page.url(),
      viewport: viewportLabel,
    });
  });
}

async function settle(page, waitMs) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});
  if (waitMs > 0) await page.waitForTimeout(waitMs);
}

async function openRoute(page, route, waitMs) {
  const response = await page.goto(`${BASE_URL}${route}`, {
    waitUntil: 'domcontentloaded',
    timeout: 30_000,
  });

  if (!response) {
    throw new Error(`A navegação para ${route} não retornou uma resposta.`);
  }
  if (!response.ok()) {
    throw new Error(`A rota ${route} respondeu HTTP ${response.status()}.`);
  }

  await settle(page, waitMs);
}

async function firstVisible(locators) {
  for (const locator of locators) {
    const count = await locator.count();
    for (let index = 0; index < count; index += 1) {
      const candidate = locator.nth(index);
      if (await candidate.isVisible()) return candidate;
    }
  }
  return null;
}

/** Limpa o estado local e cria um projeto JÁ CONCLUÍDO (via gancho de dev window.__sora). */
async function seedProject(page) {
  await openRoute(page, '/', 0);
  await page.evaluate(() => { localStorage.clear(); sessionStorage.setItem('sora.chegou', '1'); });
  await openRoute(page, '/', 300);
  const seed = await page.evaluate((message) => {
    const sora = window.__sora;
    if (!sora) return null;
    const projeto = sora.criarProjeto(message, Date.now() - 120_000);
    return { projectId: projeto.id, agentIds: projeto.agenteIds };
  }, FLOW_MESSAGE);
  if (!seed) throw new Error('window.__sora indisponível (o app precisa rodar em modo dev).');
  await page.waitForTimeout(250);
  return seed;
}

function resolveRoute(route, seed) {
  return route
    .replace('@projeto', seed.projectId)
    .replace(/@(\d+)/g, (_, n) => seed.agentIds[Number(n) - 1] ?? 'sora');
}

async function fillAndSend(page, textarea, text) {
  await textarea.fill(text);
  await textarea.press('Enter');
}

async function runAgentes(browser, options, diagnostics) {
  const viewport = VIEWPORTS[0];
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: 'dark', reducedMotion: 'no-preference' });
  const page = await context.newPage();
  attachDiagnostics(page, diagnostics, `${viewport.width}x${viewport.height}`);
  const created = [];
  const shot = async (name) => {
    const filename = `agentes-${name}.png`;
    await page.screenshot({ path: join(shotsDir, filename), fullPage: false });
    created.push(filename);
    console.log(`capturado aba Agentes: ${name} -> ${filename}`);
  };
  try {
    await openRoute(page, '/', 0);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.setItem('sora.chegou', '1'); });
    await openRoute(page, '/', options.waitMs);
    await page.getByRole('link', { name: 'Agentes', exact: true }).first().click();
    await page.waitForTimeout(600);
    await shot('00-galeria');
    await page.getByRole('link', { name: /Criar agente/i }).first().click();
    await page.waitForTimeout(800);
    await shot('01-novo');
    // O construtor pode ser o provisório (campo "Descreva o agente…") ou o novo do Forja.
    const descricao = page.getByPlaceholder(/Descreva o agente/i);
    if (!(await descricao.count())) {
      console.log('construtor sem o campo "Descreva o agente…": captura só a tela inicial');
      return created;
    }
    await fillAndSend(page, descricao.first(), AGENT_DESCRIPTION);
    await page.waitForTimeout(600);
    await shot('02-sora-pensando');
    await page.waitForTimeout(2_000);
    await shot('03-preenchido');
    await page.getByRole('button', { name: 'Criar agente' }).click();
    await page.waitForTimeout(900);
    await shot('04-criado');
    await fillAndSend(page, page.getByPlaceholder(/Mensagem para/i), 'Escreva 3 legendas para o post de sexta.');
    await page.waitForTimeout(4_000);
    await shot('05-trabalhando');
    await page.waitForTimeout(8_000);
    await shot('06-concluido');
    return created;
  } finally {
    await context.close();
  }
}

async function runRoutes(browser, options, diagnostics) {
  const created = [];

  for (const viewport of VIEWPORTS) {
    const viewportLabel = `${viewport.width}x${viewport.height}`;
    const context = await browser.newContext({
      viewport,
      deviceScaleFactor: 1,
      colorScheme: 'dark',
      reducedMotion: 'no-preference',
    });
    const page = await context.newPage();
    attachDiagnostics(page, diagnostics, viewportLabel);

    try {
      const seed = await seedProject(page);
      for (const rawRoute of options.routes) {
        const route = resolveRoute(rawRoute, seed);
        if (route !== '/') {
          await page.evaluate((id) => window.__sora?.abrirProjeto(id), seed.projectId);
          await page.waitForTimeout(250);
        }
        await openRoute(page, route, options.waitMs);
        const filename = `${routeSlug(rawRoute.replace(/@(\d+)/g, 'agente-$1').replace('@', ''))}-${viewport.width}.png`;
        await page.screenshot({
          path: join(shotsDir, filename),
          fullPage: false,
        });
        created.push(filename);
        console.log(`capturado ${route} em ${viewportLabel} -> ${filename}`);
      }
    } finally {
      await context.close();
    }
  }

  return created;
}

async function runFlow(browser, options, diagnostics) {
  const viewport = VIEWPORTS[0];
  const viewportLabel = `${viewport.width}x${viewport.height}`;
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    colorScheme: 'dark',
    reducedMotion: 'no-preference',
  });
  const page = await context.newPage();
  attachDiagnostics(page, diagnostics, viewportLabel);

  try {
    await openRoute(page, '/', 0);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.removeItem('sora.chegou'); });
    await openRoute(page, '/', options.waitMs);

    const composer = await firstVisible([
      page.getByPlaceholder(/Peça qualquer coisa à Sora/i),
      page.getByRole('textbox'),
      page.locator('textarea, input:not([type="hidden"]), [contenteditable="true"]'),
    ]);

    if (!composer) {
      throw new Error('Campo de mensagem visível não encontrado na rota /.');
    }

    await composer.fill(FLOW_MESSAGE);

    const sendButton = await firstVisible([
      page.getByRole('button', { name: /enviar(?: mensagem)?|send/i }),
      page.locator('button[type="submit"]'),
    ]);

    if (sendButton && (await sendButton.isEnabled())) {
      await sendButton.click();
    } else {
      await composer.press('Enter');
    }

    const created = [];
    const frameCount = FLOW_DURATION_MS / FLOW_INTERVAL_MS;
    for (let frame = 1; frame <= frameCount; frame += 1) {
      await page.waitForTimeout(FLOW_INTERVAL_MS);
      const filename = `flow-${String(frame).padStart(2, '0')}.png`;
      await page.screenshot({ path: join(shotsDir, filename), fullPage: false });
      created.push(filename);
      console.log(`capturado fluxo +${frame * 3}s -> ${filename}`);
    }

    return created;
  } finally {
    await context.close();
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const diagnostics = [];
  const startedAt = new Date().toISOString();
  let browser;
  let created = [];
  let fatalError = null;

  await mkdir(shotsDir, { recursive: true });

  try {
    browser = logarTodoContexto(await chromium.launch({ headless: true }));
    created = options.flow
      ? await runFlow(browser, options, diagnostics)
      : options.agentes
        ? await runAgentes(browser, options, diagnostics)
        : await runRoutes(browser, options, diagnostics);
  } catch (error) {
    fatalError = serializeError(error);
    diagnostics.push({
      timestamp: new Date().toISOString(),
      type: 'runner',
      level: 'error',
      text: fatalError.message,
      stack: fatalError.stack,
      url: null,
      viewport: null,
    });
  } finally {
    if (browser) await browser.close();

    const report = {
      startedAt,
      finishedAt: new Date().toISOString(),
      baseURL: BASE_URL,
      mode: options.flow ? 'flow' : options.agentes ? 'agentes' : 'routes',
      waitMs: options.waitMs,
      routes: options.flow || options.agentes ? ['/'] : options.routes,
      viewports: options.flow || options.agentes ? [VIEWPORTS[0]] : VIEWPORTS,
      created,
      summary: {
        screenshots: created.length,
        warnings: diagnostics.filter((entry) => entry.level === 'warning').length,
        errors: diagnostics.filter((entry) => entry.level === 'error').length,
      },
      entries: diagnostics,
    };

    await writeFile(join(shotsDir, 'console.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  }

  if (fatalError) {
    console.error(fatalError.stack || fatalError.message);
    process.exitCode = 1;
    return;
  }

  console.log(
    `concluído: ${created.length} screenshot(s), ` +
      `${diagnostics.filter((entry) => entry.level === 'warning').length} warning(s), ` +
      `${diagnostics.filter((entry) => entry.level === 'error').length} erro(s)`,
  );
}

await main();
