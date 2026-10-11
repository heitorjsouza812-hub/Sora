// Pilha de camadas (Modal, BottomSheet, Popover): uma só escuta de Esc que fecha apenas a camada
// do topo, 'inert' no fundo enquanto há camada modal e trava de rolagem sem pulo de layout.
// Filhos do <body> com [data-camada-livre] (ex.: avisos) nunca ficam inertes.

interface Camada { id: number; el: HTMLElement; modal: boolean; onEsc: () => void }

const pilha: Camada[] = [];
let seq = 0;
const inertesNossos = new Set<HTMLElement>();
let observador: MutationObserver | null = null;
let rolagemSalva: { overflow: string; paddingRight: string } | null = null;

const filhoDoBody = (el: HTMLElement): HTMLElement | null => {
  let atual: HTMLElement | null = el;
  while (atual && atual.parentElement !== document.body) atual = atual.parentElement;
  return atual;
};

function aplicarInert() {
  let topoModal = -1;
  pilha.forEach((c, i) => { if (c.modal) topoModal = i; });
  const livres = new Set<HTMLElement>();
  if (topoModal >= 0) pilha.slice(topoModal).forEach(c => { const f = filhoDoBody(c.el); if (f) livres.add(f); });
  for (const filho of Array.from(document.body.children) as HTMLElement[]) {
    const inerte = topoModal >= 0 && !livres.has(filho) && !filho.hasAttribute('data-camada-livre')
      && filho.tagName !== 'SCRIPT' && filho.tagName !== 'STYLE';
    if (inerte && !filho.inert) { filho.inert = true; inertesNossos.add(filho); }
    else if (!inerte && inertesNossos.has(filho)) { filho.inert = false; inertesNossos.delete(filho); }
  }
  for (const el of Array.from(inertesNossos)) if (!el.isConnected) inertesNossos.delete(el);
}

// compensa a largura da barra de rolagem para o conteúdo não "pular" ao travar
function travarRolagem(travar: boolean) {
  const body = document.body;
  if (travar && !rolagemSalva) {
    const barra = window.innerWidth - document.documentElement.clientWidth;
    rolagemSalva = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
    if (barra > 0) body.style.paddingRight = `${(parseFloat(getComputedStyle(body).paddingRight) || 0) + barra}px`;
    body.style.overflow = 'hidden';
  } else if (!travar && rolagemSalva) {
    body.style.overflow = rolagemSalva.overflow;
    body.style.paddingRight = rolagemSalva.paddingRight;
    rolagemSalva = null;
  }
}

function aoTeclar(event: KeyboardEvent) {
  if (event.key !== 'Escape' || event.defaultPrevented) return;
  const topo = pilha[pilha.length - 1];
  if (!topo) return;
  event.preventDefault();
  event.stopPropagation();
  topo.onEsc();
}

function atualizar() {
  const temModal = pilha.some(c => c.modal);
  aplicarInert();
  travarRolagem(temModal);
  if (temModal && !observador) {
    observador = new MutationObserver(aplicarInert);
    observador.observe(document.body, { childList: true });
  } else if (!temModal && observador) {
    observador.disconnect();
    observador = null;
  }
}

/** registra uma camada aberta; `remover` tira da pilha ao fechar */
export function empilharCamada(el: HTMLElement, opcoes: { modal: boolean; onEsc: () => void }) {
  if (!pilha.length) document.addEventListener('keydown', aoTeclar, true);
  const camada: Camada = { id: ++seq, el, ...opcoes };
  pilha.push(camada);
  atualizar();
  return {
    id: camada.id,
    remover: () => {
      const i = pilha.indexOf(camada);
      if (i >= 0) pilha.splice(i, 1);
      atualizar();
      if (!pilha.length) document.removeEventListener('keydown', aoTeclar, true);
    },
  };
}

/** a camada é a de cima? (o foco preso só age na camada do topo) */
export const ehCamadaDoTopo = (id: number) => pilha[pilha.length - 1]?.id === id;
