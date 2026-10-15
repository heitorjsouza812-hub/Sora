/**
 * Fumaça do Tauri real para as capabilities por janela (APP-003).
 *
 * Uso com pouca memória, a partir de app/ e em terminais separados:
 *   1. npm run dev
 *   2. $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9333'
 *      node .\node_modules\@tauri-apps\cli\tauri.js dev --no-watch --config .\qa\tauri-capabilities.config.json
 *   3. node qa/desktop-capabilities.mjs
 *
 * O JSON auxiliar apenas esvazia beforeDevCommand para não subir um segundo Vite;
 * ele é necessário neste fluxo porque o servidor da porta 5173 já está rodando no passo 1.
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { chromium } from '@playwright/test';

const CDP = process.env.SORA_CDP_URL ?? 'http://127.0.0.1:9333';
const ESPERA = 15_000;
const errosConsole = [];

const dormir = (ms) => new Promise(resolve => setTimeout(resolve, ms));

function textoErro(erro) {
  return erro instanceof Error ? erro.message : String(erro);
}

function observarConsole(page, janela) {
  page.on('console', mensagem => {
    if (mensagem.type() === 'error') {
      errosConsole.push({ janela, tipo: 'console', texto: mensagem.text() });
    }
  });
  page.on('pageerror', erro => {
    errosConsole.push({ janela, tipo: 'pageerror', texto: erro.message });
  });
}

function powershell(comando) {
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', comando], {
    windowsHide: true,
    stdio: 'pipe',
  });
}

function moverCursor(x, y) {
  powershell(`Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(${Math.round(x)}, ${Math.round(y)})`);
}

function atalhoGlobal() {
  powershell("Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^+s')");
}

async function conectar() {
  const limite = Date.now() + 60_000;
  let ultimoErro;
  while (Date.now() < limite) {
    try {
      return await chromium.connectOverCDP(CDP);
    } catch (erro) {
      ultimoErro = erro;
      await dormir(500);
    }
  }
  throw new Error(`CDP indisponivel em ${CDP}: ${textoErro(ultimoErro)}`);
}

async function esperarPaginas(browser) {
  const limite = Date.now() + ESPERA;
  while (Date.now() < limite) {
    const paginas = browser.contexts().flatMap(contexto => contexto.pages());
    const ilha = paginas.find(page => new URL(page.url()).searchParams.get('janela') === 'ilha');
    const main = paginas.find(page => page !== ilha && page.url().startsWith('http://localhost:5173'));
    if (main && ilha) return { main, ilha };
    await dormir(250);
  }
  throw new Error('As WebViews main e ilha nao apareceram no CDP.');
}

async function modoIlha(ilha) {
  return ilha.locator('.ilha').getAttribute('data-modo');
}

async function prepararDados(main, ilha) {
  const original = await main.evaluate(() => ({
    projetos: localStorage.getItem('sora.projetos.v1'),
    ilha: localStorage.getItem('sora.ilha.v1'),
  }));

  await main.evaluate(async () => {
    const estado = await import('/src/state/projetos.ts');
    const prefs = await import('/src/components/ilha/ilhaEstado.ts');
    prefs.definirIlhaPrefs({ visivel: true, esconderOciosa: false, ilhaNoApp: false });
    if (estado.lerEstado().projetos.length === 0) {
      estado.criarProjeto('Ola, teste de capabilities do desktop', Date.now() - 5_000, { tipo: 'chat' });
    }
  });

  await ilha.locator('.ilha').waitFor({ state: 'attached', timeout: ESPERA });
  return original;
}

async function restaurarDados(main, ilha, original) {
  for (const page of [main, ilha]) {
    await page.evaluate(({ projetos, ilhaPrefs }) => {
      if (projetos === null) localStorage.removeItem('sora.projetos.v1');
      else localStorage.setItem('sora.projetos.v1', projetos);
      if (ilhaPrefs === null) localStorage.removeItem('sora.ilha.v1');
      else localStorage.setItem('sora.ilha.v1', ilhaPrefs);
    }, { projetos: original.projetos, ilhaPrefs: original.ilha }).catch(() => {});
  }
}

async function instalarSondas(main, ilha) {
  await ilha.evaluate(async () => {
    const ponte = await import('/src/desktop/ponte.ts');
    window.__desktopQa = { mouse: [], alternar: 0 };
    window.__desktopQaLimpar = [
      ponte.aoMouseIlha(payload => window.__desktopQa.mouse.push(payload)),
      ponte.aoAlternarIlha(() => { window.__desktopQa.alternar += 1; }),
    ];
  });
  await main.evaluate(async () => {
    const ponte = await import('/src/desktop/ponte.ts');
    window.__desktopQa = { navegar: [] };
    window.__desktopQaLimpar = [
      ponte.aoNavegar(caminho => window.__desktopQa.navegar.push(caminho)),
    ];
  });
  await dormir(500);
}

async function testarMouseEHover(ilha) {
  await ilha.evaluate(async () => {
    const ui = await import('/src/components/ilha/ilhaUi.ts');
    ui.fecharIlha();
  });
  await ilha.locator('.ilha[data-modo="compacta"]').waitFor({ timeout: ESPERA });
  await dormir(900);

  const posicao = await ilha.evaluate(() => {
    const elemento = document.querySelector('.ilha-pilula');
    if (!elemento) throw new Error('Ilha nao renderizada');
    const r = elemento.getBoundingClientRect();
    return {
      dentroX: window.screenX + (r.left + r.width / 2) * window.devicePixelRatio,
      dentroY: window.screenY + Math.min(r.top + r.height / 2, 80) * window.devicePixelRatio,
      foraX: window.screenX + 10 * window.devicePixelRatio,
      foraY: window.screenY + (window.innerHeight - 10) * window.devicePixelRatio,
    };
  });

  moverCursor(posicao.foraX, posicao.foraY);
  await dormir(250);
  moverCursor(posicao.dentroX, posicao.dentroY);
  await ilha.locator('.ilha[data-modo="expandida"]').waitFor({ timeout: ESPERA });
  await ilha.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });
  moverCursor(posicao.foraX, posicao.foraY);
  await dormir(1_500);
  const fechouAoSair = await modoIlha(ilha) === 'compacta';
  if (!fechouAoSair) {
    await ilha.evaluate(async () => {
      const ui = await import('/src/components/ilha/ilhaUi.ts');
      ui.fecharIlha();
    });
    await ilha.locator('.ilha[data-modo="compacta"]').waitFor({ timeout: ESPERA });
  }

  const eventos = await ilha.evaluate(() => window.__desktopQa.mouse);
  assert.ok(eventos.some(evento => evento.dentro === true), 'ilha-mouse nao informou entrada');
  assert.ok(eventos.some(evento => evento.dentro === false), 'ilha-mouse nao informou saida');
  return {
    recebidos: eventos.length,
    entrada: eventos.find(evento => evento.dentro === true),
    saida: [...eventos].reverse().find(evento => evento.dentro === false),
    abriuAoEntrar: true,
    fechouAoSair,
    transicao: fechouAoSair ? 'compacta -> expandida -> compacta' : 'compacta -> expandida; permaneceu expandida apos sair',
  };
}

async function testarAtalho(ilha, main) {
  await ilha.evaluate(async () => {
    const ui = await import('/src/components/ilha/ilhaUi.ts');
    ui.fecharIlha();
  });
  await ilha.locator('.ilha[data-modo="compacta"]').waitFor({ timeout: ESPERA });
  await main.bringToFront();

  atalhoGlobal();
  await ilha.locator('.ilha[data-modo="expandida"]').waitFor({ timeout: ESPERA });
  const aposAbrir = await ilha.evaluate(() => window.__desktopQa.alternar);

  atalhoGlobal();
  await ilha.locator('.ilha[data-modo="compacta"]').waitFor({ timeout: ESPERA });
  const aposFechar = await ilha.evaluate(() => window.__desktopQa.alternar);

  assert.ok(aposAbrir >= 1, 'ilha-alternar nao chegou ao abrir');
  assert.ok(aposFechar > aposAbrir, 'ilha-alternar nao chegou ao fechar');
  return { eventos: aposFechar, transicao: 'compacta -> expandida -> compacta' };
}

async function testarNavegacao(main, ilha) {
  const caminho = '/configuracoes?qa=desktop-capabilities';
  const retorno = await ilha.evaluate(caminhoInterno => (
    window.__TAURI_INTERNALS__.invoke('navegar', { caminho: caminhoInterno })
  ), caminho);
  await main.waitForURL(url => url.pathname === '/configuracoes' && url.searchParams.get('qa') === 'desktop-capabilities', { timeout: ESPERA });
  await main.waitForFunction(rota => window.__desktopQa.navegar.includes(rota), caminho, { timeout: ESPERA });
  const recebidos = await main.evaluate(() => window.__desktopQa.navegar);
  assert.equal(retorno, null);
  return { invoke: retorno, evento: recebidos.at(-1), urlMain: main.url() };
}

async function invokeNegado(page, comando, argumentos) {
  const resultado = await page.evaluate(async ({ comandoInterno, argumentosInternos }) => {
    try {
      const valor = await window.__TAURI_INTERNALS__.invoke(comandoInterno, argumentosInternos);
      return { negado: false, valor };
    } catch (erro) {
      return { negado: true, erro: erro instanceof Error ? erro.message : String(erro) };
    }
  }, { comandoInterno: comando, argumentosInternos: argumentos });
  assert.equal(resultado.negado, true, `${comando} deveria ser negado`);
  return resultado.erro;
}

async function testarNegacoes(main, ilha) {
  return {
    ilha_ilha_visivel: await invokeNegado(ilha, 'ilha_visivel', { visivel: true }),
    main_ilha_retangulo: await invokeNegado(main, 'ilha_retangulo', { x: 0, y: 0, w: 10, h: 10 }),
    main_navegar: await invokeNegado(main, 'navegar', { caminho: '/projetos' }),
  };
}

let browser;
let paginas;
let original;
try {
  browser = await conectar();
  paginas = await esperarPaginas(browser);
  observarConsole(paginas.main, 'main');
  observarConsole(paginas.ilha, 'ilha');
  await Promise.all([paginas.main.waitForLoadState('domcontentloaded'), paginas.ilha.waitForLoadState('domcontentloaded')]);

  original = await prepararDados(paginas.main, paginas.ilha);
  await instalarSondas(paginas.main, paginas.ilha);

  console.error('[QA] testando ilha-mouse e hover');
  const mouse = await testarMouseEHover(paginas.ilha);
  console.error('[QA] testando ilha-alternar por Ctrl+Shift+S');
  const atalho = await testarAtalho(paginas.ilha, paginas.main);
  console.error('[QA] testando sora-navegar');
  const navegacao = await testarNavegacao(paginas.main, paginas.ilha);
  console.error('[QA] testando comandos negados por janela');
  const negacoes = await testarNegacoes(paginas.main, paginas.ilha);
  await dormir(750);

  assert.deepEqual(errosConsole, [], `Erros novos no console: ${JSON.stringify(errosConsole)}`);
  const ok = mouse.fechouAoSair;
  console.log(JSON.stringify({
    ok,
    paginas: { main: paginas.main.url(), ilha: paginas.ilha.url() },
    mouse,
    atalho,
    navegacao,
    negacoes,
    console: { main: 'sem erros novos', ilha: 'sem erros novos' },
  }, null, 2));
  if (!ok) process.exitCode = 1;
} catch (erro) {
  const diagnostico = paginas ? await paginas.ilha.evaluate(() => ({
    modo: document.querySelector('.ilha')?.getAttribute('data-modo') ?? null,
    sonda: window.__desktopQa ?? null,
  })).catch(() => null) : null;
  console.error(JSON.stringify({ ok: false, erro: textoErro(erro), diagnostico, errosConsole }, null, 2));
  process.exitCode = 1;
} finally {
  if (paginas && original) await restaurarDados(paginas.main, paginas.ilha, original);
  if (paginas) {
    for (const page of [paginas.main, paginas.ilha]) {
      await page.evaluate(() => window.__desktopQaLimpar?.forEach(limpar => limpar())).catch(() => {});
    }
  }
  await browser?.close().catch(() => {});
}
