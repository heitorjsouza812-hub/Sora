// Peças comuns dos cartões "Precisa de você": o mesmo cabeçalho e as mesmas opções em todo lugar
// (chat do bot, grupo, Ilha e a central da barra lateral).
import type { ReactNode } from 'react';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import type { Movimento } from '../../types';
import { COR_SORA_PEDIDO, ROTULOS_DECISAO } from './rotulos';
import './pendencias.css';

export function CabecaPedido({ cor = COR_SORA_PEDIDO, movimento, origem }: { cor?: string; movimento?: Movimento; origem?: ReactNode }) {
  return (
    <header className="pend-cabeca">
      <SoraOrb size={28} color={cor} movimento={movimento} state="listening" glow={false} decorative seed={11} />
      <strong>Precisa de você</strong>
      {origem && <span className="pend-origem">{origem}</span>}
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

