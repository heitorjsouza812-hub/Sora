// Laboratório do mascote (agente "Prisma") — rota /lab/orb.
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';
import { SoraOrb, SoraThinking, type OrbState } from '../components/mascot';
import { OrbRenderer } from '../components/mascot/orbEngine';
import type { Movimento } from '../types';

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

const s = {
  page: { minHeight: '100vh', background: 'var(--bg, #050608)', color: 'var(--text, #F2F5FB)', fontFamily: 'var(--font)', padding: '40px clamp(16px, 4vw, 56px) 80px', boxSizing: 'border-box' },
  h1: { fontSize: 28, fontWeight: 600, margin: '0 0 6px' },
  sub: { color: 'var(--text-2, #8B93A3)', margin: '0 0 36px', fontSize: 15 },
  h2: { fontSize: 13, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3, #6B7280)', textTransform: 'uppercase', margin: '48px 0 16px' },
  card: { background: 'var(--panel, #0F1115)', border: '1px solid var(--line, rgba(255,255,255,.08))', borderRadius: 'var(--r-lg, 18px)', padding: 20 },
  grid: (min: number) => ({ display: 'grid', gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))`, gap: 16 }),
  small: { color: 'var(--text-2, #8B93A3)', fontSize: 13 },
  btn: (on: boolean) => ({
    border: '1px solid var(--line, rgba(255,255,255,.08))', borderRadius: 999, padding: '8px 14px', cursor: 'pointer',
    fontSize: 13, fontFamily: 'inherit', background: on ? '#EEF2FA' : 'var(--panel-2, #14161B)', color: on ? '#0B0D12' : 'var(--text, #F2F5FB)',
  }),
} satisfies Record<string, CSSProperties | ((...a: never[]) => CSSProperties)>;

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return <section><h2 style={s.h2}>{titulo}</h2>{children}</section>;
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
function OrbSolo({ q }: { q: URLSearchParams }) {
  const size = Number(q.get('solo')) || 240;
  const state = (q.get('state') || 'idle') as OrbState;
  const color = q.get('color') || '#E2ECFF';
  const movimento = (q.get('mov') || 'gira') as Movimento;
  const glow = q.has('glow') ? q.get('glow') !== '0' : undefined;
  const t = q.get('t'), rot = Number(q.get('rot') ?? 0);
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (t === null) return;
    const r = new OrbRenderer(ref.current!, { size, color, state, movimento, lookAt: null, pulseKey: undefined, glow: glow ?? size >= 96, seed: 0 });
    r.renderAt(Number(t), rot);
  }, [size, color, state, movimento, glow, t, rot]);
  return (
    <div style={{ minHeight: '100vh', background: '#050608', display: 'grid', placeItems: 'center' }}>
      {t === null
        ? <SoraOrb size={size} state={state} color={color} movimento={movimento} glow={glow} />
        : <canvas ref={ref} data-solo style={{ width: size, height: size }} />}
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
    <div style={s.page}>
      <h1 style={s.h1}>Laboratório do mascote</h1>
      <p style={s.sub}>Todos os estados, cores de agente e tamanhos da Sora. {fps} fps</p>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(260px, 340px)', gap: 20, alignItems: 'start' }}>
        <div
          ref={palco}
          style={{ ...s.card, display: 'grid', placeItems: 'center', minHeight: 420 }}
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
          <p style={{ ...s.small, marginTop: 8 }}>
            {ESTADOS.find(e => e.id === estado)?.desc} · mova o mouse para o olhar seguir
          </p>
        </div>

        <div style={{ ...s.card, display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div>
            <div style={{ ...s.small, marginBottom: 8 }}>Estado</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {ESTADOS.map(e => (
                <button key={e.id} style={s.btn(estado === e.id)}
                  onClick={() => { setEstado(e.id); if (e.id === 'arriving') setChegada(c => c + 1); }}>
                  {e.nome}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ ...s.small, marginBottom: 8 }}>Agente (cor + movimento)</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {AGENTES.map((a, i) => (
                <button key={a.nome} style={{ ...s.btn(agente === i), color: agente === i ? '#0B0D12' : a.cor }} onClick={() => setAgente(i)}>
                  {a.nome} · {a.movimento}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button style={s.btn(false)} onClick={() => setPulso(p => p + 1)}>Disparar pulso</button>
            <button style={s.btn(estresse)} onClick={() => setEstresse(v => !v)}>Teste de carga (60 orbs)</button>
          </div>
          <SoraThinking />
        </div>
      </div>

      <Secao titulo="Estados">
        <div style={s.grid(150)}>
          {ESTADOS.map((e, i) => (
            <div key={e.id} style={{ ...s.card, display: 'grid', justifyItems: 'center', gap: 8, padding: 14 }}>
              <SoraOrb size={120} state={e.id} seed={i + 1} movimento="gira" />
              <div style={{ fontWeight: 600, fontSize: 14 }}>{e.nome}</div>
              <div style={{ ...s.small, textAlign: 'center' }}>{e.desc}</div>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Pensando (thinking orb) — 28, 72 e 240 px">
        <div style={{ ...s.card, display: 'flex', alignItems: 'flex-end', gap: 36, flexWrap: 'wrap' }}>
          {[28, 72, 240].map((t, i) => (
            <div key={t} style={{ display: 'grid', justifyItems: 'center', gap: 6 }}>
              <SoraOrb size={t} state="thinking" seed={i + 31} />
              <span style={s.small}>{t}px</span>
            </div>
          ))}
          {AGENTES.slice(1).map((a, i) => (
            <div key={a.nome} style={{ display: 'grid', justifyItems: 'center', gap: 6 }}>
              <SoraOrb size={72} state="thinking" color={a.cor} seed={i + 41} title={a.nome} />
              <span style={{ ...s.small, color: a.cor }}>{a.nome}</span>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Agentes trabalhando">
        <div style={s.grid(200)}>
          {AGENTES.map((a, i) => (
            <div key={a.nome} style={{ ...s.card, display: 'grid', justifyItems: 'center', gap: 8 }}>
              <SoraOrb size={150} color={a.cor} state={i === 0 ? 'coordinating' : 'working'} movimento={a.movimento} seed={i * 3 + 2} title={a.nome} />
              <div style={{ fontWeight: 600, color: a.cor }}>{a.nome}</div>
              <div style={s.small}>{a.verbo} · {a.movimento}</div>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Tamanhos (20 px a 320 px)">
        <div style={{ ...s.card, display: 'flex', alignItems: 'flex-end', gap: 24, flexWrap: 'wrap' }}>
          {TAMANHOS.map((t, i) => (
            <div key={t} style={{ display: 'grid', justifyItems: 'center', gap: 6 }}>
              <SoraOrb size={t} seed={i + 11} state={estado === 'arriving' ? 'idle' : estado} color={A.cor} movimento={A.movimento} />
              <span style={s.small}>{t}px</span>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="Barra lateral (avatares)">
        <div style={{ ...s.card, maxWidth: 300, display: 'grid', gap: 4, padding: 10 }}>
          {AGENTES.map((a, i) => (
            <div key={a.nome} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 10px', borderRadius: 12, background: i === 0 ? 'var(--panel-2, #14161B)' : 'transparent' }}>
              <SoraOrb size={36} color={a.cor} state={i === 0 ? 'coordinating' : 'working'} movimento={a.movimento} seed={i + 21} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{a.nome}</div>
                <div style={{ fontSize: 12, color: a.cor }}>{i === 0 ? 'Coordenando 3 agentes' : a.verbo}</div>
              </div>
            </div>
          ))}
        </div>
      </Secao>

      <Secao titulo="SoraThinking (inline no chat)">
        <div style={{ ...s.card, display: 'grid', gap: 18, maxWidth: 560 }}>
          <div style={{ alignSelf: 'end', justifySelf: 'end', background: 'var(--panel-2, #14161B)', borderRadius: 16, padding: '10px 14px', fontSize: 14 }}>
            Crie uma campanha para lançar minha cafeteria.
          </div>
          <SoraThinking />
          <SoraThinking label="Pesquisando na web…" size={22} color="#56A8FF" />
          <SoraThinking label="Criando as peças…" size={22} color="#AC80FF" />
          <SoraThinking label="Escrevendo legendas…" size={22} color="#46E8A8" />
          <SoraThinking label="Montando o plano…" size={40} />
        </div>
        <div style={{ ...s.card, display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 16 }}>
          <div style={{ ...s.card, background: 'var(--panel-2, #14161B)', flex: '1 1 240px', display: 'grid', placeItems: 'center', minHeight: 220 }}>
            <SoraThinking layout="stacked" size={72} label="Preparando a equipe…" />
          </div>
          <div style={{ ...s.card, background: 'var(--panel-2, #14161B)', flex: '1 1 240px', display: 'grid', placeItems: 'center', minHeight: 220 }}>
            <SoraThinking layout="stacked" size={96} color="#AC80FF" label="Luna está criando as peças…" />
          </div>
        </div>
      </Secao>

      {estresse && (
        <Secao titulo="Teste de carga">
          <div style={{ ...s.card, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
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
