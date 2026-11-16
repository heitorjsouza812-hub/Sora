import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { nomeAmigavelDoModelo, PROVEDORES_MODELO, useModelos, type ModeloConfigurado } from '../../state/modelos';
import { usePreferenciasConversa, type ControlePreferencias } from '../../state/preferenciasConversa';
import type { PreferenciasConversa } from '../../api/preferenciasConversa';
import { Popover } from '../overlay/Popover';
import { BottomSheet } from '../overlay/BottomSheet';
import { Modal } from '../overlay/Modal';
import { Button } from '../base';
import { useCelular } from './useMedia';
import './seletorModelo.css';

// Modelos de fala, transcrição, moderação e vetores não conversam: ficam fora da lista.
const naoConversa = /orpheus|playai|whisper|guard|tts|embed|moderation/i;
const niveis = { auto: 'Automático', baixo: 'Baixo', medio: 'Médio', alto: 'Alto', extra_alto: 'Extra alto', maximo: 'Máximo' };
export function SeletorModelo({ controle }: { controle?: ControlePreferencias }) {
  const contexto = usePreferenciasConversa();
  const { valor, mudar, ocupado, erro } = controle ?? contexto;
  const catalogo = useModelos();
  const [aberto, setAberto] = useState(false);
  const [confirmar, setConfirmar] = useState(false);
  const [busca, setBusca] = useState('');
  const [provedor, setProvedor] = useState<string | null>(null);
  const ancora = useRef<HTMLButtonElement>(null);
  const conteudo = useRef<HTMLDivElement>(null);
  const celular = useCelular();
  const provedores = PROVEDORES_MODELO.flatMap(p => {
    const c = catalogo.provedores[p.id]?.conexao;
    return c ? [{ id: c.id, nome: p.nome }] : [];
  });
  const ativo = provedor ?? valor.provedor_id ?? provedores[0]?.id;
  const modelos = catalogo.modelos.filter(m => m.ativo && !naoConversa.test(m.modelo) && m.provedor_id === ativo && nomeAmigavelDoModelo(m).toLocaleLowerCase('pt-BR').includes(busca.toLocaleLowerCase('pt-BR')));
  const escolhido = catalogo.modelos.find(m => m.provedor_id === valor.provedor_id && m.modelo === valor.modelo);
  const escolher = (m?: ModeloConfigurado) => mudar({ ...valor, provedor_id: m?.provedor_id ?? null, modelo: m?.modelo ?? null, raciocinio: 'auto' });
  useEffect(() => {
    if (!aberto) return;
    const frame = requestAnimationFrame(() => conteudo.current?.querySelector<HTMLInputElement>('input')?.focus());
    return () => cancelAnimationFrame(frame);
  }, [aberto]);
  useEffect(() => {
    const atalhos = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented || confirmar || ocupado || !e.ctrlKey || e.altKey || e.metaKey || e.shiftKey || !/^[1-4]$/.test(e.key)) return;
      if (!aberto && !ancora.current?.closest('form')?.contains(document.activeElement)) return;
      const m = modelos[Number(e.key) - 1];
      if (m) { e.preventDefault(); escolher(m); }
    };
    document.addEventListener('keydown', atalhos);
    return () => document.removeEventListener('keydown', atalhos);
  });
  const teclado = (e: KeyboardEvent<HTMLDivElement>) => {
    // Os controles nativos mantêm Enter/Tab; setas percorrem a coluna atual.
    if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.key) || e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    const colunas = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[data-coluna]'));
    const coluna = (e.target as HTMLElement).closest<HTMLElement>('[data-coluna]');
    if (!coluna) return;
    let destino: HTMLElement | undefined;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      const i = colunas.indexOf(coluna) + (e.key === 'ArrowRight' ? 1 : -1);
      destino = colunas[(i + colunas.length) % colunas.length]?.querySelector<HTMLElement>('button:not(:disabled), input') ?? undefined;
    } else {
      const itens = Array.from(coluna.querySelectorAll<HTMLElement>('button:not(:disabled)'));
      destino = itens[(itens.indexOf(e.target as HTMLElement) + (e.key === 'ArrowDown' ? 1 : -1) + itens.length) % itens.length];
    }
    if (destino) { e.preventDefault(); destino.focus(); }
  };
  const corpo = <div ref={conteudo} className="seletor-corpo" onKeyDown={teclado}>
    <div className="seletor-colunas">
      <div data-coluna className="seletor-provedores" aria-label="Provedores conectados">{provedores.map(p => <button type="button" key={p.id} title={p.nome} aria-label={p.nome} aria-pressed={ativo === p.id} onClick={() => { setProvedor(p.id); setBusca(''); }}>{p.nome.slice(0, 2)}</button>)}</div>
      <div data-coluna className="seletor-modelos">
        <input aria-label="Buscar modelos" placeholder="Buscar modelos…" value={busca} onChange={e => setBusca(e.target.value)} onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); e.currentTarget.parentElement?.querySelector('button')?.focus(); } }} />
        <button type="button" disabled={ocupado} aria-pressed={!valor.modelo} onClick={() => escolher()}>Automático</button>
        {modelos.map((m, i) => <button type="button" key={m.id} disabled={ocupado} aria-pressed={escolhido?.id === m.id} onClick={() => escolher(m)}><span>{nomeAmigavelDoModelo(m)}</span><small>{[m.capacidades.includes('visao') && 'Visão', m.capacidades.includes('ferramentas') && 'Ferramentas', m.rapido && 'Rápido'].filter(Boolean).join(' · ')}{i < 4 && <kbd>Ctrl+{i + 1}</kbd>}</small></button>)}
        {!modelos.length && <p className="seletor-ajuda">{catalogo.carregando ? 'Carregando modelos…' : 'Nenhum modelo encontrado.'}</p>}
      </div>
      {!!escolhido?.raciocinio?.length && <div data-coluna className="seletor-raciocinio"><strong>Raciocínio</strong>{(['auto', ...escolhido.raciocinio] as const).map(n => <button type="button" key={n} disabled={ocupado} aria-pressed={valor.raciocinio === n} onClick={() => mudar({ ...valor, raciocinio: n })}>{niveis[n]}</button>)}</div>}
    </div>
    <footer className="seletor-permissao"><label>♢ Permissão <select aria-label="Permissão" disabled={ocupado} value={valor.permissao} onChange={e => { const p = e.target.value as PreferenciasConversa['permissao']; if (p === 'total') { setAberto(false); setConfirmar(true); } else mudar({ ...valor, permissao: p }); }}><option value="perguntar">Perguntar sempre</option><option value="automatico">Automático</option><option value="total">Acesso total</option></select></label><p className="seletor-ajuda">{valor.permissao === 'automatico' ? 'O bot aprova sozinho ações de baixo risco.' : valor.permissao === 'total' ? 'O bot age sem pedir, respeitando os bloqueios permanentes.' : 'O bot pede sua aprovação antes de agir.'}</p>{(erro || catalogo.erro) && <p role="alert">{erro || catalogo.erro}</p>}</footer>
  </div>;
  return <>
    <button type="button" ref={ancora} className="tool-button seletor-gatilho" aria-haspopup="dialog" aria-expanded={aberto} onClick={() => setAberto(!aberto)}>{escolhido ? nomeAmigavelDoModelo(escolhido) : valor.modelo ?? 'Automático'} <span aria-hidden="true">⌄</span></button>
    {celular ? <BottomSheet open={aberto} onClose={() => setAberto(false)} title="Modelo e permissão" className="seletor-folha">{corpo}</BottomSheet> : <Popover open={aberto} onClose={() => setAberto(false)} anchorRef={ancora} side="top" align="start" width={640} ariaLabel="Modelo e permissão" className="seletor-popover">{corpo}</Popover>}
    <Modal open={confirmar} onClose={() => { setConfirmar(false); ancora.current?.focus(); }} title="Ativar acesso total?" description="O bot poderá agir sem pedir sua aprovação." footer={<div className="seletor-botoes"><Button variante="secundario" onClick={() => { setConfirmar(false); ancora.current?.focus(); }}>Cancelar</Button><Button onClick={() => { mudar({ ...valor, permissao: 'total' }, true); setConfirmar(false); ancora.current?.focus(); }}>Ativar acesso total</Button></div>}><p>Continuam sempre bloqueados:</p><ul className="seletor-bloqueios"><li>senhas;</li><li>programas bloqueados;</li><li>envio pelos canais da empresa;</li><li>o bot mudar as próprias instruções;</li><li>pagamentos.</li></ul></Modal>
  </>;
}
