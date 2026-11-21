// Notificação no celular (Web Push) do "Precisa de você". Só no navegador (no app de desktop o
// aviso é do sistema, pela Ilha). O service worker é /sw.js (sem cache); o backend é app/api/push.py.
import { api } from '../api/cliente';
import { noDesktop } from '../desktop/ponte';

export type SituacaoPush = 'sem_suporte' | 'precisa_instalar' | 'servidor_desligado' | 'bloqueado' | 'desligado' | 'ligado';

export function temSuporte(): boolean {
  return !noDesktop && typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && window.isSecureContext;
}

/** iPhone/iPad só recebem push com a Sora instalada na Tela de Início. */
export function precisaInstalar(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const instalada = window.matchMedia?.('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !instalada;
}

/** Registra /sw.js (uma vez). Chamado na abertura do app no navegador. */
export async function registrarServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!temSuporte()) return null;
  try { return await navigator.serviceWorker.register('/sw.js', { scope: '/' }); } catch { return null; }
}

function chaveParaBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const preenchido = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  const bruto = atob(preenchido);
  const bytes = new Uint8Array(new ArrayBuffer(bruto.length));
  for (let i = 0; i < bruto.length; i += 1) bytes[i] = bruto.charCodeAt(i);
  return bytes;
}

async function inscricaoAtual(): Promise<PushSubscription | null> {
  const registro = await navigator.serviceWorker.getRegistration('/');
  return registro ? registro.pushManager.getSubscription() : null;
}

export async function situacao(): Promise<SituacaoPush> {
  if (!temSuporte()) return precisaInstalar() ? 'precisa_instalar' : 'sem_suporte';
  if (precisaInstalar()) return 'precisa_instalar';
  const { chave_publica } = await api.get<{ chave_publica: string | null }>('/v1/push/chave');
  if (!chave_publica) return 'servidor_desligado';
  if (Notification.permission === 'denied') return 'bloqueado';
  return (await inscricaoAtual()) ? 'ligado' : 'desligado';
}

/** Pede permissão, inscreve o aparelho e manda a inscrição para o servidor. */
export async function ligar(): Promise<SituacaoPush> {
  const { chave_publica } = await api.get<{ chave_publica: string | null }>('/v1/push/chave');
  if (!chave_publica) return 'servidor_desligado';
  const permissao = await Notification.requestPermission();
  if (permissao !== 'granted') return permissao === 'denied' ? 'bloqueado' : 'desligado';
  const registro = (await registrarServiceWorker()) ?? (await navigator.serviceWorker.ready);
  const inscricao = (await registro.pushManager.getSubscription())
    ?? await registro.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: chaveParaBytes(chave_publica) });
  const json = inscricao.toJSON();
  await api.post<void>('/v1/push/inscricoes', { endpoint: json.endpoint, keys: json.keys });
  return 'ligado';
}

export async function desligar(): Promise<SituacaoPush> {
  const inscricao = await inscricaoAtual();
  if (inscricao) {
    await api.delete<void>('/v1/push/inscricoes', { endpoint: inscricao.endpoint }).catch(() => undefined);
    await inscricao.unsubscribe().catch(() => false);
  }
  return 'desligado';
}

export const testar = () => api.post<{ enviadas: number }>('/v1/push/teste');
