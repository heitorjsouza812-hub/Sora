// Ilha da Sora (adaptação do Coucou): pílula preta no topo com a Sora e os agentes rodando.
// FSM: oculta → espiando → compacta → expandida · alerta (equipe pronta abre sozinha na Aprovação).
// Aberta/vista/agente vêm do store ilhaUi (comandos e atalhos de fora também abrem a ilha).
import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as KE, type PointerEvent as PE, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { useProjetos } from '../../state/projetos';
import { definirIlhaPrefs, useIlha, useIlhaPrefs, type VisaoIlha } from './ilhaEstado';
import { abrirIlha, alternarIlha, fecharIlha, useIlhaUi } from './ilhaUi';
import { VisaoGeral } from './VisaoGeral';
import { Aprovacao } from './Aprovacao';
import { SeletorProjeto } from './SeletorProjeto';
import { DetalheAgente } from './DetalheAgente';
import { tocar } from './som';
import { useJanelaDestacada } from './useJanelaDestacada';
import './ilha.css';

export type ModoIlha = 'oculta' | 'espiando' | 'compacta' | 'expandida' | 'alerta';

const HOVER_ABRIR = 250;
const HOVER_FECHAR = 400;
const MAX_BONECOS = 5;
const CHAVE_ALERTAS = 'sora.ilha.alertas.v1';

/** Alertas já mostrados (uma vez por projeto/versão), lembrados entre recargas. */
function alertasVistos(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(CHAVE_ALERTAS) ?? '[]') as string[]); } catch { return new Set(); }
}
function marcarAlerta(chave: string) {
  const s = alertasVistos();
  s.add(chave);
  try { localStorage.setItem(CHAVE_ALERTAS, JSON.stringify([...s].slice(-50))); } catch { /* ignora */ }
}

const mouseFino = () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches;

function Icone({ d }: { d: string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>;
}

/** Pílula compacta: Sora pequena + texto curto + bonecos. */
function Compacta({ v, pulsoExtra, olhar }: { v: VisaoIlha; pulsoExtra: number; olhar: { x: number; y: number } | null }) {
  const texto = v.trabalhando > 0 && v.sora.orb !== 'thinking' ? `${v.trabalhando} trabalhando` : v.sora.rotulo;
  const extras = v.agentes.length - MAX_BONECOS;
  return (
    <>
      <span className="ilha-compacta-sora">
        <SoraOrb size={24} color={v.sora.cor} state={v.sora.orb} pulseKey={v.sora.pulso + pulsoExtra} lookAt={olhar} glow={false} decorative seed={11} />
      </span>
      <span className="ilha-compacta-texto">{texto}</span>
      {v.agentes.length > 0 && (
        <span className="ilha-bonecos" aria-hidden="true">
          {v.agentes.slice(0, MAX_BONECOS).map((a, i) => (
            <SoraOrb key={a.id} size={18} color={a.cor} state={a.orb} movimento={a.movimento} glow={false} decorative seed={20 + i} />
          ))}
          {extras > 0 && <span className="ilha-bonecos-mais">+{extras}</span>}
        </span>
      )}
    </>
  );
}

interface CabecalhoProps {
  v: VisaoIlha;
  vista: string;
  som: boolean;
  podeDestacar: boolean;
  destacada: boolean;
  onDestacar: () => void;
  onFechar: () => void;
  onAbrirChat: () => void;
}

function Cabecalho({ v, vista, som, podeDestacar, destacada, onDestacar, onFechar, onAbrirChat }: CabecalhoProps) {
  return (
    <div className="ilha-cabecalho">
      <div className="ilha-abas" role="toolbar" aria-label="Navegação da ilha">
        <button type="button" className="ilha-icone" aria-label="Início" aria-pressed={vista === 'inicio'} title="Início" onClick={() => abrirIlha('inicio')}>
          <Icone d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z" />
        </button>
        <button type="button" className="ilha-aba-projeto" aria-pressed={vista === 'projeto'} aria-haspopup="listbox"
          onClick={() => abrirIlha(vista === 'projeto' ? 'inicio' : 'projeto')}>
          <span className="ilha-aba-projeto-titulo">{v.projeto?.titulo ?? 'Projeto'}</span>
          <Icone d="m7 10 5 5 5-5" />
        </button>
        <button type="button" className="ilha-icone" aria-label="Abrir chat do projeto" title="Abrir chat" disabled={!v.projeto} onClick={onAbrirChat}>
          <Icone d="M5 5h14v10H9l-4 4z" />
        </button>
      </div>
      <div className="ilha-status">
        {v.trabalhando > 0 && <span className="ilha-contador" role="status">{v.trabalhando} trabalhando</span>}
        <button type="button" className="ilha-icone" aria-label={som ? 'Desligar sons' : 'Ligar sons'} aria-pressed={som} title={som ? 'Som ligado' : 'Som desligado'}
          onClick={() => definirIlhaPrefs({ som: !som })}>
          {som ? <Icone d="M4 9v6h4l5 4V5L8 9zm12 0a4 4 0 0 1 0 6m2-9a8 8 0 0 1 0 12" /> : <Icone d="M4 9v6h4l5 4V5L8 9zm12 1 4 4m0-4-4 4" />}
        </button>
        {podeDestacar && (
          <button type="button" className="ilha-icone" aria-label={destacada ? 'Voltar a ilha para o app' : 'Destacar em janela'} aria-pressed={destacada}
            title={destacada ? 'Voltar para o app' : 'Destacar'} onClick={onDestacar}>
            <Icone d="M9 5H5v14h14v-4M13 5h6v6m0-6-8 8" />
          </button>
        )}
        <button type="button" className="ilha-icone" aria-label="Fechar ilha" title="Fechar (Esc)" onClick={onFechar}>
          <Icone d="m6 6 12 12M18 6 6 18" />
        </button>
      </div>
    </div>
  );
}

export function Ilha() {
  const v = useIlha();
  const prefs = useIlhaPrefs();
  const ui = useIlhaUi();
  const e = useProjetos();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const janela = useJanelaDestacada();

  const raiz = useRef<HTMLDivElement>(null);
  const timerAbrir = useRef<number | undefined>(undefined);
  const timerFechar = useRef<number | undefined>(undefined);
  /** aberta por hover (fecha ao sair o mouse) ou fixada (clique, teclado, comando, alerta) */
  const porHover = useRef(false);
  const [espiandoHover, setEspiandoHover] = useState(false);
  const [pulsoExtra, setPulsoExtra] = useState(0);
  const [olhar, setOlhar] = useState<{ x: number; y: number } | null>(null);

  // ---------- FSM ----------
  const semProjetoNaHome = pathname === '/' && !e.projetoAtivoId && v.rodando === 0;
  const oculta = !prefs.visivel || v.projetos.length === 0 || semProjetoNaHome;
  const destacada = janela.aberta && !!janela.container;
  const aberta = ui.aberta && !oculta;
  const modo: ModoIlha = oculta ? 'oculta'
    : aberta && !destacada ? (ui.vista === 'aprovacao' && v.alerta ? 'alerta' : 'expandida')
    : prefs.esconderOciosa && v.rodando === 0 && !espiandoHover ? 'espiando'
    : 'compacta';

  const limparTimers = () => { window.clearTimeout(timerAbrir.current); window.clearTimeout(timerFechar.current); };
  useEffect(() => limparTimers, []);

  const fechar = useCallback(() => {
    limparTimers();
    porHover.current = false;
    fecharIlha();
  }, []);

  const abrirFixada = useCallback(() => {
    limparTimers();
    porHover.current = false;
    if (!ui.aberta) abrirIlha(ui.vista === 'aprovacao' && !v.alerta ? 'inicio' : ui.vista, ui.agenteId ?? undefined);
  }, [ui.aberta, ui.vista, ui.agenteId, v.alerta]);

  // pedidos externos (comando, atalho) fixam a ilha aberta
  const ultimoPedido = useRef(ui.pedido);
  useEffect(() => {
    if (ui.pedido === ultimoPedido.current) return;
    ultimoPedido.current = ui.pedido;
    porHover.current = false;
  }, [ui.pedido]);

  // vista Aprovação sem alerta (ex.: aprovou em outra tela) volta ao Início
  useEffect(() => {
    if (ui.aberta && ui.vista === 'aprovacao' && !v.alerta) abrirIlha('inicio');
  }, [ui.aberta, ui.vista, v.alerta]);

  // ---------- alerta: equipe pronta → abre sozinha na Aprovação (uma vez por projeto/versão) ----------
  const alertaChave = v.alerta ? `${v.alerta.projetoId}:${e.projetos.find(p => p.id === v.alerta!.projetoId)?.versao ?? 1}` : null;
  useEffect(() => {
    if (!alertaChave || oculta) return;
    if (alertasVistos().has(alertaChave)) return;
    marcarAlerta(alertaChave);
    porHover.current = false;
    abrirIlha('aprovacao');
    if (prefs.som) tocar('pronto');
  }, [alertaChave, oculta, prefs.som]);

  // ---------- pulso + som quando um agente conclui ----------
  const concluidos = v.agentes.filter(a => a.status === 'concluido').length;
  const projetoMostrado = v.projeto?.id ?? null;
  const anterior = useRef({ projeto: projetoMostrado, n: concluidos });
  useEffect(() => {
    const a = anterior.current;
    if (a.projeto === projetoMostrado && concluidos > a.n) {
      setPulsoExtra(p => p + 1);
      if (prefs.som) tocar('concluiu');
    }
    anterior.current = { projeto: projetoMostrado, n: concluidos };
  }, [concluidos, projetoMostrado, prefs.som]);

  // ---------- Esc, clique fora, Ctrl/⌘+Shift+S ----------
  useEffect(() => {
    const tecla = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && ev.key.toLowerCase() === 's') {
        ev.preventDefault();
        porHover.current = false;
        alternarIlha();
        return;
      }
      if (ev.key === 'Escape' && ui.aberta && !destacada) {
        // não fecha se um diálogo (modal) estiver por cima
        if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
        fechar();
        raiz.current?.querySelector<HTMLElement>('.ilha-pilula')?.focus();
      }
    };
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [ui.aberta, destacada, fechar]);

  useEffect(() => {
    if (!aberta || destacada) return;
    const fora = (ev: PointerEvent) => {
      const alvo = ev.target as Node | null;
      if (alvo && raiz.current?.contains(alvo)) return;
      // menus/popovers que a ilha abre em portal ficam fora da raiz; não fechar por eles
      if (alvo instanceof Element && alvo.closest('[data-ilha-portal]')) return;
      fechar();
    };
    document.addEventListener('pointerdown', fora);
    return () => document.removeEventListener('pointerdown', fora);
  }, [aberta, destacada, fechar]);

  // ---------- olhar: a Sora da pílula segue o mouse perto do topo ----------
  useEffect(() => {
    if (modo !== 'compacta' || !mouseFino()) return;
    let quadro = 0;
    const mover = (ev: PointerEvent) => {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(() => {
        const el = raiz.current?.querySelector('.ilha-compacta-sora');
        if (!el || ev.clientY > 160) { setOlhar(null); return; }
        const r = el.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const x = Math.max(-1, Math.min(1, (ev.clientX - cx) / 400));
        const y = Math.max(-1, Math.min(1, (ev.clientY - cy) / 120));
        setOlhar(o => o && Math.abs(o.x - x) < 0.05 && Math.abs(o.y - y) < 0.05 ? o : { x, y });
      });
    };
    window.addEventListener('pointermove', mover);
    return () => { window.removeEventListener('pointermove', mover); cancelAnimationFrame(quadro); };
  }, [modo]);

  // ---------- hover (só mouse) ----------
  const entrar = (ev: PE) => {
    if (ev.pointerType !== 'mouse') return;
    window.clearTimeout(timerFechar.current);
    if (modo === 'espiando') { setEspiandoHover(true); return; }
    if (ui.aberta) return;
    window.clearTimeout(timerAbrir.current);
    timerAbrir.current = window.setTimeout(() => {
      porHover.current = true;
      abrirIlha(ui.vista === 'aprovacao' && !v.alerta ? 'inicio' : ui.vista, ui.agenteId ?? undefined);
    }, HOVER_ABRIR);
  };
  const sair = (ev: PE) => {
    if (ev.pointerType !== 'mouse') return;
    window.clearTimeout(timerAbrir.current);
    timerFechar.current = window.setTimeout(() => {
      setEspiandoHover(false);
      // não fecha se o foco está dentro (ex.: digitando para um agente)
      if (porHover.current && !raiz.current?.contains(document.activeElement)) fechar();
    }, HOVER_FECHAR);
  };

  const teclaPilula = (ev: KE) => {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrirFixada(); }
  };

  // aberta por hover: o clique só fixa; fixada: o clique fecha
  const cliquePilula = () => {
    if (!ui.aberta || destacada) { abrirFixada(); return; }
    if (porHover.current) { porHover.current = false; return; }
    fechar();
  };

  const abrirChat = () => {
    if (!v.projeto) return;
    navigate(`/projeto/${v.projeto.id}`);
    fechar();
  };

  const destacar = async () => {
    if (destacada) { janela.fechar(); return; }
    try {
      await janela.abrir();
      porHover.current = false;
      if (!ui.aberta) abrirIlha(ui.vista, ui.agenteId ?? undefined);
    } catch { /* sem suporte ou bloqueado: segue no app */ }
  };

  if (modo === 'oculta' && !destacada) return null;

  const vista = ui.vista === 'aprovacao' && !v.alerta ? 'inicio' : ui.vista;
  const conteudo: ReactNode = (
    vista === 'projeto' ? <SeletorProjeto onEscolhido={() => abrirIlha('inicio')} />
    : vista === 'agente' && ui.agenteId ? <DetalheAgente agenteId={ui.agenteId} onVoltar={() => abrirIlha('inicio')} />
    : vista === 'aprovacao' && v.alerta ? <Aprovacao alerta={v.alerta} onFeito={fechar} />
    : <VisaoGeral v={v} onAgente={id => abrirIlha('agente', id)} />
  );

  const painel = (
    <div className={`ilha-painel${modo === 'alerta' ? ' ilha-painel--alerta' : ''}`} role="dialog" aria-modal="false" aria-label="Ilha da Sora">
      <Cabecalho v={v} vista={vista} som={prefs.som} podeDestacar={janela.suportado} destacada={destacada}
        onDestacar={() => { void destacar(); }} onFechar={destacada ? () => janela.fechar() : fechar} onAbrirChat={abrirChat} />
      <div className="ilha-corpo">{conteudo}</div>
    </div>
  );

  return (
    <>
      {modo !== 'oculta' && (
        <div className="ilha-ancora" data-modo={modo}>
          <div ref={raiz} className="ilha" data-modo={modo} onPointerEnter={entrar} onPointerLeave={sair}
            style={{ '--ilha-cor': v.agentes.find(a => a.status === 'trabalhando')?.cor ?? v.sora.cor } as CSSProperties}>
            {modo === 'espiando' ? (
              <button type="button" className="ilha-espiando" aria-label="Mostrar a Ilha da Sora" onClick={() => setEspiandoHover(true)} onFocus={() => setEspiandoHover(true)} />
            ) : (
              <div className="ilha-pilula" role="button" tabIndex={0} aria-expanded={modo === 'expandida' || modo === 'alerta'}
                aria-label={`Ilha da Sora: ${v.projeto?.titulo ?? 'sem projeto'}. ${v.sora.rotulo}. Abrir`}
                onClick={cliquePilula}
                onKeyDown={teclaPilula}>
                <Compacta v={v} pulsoExtra={pulsoExtra} olhar={modo === 'compacta' ? olhar : null} />
              </div>
            )}
            {(modo === 'expandida' || modo === 'alerta') && painel}
          </div>
        </div>
      )}
      {destacada && janela.container && createPortal(<div className="ilha-destacada">{painel}</div>, janela.container)}
    </>
  );
}

export default Ilha;
