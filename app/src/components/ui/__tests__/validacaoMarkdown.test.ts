// Validação adversarial (Tranca) do markdownSeguro: tenta executar script, carregar recursos e sobrepor a UI.
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { markdownSeguro } from '../markdownSeguro';

const montar = (fonte: string) => {
  const raiz = document.createElement('div');
  raiz.innerHTML = markdownSeguro(fonte);
  return raiz;
};
const perigosos = (raiz: HTMLElement) => {
  const achados: string[] = [];
  raiz.querySelectorAll('*').forEach(el => {
    for (const a of Array.from(el.attributes)) {
      if (/^on/i.test(a.name)) achados.push(`${el.tagName}@${a.name}`);
      if (['href', 'src', 'action', 'formaction', 'xlink:href', 'srcdoc', 'data'].includes(a.name)
        && /^\s*(javascript|data|vbscript):/i.test([...a.value].filter(c => c.charCodeAt(0) > 32).join(''))) achados.push(`${el.tagName}@${a.name}=${a.value}`);
    }
    if (['SCRIPT', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH', 'IMG', 'STYLE', 'LINK', 'META', 'BASE', 'FORM'].includes(el.tagName.toUpperCase())) achados.push(el.tagName);
  });
  return achados;
};

const ataques: Record<string, string> = {
  'link javascript': '[x](javascript:alert(1))',
  'link javascript maiúsculo/espaço': '[x](JaVa\tScRiPt:alert(1))',
  'link com entidade decimal': '[x](&#106;avascript:alert(1))',
  'link com entidade hex': '[x](&#x6A;avascript:alert(1))',
  'link angular': '[x](<javascript:alert(1)>)',
  'link data html': '[x](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)',
  'autolink javascript': '<javascript:alert(1)>',
  'html cru script': '<script>alert(1)</script>',
  'img onerror': '<img src=x onerror=alert(1)>',
  'markdown img': '![a](https://attacker.example/p.gif)',
  'svg onload': '<svg onload=alert(1)><circle/></svg>',
  'svg dentro de a': '<a href="x"><svg><a xlink:href="javascript:alert(1)"><text>x</text></a></svg></a>',
  'math mxss': '<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>',
  'noscript mxss': '<noscript><p title="</noscript><img src=x onerror=alert(1)>">',
  'div onclick': '<div onclick="alert(1)">x</div>',
  'details ontoggle': '<details open ontoggle=alert(1)>x</details>',
  'iframe srcdoc': '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
  'form action': '<form action="https://attacker.example"><button formaction="javascript:alert(1)">x</button></form>',
  'base href': '<base href="https://attacker.example/">',
  'meta refresh': '<meta http-equiv="refresh" content="0;url=https://attacker.example">',
  'style tag': '<style>body{display:none}</style>',
  'código com HTML': '```html\n<img src=x onerror=alert(1)>\n```',
  'tabela com payload': '| a |\n|---|\n| <img src=x onerror=alert(1)> |',
};

describe('markdownSeguro — tentativas de contornar', () => {
  for (const [nome, fonte] of Object.entries(ataques)) {
    it(nome, () => { expect(perigosos(montar(fonte))).toEqual([]); });
  }
  it('links sempre com noopener e _blank', () => {
    const a = montar('[x](https://exemplo.com)').querySelector('a')!;
    expect(a.getAttribute('rel')).toBe('noopener noreferrer');
    expect(a.getAttribute('target')).toBe('_blank');
    const b = montar('<a href="https://e.com" target="_top" rel="opener">y</a>').querySelector('a')!;
    expect(b.getAttribute('target')).toBe('_blank');
    expect(b.getAttribute('rel')).toBe('noopener noreferrer');
  });
  it('VAL-15 não deixa o atacante sobrepor a tela com style inline (UI redress)', () => {
    const el = montar('<div style="position:fixed;inset:0;background:#000;z-index:99999">Sua sessão expirou: <a href="https://e.com">entre aqui</a></div>');
    expect(el.querySelector('[style]')).toBeNull();
  });
  it('VAL-16 não deixa o atacante forjar o botão Copiar nem classes internas do app', () => {
    const el = montar('<button data-copiar class="md-copy">Copiar</button><div class="md-code">x</div>');
    expect(el.querySelector('[data-copiar]')).toBeNull();
    expect(el.querySelector('[class]')).toBeNull();
  });
  it('VAL-16 tira ids e data-* do conteúdo e não aceita id de bloco forjado', () => {
    const el = montar('<pre id="mdc-000000000000000000000000-0"><code>x</code></pre><p id="raiz" data-x="1">y</p>\n\n```js\nok()\n```');
    expect(el.querySelectorAll('[id]')).toHaveLength(0);
    expect(el.querySelector('[data-x]')).toBeNull();
    expect(el.querySelectorAll('.md-code')).toHaveLength(1); // só o bloco de verdade
  });
  it('blocos de código continuam com rótulo da linguagem e botão Copiar', () => {
    const el = montar('```python\nprint("<b>oi</b>")\n```\n\n```\nsem linguagem\n```');
    const blocos = el.querySelectorAll('.md-code');
    expect(blocos).toHaveLength(2);
    expect(blocos[0].querySelector('.md-code-bar span')!.textContent).toBe('python');
    expect(blocos[1].querySelector('.md-code-bar span')!.textContent).toBe('código');
    const botao = blocos[0].querySelector('button.md-copy[data-copiar]')!;
    expect(botao.closest('.md-code')!.querySelector('code')!.textContent).toBe('print("<b>oi</b>")');
    expect(el.querySelector('b')).toBeNull();
  });
  it('rótulo de linguagem malicioso vira texto', () => {
    const el = montar('```"><img src=x onerror=alert(1)>\nx\n```');
    expect(el.querySelector('img')).toBeNull();
    expect(el.querySelector('.md-code-bar span')!.textContent).toContain('<img');
  });
});

describe('markdownSeguro — rodada 5', () => {
  it('VAL-19 atributo background (table/td/th) não carrega imagem externa', () => {
    const el = montar('<table background="https://atacante.example/p.gif"><tr><td background="https://atacante.example/q.gif">x</td></tr></table>');
    expect(el.querySelector('[background]')).toBeNull();
  });
  const legados: Record<string, [string, string]> = {
    bgcolor: ['<table bgcolor="#000"><tr><td bgcolor="red">x</td></tr></table>', '[bgcolor]'],
    'width/height': ['<table width="99999" height="99999"><tr><td width="9999">x</td></tr></table><hr width="9999">', '[width], [height]'],
    hidden: ['<p hidden>x</p><div hidden>y</div>', '[hidden]'],
    'dialog open': ['<dialog open>Sua sessão expirou</dialog>', 'dialog'],
    'svg': ['<svg width="9999"><image href="https://atacante.example/p.gif"/></svg>', 'svg, image'],
    'math': ['<math><mi>x</mi></math>', 'math, mi'],
    'div/span/details': ['<div>a</div><span>b</span><details open><summary>c</summary></details>', 'div, span, details, summary'],
    'video/audio/source': ['<video poster="https://a.example/p.gif"><source src="https://a.example/v.mp4"></video><audio src="x"></audio>', 'video, audio, source'],
    'input/button': ['<input type="checkbox" checked><button>Copiar</button>', 'input, button'],
    'aria/role/lang/dir': ['<p role="alert" aria-live="assertive" lang="ar" dir="rtl" tabindex="0">x</p>', '[role], [aria-live], [lang], [dir], [tabindex]'],
    'align fora de th/td ou estranho': ['<p align="center">x</p><table><tr><td align="justify;x">y</td></tr></table>', '[align]'],
  };
  for (const [nome, [fonte, seletor]] of Object.entries(legados)) {
    it(`VAL-19 lista de permitidos remove ${nome}`, () => { expect(montar(fonte).querySelector(seletor)).toBeNull(); });
  }
  it('VAL-19 links só http(s)/mailto; outros esquemas perdem o href', () => {
    const el = montar('[a](https://e.com) [b](mailto:x@e.com) [c](ftp://e.com) [d](tel:123) <a href="//e.com">e</a> <a href="blob:x">f</a>');
    const hrefs = Array.from(el.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(['https://e.com', 'mailto:x@e.com', null, null, null, null]);
    for (const a of Array.from(el.querySelectorAll('a:not([href])'))) expect(a.hasAttribute('target')).toBe(false);
  });
  it('markdown legítimo continua inteiro (tabelas, listas, código com Copiar, links, títulos)', () => {
    const el = montar([
      '# Título', '## Sub', '', '| a | b |', '|:-:|--:|', '| 1 | 2 |', '', '3. três', '4. quatro', '', '- item', '- **negrito** *itálico* ~~riscado~~ `cód`',
      '', '> citação', '', '---', '', 'linha 1', 'linha 2', '', '[link](https://exemplo.com "Dica")', '', '```ts', 'const x = 1;', '```',
    ].join('\n'));
    for (const tag of ['h1', 'h2', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'ol', 'ul', 'li', 'strong', 'em', 'del', 'code', 'blockquote', 'hr', 'br', 'a', 'pre']) {
      expect(el.querySelector(tag), tag).not.toBeNull();
    }
    expect(el.querySelector('th')!.getAttribute('align')).toBe('center');
    expect(el.querySelectorAll('td')[1].getAttribute('align')).toBe('right');
    expect(el.querySelector('ol')!.getAttribute('start')).toBe('3');
    const a = el.querySelector('a')!;
    expect([a.getAttribute('href'), a.getAttribute('title'), a.getAttribute('target'), a.getAttribute('rel')]).toEqual(['https://exemplo.com', 'Dica', '_blank', 'noopener noreferrer']);
    const bloco = el.querySelector('.md-code')!;
    expect(bloco.querySelector('.md-code-bar span')!.textContent).toBe('ts');
    expect(bloco.querySelector('button.md-copy[data-copiar]')).not.toBeNull();
    expect(bloco.querySelector('pre code')!.textContent).toBe('const x = 1;');
  });
});

describe('markdownSeguro — allowlist (rodada 6)', () => {
  const todosOsAtributos = (r: HTMLElement) => {
    const s = new Set<string>();
    r.querySelectorAll('*').forEach(e => Array.from(e.attributes).forEach(a => s.add(`${e.tagName.toLowerCase()}@${a.name}`)));
    return [...s];
  };
  const ataquesExtra = [
    '<table background="https://a.example/p.gif" bgcolor=red width=9999 height=9999 style="x:y" class="z" hidden><tr><td align=center background="https://a.example/q.gif" onclick=1>x</td></tr></table>',
    '<dialog open>x</dialog><details open ontoggle=alert(1)><summary>s</summary></details>',
    '<a href="//atacante.example/x" ping="https://a.example/p" referrerpolicy="unsafe-url" download="x">a</a>',
    '<a href="/relativo">r</a><a href="#ancora">h</a><a href="java&#x0A;script:alert(1)">j</a><a href=" \tjavascript:alert(1)">k</a>',
    '<a href="https://ok.example" id="location" name="cookie" title="t">ok</a>',
    '<td align="javascript:1">x</td><p align=center>y</p>',
    '<input autofocus onfocus=alert(1)><textarea><img src=x onerror=alert(1)></textarea>',
    '<math><mi xlink:href="javascript:alert(1)">x</mi></math><svg><use href="data:image/svg+xml,<svg onload=alert(1)>"/></svg>',
    '<form><button formaction="javascript:alert(1)">x</button></form><object data="javascript:alert(1)"></object>',
    '[x](https://ok.example "titulo") ![i](https://a.example/p.gif) <https://a.example>',
  ];
  it('só sobram tags e atributos do markdown, em qualquer entrada', () => {
    const permitidos = new Set(['a@href', 'a@target', 'a@rel', 'a@title', 'th@align', 'td@align', 'ol@start', 'td@colspan', 'td@rowspan', 'th@colspan', 'th@rowspan']);
    for (const fonte of ataquesExtra) {
      const raiz = montar(fonte);
      expect(perigosos(raiz), fonte).toEqual([]);
      for (const a of todosOsAtributos(raiz)) expect(permitidos.has(a) || a.endsWith('@title'), `${a} em ${fonte}`).toBe(true);
      raiz.querySelectorAll('a[href]').forEach(a => expect(a.getAttribute('href')).toMatch(/^(https?:\/\/|mailto:)/i));
    }
  });
  it('markdown comum continua funcionando', () => {
    const raiz = montar('# Título\n\n**negrito** _itálico_ ~~riscado~~\n\n- a\n- b\n\n1. um\n2. dois\n\n| a | b |\n|:-:|--:|\n| 1 | 2 |\n\n```js\nconst x = 1;\n```\n\n[site](https://ok.example)');
    expect(raiz.querySelector('h1')?.textContent).toBe('Título');
    expect(raiz.querySelectorAll('li').length).toBe(4);
    expect(raiz.querySelector('table td[align]')).not.toBeNull();
    expect(raiz.querySelector('.md-code [data-copiar]')).not.toBeNull();
    expect(raiz.querySelector('.md-code span')?.textContent).toBe('js');
    expect(raiz.querySelector('a')?.getAttribute('target')).toBe('_blank');
  });
});
