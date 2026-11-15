import DOMPurify from 'dompurify';
import hljs from './vendor/highlight.js';
import python from './vendor/python.js';
import javascript from './vendor/javascript.js';
import json from './vendor/json.js';
import bash from './vendor/bash.js';
import css from './vendor/css.js';
import xml from './vendor/xml.js';
for (const [nome, linguagem] of Object.entries({ python, javascript, json, bash, css, xml })) hljs.registerLanguage(nome, linguagem);
export function realcarCodigo(raiz: HTMLElement) {
  for (const bloco of raiz.querySelectorAll<HTMLElement>('.md-code')) {
    const linguagem = bloco.querySelector('.md-code-bar span')?.textContent ?? '';
    const codigo = bloco.querySelector('code');
    if (!codigo || !hljs.getLanguage(linguagem)) continue;
    const html = hljs.highlight(codigo.textContent ?? '', { language: linguagem, ignoreIllegals: true }).value;
    // Só a saída do realçador recebe classes; HTML escrito pelo modelo continua sem classes/style.
    codigo.innerHTML = DOMPurify.sanitize(html, { ALLOWED_TAGS: ['span'], ALLOWED_ATTR: ['class'], ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false });
  }
}
