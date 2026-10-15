// Markdown → HTML seguro: marked gera o HTML e o DOMPurify sanitiza tudo.
// Lista de PERMITIDOS (VAL-19): o conteúdo (resposta de agente/LLM, página lida) só traz as tags
// e atributos do markdown; nada de style, class, id, data-* (VAL-15/16). A moldura dos blocos de código (rótulo + botão "Copiar") é montada DEPOIS da
// sanitização, só nos <pre> que o renderer marcou com um id de uso único (o atacante não adivinha).
import DOMPurify from 'dompurify';
import { Marked, type Tokens } from 'marked';

const escapar = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// estado de uma chamada (parse e sanitize são síncronos)
let marcaAtual = '';
let linguagens: string[] = [];

const md = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    code({ text, lang }: Tokens.Code) {
      linguagens.push((lang ?? '').split(/\s/)[0]);
      return `<pre id="${marcaAtual}${linguagens.length - 1}"><code>${escapar(text)}</code></pre>`;
    },
  },
});

function novaMarca() {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return `mdc-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}-`;
}

// LISTA DE PERMITIDOS (VAL-19): só o que o marked gera para markdown. Tudo o mais some —
// img/svg/math/dialog/form, atributos legados (background, bgcolor, width, height, hidden) etc.
const TAGS_PERMITIDAS = [
  'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'a',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
];
// `id` só entra para a marca dos blocos de código; todo id é apagado logo depois.
const ATRIBUTOS_PERMITIDOS = ['href', 'title', 'start', 'colspan', 'rowspan', 'align', 'id'];
// conferido no gancho, só no href (o ALLOWED_URI_REGEXP do DOMPurify vale para todo atributo e
// apagaria align/start/colspan)
const URL_PERMITIDA = /^(?:https?:\/\/|mailto:)/i;
const ALINHAMENTOS = new Set(['left', 'center', 'right']);

// links sempre abrem em nova aba, sem dar acesso à janela de origem; align só left/center/right
let ganchoInstalado = false;
function instalarGancho() {
  if (ganchoInstalado) return;
  ganchoInstalado = true;
  DOMPurify.addHook('afterSanitizeAttributes', (no) => {
    if (no.tagName === 'A') {
      const href = no.getAttribute('href');
      if (href !== null && !URL_PERMITIDA.test(href.replace(/[\p{Cc}\p{Z}\s]/gu, ''))) no.removeAttribute('href');
      if (no.getAttribute('href')) { no.setAttribute('target', '_blank'); no.setAttribute('rel', 'noopener noreferrer'); }
      else { no.removeAttribute('target'); no.removeAttribute('rel'); }
    }
    const alinhamento = no.getAttribute('align');
    if (alinhamento !== null && (!(no.tagName === 'TH' || no.tagName === 'TD') || !ALINHAMENTOS.has(alinhamento.toLowerCase()))) no.removeAttribute('align');
  });
}

/** Moldura do bloco de código, criada pelo app (nunca vem do conteúdo). */
function emoldurar(pre: Element, linguagem: string) {
  const doc = pre.ownerDocument;
  const caixa = doc.createElement('div');
  caixa.className = 'md-code';
  const barra = doc.createElement('div');
  barra.className = 'md-code-bar';
  const rotulo = doc.createElement('span');
  rotulo.textContent = linguagem || 'código';
  const botao = doc.createElement('button');
  botao.type = 'button';
  botao.className = 'md-copy';
  botao.setAttribute('data-copiar', '');
  botao.textContent = 'Copiar';
  barra.append(rotulo, botao);
  pre.replaceWith(caixa);
  caixa.append(barra, pre);
}

/** Converte markdown em HTML seguro (sanitizado). */
export function markdownSeguro(fonte: string) {
  instalarGancho();
  const marca = novaMarca();
  marcaAtual = marca;
  linguagens = [];
  try {
    const html = md.parse(fonte, { async: false }) as string;
    const fragmento = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: TAGS_PERMITIDAS,
      ALLOWED_ATTR: ATRIBUTOS_PERMITIDOS,
      ALLOW_DATA_ATTR: false,
      ALLOW_ARIA_ATTR: false,
      RETURN_DOM_FRAGMENT: true,
    });
    // ids do conteúdo saem (sem âncoras/clobbering); os nossos viram a moldura do código
    for (const el of Array.from(fragmento.querySelectorAll('[id]'))) {
      const id = el.getAttribute('id') ?? '';
      el.removeAttribute('id');
      if (el.tagName !== 'PRE' || !id.startsWith(marca)) continue;
      const indice = Number(id.slice(marca.length));
      if (Number.isInteger(indice) && indice >= 0 && indice < linguagens.length) emoldurar(el, linguagens[indice]);
    }
    const saida = document.createElement('div');
    saida.append(fragmento);
    return saida.innerHTML;
  } finally {
    marcaAtual = '';
    linguagens = [];
  }
}
