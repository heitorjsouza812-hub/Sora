import { useEffect, useRef, useState } from 'react';
import { abrirEditorAgente } from './abrirEditor';
import './studio.css';

export interface ItemMenu { rotulo: string; onClick: () => void }

/** Botão "…" com menu: "Editar agente" sempre presente + itens extras (Ver trabalho, Conversar…). */
export function MenuAgente({ agenteId, nome, itens = [], className = '' }: { agenteId: string; nome: string; itens?: ItemMenu[]; className?: string }) {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const fora = (ev: MouseEvent) => { if (!raiz.current?.contains(ev.target as Node)) setAberto(false); };
    const esc = (ev: KeyboardEvent) => { if (ev.key === 'Escape') setAberto(false); };
    document.addEventListener('mousedown', fora); document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', fora); document.removeEventListener('keydown', esc); };
  }, [aberto]);
  const todos: ItemMenu[] = [{ rotulo: agenteId === 'sora' ? 'Personalizar' : 'Editar agente', onClick: () => abrirEditorAgente(agenteId) }, ...itens];
  return (
    <div className={`st-menu ${className}`} ref={raiz}>
      <button type="button" className="st-menu-btn" aria-label={`Opções de ${nome}`} aria-haspopup="menu" aria-expanded={aberto}
        onClick={ev => { ev.preventDefault(); ev.stopPropagation(); setAberto(v => !v); }}>•••</button>
      {aberto && (
        <div className="st-menu-list" role="menu">
          {todos.map(i => (
            <button key={i.rotulo} type="button" role="menuitem" onClick={ev => { ev.preventDefault(); ev.stopPropagation(); setAberto(false); i.onClick(); }}>{i.rotulo}</button>
          ))}
        </div>
      )}
    </div>
  );
}
