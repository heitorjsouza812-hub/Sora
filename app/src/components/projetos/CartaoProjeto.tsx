// Card de um projeto: título, pedido resumido, equipe (orbs na cor de cada agente), fase, progresso e data.
import type { CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { abrirProjeto, estadoAgente, estadoProjeto, type EstadoProjetos, type ProjetoSora } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { MenuItemAcoes } from '../gestao';
import { FASES, resumirPedido, tempoRelativo } from './util';

const MAX_AVATARES = 4;

export function CartaoProjeto({ e, projeto, agora }: { e: EstadoProjetos; projeto: ProjetoSora; agora: number }) {
  const navigate = useNavigate();
  const ep = estadoProjeto(e, projeto, agora);
  const fase = FASES[ep.fase];
  const href = `/projeto/${projeto.id}`;
  const equipe = projeto.agenteIds.map((id) => e.agentes[id]).filter((a) => !!a && a.criadoEm <= agora);
  const visiveis = equipe.slice(0, MAX_AVATARES);
  const extra = equipe.length - visiveis.length;
  const trabalhando = ep.fase === 'pensando' || ep.fase === 'planejando' || ep.fase === 'coordenando';
  const progresso = ep.fase === 'pronto' || ep.fase === 'aprovado' ? 100 : ep.fase === 'coordenando' ? ep.progresso : 0;
  const abrir = () => { abrirProjeto(projeto.id); };
  const equipeTexto = equipe.length ? equipe.map((a) => a.nome).join(', ') : 'Equipe ainda sendo criada';

  return (
    <article className={`pj-card pj-fase-${ep.fase} ${trabalhando ? 'is-busy' : ''}`}>
      <header className="pj-card-top">
        <span className="pj-fase" role="status"><i aria-hidden="true" />{fase.rotulo}</span>
        <MenuItemAcoes alvo={{ tipo: 'projeto', id: projeto.id }} nome={projeto.titulo}
          itens={[{ rotulo: 'Abrir', onClick: () => { abrir(); navigate(href); } }]} />
      </header>
      <h3><Link to={href} onClick={abrir} className="pj-card-link">{projeto.titulo}</Link></h3>
      <p className="pj-pedido">{resumirPedido(projeto.pedido)}</p>
      <div className="pj-card-bottom">
        <div className="pj-equipe" aria-label={`Equipe: ${equipeTexto}`} role="img">
          <span className="pj-avatar" style={{ '--cor': e.sora.cor } as CSSProperties}>
            <SoraOrb size={30} color={e.sora.cor} decorative glow={false} seed={2}
              state={ep.fase === 'pensando' ? 'thinking' : trabalhando ? 'coordinating' : 'idle'} />
          </span>
          {visiveis.map((a, i) => {
            const st = estadoAgente(e, a.id, agora);
            return (
              <span key={a.id} className="pj-avatar" style={{ '--cor': a.cor } as CSSProperties}>
                <SoraOrb size={30} color={a.cor} movimento={a.tipoMovimento} decorative glow={false} seed={i + 4}
                  state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : 'idle'} />
              </span>
            );
          })}
          {extra > 0 && <span className="pj-avatar pj-avatar-mais">+{extra}</span>}
        </div>
        <time className="pj-data" dateTime={new Date(projeto.criadoEm).toISOString()}>{tempoRelativo(projeto.criadoEm, agora)}</time>
      </div>
      <progress className="pj-progresso" max={100} value={progresso}
        aria-label={`Progresso de ${projeto.titulo}`} aria-valuetext={`${progresso}%, ${fase.rotulo.toLowerCase()}`} />
    </article>
  );
}
