import { useState, type CSSProperties } from 'react';
import { COR_SORA, PALETA_AGENTES } from '../../data/planejador';

const HEX = /^#[0-9a-f]{6}$/i;

/** Paleta de swatches + campo hex livre + seletor nativo. */
export function SeletorCor({ valor, onChange, incluirSora = false, emUso = [] }: {
  valor: string; onChange: (cor: string) => void; incluirSora?: boolean; emUso?: string[];
}) {
  const [texto, setTexto] = useState(valor);
  const [ultimo, setUltimo] = useState(valor);
  if (valor !== ultimo) { setUltimo(valor); setTexto(valor); }
  const usados = new Set(emUso.map(c => c.toUpperCase()));
  const cores = incluirSora ? [COR_SORA, ...PALETA_AGENTES] : [...PALETA_AGENTES];
  return (
    <div className="st-color">
      <div className="st-swatches" role="radiogroup" aria-label="Cor">
        {cores.map(c => (
          <button key={c} type="button" role="radio" aria-checked={c.toUpperCase() === valor.toUpperCase()} aria-label={c}
            className={`st-swatch ${c.toUpperCase() === valor.toUpperCase() ? 'is-on' : ''} ${usados.has(c.toUpperCase()) ? 'is-used' : ''}`}
            title={usados.has(c.toUpperCase()) ? `${c} · já usada por outro agente` : c}
            style={{ '--c': c } as CSSProperties} onClick={() => onChange(c)} />
        ))}
      </div>
      <label className="st-hex">
        <span className="st-hex-dot" style={{ background: HEX.test(texto) ? texto : valor }} />
        <input value={texto} maxLength={7} spellCheck={false} aria-label="Cor em hexadecimal"
          onChange={ev => {
            let v = ev.target.value.trim(); if (v && !v.startsWith('#')) v = '#' + v;
            setTexto(v); if (HEX.test(v)) onChange(v.toUpperCase());
          }} />
        <input type="color" value={HEX.test(valor) ? valor : '#56A8FF'} aria-label="Escolher cor livre" onChange={ev => onChange(ev.target.value.toUpperCase())} />
      </label>
    </div>
  );
}
