// Vista Início da ilha: Sora branca grande + ticker à esquerda; pílulas dos bonecos (agentes) à direita.
import { useRef, useState, type CSSProperties } from 'react';
import { SoraOrb } from '../mascot';
import { alternarAgenteOculto, definirIlhaPrefs, filtrarAgentes, useIlhaPrefs, type FiltroAgentes, type VisaoIlha } from './ilhaEstado';
import { Ticker } from './Ticker';
import { AnelConclusao } from './animacao';
import { usePresenca } from './usePresenca';

const FILTROS: { id: FiltroAgentes; rotulo: string }[] = [
  { id: 'todos', rotulo: 'Todos' },
  { id: 'trabalhando', rotulo: 'Trabalhando' },
  { id: 'concluidos', rotulo: 'Concluídos' },
];
const VAZIO_FILTRO: Record<FiltroAgentes, string> = {
  todos: 'Todos os agentes deste projeto estão escondidos',
  trabalhando: 'Nenhum agente trabalhando agora',
  concluidos: 'Nenhum agente concluiu ainda',
};

function Olho({ aberto }: { aberto: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
      {aberto ? <circle cx="12" cy="12" r="3" /> : <path d="M4 4l16 16" />}
    </svg>
  );
}

const CUTUCADAS = 5;
const JANELA_CUTUCAR = 1200;
const DURACAO_TONTA = 1500;

export interface VisaoGeralProps {
  v: VisaoIlha;
  onAgente: (agenteId: string) => void;
}

export function VisaoGeral({ v, onAgente }: VisaoGeralProps) {
  // easter egg (o "dizzy" do Coucou): 5 cliques rápidos na Sora
  const cliques = useRef<number[]>([]);
  const [tonta, setTonta] = useState(0);
  const [tontaAte, setTontaAte] = useState(0);
  const cutucar = () => {
    const agora = performance.now();
    cliques.current = [...cliques.current.filter(t => agora - t < JANELA_CUTUCAR), agora];
    if (cliques.current.length >= CUTUCADAS) {
      cliques.current = [];
      setTonta(n => n + 1);
      setTontaAte(agora + DURACAO_TONTA);
      window.setTimeout(() => setTontaAte(0), DURACAO_TONTA);
    }
  };
  const rotulo = tontaAte ? 'Ei! 😵‍💫' : v.sora.rotulo;

  // filtro Todos · Trabalhando · Concluídos + bonecos escondidos (botão olho)
  const prefs = useIlhaPrefs();
  const visiveis = v.agentes.filter(a => !prefs.ocultos.includes(a.id));
  const escondidos = v.agentes.filter(a => prefs.ocultos.includes(a.id));
  const contagem: Record<FiltroAgentes, number> = {
    todos: visiveis.length,
    trabalhando: visiveis.filter(a => a.status === 'trabalhando').length,
    concluidos: visiveis.filter(a => a.status === 'concluido').length,
  };
  const presentes = usePresenca(filtrarAgentes(v.agentes, prefs));

  return (
    <div className="ilha-visao">
      <section className="ilha-card ilha-card-sora" aria-label="Sora">
        <button type="button" className="ilha-sora-grande" onClick={cutucar} aria-label="Sora">
          <SoraOrb size={96} color={v.sora.cor} state={v.sora.orb} pulseKey={v.sora.pulso + tonta} glow decorative seed={5} />
        </button>
        <div className="ilha-sora-info">
          <p className="ilha-sora-titulo">
            <span className="ilha-ponto" aria-hidden="true" />
            <strong>{v.projeto?.titulo ?? v.sora.nome}</strong>
          </p>
          <p className="ilha-sora-rotulo" role="status">{rotulo}</p>
          {v.ticker.length > 0 && <Ticker passos={v.ticker} compacto />}
        </div>
      </section>

      <section className="ilha-card ilha-card-bonecos" aria-label="Agentes rodando">
        {v.agentes.length === 0 ? (
          <p className="ilha-vazio">Sem agentes rodando neste projeto</p>
        ) : (
          <>
            <div className="ilha-filtro" role="radiogroup" aria-label="Filtrar agentes">
              {FILTROS.map(f => (
                <button key={f.id} type="button" role="radio" aria-checked={prefs.filtro === f.id} className="ilha-filtro-opcao"
                  onClick={() => definirIlhaPrefs({ filtro: f.id })}>
                  {f.rotulo} <span className="ilha-filtro-n">{contagem[f.id]}</span>
                </button>
              ))}
            </div>
            {presentes.length === 0 ? <p className="ilha-vazio">{VAZIO_FILTRO[prefs.filtro]}</p> : (
              <ul className="ilha-bonecos-lista">
                {presentes.map(({ item: a, saindo }, i) => (
                  <li key={a.id} className={saindo ? 'ilha-saindo' : undefined} style={{ '--i': i, '--agente': a.cor } as CSSProperties}>
                    <button type="button" className="ilha-boneco" data-status={a.status} tabIndex={saindo ? -1 : undefined}
                      onClick={() => onAgente(a.id)} aria-label={`${a.nome}: ${a.rotulo}, ${a.progresso}%. Ver detalhes`}>
                      <span className="ilha-boneco-orb">
                        <SoraOrb size={28} color={a.cor} state={a.orb} movimento={a.movimento} glow={false} decorative seed={30 + i} />
                        <AnelConclusao agente={a} />
                      </span>
                      <span className="ilha-boneco-texto">
                        <strong>{a.nome}</strong>
                        <small className={a.status === 'trabalhando' ? 'shimmer' : undefined}>{a.rotulo}</small>
                      </span>
                      <span className="ilha-boneco-barra" aria-hidden="true"><i style={{ width: `${a.progresso}%` }} /></span>
                    </button>
                    <button type="button" className="ilha-olho" aria-label={`Esconder ${a.nome}`} title={`Esconder ${a.nome}`}
                      tabIndex={saindo ? -1 : undefined} onClick={() => alternarAgenteOculto(a.id)}>
                      <Olho aberto />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {escondidos.length > 0 && (
              <div className="ilha-escondidos">
                <span>{escondidos.length} {escondidos.length === 1 ? 'escondido' : 'escondidos'}</span>
                <span aria-hidden="true">·</span>
                {escondidos.map(a => (
                  <button key={a.id} type="button" className="ilha-escondido" style={{ '--agente': a.cor } as CSSProperties}
                    aria-label={`Mostrar ${a.nome}`} title={`Mostrar ${a.nome}`} onClick={() => alternarAgenteOculto(a.id)}>
                    <Olho aberto={false} /> {a.nome}
                  </button>
                ))}
                <button type="button" className="ilha-escondidos-todos" aria-label={`Mostrar todos os ${escondidos.length} escondidos`}
                  onClick={() => definirIlhaPrefs({ ocultos: prefs.ocultos.filter(id => !escondidos.some(a => a.id === id)) })}>
                  mostrar
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

export default VisaoGeral;
