import { useState } from 'react';
import { PLUGIN_ICONS } from '../../data/pluginIcons';
import { PluginMark } from '../ui/PluginMark';

/** Escolha das ferramentas (plugins) que o agente pode usar. */
export function SeletorFerramentas({ valor, onChange, max = 6 }: { valor: string[]; onChange: (f: string[]) => void; max?: number }) {
  const [busca, setBusca] = useState('');
  const [todas, setTodas] = useState(false);
  const alternar = (nome: string) => onChange(valor.includes(nome) ? valor.filter(n => n !== nome) : valor.length >= max ? valor : [...valor, nome]);
  const q = busca.trim().toLowerCase();
  const lista = PLUGIN_ICONS.filter(p => !q || p.name.toLowerCase().includes(q));
  const visiveis = todas || q ? lista : lista.slice(0, 18);
  return (
    <div className="st-tools">
      <div className="st-tools-picked">
        {valor.length === 0 && <small>Nenhuma ferramenta. O agente só conversa.</small>}
        {valor.map(nome => {
          const p = PLUGIN_ICONS.find(x => x.name === nome);
          return (
            <button key={nome} type="button" className="st-tool-chip" onClick={() => alternar(nome)} aria-label={`Remover ${nome}`}>
              <PluginMark nome={nome} cor={p?.hex ?? '#8B93A3'} path={p?.path ?? null} size={18} /><span>{nome}</span><b aria-hidden="true">×</b>
            </button>
          );
        })}
      </div>
      <input className="st-input st-tools-search" placeholder="Buscar plugin…" value={busca} onChange={ev => setBusca(ev.target.value)} aria-label="Buscar plugin" />
      <div className="st-tools-grid">
        {visiveis.map(p => {
          const on = valor.includes(p.name);
          return (
            <button key={p.name} type="button" className={`st-tool ${on ? 'is-on' : ''}`} aria-pressed={on} onClick={() => alternar(p.name)}
              disabled={!on && valor.length >= max} title={!on && valor.length >= max ? `Máximo de ${max} ferramentas` : p.name}>
              <PluginMark nome={p.name} cor={p.hex} path={p.path} size={20} /><span>{p.name}</span>
            </button>
          );
        })}
      </div>
      {!q && !todas && lista.length > 18 && <button type="button" className="st-link" onClick={() => setTodas(true)}>Ver todos os {lista.length} plugins</button>}
    </div>
  );
}
