// Vista Início da ilha: Sora branca grande + ticker à esquerda; pílulas dos bonecos (agentes) à direita.
import { useRef, useState, type CSSProperties } from 'react';
import { SoraOrb } from '../mascot';
import type { VisaoIlha } from './ilhaEstado';
import { Ticker } from './Ticker';

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
          <ul className="ilha-bonecos-lista">
            {v.agentes.map((a, i) => (
              <li key={a.id}>
                <button type="button" className="ilha-boneco" style={{ '--agente': a.cor } as CSSProperties}
                  onClick={() => onAgente(a.id)} aria-label={`${a.nome}: ${a.rotulo}, ${a.progresso}%. Ver detalhes`}>
                  <SoraOrb size={28} color={a.cor} state={a.orb} movimento={a.movimento} glow={false} decorative seed={30 + i} />
                  <span className="ilha-boneco-texto">
                    <strong>{a.nome}</strong>
                    <small className={a.status === 'trabalhando' ? 'shimmer' : undefined}>{a.rotulo}</small>
                  </span>
                  <span className="ilha-boneco-barra" aria-hidden="true"><i style={{ width: `${a.progresso}%` }} /></span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default VisaoGeral;
