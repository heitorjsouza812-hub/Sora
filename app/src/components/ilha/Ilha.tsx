// Ilha da Sora (adaptação do Coucou): pílula preta no topo com a Sora e os bots trabalhando.
// Etapa 5 — "Ilha só fora do app": esta janela React só existe dentro da janela dedicada "ilha" do
// app de desktop (Tauri mostra/oculta essa janela nativa pelo foco da "main", ver src-tauri/src/lib.rs).
// Dentro do app principal e no navegador este componente nunca desenha nada (`desktop` não vem true).
// FSM: oculta → espiando → compacta → expandida. Aberta/vista vêm do store ilhaUi (comandos e atalhos
// de fora também abrem a ilha).
import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as KE, type PointerEvent as PE, type ReactNode } from 'react';
import { SoraOrb } from '../mascot';
import { definirIlhaPrefs, filtrarBonecos, useIlha, useIlhaPrefs, type BonecoIlha, type VisaoIlha } from './ilhaEstado';
import { abrirIlha, fecharIlha, useIlhaUi } from './ilhaUi';
import { VisaoGeral } from './VisaoGeral';
import { DetalheAgente } from './DetalheAgente';
import { tocar } from './som';
import { usePresenca } from './usePresenca';
import { aoMouseIlha, abrirNoApp, type Retangulo } from '../../desktop/ponte';
import './ilha.css';

export type ModoIlha = 'oculta' | 'espiando' | 'compacta' | 'expandida';

const HOVER_ABRIR = 250;
const HOVER_FECHAR = 400;
const MAX_BONECOS = 5;

const mouseFino = () => typeof window !== 'undefined' && window.matchMedia?.('(hover: hover) and (pointer: fine)').matches;

function Icone({ d }: { d: string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>;
}

/** Pílula compacta: Sora pequena + texto curto + bonecos (bots ativos, já filtrados pelos ocultos). */
function Compacta({ v, ativos, trabalhando, pulsoExtra, olhar }: {
  v: VisaoIlha; ativos: BonecoIlha[]; trabalhando: number; pulsoExtra: number; olhar: { x: number; y: number } | null;
}) {
  const presentes = usePresenca(ativos.slice(0, MAX_BONECOS));
  const extras = ativos.length - MAX_BONECOS;
  const orbDaSora = v.precisaDeVoce.length > 0 ? 'listening' : trabalhando > 0 ? 'coordinating' : 'idle';
  const texto = v.precisaDeVoce.length > 0 ? `${v.precisaDeVoce.length} precisa${v.precisaDeVoce.length === 1 ? '' : 'm'} de você`
    : trabalhando > 0 ? <><span key={trabalhando} className="ilha-num">{trabalhando}</span> trabalhando</>
    : 'Tudo tranquilo';
  return (
    <>
      <span className="ilha-compacta-sora">
        <SoraOrb size={24} color={v.sora.cor} state={orbDaSora} pulseKey={pulsoExtra} lookAt={olhar} glow={false} decorative seed={11} />
      </span>
      <span className="ilha-compacta-texto">{texto}</span>
      {presentes.length > 0 && (
        <span className="ilha-bonecos" aria-hidden="true">
          {presentes.map(({ item: a, saindo }, i) => (
            <span key={a.id} className={`ilha-boneco-mini${saindo ? ' ilha-saindo' : ''}`} style={{ '--i': i, '--agente': a.cor } as CSSProperties}>
              <SoraOrb size={18} color={a.cor} state={a.orb} glow={false} decorative seed={20 + i} />
            </span>
          ))}
          {extras > 0 && <span className="ilha-bonecos-mais">+{extras}</span>}
        </span>
      )}
    </>
  );
}

interface CabecalhoProps {
  trabalhando: number;
  som: boolean;
  onFechar: () => void;
  onAbrirSora: () => void;
}

function Cabecalho({ trabalhando, som, onFechar, onAbrirSora }: CabecalhoProps) {
  return (
    <div className="ilha-cabecalho">
      <div className="ilha-abas" role="toolbar" aria-label="Navegação da ilha">
        <button type="button" className="ilha-icone" aria-label="Início" aria-pressed title="Início" onClick={() => abrirIlha('inicio')}>
          <Icone d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z" />
        </button>
        <button type="button" className="ilha-icone" aria-label="Abrir a Sora" title="Abrir a Sora" onClick={onAbrirSora}>
          <Icone d="M5 5h14v10H9l-4 4z" />
        </button>
      </div>
      <div className="ilha-status">
        {trabalhando > 0 && <span className="ilha-contador" role="status"><span key={trabalhando} className="ilha-num">{trabalhando}</span> trabalhando</span>}
        <button type="button" className="ilha-icone" aria-label={som ? 'Desligar sons' : 'Ligar sons'} aria-pressed={som} title={som ? 'Som ligado' : 'Som desligado'}
          onClick={() => definirIlhaPrefs({ som: !som })}>
          {som ? <Icone d="M4 9v6h4l5 4V5L8 9zm12 0a4 4 0 0 1 0 6m2-9a8 8 0 0 1 0 12" /> : <Icone d="M4 9v6h4l5 4V5L8 9zm12 1 4 4m0-4-4 4" />}
        </button>
        <button type="button" className="ilha-icone" aria-label="Fechar ilha" title="Fechar (Esc)" onClick={onFechar}>
          <Icone d="m6 6 12 12M18 6 6 18" />
        </button>
      </div>
    </div>
  );
}

export interface IlhaProps {
  /** só true na janela dedicada "ilha" do app de desktop (ver IlhaDesktop.tsx). Fora dela (app
   *  principal ou navegador) o componente não desenha nada — a ilha é "só fora do app" (etapa 5). */
  desktop?: boolean;
  /** recebe o retângulo desenhado (px relativos à janela) para os cliques atravessarem fora dele */
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

/** Brilho que corre na borda, nas cores dos bots trabalhando. */
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

  // bots ativos (trabalhando ou precisando de você), sem os escondidos pelo botão "olho"
  const ativos = v.bonecos.filter(a => a.estado !== 'livre' && !prefs.ocultos.includes(a.id));
  const bonecosDoInicio = filtrarBonecos(v.bonecos, prefs);
  const trabalhando = ativos.filter(a => a.estado === 'trabalhando').length;
  const coresTrabalhando = ativos.filter(a => a.estado === 'trabalhando').map(a => a.cor);

  // ---------- FSM ----------
  // Etapa 5: a ilha só existe mesmo na janela dedicada do desktop; fora dela não há nada a desenhar
  // (o app principal e o navegador nunca recebem `desktop=true`). `prefs.visivel` ainda controla se
  // o usuário quer a ilha ligada — a janela nativa mesmo assim só aparece fora do app (ver lib.rs).
  const oculta = !desktop || !prefs.visivel;
  const aberta = ui.aberta && !oculta;
  const modo: ModoIlha = oculta ? 'oculta'
    : aberta ? 'expandida'
    : prefs.esconderOciosa && ativos.length === 0 && !espiandoHover ? 'espiando'
    : 'compacta';
  const painelVisivel = modo === 'expandida';

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
    if (!ui.aberta) abrirIlha(ui.vista, ui.agenteId ?? undefined);
  }, [ui.aberta, ui.vista, ui.agenteId]);

  // pedidos externos (comando, atalho Ctrl/⌘+Shift+S) fixam a ilha aberta
  const ultimoPedido = useRef(ui.pedido);
  useEffect(() => {
    if (ui.pedido === ultimoPedido.current) return;
    ultimoPedido.current = ui.pedido;
    porHover.current = false;
  }, [ui.pedido]);

  // ---------- pedido novo "precisa de você": abre sozinha no Início, uma vez por pedido ----------
  const pedidosVistos = useRef(new Set<string>());
  const primeiraLista = useRef(true);
  useEffect(() => {
    const novo = v.precisaDeVoce.find(p => !pedidosVistos.current.has(p.id));
    v.precisaDeVoce.forEach(p => pedidosVistos.current.add(p.id));
    // a primeira lista carregada (ex.: app recém-aberto) não é "nova": só pedidos que chegam depois
    if (primeiraLista.current) { primeiraLista.current = false; return; }
    if (oculta || !novo) return;
    porHover.current = false;
    abrirIlha('inicio');
    if (prefs.som) tocar('pronto');
  }, [v.precisaDeVoce, oculta, prefs.som]);

  // ---------- pulso + som quando um bot termina de trabalhar ----------
  const idsTrabalhando = new Set(v.bonecos.filter(a => a.estado === 'trabalhando').map(a => a.id));
  const anterior = useRef(idsTrabalhando);
  useEffect(() => {
    const terminou = [...anterior.current].some(id => !idsTrabalhando.has(id));
    if (terminou) {
      setPulsoExtra(p => p + 1);
      if (prefs.som) tocar('concluiu');
    }
    anterior.current = idsTrabalhando;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v.bonecos.map(a => `${a.id}:${a.estado}`).join(',')]);

  // ---------- Esc, clique fora, janela perdeu o foco (desktop) ----------
  useEffect(() => {
    const tecla = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape' && ui.aberta) {
        if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
        focarPilula.current = true;
        fechar();
      }
    };
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [ui.aberta, fechar]);

  useEffect(() => {
    if (!aberta) return;
    const fora = (ev: PointerEvent) => {
      const alvo = ev.target as Node | null;
      if (alvo && raiz.current?.contains(alvo)) return;
      if (alvo instanceof Element && alvo.closest('[data-ilha-portal]')) return;
      fechar();
    };
    document.addEventListener('pointerdown', fora);
    // no desktop o clique fora vai para outro programa: a janela da ilha só perde o foco
    window.addEventListener('blur', fechar);
    return () => { document.removeEventListener('pointerdown', fora); window.removeEventListener('blur', fechar); };
  }, [aberta, fechar]);

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
    if (modo !== 'compacta' || !mouseFino()) return;
    let quadro = 0;
    const mover = (ev: PointerEvent) => {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(() => olharPara(ev.clientX, ev.clientY));
    };
    window.addEventListener('pointermove', mover);
    return () => { window.removeEventListener('pointermove', mover); cancelAnimationFrame(quadro); };
  }, [modo, olharPara]);

  // ---------- hover ----------
  const entrarMouse = () => {
    window.clearTimeout(timerFechar.current);
    if (modo === 'espiando') { setEspiandoHover(true); return; }
    if (ui.aberta) return;
    window.clearTimeout(timerAbrir.current);
    timerAbrir.current = window.setTimeout(() => {
      porHover.current = true;
      abrirIlha(ui.vista, ui.agenteId ?? undefined, { porHover: true });
    }, HOVER_ABRIR);
  };
  const sairMouse = () => {
    window.clearTimeout(timerAbrir.current);
    timerFechar.current = window.setTimeout(() => {
      setEspiandoHover(false);
      if (porHover.current && !raiz.current?.contains(document.activeElement)) fechar();
    }, HOVER_FECHAR);
  };
  const entrar = (ev: PE) => { if (ev.pointerType === 'mouse') entrarMouse(); };
  const sair = (ev: PE) => { if (ev.pointerType === 'mouse') sairMouse(); };

  // o Rust manda {dentro,x,y} ~30×/s (click-through); os handlers mais recentes ficam num ref
  const maos = useRef({ entrarMouse, sairMouse, olharPara, modo });
  useEffect(() => { maos.current = { entrarMouse, sairMouse, olharPara, modo }; });
  useEffect(() => {
    let dentro = false;
    return aoMouseIlha(m => {
      if (m.dentro !== dentro) {
        dentro = m.dentro;
        if (dentro) maos.current.entrarMouse(); else maos.current.sairMouse();
      }
      if (maos.current.modo === 'compacta') maos.current.olharPara(m.x, m.y);
    });
  }, []);

  // ---------- retângulo visível para o click-through ----------
  const alvo = modo === 'oculta' ? { w: 0, h: 0 }
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

  const abrirSora = () => { void abrirNoApp('/'); fechar(); };

  if (modo === 'oculta') return null;

  const conteudo: ReactNode = (
    ui.vista === 'agente' && ui.agenteId ? <DetalheAgente agenteId={ui.agenteId} onVoltar={() => abrirIlha('inicio')} />
    : <VisaoGeral v={{ ...v, bonecos: bonecosDoInicio }} onAgente={id => abrirIlha('agente', id)} />
  );

  const estilo = {
    '--ilha-cor': coresTrabalhando[0] ?? v.sora.cor,
    '--ilha-halo': gradienteHalo(coresTrabalhando),
  } as CSSProperties;

  return (
    <div className="ilha-ancora" data-modo={modo} data-desktop={desktop || undefined}>
      <div ref={raiz} className="ilha" data-modo={modo} onPointerEnter={entrar} onPointerLeave={sair} style={estilo}
        data-trabalhando={coresTrabalhando.length > 0 || undefined}
        data-respira={(v.precisaDeVoce.length > 0 && modo === 'compacta') || undefined}>
        {modo === 'espiando' ? (
          <button type="button" className="ilha-espiando" aria-label="Mostrar a Ilha da Sora" onClick={() => setEspiandoHover(true)} onFocus={() => setEspiandoHover(true)} />
        ) : (
          <div className="ilha-casca" style={{ width: alvo.w, height: alvo.h }}>
            {painelVisivel ? (
              <div ref={medir} className="ilha-painel" role="dialog" aria-modal="false" aria-label="Ilha da Sora"
                onPointerDown={() => { porHover.current = false; }}>
                <Cabecalho trabalhando={trabalhando} som={prefs.som} onFechar={fechar} onAbrirSora={abrirSora} />
                <div key={ui.vista} className="ilha-corpo">{conteudo}</div>
              </div>
            ) : (
              <div ref={refPilula} key="pilula" className="ilha-pilula" role="button" tabIndex={0} aria-expanded={false}
                aria-label={`Ilha da Sora: ${v.precisaDeVoce.length > 0 ? `${v.precisaDeVoce.length} pedidos esperando você` : `${trabalhando} trabalhando`}. Abrir`}
                onClick={abrirFixada} onKeyDown={teclaPilula}>
                <Compacta v={v} ativos={ativos} trabalhando={trabalhando} pulsoExtra={pulsoExtra} olhar={modo === 'compacta' ? olhar : null} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default Ilha;
