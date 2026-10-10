import type { CSSProperties } from 'react';
import type { Movimento } from '../../types';
import { MOVIMENTOS } from '../../data/planejador';
import { SoraOrb } from '../mascot';

/** 4 tipos de movimento, cada um com mini-prévia animada na cor escolhida. */
export function SeletorMovimento({ valor, cor, onChange }: { valor: Movimento; cor: string; onChange: (m: Movimento) => void }) {
  return (
    <div className="st-moves" role="radiogroup" aria-label="Movimento">
      {MOVIMENTOS.map((m, i) => (
        <button key={m.id} type="button" role="radio" aria-checked={valor === m.id}
          className={`st-move ${valor === m.id ? 'is-on' : ''}`} style={{ '--agent': cor } as CSSProperties} onClick={() => onChange(m.id)}>
          <SoraOrb size={52} color={cor} movimento={m.id} state="working" glow={false} seed={i * 5 + 3} title={m.nome} />
          <strong>{m.nome}</strong>
          <small>{m.descricao}</small>
        </button>
      ))}
    </div>
  );
}
