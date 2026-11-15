// Peças comuns dos cartões "Precisa de você": a mesma cabeça e as mesmas opções em todo lugar
// (chat do bot, grupo, Ilha e a central da barra lateral).
import type { ReactNode } from 'react';
import { Button } from '../base';
import { ROTULOS_DECISAO } from './rotulos';
import './pendencias.css';

/** Cabeça do cartão: ponto, "Precisa de você", origem (quando não é óbvia) e a hora à direita. */
export function CabecaPedido({ origem, hora }: { origem?: ReactNode; hora?: string }) {
  return (
    <header className="pend-cabeca">
      <span className="pend-sinal" aria-hidden="true" />
      <strong>Precisa de você</strong>
      {origem && <span className="pend-origem">{origem}</span>}
      {hora && <time className="pend-hora">{hora}</time>}
    </header>
  );
}

/** Permitir uma vez · Sempre permitir (quando o servidor aceita) · Recusar. */
export function BotoesAprovacao({ desabilitado, onPermitir, onSempre, onRecusar }: { desabilitado?: boolean; onPermitir: () => void; onSempre?: () => void; onRecusar: () => void }) {
  return (
    <div className="pend-acoes" role="group" aria-label="Decisão">
      <Button tamanho="M" variante="primario" disabled={desabilitado} onClick={onPermitir}>{ROTULOS_DECISAO.permitirUmaVez}</Button>
      {onSempre && <Button tamanho="M" variante="secundario" disabled={desabilitado} onClick={onSempre}>{ROTULOS_DECISAO.semprePermitir}</Button>}
      <Button tamanho="M" variante="perigo" disabled={desabilitado} onClick={onRecusar}>{ROTULOS_DECISAO.recusar}</Button>
    </div>
  );
}
