// Botão "…" acessível (padrão WAI-ARIA menu button): itens extras + Renomear + Apagar.
// Teclado: Enter/Espaço/↓ abre no 1º item, ↑ abre no último; ↑/↓/Home/End navegam; Esc fecha e devolve o foco.
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { Popover } from '../overlay';
import { pedirApagar, pedirRenomear, type AlvoGestao } from './acoes';
import './gestao.css';

export interface ItemAcao { rotulo: string; onClick: () => void; perigo?: boolean }

export interface MenuItemAcoesProps {
  alvo: AlvoGestao;
  /** nome do item (vira "Opções de <nome>" para o leitor de tela) */
  nome: string;
  /** itens antes de Renomear/Apagar (ex.: Abrir, Ver trabalho) */
  itens?: ItemAcao[];
  renomear?: boolean;
  apagar?: boolean;
  className?: string;
}

export function MenuItemAcoes({ alvo, nome, itens = [], renomear = true, apagar = true, className = '' }: MenuItemAcoesProps) {
  const [aberto, setAberto] = useState(false);
  const [foco, setFoco] = useState(0);
  const botao = useRef<HTMLButtonElement>(null);
  const lista = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();
  const sora = alvo.tipo === 'agente' && alvo.id === 'sora';

  const todos: ItemAcao[] = [
    ...itens,
    ...(renomear ? [{ rotulo: 'Renomear', onClick: () => pedirRenomear(alvo) }] : []),
    ...(apagar && !sora ? [{ rotulo: 'Apagar', onClick: () => pedirApagar(alvo), perigo: true }] : []),
  ];

  useEffect(() => { if (aberto) lista.current[foco]?.focus(); }, [aberto, foco]);

  const abrir = (i: number) => { setFoco(i); setAberto(true); };
  const fechar = (devolverFoco = true) => { setAberto(false); if (devolverFoco) botao.current?.focus(); };

  const teclaBotao = (ev: KeyboardEvent) => {
    if (ev.key === 'ArrowDown') { ev.preventDefault(); abrir(0); }
    if (ev.key === 'ArrowUp') { ev.preventDefault(); abrir(todos.length - 1); }
  };
  const teclaMenu = (ev: KeyboardEvent) => {
    const n = todos.length;
    const mover: Record<string, number> = { ArrowDown: (foco + 1) % n, ArrowUp: (foco - 1 + n) % n, Home: 0, End: n - 1 };
    if (ev.key in mover) { ev.preventDefault(); setFoco(mover[ev.key]); }
    if (ev.key === 'Tab') fechar(false);
  };

  if (!todos.length) return null;
  return (
    <div className={`gestao-menu ${className}`} onClick={(ev) => ev.stopPropagation()}>
      <button ref={botao} type="button" className="gestao-menu-btn" aria-label={`Opções de ${nome}`}
        aria-haspopup="menu" aria-expanded={aberto} aria-controls={aberto ? menuId : undefined}
        onClick={(ev) => { ev.preventDefault(); ev.stopPropagation(); if (aberto) fechar(); else abrir(0); }}
        onKeyDown={teclaBotao}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="19" cy="12" r="1.7" /></svg>
      </button>
      <Popover open={aberto} onClose={() => setAberto(false)} anchorRef={botao} role="menu" ariaLabel={`Opções de ${nome}`} width={190} className="gestao-menu-list">
        <div id={menuId} onKeyDown={teclaMenu}>
          {todos.map((item, i) => (
            <button key={item.rotulo} ref={(el) => { lista.current[i] = el; }} type="button" role="menuitem"
              tabIndex={i === foco ? 0 : -1} className={item.perigo ? 'is-danger' : undefined}
              onClick={(ev) => { ev.stopPropagation(); fechar(!item.perigo && item.rotulo !== 'Renomear'); item.onClick(); }}>
              {item.rotulo}
            </button>
          ))}
        </div>
      </Popover>
    </div>
  );
}
