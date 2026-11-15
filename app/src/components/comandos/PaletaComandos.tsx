// Paleta de comandos da etapa 5: busca em ações, bots e grupos.
// Padrão WAI-ARIA "combobox + listbox" dentro de um diálogo modal: o foco fica no campo e a opção ativa
// é indicada por aria-activedescendant; ↑/↓ (e Home/End com Ctrl) navegam, Enter abre, Esc fecha.
// Usa a pilha de camadas do overlay (Esc só fecha a camada do topo, fundo inerte, rolagem travada).
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { buscarMensagens, rotaDoResultado, type ResultadoBusca } from '../../state/pecas';
import { useBots } from '../../state/bots';
import { useGrupos } from '../../state/grupos';
import { SoraOrb } from '../mascot';
import { empilharCamada } from '../overlay/camadas';
import { normalizar } from '../projetos/util';
import { ATALHOS, MOD, fecharPaleta } from './atalhos';
import { usePrecisaDeVoce } from '../../state/atencao';
import './comandos.css';

interface Item {
  id: string;
  grupo: 'Ações' | 'Bots' | 'Grupos' | 'Mensagens';
  /** Mensagens vêm do servidor já filtradas: não passam pelo filtro local. */
  remoto?: boolean;
  rotulo: string;
  detalhe?: string;
  conteudo?: ReactNode;
  icone: ReactNode;
  teclas?: string[];
  busca: string;
  executar: () => void;
}

const LIMITE_SEM_BUSCA = 5;
const quandoCurto = (iso: string) => new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
/** Trecho com os destaques do servidor ([início, fim) dentro do trecho) em negrito. */
export function TrechoDestacado({ trecho, destaques }: { trecho: string; destaques: [number, number][] }) {
  const partes: ReactNode[] = []; let pos = 0;
  [...destaques].sort((a, b) => a[0] - b[0]).forEach(([i, f], n) => {
    if (i < pos || f > trecho.length || f <= i) return;
    if (i > pos) partes.push(trecho.slice(pos, i));
    partes.push(<b key={n}>{trecho.slice(i, f)}</b>); pos = f;
  });
  if (pos < trecho.length) partes.push(trecho.slice(pos));
  return <>{partes}</>;
}
const Icone = ({ d }: { d: string }) => <svg viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>;
const IC = {
  mais: 'M12 5v14M5 12h14',
  grupo: 'M7 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20a5 5 0 0 1 10 0M12 20a5 5 0 0 1 10 0',
  agente: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0',
  engrenagem: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1',
};

export function PaletaComandos({ onAbrirCentral }: { onAbrirCentral: () => void }) {
  const { lista: pedidos } = usePrecisaDeVoce();
  const pendentes = pedidos.length;
  const [atalhos, setAtalhos] = useState(false);
  const bots = useBots();
  const estadoGrupos = useGrupos();
  const navigate = useNavigate();
  const [busca, setBusca] = useState('');
  const [ativo, setAtivo] = useState(0);
  const [achadas, setAchadas] = useState<ResultadoBusca[]>([]);
  const dialogo = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLInputElement>(null);
  const lista = useRef<HTMLDivElement>(null);
  const base = useId();
  const listaId = `${base}-lista`;

  // camada modal: Esc fecha, fundo inerte, foco volta para onde estava
  useLayoutEffect(() => {
    const antes = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const camada = empilharCamada(dialogo.current!, { modal: true, onEsc: fecharPaleta });
    campo.current?.focus();
    return () => { camada.remover(); if (antes?.isConnected) antes.focus(); };
  }, []);

  const ir = (rota: string, antes?: () => void) => () => { fecharPaleta(); antes?.(); navigate(rota); };

  const itens = useMemo<Item[]>(() => {
    const acoes: Item[] = [
      { id: 'sora', grupo: 'Ações', rotulo: 'Conversar com a Sora', icone: <Icone d={IC.mais} />, teclas: [MOD, 'Shift', 'O'], busca: 'sora conversa', executar: ir('/') },
      { id: 'bots', grupo: 'Ações', rotulo: 'Ver bots', icone: <Icone d={IC.agente} />, busca: 'bots agentes', executar: ir('/bots') },
      { id: 'grupos', grupo: 'Ações', rotulo: 'Ver grupos', icone: <Icone d={IC.grupo} />, busca: 'grupos equipe', executar: ir('/grupos') },
      { id: 'configuracoes', grupo: 'Ações', rotulo: 'Configurações', icone: <Icone d={IC.engrenagem} />, busca: 'configuracoes ajustes conta modelos api', executar: ir('/configuracoes') },
    ];
    const itensBots = bots.map<Item>((bot) => ({
      id: `b-${bot.id}`, grupo: 'Bots', rotulo: bot.nome, detalhe: bot.funcao,
      icone: <span className="cmd-orb" style={{ '--agent-color': bot.cor } as CSSProperties}><SoraOrb size={20} color={bot.cor} glow={false} decorative /></span>,
      busca: `${bot.nome} ${bot.funcao}`, executar: ir(`/bots/${bot.id}`),
    }));
    const itensGrupos = estadoGrupos.lista.map<Item>((grupo) => ({
      id: `g-${grupo.id}`, grupo: 'Grupos', rotulo: grupo.nome, detalhe: `${grupo.membros.length} bots`,
      icone: <Icone d={IC.grupo} />, busca: grupo.nome, executar: ir(`/grupos/${grupo.id}`),
    }));
    const atencao: Item = { id: 'atencao', grupo: 'Ações', rotulo: pendentes ? `Precisa de você (${pendentes})` : 'Precisa de você', icone: <Icone d={IC.agente} />, busca: 'pendencias aprovacoes pedidos', executar: onAbrirCentral };
    acoes.push({ id: 'atalhos', grupo: 'Ações', rotulo: 'Ver atalhos', icone: <Icone d={IC.mais} />, busca: 'teclado ajuda', executar: () => setAtalhos(true) });
    return [...(pendentes ? [atencao, ...acoes] : [...acoes, atencao]), ...itensBots, ...itensGrupos];
  // ir/navigate são estáveis o bastante para a vida curta da paleta
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bots, estadoGrupos.lista, pendentes, onAbrirCentral]);

  const termo = normalizar(busca.trim());

  // busca nas mensagens: espera ~200 ms parado e cancela a anterior
  useEffect(() => {
    const q = busca.trim();
    if (q.length < 2) { setAchadas([]); return; }
    const ctl = new AbortController();
    const t = window.setTimeout(() => { buscarMensagens(q, 8, ctl.signal).then(r => { if (!ctl.signal.aborted) setAchadas(r); }).catch(() => { if (!ctl.signal.aborted) setAchadas([]); }); }, 200);
    return () => { window.clearTimeout(t); ctl.abort(); };
  }, [busca]);
  const itensMensagens = useMemo<Item[]>(() => achadas.map(r => ({
    id: `m-${r.mensagem_id}`, grupo: 'Mensagens', remoto: true, rotulo: r.titulo, busca: '', detalhe: `${r.autor_nome} · ${quandoCurto(r.criada_em)}`,
    icone: <Icone d={r.tipo === 'grupo' ? IC.grupo : IC.agente} />, conteudo: <TrechoDestacado trecho={r.trecho} destaques={r.destaques} />,
    executar: ir(rotaDoResultado(r)),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  })), [achadas]);
  const visiveis = useMemo(() => {
    if (!termo) {
      const conta: Record<string, number> = {};
      return itens.filter((i) => i.grupo === 'Ações' || (conta[i.grupo] = (conta[i.grupo] ?? 0) + 1) <= LIMITE_SEM_BUSCA);
    }
    const palavras = termo.split(/\s+/);
    return [...itens.filter((i) => { const alvo = normalizar(`${i.rotulo} ${i.busca}`); return palavras.every((w) => alvo.includes(w)); }), ...itensMensagens];
  }, [itens, termo, itensMensagens]);

  const atual = Math.min(ativo, Math.max(0, visiveis.length - 1));
  const opcaoId = (i: number) => `${base}-op-${i}`;

  useEffect(() => {
    lista.current?.querySelector(`#${CSS.escape(opcaoId(atual))}`)?.scrollIntoView({ block: 'nearest' });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atual]);

  const tecla = (ev: KeyboardEvent<HTMLInputElement>) => {
    const n = visiveis.length;
    if (ev.key === 'ArrowDown' && n) { ev.preventDefault(); setAtivo((atual + 1) % n); }
    else if (ev.key === 'ArrowUp' && n) { ev.preventDefault(); setAtivo((atual - 1 + n) % n); }
    else if (ev.key === 'Home' && ev.ctrlKey && n) { ev.preventDefault(); setAtivo(0); }
    else if (ev.key === 'End' && ev.ctrlKey && n) { ev.preventDefault(); setAtivo(n - 1); }
    else if (ev.key === 'Enter') { ev.preventDefault(); visiveis[atual]?.executar(); }
    else if (ev.key === 'Tab') ev.preventDefault(); // o foco fica no campo (padrão combobox)
  };

  // agrupa mantendo o índice global (para aria-activedescendant)
  const grupos: { nome: Item['grupo']; itens: { item: Item; i: number }[] }[] = [];
  visiveis.forEach((item, i) => {
    const g = grupos.find((x) => x.nome === item.grupo) ?? (grupos.push({ nome: item.grupo, itens: [] }), grupos[grupos.length - 1]);
    g.itens.push({ item, i });
  });

  return createPortal(
    <div className="cmd-fundo" onPointerDown={(ev) => { if (ev.target === ev.currentTarget) fecharPaleta(); }}>
      <div ref={dialogo} className="cmd" role="dialog" aria-modal="true" aria-label="Paleta de comandos">
        <div className="cmd-busca">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
          <input ref={campo} type="text" role="combobox" aria-expanded="true" aria-controls={listaId} aria-autocomplete="list"
            aria-activedescendant={visiveis.length ? opcaoId(atual) : undefined} aria-label="Buscar bots, grupos, mensagens e ações"
            placeholder="Buscar bots, grupos, mensagens e ações…" value={busca} autoComplete="off" spellCheck={false}
            onChange={(ev) => { setBusca(ev.target.value); setAtivo(0); }} onKeyDown={tecla} />
          <button className="cmd-fechar" type="button" aria-label="Fechar paleta" onClick={fecharPaleta}>Esc</button>
        </div>
        <div ref={lista} id={listaId} className="cmd-lista" role="listbox" aria-label="Resultados">
          {grupos.map((g) => (
            <div key={g.nome} role="group" aria-labelledby={`${base}-g-${g.nome}`} className="cmd-grupo">
              <div id={`${base}-g-${g.nome}`} className="cmd-grupo__titulo" role="presentation">{g.nome}</div>
              {g.itens.map(({ item, i }) => (
                <div key={item.id} id={opcaoId(i)} role="option" aria-selected={i === atual} className="cmd-op"
                  onPointerMove={() => { if (i !== atual) setAtivo(i); }} onClick={item.executar}>
                  <span className="cmd-op__icone">{item.icone}</span>
                  <span className="cmd-op__texto"><span>{item.rotulo}</span>{item.conteudo && <span className="cmd-trecho">{item.conteudo}</span>}{item.detalhe && <small>{item.detalhe}</small>}</span>
                  {item.teclas && <span className="cmd-teclas" aria-hidden="true">{item.teclas.map((t) => <kbd key={t}>{t}</kbd>)}</span>}
                </div>
              ))}
            </div>
          ))}
          {!visiveis.length && <p className="cmd-vazio">Nada encontrado para “{busca.trim()}”.</p>}
        </div>
        <span className="cmd-sr" role="status" aria-live="polite">{visiveis.length ? `${visiveis.length} resultados` : 'Nenhum resultado'}</span>
        <footer className="cmd-atalhos" aria-label="Atalhos de teclado">
          <span>↑↓ Navegar · Enter Abrir · Esc Fechar</span>
          {atalhos && <><h2>Atalhos</h2>
          <ul>
            {ATALHOS.map((a) => (
              <li key={a.acao}><span className="cmd-teclas">{a.teclas.map((t) => <kbd key={t}>{t}</kbd>)}</span>{a.acao}</li>
            ))}
          </ul><button type="button" className="cmd-fechar" onClick={() => { setAtalhos(false); campo.current?.focus(); }}>Voltar à busca</button></>}
        </footer>
      </div>
    </div>,
    document.body,
  );
}
