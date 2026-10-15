// Laboratório do mascote (agente "Prisma") — rota /lab/orb.
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';
import { SoraOrb, SoraThinking, type OrbState } from '../components/mascot';
import { OrbRenderer } from '../components/mascot/orbEngine';
import type { Movimento } from '../types';
import './orb-lab.css';

const ESTADOS: { id: OrbState; nome: string; desc: string }[] = [
  { id: 'arriving', nome: 'Chegando', desc: 'pontos se juntam, olhos abrem' },
  { id: 'idle', nome: 'Ocioso', desc: 'respira, gira devagar, pisca' },
  { id: 'listening', nome: 'Ouvindo', desc: 'superfície ondula, olha o campo' },
  { id: 'thinking', nome: 'Pensando', desc: 'espiral de luz, olhos semicerrados' },
  { id: 'coordinating', nome: 'Coordenando', desc: 'gira devagar' },
  { id: 'working', nome: 'Trabalhando', desc: 'movimento próprio do agente' },
  { id: 'done', nome: 'Pronto', desc: 'calma, pulso ao concluir' },
];

const AGENTES: { nome: string; cor: string; movimento: Movimento; verbo: string }[] = [
  { nome: 'Sora', cor: '#E2ECFF', movimento: 'gira', verbo: 'Coordenando' },
  { nome: 'Atlas', cor: '#56A8FF', movimento: 'vibracao', verbo: 'Pesquisando' },
  { nome: 'Luna', cor: '#AC80FF', movimento: 'espiral', verbo: 'Criando' },
  { nome: 'Nina', cor: '#46E8A8', movimento: 'ondas', verbo: 'Escrevendo' },
];

const TAMANHOS = [20, 28, 40, 64, 96, 160, 240, 320];

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return <section><h2 className="orb-lab-section-title">{titulo}</h2>{children}</section>;
}

function useFps() {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let raf = 0, n = 0, t0 = performance.now();
    const tick = (t: number) => {
      n++;
      if (t - t0 >= 1000) { setFps(Math.round(n * 1000 / (t - t0))); n = 0; t0 = t; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  return fps;
}

// /lab/orb?solo=240&state=thinking&color=%23AC80FF&mov=espiral[&t=10&rot=4.2][&glow=0]
// Um orb isolado em fundo preto, para QA e comparação lado a lado com a demo.
// Com `t` (e `rot`) o quadro é determinístico e estático.
const ESTADOS_VALIDOS: OrbState[] = ['arriving', 'idle', 'listening', 'thinking', 'coordinating', 'working', 'done'];
const MOVIMENTOS_VALIDOS: Movimento[] = ['gira', 'vibracao', 'espiral', 'ondas'];
const num = (v: string | null, min: number, max: number, padrao: number) => {
  const n = Number(v);
  return v !== null && Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : padrao;
};

function OrbSolo({ q }: { q: URLSearchParams }) {
  // parâmetros públicos validados: enums conhecidos, cor hex, tamanho limitado (evita canvas gigante)
  const size = Math.round(num(q.get('solo'), 16, 720, 240));
  const st = q.get('state') as OrbState;
  const state = ESTADOS_VALIDOS.includes(st) ? st : 'idle';
  const corQ = q.get('color') ?? '';
  const color = /^#[0-9a-f]{6}$/i.test(corQ) ? corQ : '#E2ECFF';
  const mv = q.get('mov') as Movimento;
  const movimento = MOVIMENTOS_VALIDOS.includes(mv) ? mv : 'gira';
  const glow = q.has('glow') ? q.get('glow') !== '0' : undefined;
  const t = q.has('t') ? String(num(q.get('t'), 0, 1e5, 0)) : null;
  const rot = num(q.get('rot'), -1e4, 1e4, 0);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (t === null) return;
    const r = new OrbRenderer(ref.current!, { size, color, state, movimento, lookAt: null, pulseKey: undefined, glow: glow ?? size >= 96, seed: 0 });
    r.renderAt(Number(t), rot);
  }, [size, color, state, movimento, glow, t, rot]);
  return (
    <div className="orb-lab-solo">
      {t === null
        ? <SoraOrb size={size} state={state} color={color} movimento={movimento} glow={glow} />
        : <canvas ref={ref} data-solo width={size} height={size} />}
    </div>
  );
}

export default function OrbLab() {
  const q = new URLSearchParams(window.location.search);
  return q.has('solo') ? <OrbSolo q={q} /> : <OrbLabFull />;
}

function OrbLabFull() {
  const [estado, setEstado] = useState<OrbState>('arriving');
  const [agente, setAgente] = useState(0);
  const [pulso, setPulso] = useState(0);
  const [chegada, setChegada] = useState(0);
  const [look, setLook] = useState<{ x: number; y: number } | null>(null);
  const [estresse, setEstresse] = useState(false);
  const palco = useRef<HTMLDivElement>(null);
  const fps = useFps();
  const A = AGENTES[agente];

  const mover = (e: PointerEvent) => {
    const r = palco.current!.getBoundingClientRect();
    setLook({ x: ((e.clientX - r.left) / r.width) * 2 - 1, y: ((e.clientY - r.top) / r.height) * 2 - 1 });
  };

  return (
    <div className="orb-lab-page">
      <h1>Laboratório do mascote</h1>
      <p className="orb-lab-subtitle">Todos os estados, cores de agente e tamanhos da Sora. {fps} fps</p>

      <div className="orb-lab-hero">
        <div
          ref={palco}
          className="orb-lab-card orb-lab-stage"
          onPointerMove={mover}
          onPointerLeave={() => setLook(null)}
        >
          <SoraOrb
            key={chegada}
            size={320}
            color={A.cor}
            state={estado}
            movimento={A.movimento}
            lookAt={look}
            pulseKey={pulso}
            title={A.nome}
            onArrived={() => setEstado(e => (e === 'arriving' ? 'idle' : e))}
          />
          <p className="orb-lab-small orb-lab-stage-caption">
            {ESTADOS.find(e => e.id === estado)?.desc} · mova o mouse para o olhar seguir
          </p>
        </div>

        <div className="orb-lab-card orb-lab-controls">
          <div>
            <div className="orb-lab-small orb-lab-label">Estado</div>
            <div className="orb-lab-actions">
              {ESTADOS.map(e => (
                <button key={e.id} className={`orb-lab-button ${estado === e.id ? 'is-active' : ''}`}
                  onClick={() => { setEstado(e.id); if (e.id === 'arriving') setChegada(c => c + 1); }}>
                  {e.nome}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="orb-lab-small orb-lab-label">Agente (cor + movimento)</div>
            <div className="orb-lab-actions">
              {AGENTES.map((a, i) => (
                <button key={a.nome} className={`orb-lab-button ${agente === i ? 'is-active' : ''}`} style={{ '--agent-color': a.cor } as CSSProperties} onClick={() => setAgente(i)}>
                  {a.nome} · {a.movimento}
                </button>
              ))}
            </div>
          </div>
          <div className="orb-lab-actions">
            <button className="orb-lab-button" onClick={() => setPulso(p => p + 1)}>Disparar pulso</button>
            <button className={`orb-lab-button ${estresse ? 'is-active' : ''}`} onClick={() => setEstresse(v => !v)}>Teste de carga (60 orbs)</button>
          </div>
          <SoraThinking />
        </div>
      </div>

      <Secao titulo="Estados">
        <div className="orb-lab-grid orb-lab-grid-states">
          {ESTADOS.map((e, i) => (
            <div key={e.id} className="orb-lab-card orb-lab-item orb-lab-state-card">
              <SoraOrb size={120} state={e.id} seed={i + 1} movimento="gira" />
              <div className="orb-lab-item-title">{e.nome}</div>
              <div className="orb-lab-small orb-lab-centered">{e.desc}</div>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Pensando (thinking orb) — 28, 72 e 240 px">
        <div className="orb-lab-card orb-lab-orb-row orb-lab-thinking-row">
          {[28, 72, 240].map((t, i) => (
            <div key={t} className="orb-lab-orb-item">
              <SoraOrb size={t} state="thinking" seed={i + 31} />
              <span className="orb-lab-small">{t}px</span>
            </div>
          ))}
          {AGENTES.slice(1).map((a, i) => (
            <div key={a.nome} className="orb-lab-orb-item">
              <SoraOrb size={72} state="thinking" color={a.cor} seed={i + 41} title={a.nome} />
              <span className="orb-lab-small orb-lab-agent-color" style={{ '--agent-color': a.cor } as CSSProperties}>{a.nome}</span>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Agentes trabalhando">
        <div className="orb-lab-grid orb-lab-grid-agents">
          {AGENTES.map((a, i) => (
            <div key={a.nome} className="orb-lab-card orb-lab-item">
              <SoraOrb size={150} color={a.cor} state={i === 0 ? 'coordinating' : 'working'} movimento={a.movimento} seed={i * 3 + 2} title={a.nome} />
              <div className="orb-lab-item-title orb-lab-agent-color" style={{ '--agent-color': a.cor } as CSSProperties}>{a.nome}</div>
              <div className="orb-lab-small">{a.verbo} · {a.movimento}</div>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Tamanhos (20 px a 320 px)">
        <div className="orb-lab-card orb-lab-orb-row">
          {TAMANHOS.map((t, i) => (
            <div key={t} className="orb-lab-orb-item">
              <SoraOrb size={t} seed={i + 11} state={estado === 'arriving' ? 'idle' : estado} color={A.cor} movimento={A.movimento} />
              <span className="orb-lab-small">{t}px</span>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Barra lateral (avatares)">
        <div className="orb-lab-card orb-lab-sidebar">
          {AGENTES.map((a, i) => (
            <div key={a.nome} className={`orb-lab-sidebar-row ${i === 0 ? 'is-current' : ''}`}>
              <SoraOrb size={36} color={a.cor} state={i === 0 ? 'coordinating' : 'working'} movimento={a.movimento} seed={i + 21} />
              <div>
                <div className="orb-lab-sidebar-name">{a.nome}</div>
                <div className="orb-lab-sidebar-status orb-lab-agent-color" style={{ '--agent-color': a.cor } as CSSProperties}>{i === 0 ? 'Coordenando 3 agentes' : a.verbo}</div>
              </div>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="SoraThinking (inline no chat)">
        <div className="orb-lab-card orb-lab-inline-demo">
          <div className="orb-lab-user-message">
            Crie uma campanha para lançar minha cafeteria.
          </div>
          <SoraThinking />
          <SoraThinking label="Pesquisando na web…" size={22} color="#56A8FF" />
          <SoraThinking label="Criando as peças…" size={22} color="#AC80FF" />
          <SoraThinking label="Escrevendo legendas…" size={22} color="#46E8A8" />
          <SoraThinking label="Montando o plano…" size={40} />
        </div>
        <div className="orb-lab-card orb-lab-placeholder-row">
          <div className="orb-lab-card orb-lab-placeholder">
            <SoraThinking layout="stacked" size={72} label="Preparando a equipe…" />
          </div>
          <div className="orb-lab-card orb-lab-placeholder">
            <SoraThinking layout="stacked" size={96} color="#AC80FF" label="Luna está criando as peças…" />
          </div>
        </div>
      </Secao>

      {estresse && (
        <Secao titulo="Teste de carga">
          <div className="orb-lab-card orb-lab-load-test">
            {Array.from({ length: 60 }, (_, i) => {
              const a = AGENTES[i % 4];
              return <SoraOrb key={i} size={i % 10 === 0 ? 64 : 28} color={a.cor} state={i % 5 === 0 ? 'thinking' : 'working'} movimento={a.movimento} seed={i} />;
            })}
          </div>
        </Secao>
      )}
    </div>
  );
}
