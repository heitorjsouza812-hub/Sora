// Vista Início da ilha: Sora branca grande + o que a equipe espera de você (cartões do Mosaico)
// + pílulas dos bonecos (bots) com filtro Todos · Trabalhando · Precisa de você.
import { useRef, useState, type CSSProperties } from 'react';
import { SoraOrb } from '../mascot';
import { CartaoPrecisaDeVoce } from '../pendencias/CartaoPrecisaDeVoce';
import { alternarAgenteOculto, definirIlhaPrefs, filtrarBonecos, useIlhaPrefs, type FiltroBots, type VisaoIlha } from './ilhaEstado';
import { usePresenca } from './usePresenca';

const FILTROS: { id: FiltroBots; rotulo: string }[] = [
  { id: 'todos', rotulo: 'Todos' },
  { id: 'trabalhando', rotulo: 'Trabalhando' },
  { id: 'precisa_de_voce', rotulo: 'Precisa de você' },
];
const VAZIO_FILTRO: Record<FiltroBots, string> = {
  todos: 'Nenhum bot criado ainda',
  trabalhando: 'Nenhum bot trabalhando agora',
  precisa_de_voce: 'Nenhum bot precisa de você agora',
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
  const rotulo = tontaAte ? 'Ei! 😵‍💫'
    : v.precisaDeVoce.length > 0 ? `${v.precisaDeVoce.length} ${v.precisaDeVoce.length === 1 ? 'pedido' : 'pedidos'} esperando você`
    : v.trabalhando > 0 ? `${v.trabalhando} trabalhando`
    : 'Tudo tranquilo';
  const orbDaSora = v.precisaDeVoce.length > 0 ? 'listening' : v.trabalhando > 0 ? 'coordinating' : 'idle';

  // filtro Todos · Trabalhando · Precisa de você + bonecos escondidos (botão olho)
  const prefs = useIlhaPrefs();
  const visiveis = v.bonecos.filter(a => !prefs.ocultos.includes(a.id));
  const escondidos = v.bonecos.filter(a => prefs.ocultos.includes(a.id));
  const contagem: Record<FiltroBots, number> = {
    todos: visiveis.length,
    trabalhando: visiveis.filter(a => a.estado === 'trabalhando').length,
    precisa_de_voce: visiveis.filter(a => a.estado === 'precisa_de_voce').length,
  };
  const presentes = usePresenca(filtrarBonecos(v.bonecos, prefs));

  return (
    <div className="ilha-visao">
      {v.precisaDeVoce.length > 0 && (
        <div className="ilha-pendencias pend-lista" aria-label="Precisa de você">
          {v.precisaDeVoce.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} compacto />)}
        </div>
      )}
      <section className="ilha-card ilha-card-sora" aria-label="Sora">
        <button type="button" className="ilha-sora-grande" onClick={cutucar} aria-label="Sora">
          <SoraOrb size={96} color={v.sora.cor} state={orbDaSora} pulseKey={tonta} glow decorative seed={5} />
        </button>
        <div className="ilha-sora-info">
          <p className="ilha-sora-titulo">
            <span className="ilha-ponto" aria-hidden="true" />
            <strong>{v.sora.nome}</strong>
          </p>
          <p className="ilha-sora-rotulo" role="status">{rotulo}</p>
          {v.gruposTrabalhando > 0 && <p className="ilha-sora-rotulo">{v.gruposTrabalhando} {v.gruposTrabalhando === 1 ? 'grupo' : 'grupos'} em andamento</p>}
        </div>
      </section>

      <section className="ilha-card ilha-card-bonecos" aria-label="Bots">
        {v.bonecos.length === 0 ? (
          <p className="ilha-vazio">Nenhum bot criado ainda</p>
        ) : (
          <>
            <div className="ilha-filtro" role="radiogroup" aria-label="Filtrar bots">
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
                    <button type="button" className="ilha-boneco" data-status={a.estado} tabIndex={saindo ? -1 : undefined}
                      onClick={() => onAgente(a.id)} aria-label={`${a.nome}: ${a.funcao}. Ver detalhes`}>
                      <span className="ilha-boneco-orb">
                        <SoraOrb size={28} color={a.cor} state={a.orb} glow={false} decorative seed={30 + i} />
                      </span>
                      <span className="ilha-boneco-texto">
                        <strong>{a.nome}</strong>
                        <small className={a.estado === 'trabalhando' ? 'shimmer' : undefined}>
                          {a.estado === 'trabalhando' ? 'Trabalhando' : a.estado === 'precisa_de_voce' ? 'Precisa de você' : a.funcao}
                        </small>
                      </span>
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
