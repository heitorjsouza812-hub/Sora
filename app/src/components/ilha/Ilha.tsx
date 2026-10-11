// Ilha da Sora (adaptação do Coucou): pílula preta no topo com a Sora e os agentes rodando.
// FSM: oculta → espiando → compacta → expandida · alerta (equipe pronta abre sozinha na Aprovação).
// Aberta/vista/agente vêm do store ilhaUi (comandos e atalhos de fora também abrem a ilha).
import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as KE, type PointerEvent as PE, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { useProjetos } from '../../state/projetos';
import { definirIlhaPrefs, filtrarAgentes, useIlha, useIlhaPrefs, type AgenteIlha, type VisaoIlha } from './ilhaEstado';
import { abrirIlha, fecharIlha, useIlhaUi } from './ilhaUi';
import { VisaoGeral } from './VisaoGeral';
import { Aprovacao } from './Aprovacao';
import { SeletorProjeto } from './SeletorProjeto';
import { DetalheAgente } from './DetalheAgente';
import { tocar } from './som';
import { useJanelaDestacada } from './useJanelaDestacada';
import { AnelConclusao } from './animacao';
import { usePresenca } from './usePresenca';
import { aoMouseIlha, janelaAtual, noDesktop, type Retangulo } from '../../desktop/ponte';
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

/** Pílula compacta: Sora pequena + texto curto + bonecos (já filtrados pelas preferências). */
function Compacta({ v, bonecos, trabalhando, pulsoExtra, olhar }: {
  v: VisaoIlha; bonecos: AgenteIlha[]; trabalhando: number; pulsoExtra: number; olhar: { x: number; y: number } | null;
}) {
  const presentes = usePresenca(bonecos.slice(0, MAX_BONECOS));
  const extras = bonecos.length - MAX_BONECOS;
  return (
    <>
      <span className="ilha-compacta-sora">
        <SoraOrb size={24} color={v.sora.cor} state={v.sora.orb} pulseKey={v.sora.pulso + pulsoExtra} lookAt={olhar} glow={false} decorative seed={11} />
      </span>
      <span className="ilha-compacta-texto">
        {trabalhando > 0 && v.sora.orb !== 'thinking'
          ? <><span key={trabalhando} className="ilha-num">{trabalhando}</span> trabalhando</>
          : v.sora.rotulo}
      </span>
      {presentes.length > 0 && (
        <span className="ilha-bonecos" aria-hidden="true">
          {presentes.map(({ item: a, saindo }, i) => (
            <span key={a.id} className={`ilha-boneco-mini${saindo ? ' ilha-saindo' : ''}`} style={{ '--i': i, '--agente': a.cor } as CSSProperties}>
              <SoraOrb size={18} color={a.cor} state={a.orb} movimento={a.movimento} glow={false} decorative seed={20 + i} />
              <AnelConclusao agente={a} />
            </span>
          ))}
          {extras > 0 && <span className="ilha-bonecos-mais">+{extras}</span>}
        </span>
      )}
    </>
  );
}

interface CabecalhoProps {
  v: VisaoIlha;
  trabalhando: number;
  vista: string;
  som: boolean;
  podeDestacar: boolean;
  destacada: boolean;
  onDestacar: () => void;
  onFechar: () => void;
  onAbrirChat: () => void;
}

function Cabecalho({ v, trabalhando, vista, som, podeDestacar, destacada, onDestacar, onFechar, onAbrirChat }: CabecalhoProps) {
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
        {trabalhando > 0 && <span className="ilha-contador" role="status"><span key={trabalhando} className="ilha-num">{trabalhando}</span> trabalhando</span>}
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

export interface IlhaProps {
  /** janela própria do app de desktop: pílula colada no topo da tela e mouse vindo do Rust (click-through) */
  desktop?: boolean;
  /** desktop: recebe o retângulo desenhado (px relativos à janela) para os cliques atravessarem fora dele */
  onRetangulo?: (r: Retangulo) => void;
}

const PADRAO_COMPACTA = { w: 300, h: 40 };
const PADRAO_PAINEL = { w: 720, h: 300 };
const ESPIANDO = { w: 120, h: 6 };
const MARGEM_HALO = 6;
const DURACAO_MOLA = 460;

/** Mede o conteúdo ativo (pílula ou painel); a casca preta anima até esse tamanho. */
function useTamanho() {
  const [tam, setTam] = useState<{ w: number; h: number } | null>(null);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: HTMLElement | null) => {
    ro.current?.disconnect();
    ro.current = null;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const medir = () => {
      const w = el.offsetWidth, h = el.offsetHeight;
      setTam(t => (t && t.w === w && t.h === h ? t : { w, h }));
    };
    ro.current = new ResizeObserver(medir);
    ro.current.observe(el);
  }, []);
  return [ref, tam] as const;
}

/** Brilho que corre na borda, nas cores dos agentes trabalhando. */
function gradienteHalo(cores: string[]) {
  if (!cores.length) return undefined;
  const passo = 360 / cores.length;
  const partes = cores.flatMap((c, i) => [`transparent ${i * passo}deg`, `${c} ${i * passo + passo / 2}deg`]);
  return `conic-gradient(from var(--ilha-ang), ${partes.join(', ')}, transparent 360deg)`;
}

export function Ilha({ desktop = false, onRetangulo }: IlhaProps) {
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
  const focarPilula = useRef(false);
  const [espiandoHover, setEspiandoHover] = useState(false);
  const [pulsoExtra, setPulsoExtra] = useState(0);
  const [olhar, setOlhar] = useState<{ x: number; y: number } | null>(null);
  const [medir, tamanho] = useTamanho();

  /** mouse vem do Rust (com click-through o DOM nem sempre recebe pointerleave) */
  const usarPonte = desktop && noDesktop;
  /** na janela principal do desktop a ilha de verdade está no topo da tela; sons só tocam lá */
  const naJanelaMain = !desktop && janelaAtual === 'main';
  const tocaSom = prefs.som && !naJanelaMain;

  // filtro (Todos · Trabalhando · Concluídos) e bonecos escondidos; a Sora sempre aparece
  const bonecos = filtrarAgentes(v.agentes, prefs);
  const trabalhando = Math.max(0, v.trabalhando - v.agentes.filter(a => a.status === 'trabalhando' && prefs.ocultos.includes(a.id)).length);
  const coresTrabalhando = bonecos.filter(a => a.status === 'trabalhando').map(a => a.cor);

  // ---------- FSM ----------
  const semProjetoNaHome = !desktop && pathname === '/' && !e.projetoAtivoId && v.rodando === 0;
  const oculta = (naJanelaMain && !prefs.ilhaNoApp) || !prefs.visivel || v.projetos.length === 0 || semProjetoNaHome;
  const destacada = janela.aberta && !!janela.container;
  const aberta = ui.aberta && !oculta;
  const modo: ModoIlha = oculta ? 'oculta'
    : aberta && !destacada ? (ui.vista === 'aprovacao' && v.alerta ? 'alerta' : 'expandida')
    : prefs.esconderOciosa && v.rodando === 0 && !espiandoHover ? 'espiando'
    : 'compacta';
  const painelVisivel = modo === 'expandida' || modo === 'alerta';

  const limparTimers = () => { window.clearTimeout(timerAbrir.current); window.clearTimeout(timerFechar.current); };
  useEffect(() => limparTimers, []);

  const fechar = useCallback(() => {
    limparTimers();
    porHover.current = false;
    fecharIlha();
  }, []);

  const vistaParaAbrir = ui.vista === 'aprovacao' && !v.alerta ? 'inicio' : ui.vista;
  const abrirFixada = useCallback(() => {
    limparTimers();
    porHover.current = false;
    if (!ui.aberta) abrirIlha(vistaParaAbrir, ui.agenteId ?? undefined);
  }, [ui.aberta, vistaParaAbrir, ui.agenteId]);

  // pedidos externos (comando, atalho Ctrl/⌘+Shift+S) fixam a ilha aberta
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
    if (tocaSom) tocar('pronto');
  }, [alertaChave, oculta, tocaSom]);

  // ---------- pulso + som quando um agente conclui ----------
  const concluidos = v.agentes.filter(a => a.status === 'concluido').length;
  const projetoMostrado = v.projeto?.id ?? null;
  const anterior = useRef({ projeto: projetoMostrado, n: concluidos });
  useEffect(() => {
    const a = anterior.current;
    if (a.projeto === projetoMostrado && concluidos > a.n) {
      setPulsoExtra(p => p + 1);
      if (tocaSom) tocar('concluiu');
    }
    anterior.current = { projeto: projetoMostrado, n: concluidos };
  }, [concluidos, projetoMostrado, tocaSom]);

  // ---------- Esc, clique fora, janela perdeu o foco (desktop) ----------
  useEffect(() => {
    const tecla = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape' && ui.aberta && !destacada) {
        // não fecha se um diálogo (modal) estiver por cima
        if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
        focarPilula.current = true;
        fechar();
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
    // no desktop o clique fora vai para outro programa: a janela da ilha só perde o foco
    if (desktop) window.addEventListener('blur', fechar);
    return () => { document.removeEventListener('pointerdown', fora); window.removeEventListener('blur', fechar); };
  }, [aberta, destacada, fechar, desktop]);

  // ---------- olhar: a Sora da pílula segue o mouse perto do topo ----------
  const olharPara = useCallback((cx: number, cy: number) => {
    const el = raiz.current?.querySelector('.ilha-compacta-sora');
    if (!el || cy > 160) { setOlhar(o => (o ? null : o)); return; }
    const r = el.getBoundingClientRect();
    const x = Math.max(-1, Math.min(1, (cx - (r.left + r.width / 2)) / 400));
    const y = Math.max(-1, Math.min(1, (cy - (r.top + r.height / 2)) / 120));
    setOlhar(o => (o && Math.abs(o.x - x) < 0.05 && Math.abs(o.y - y) < 0.05 ? o : { x, y }));
  }, []);

  useEffect(() => {
    if (usarPonte || modo !== 'compacta' || !mouseFino()) return;
    let quadro = 0;
    const mover = (ev: PointerEvent) => {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(() => olharPara(ev.clientX, ev.clientY));
    };
    window.addEventListener('pointermove', mover);
    return () => { window.removeEventListener('pointermove', mover); cancelAnimationFrame(quadro); };
  }, [modo, usarPonte, olharPara]);

  // ---------- hover ----------
  const entrarMouse = () => {
    window.clearTimeout(timerFechar.current);
    if (modo === 'espiando') { setEspiandoHover(true); return; }
    if (ui.aberta) return;
    window.clearTimeout(timerAbrir.current);
    timerAbrir.current = window.setTimeout(() => {
      porHover.current = true;
      abrirIlha(vistaParaAbrir, ui.agenteId ?? undefined);
    }, HOVER_ABRIR);
  };
  const sairMouse = () => {
    window.clearTimeout(timerAbrir.current);
    timerFechar.current = window.setTimeout(() => {
      setEspiandoHover(false);
      // não fecha se o foco está dentro (ex.: digitando para um agente)
      if (porHover.current && !raiz.current?.contains(document.activeElement)) fechar();
    }, HOVER_FECHAR);
  };
  const entrar = (ev: PE) => { if (ev.pointerType === 'mouse' && !usarPonte) entrarMouse(); };
  const sair = (ev: PE) => { if (ev.pointerType === 'mouse' && !usarPonte) sairMouse(); };

  // desktop: o Rust manda {dentro,x,y} ~30×/s; os handlers mais recentes ficam num ref
  const maos = useRef({ entrarMouse, sairMouse, olharPara, modo });
  useEffect(() => { maos.current = { entrarMouse, sairMouse, olharPara, modo }; });
  useEffect(() => {
    if (!usarPonte) return;
    let dentro = false;
    return aoMouseIlha(m => {
      if (m.dentro !== dentro) {
        dentro = m.dentro;
        if (dentro) maos.current.entrarMouse(); else maos.current.sairMouse();
      }
      if (maos.current.modo === 'compacta') maos.current.olharPara(m.x, m.y);
    });
  }, [usarPonte]);

  // ---------- desktop: retângulo visível para o click-through ----------
  const alvo = modo === 'oculta' && !destacada ? { w: 0, h: 0 }
    : modo === 'espiando' ? ESPIANDO
    : tamanho ?? (painelVisivel ? PADRAO_PAINEL : PADRAO_COMPACTA);
  const ultimoRet = useRef(0);
  useEffect(() => {
    if (!onRetangulo) return;
    const area = alvo.w * alvo.h;
    const informar = () => {
      ultimoRet.current = area;
      onRetangulo(area === 0 ? { x: 0, y: 0, w: 0, h: 0 } : {
        x: Math.round((window.innerWidth - alvo.w) / 2) - MARGEM_HALO, y: 0,
        w: Math.round(alvo.w) + MARGEM_HALO * 2, h: Math.round(alvo.h) + MARGEM_HALO,
      });
    };
    // crescendo: informa já; encolhendo: espera a mola terminar (senão corta a animação)
    if (area >= ultimoRet.current) { informar(); return; }
    const t = window.setTimeout(informar, DURACAO_MOLA);
    return () => window.clearTimeout(t);
  }, [onRetangulo, alvo.w, alvo.h]);

  const refPilula = useCallback((el: HTMLDivElement | null) => {
    medir(el);
    if (el && focarPilula.current) { focarPilula.current = false; el.focus(); }
  }, [medir]);

  const teclaPilula = (ev: KE) => {
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); abrirFixada(); }
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

  const painel = (medido: boolean) => (
    <div ref={medido ? medir : undefined} className={`ilha-painel${modo === 'alerta' ? ' ilha-painel--alerta' : ''}`}
      role="dialog" aria-modal="false" aria-label="Ilha da Sora"
      // qualquer interação com o painel aberto por hover o fixa (não fecha mais ao sair o mouse)
      onPointerDown={() => { porHover.current = false; }}>
      <Cabecalho v={v} trabalhando={trabalhando} vista={vista} som={prefs.som} podeDestacar={janela.suportado && !desktop} destacada={destacada}
        onDestacar={() => { void destacar(); }} onFechar={destacada ? () => janela.fechar() : fechar} onAbrirChat={abrirChat} />
      <div key={vista} className="ilha-corpo">{conteudo}</div>
    </div>
  );

  const estilo = {
    '--ilha-cor': coresTrabalhando[0] ?? v.sora.cor,
    '--ilha-halo': gradienteHalo(coresTrabalhando),
  } as CSSProperties;

  return (
    <>
      {modo !== 'oculta' && (
        <div className="ilha-ancora" data-modo={modo} data-desktop={desktop || undefined}>
          <div ref={raiz} className="ilha" data-modo={modo} onPointerEnter={entrar} onPointerLeave={sair} style={estilo}
            data-trabalhando={coresTrabalhando.length > 0 || undefined}
            data-respira={(!!v.alerta && modo === 'compacta') || undefined}>
            {modo === 'espiando' ? (
              <button type="button" className="ilha-espiando" aria-label="Mostrar a Ilha da Sora" onClick={() => setEspiandoHover(true)} onFocus={() => setEspiandoHover(true)} />
            ) : (
              <div className="ilha-casca" style={{ width: alvo.w, height: alvo.h }}>
                {painelVisivel ? painel(true) : (
                  <div ref={refPilula} key="pilula" className="ilha-pilula" role="button" tabIndex={0} aria-expanded={false}
                    aria-label={`Ilha da Sora: ${v.projeto?.titulo ?? 'sem projeto'}. ${v.sora.rotulo}. Abrir`}
                    onClick={abrirFixada} onKeyDown={teclaPilula}>
                    <Compacta v={v} bonecos={bonecos} trabalhando={trabalhando} pulsoExtra={pulsoExtra} olhar={modo === 'compacta' ? olhar : null} />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      {destacada && janela.container && createPortal(<div className="ilha-destacada">{painel(false)}</div>, janela.container)}
    </>
  );
}

export default Ilha;
