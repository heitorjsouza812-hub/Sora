// Paleta de comandos (item 46): busca em ações, chats, projetos e agentes.
// Padrão WAI-ARIA "combobox + listbox" dentro de um diálogo modal: o foco fica no campo e a opção ativa
// é indicada por aria-activedescendant; ↑/↓ (e Home/End com Ctrl) navegam, Enter abre, Esc fecha.
// Usa a pilha de camadas do overlay (Esc só fecha a camada do topo, fundo inerte, rolagem travada).
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { abrirProjeto, novoChat, todosAgentes, useProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { empilharCamada } from '../overlay/camadas';
import { normalizar } from '../projetos/util';
import { definirIlhaPrefs, useIlhaPrefs } from '../ilha/ilhaEstado';
import { abrirIlha } from '../ilha/ilhaUi';
import { ATALHOS, MOD, alternarPainel, fecharPaleta } from './atalhos';
import './comandos.css';

interface Item {
  id: string;
  grupo: 'Ações' | 'Chats' | 'Projetos' | 'Agentes';
  rotulo: string;
  detalhe?: string;
  icone: ReactNode;
  teclas?: string[];
  busca: string;
  executar: () => void;
}

const LIMITE_SEM_BUSCA = 5;
const Icone = ({ d }: { d: string }) => <svg viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>;
const IC = {
  mais: 'M12 5v14M5 12h14',
  pasta: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  agente: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0',
  engrenagem: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1',
  plugin: 'M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0zM12 16v5',
  painel: 'M4 4h16v16H4zM15 4v16',
  balao: 'M4 5h16v11H8l-4 4z',
  ilha: 'M4 12h16M7 8h10M9 16h6',
  som: 'M5 10v4h3l4 3V7L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11',
};

export function PaletaComandos() {
  const e = useProjetos();
  const ilhaPrefs = useIlhaPrefs();
  const navigate = useNavigate();
  const [busca, setBusca] = useState('');
  const [ativo, setAtivo] = useState(0);
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
      { id: 'novo-chat', grupo: 'Ações', rotulo: 'Novo chat', icone: <Icone d={IC.mais} />, teclas: [MOD, 'Shift', 'O'], busca: 'novo chat conversa', executar: ir('/', novoChat) },
      { id: 'novo-projeto', grupo: 'Ações', rotulo: 'Novo projeto', icone: <Icone d={IC.pasta} />, busca: 'novo projeto equipe', executar: ir('/projetos') },
      { id: 'criar-agente', grupo: 'Ações', rotulo: 'Criar agente', icone: <Icone d={IC.agente} />, busca: 'criar agente novo construtor', executar: ir('/agentes/novo') },
      { id: 'painel', grupo: 'Ações', rotulo: 'Mostrar/esconder painel do projeto', icone: <Icone d={IC.painel} />, teclas: [MOD, '.'], busca: 'alternar painel lateral equipe trabalho', executar: () => { fecharPaleta(); alternarPainel(); } },
      { id: 'ilha-abrir', grupo: 'Ações', rotulo: 'Abrir a Ilha da Sora', icone: <Icone d={IC.ilha} />, teclas: [MOD, 'Shift', 'S'], busca: 'ilha sora abrir agentes atividade', executar: () => { fecharPaleta(); definirIlhaPrefs({ visivel: true }); abrirIlha(); } },
      { id: 'ilha-projeto', grupo: 'Ações', rotulo: 'Ilha: escolher projeto', icone: <Icone d={IC.pasta} />, busca: 'ilha selecionar escolher projeto', executar: () => { fecharPaleta(); definirIlhaPrefs({ visivel: true }); abrirIlha('projeto'); } },
      { id: 'ilha-som', grupo: 'Ações', rotulo: `Ilha: som ${ilhaPrefs.som ? 'desligado' : 'ligado'}`, detalhe: ilhaPrefs.som ? 'Desligar avisos sonoros' : 'Ligar avisos sonoros', icone: <Icone d={IC.som} />, busca: 'ilha som audio ligar desligar', executar: () => { definirIlhaPrefs({ som: !ilhaPrefs.som }); fecharPaleta(); } },
      { id: 'configuracoes', grupo: 'Ações', rotulo: 'Configurações', icone: <Icone d={IC.engrenagem} />, busca: 'configuracoes ajustes conta modelos api', executar: ir('/configuracoes') },
      { id: 'plugins', grupo: 'Ações', rotulo: 'Plugins', icone: <Icone d={IC.plugin} />, busca: 'plugins ferramentas conectar', executar: ir('/plugins') },
    ];
    const conversas = e.projetos.map<Item>((p) => ({
      id: `p-${p.id}`, grupo: p.tipo === 'chat' ? 'Chats' : 'Projetos', rotulo: p.titulo, detalhe: p.pedido,
      icone: <Icone d={p.tipo === 'chat' ? IC.balao : IC.pasta} />, busca: `${p.titulo} ${p.pedido}`,
      executar: ir(`/projeto/${p.id}`, () => abrirProjeto(p.id)),
    }));
    const agentes = todosAgentes(e, Number.POSITIVE_INFINITY).map<Item>((a) => ({
      id: `a-${a.id}`, grupo: 'Agentes', rotulo: a.nome, detalhe: a.funcao,
      icone: <span className="cmd-orb" style={{ '--agent-color': a.cor } as CSSProperties}><SoraOrb size={20} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative /></span>,
      busca: `${a.nome} ${a.funcao}`, executar: ir(`/chat/${a.id}`),
    }));
    return [...acoes, ...conversas, ...agentes];
  // ir/navigate são estáveis o bastante para a vida curta da paleta
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e, ilhaPrefs.som]);

  const termo = normalizar(busca.trim());
  const visiveis = useMemo(() => {
    if (!termo) {
      const conta: Record<string, number> = {};
      return itens.filter((i) => i.grupo === 'Ações' || (conta[i.grupo] = (conta[i.grupo] ?? 0) + 1) <= LIMITE_SEM_BUSCA);
    }
    const palavras = termo.split(/\s+/);
    return itens.filter((i) => { const alvo = normalizar(`${i.rotulo} ${i.busca}`); return palavras.every((w) => alvo.includes(w)); });
  }, [itens, termo]);

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
            aria-activedescendant={visiveis.length ? opcaoId(atual) : undefined} aria-label="Buscar chats, projetos, agentes e ações"
            placeholder="Buscar chats, projetos, agentes e ações…" value={busca} autoComplete="off" spellCheck={false}
            onChange={(ev) => { setBusca(ev.target.value); setAtivo(0); }} onKeyDown={tecla} />
          <kbd>Esc</kbd>
        </div>
        <div ref={lista} id={listaId} className="cmd-lista" role="listbox" aria-label="Resultados">
          {grupos.map((g) => (
            <div key={g.nome} role="group" aria-labelledby={`${base}-g-${g.nome}`} className="cmd-grupo">
              <div id={`${base}-g-${g.nome}`} className="cmd-grupo__titulo" role="presentation">{g.nome}</div>
              {g.itens.map(({ item, i }) => (
                <div key={item.id} id={opcaoId(i)} role="option" aria-selected={i === atual} className="cmd-op"
                  onPointerMove={() => { if (i !== atual) setAtivo(i); }} onClick={item.executar}>
                  <span className="cmd-op__icone">{item.icone}</span>
                  <span className="cmd-op__texto"><span>{item.rotulo}</span>{item.detalhe && <small>{item.detalhe}</small>}</span>
                  {item.teclas && <span className="cmd-teclas" aria-hidden="true">{item.teclas.map((t) => <kbd key={t}>{t}</kbd>)}</span>}
                </div>
              ))}
            </div>
          ))}
          {!visiveis.length && <p className="cmd-vazio">Nada encontrado para “{busca.trim()}”.</p>}
        </div>
        <span className="cmd-sr" role="status" aria-live="polite">{visiveis.length ? `${visiveis.length} resultados` : 'Nenhum resultado'}</span>
        <footer className="cmd-atalhos" aria-label="Atalhos de teclado">
          <h2>Atalhos</h2>
          <ul>
            {ATALHOS.map((a) => (
              <li key={a.acao}><span className="cmd-teclas">{a.teclas.map((t) => <kbd key={t}>{t}</kbd>)}</span>{a.acao}</li>
            ))}
          </ul>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
