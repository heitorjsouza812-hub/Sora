import { invoke } from '@tauri-apps/api/core';
import { noDesktop } from './ponte';

const CHAVE = 'sora.notificacoes.v1';
export function lerNotificacoes(): boolean { try { return localStorage.getItem(CHAVE) !== 'false'; } catch { return true; } }
export function definirNotificacoes(valor: boolean): void { try { localStorage.setItem(CHAVE, String(valor)); } catch { /* armazenamento indisponível */ } }
export function tituloAtencao(total: number): void {
  document.title = total ? `(${total}) Sora` : 'Sora';
  if (noDesktop) void invoke('titulo_atencao', { total }).catch(() => {});
}
export function notificarAtencao(id: number, origem: string, caminho: string, abrir: (caminho: string) => void): void {
  if (!lerNotificacoes()) return;
  if (noDesktop) { void invoke('notificar_atencao', { id, origem, caminho }).catch(() => {}); return; }
  if (document.hasFocus() || !('Notification' in window) || Notification.permission !== 'granted') return;
  const aviso = new Notification('Precisa de você', { body: origem });
  aviso.onclick = () => { window.focus(); abrir(caminho); aviso.close(); };
}
