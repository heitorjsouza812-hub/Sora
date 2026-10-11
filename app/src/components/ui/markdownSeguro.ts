// Markdown → HTML seguro: marked gera o HTML e o DOMPurify sanitiza tudo.
import DOMPurify from 'dompurify';
import { Marked, type Tokens } from 'marked';

const escapar = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const md = new Marked({
  gfm: true,
  breaks: true,
  renderer: {
    code({ text, lang }: Tokens.Code) {
      const linguagem = (lang ?? '').split(/\s/)[0];
      return `<div class="md-code"><div class="md-code-bar"><span>${escapar(linguagem || 'código')}</span>`
        + `<button type="button" class="md-copy" data-copiar>Copiar</button></div>`
        + `<pre><code>${escapar(text)}</code></pre></div>`;
    },
  },
});

// links sempre abrem em nova aba, sem dar acesso à janela de origem
let ganchoInstalado = false;
function instalarGancho() {
  if (ganchoInstalado) return;
  ganchoInstalado = true;
  DOMPurify.addHook('afterSanitizeAttributes', (no) => {
    if (no.tagName === 'A' && no.getAttribute('href')) { no.setAttribute('target', '_blank'); no.setAttribute('rel', 'noopener noreferrer'); }
  });
}

/** Converte markdown em HTML seguro (sanitizado). */
export function markdownSeguro(fonte: string) {
  instalarGancho();
  const html = md.parse(fonte, { async: false }) as string;
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true }, ADD_ATTR: ['target', 'data-copiar'], FORBID_TAGS: ['style', 'form', 'input'] });
}

