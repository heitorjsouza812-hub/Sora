// Atalhos de teclado globais (item 46) e o estado "paleta aberta" (para abrir de qualquer lugar).
import { useSyncExternalStore } from 'react';

export const ehMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const MOD = ehMac ? '⌘' : 'Ctrl';

/** Lista exibida na paleta (e reaproveitável em Configurações > Conta). */
export const ATALHOS: { teclas: string[]; acao: string }[] = [
  { teclas: [MOD, 'K'], acao: 'Paleta de comandos' },
  { teclas: [MOD, 'Shift', 'O'], acao: 'Novo chat' },
  { teclas: [MOD, 'Shift', 'S'], acao: 'Ilha da Sora' },
  { teclas: [MOD, '.'], acao: 'Painel do projeto' },
  { teclas: ['/'], acao: 'Campo de mensagem' },
  { teclas: ['↑', '↓'], acao: 'Navegar' },
  { teclas: ['Enter'], acao: 'Abrir' },
  { teclas: ['Esc'], acao: 'Fechar' },
];

let aberta = false;
const ouvintes = new Set<() => void>();
const avisar = () => ouvintes.forEach((f) => f());
export function abrirPaleta() { aberta = true; avisar(); }
export function fecharPaleta() { aberta = false; avisar(); }
export function alternarPaleta() { aberta = !aberta; avisar(); }
export const usePaletaAberta = () =>
  useSyncExternalStore((f) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; }, () => aberta, () => aberta);

/** O foco está num campo de texto? (aí '/' é só uma barra digitada) */
export function digitando(alvo: EventTarget | null) {
  const el = alvo as HTMLElement | null;
  return !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
}

/** Leva o foco ao campo de mensagem visível (compositor da tela atual). */
export function focarCampoMensagem() {
  const campos = Array.from(document.querySelectorAll<HTMLTextAreaElement>('.composer textarea, main textarea'));
  const campo = campos.find((c) => c.offsetParent !== null && !c.disabled);
  if (!campo) return false;
  campo.focus();
  campo.setSelectionRange(campo.value.length, campo.value.length);
  return true;
}

/** "Alternar painel" reaproveita o atalho Ctrl+. que o PainelLateral já escuta (sem duplicar a lógica). */
export function alternarPainel() {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: '.', ctrlKey: !ehMac, metaKey: ehMac, bubbles: true }));
}
