// Descida do compositor depois do 1º envio (spec §7.1): o campo vai do centro ao rodapé por FLIP
// (só `transform` e a altura, nunca top/margin) enquanto o título, o orb grande e as sugestões saem.
// Tudo com Element.animate; com movimento reduzido ou no celular a troca é direta.

export const DUR_DESCIDA = 420; // --dur-layout
export const EASE = 'cubic-bezier(.2, .8, .2, 1)';

export const semMovimento = () => typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const sem = (el: Element | null | undefined) => !el || typeof (el as HTMLElement).animate !== 'function';

/** FLIP: `de` é a caixa do elemento antes da troca de layout; anima do lugar antigo ao novo. */
export function animarDescida(el: HTMLElement, de: DOMRect, alturaDe?: number) {
  if (sem(el) || semMovimento()) return;
  const para = el.getBoundingClientRect();
  const dx = de.left - para.left;
  const dy = de.top - para.top;
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
  el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: DUR_DESCIDA, easing: EASE });
  // a altura do campo (120 → 54) acompanha: o contêiner interno encolhe junto
  const campo = el.querySelector<HTMLElement>('.composer');
  if (campo && alturaDe && alturaDe > campo.getBoundingClientRect().height + 1) {
    campo.animate([{ minHeight: `${alturaDe}px` }, { minHeight: `${campo.getBoundingClientRect().height}px` }], { duration: DUR_DESCIDA, easing: EASE });
  }
}

/**
 * Deixa uma cópia fixa do elemento no lugar dele e a apaga em `ms`: assim o que sai de cena (título, sugestões)
 * some com fade mesmo depois de o React desmontá-lo. Orb: encolhe (scale 1 → .23) e some em 320 ms.
 */
export function fantasma(el: HTMLElement | null, opcoes: { ms?: number; orb?: boolean } = {}) {
  if (sem(el) || semMovimento() || !el) return;
  const { ms = 120, orb = false } = opcoes;
  const r = el.getBoundingClientRect();
  const g = el.cloneNode(true) as HTMLElement;
  const origem = el.querySelectorAll('canvas');
  g.querySelectorAll('canvas').forEach((c, i) => {
    const o = origem[i]; if (!o) return;
    c.width = o.width; c.height = o.height;
    try { c.getContext('2d')?.drawImage(o, 0, 0); } catch { /* canvas sem pixels: some com o fade */ }
  });
  g.removeAttribute('id');
  Object.assign(g.style, { position: 'fixed', left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`, margin: '0', zIndex: '5', pointerEvents: 'none', inset: 'auto', right: 'auto', bottom: 'auto' } as CSSStyleDeclaration);
  document.body.append(g);
  const fim = () => g.remove();
  if (orb) {
    const caixa = g.querySelector<HTMLElement>('.sora-hero-orb');
    caixa?.animate([{ transform: 'scale(1)', opacity: 1 }, { transform: 'scale(.23)', opacity: 0 }], { duration: 320, easing: EASE, fill: 'forwards' });
    g.querySelectorAll<HTMLElement>('h1').forEach(h => h.animate([{ opacity: 1 }, { opacity: 0 }], { duration: ms, fill: 'forwards' }));
    window.setTimeout(fim, 340);
  } else {
    g.animate([{ opacity: 1 }, { opacity: 0 }], { duration: ms, fill: 'forwards' }).finished.then(fim, fim);
  }
}
