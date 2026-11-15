import { useState } from 'react';
import { definirNotificacoes, lerNotificacoes } from '../../desktop/notificacoes';

export function NotificacoesDesktop() {
  const [ligado, setLigado] = useState(lerNotificacoes);
  return <label className="cfg-ilha__linha"><span><strong>Notificações</strong><small>Avise quando um bot ou grupo precisar de você fora da Sora.</small></span><span className="cfg-switch"><input type="checkbox" checked={ligado} onChange={e => { const valor = e.target.checked; definirNotificacoes(valor); setLigado(valor); if (valor && !('__TAURI_INTERNALS__' in window) && 'Notification' in window && Notification.permission === 'default') void Notification.requestPermission(); }} /><span aria-hidden="true" /><em>{ligado ? 'Ligadas' : 'Desligadas'}</em></span></label>;
}
