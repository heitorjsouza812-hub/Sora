// Galeria de agentes (item "Agentes" da barra lateral). "Criar agente" → /agentes/novo (construtor).
import type { CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { pedirApagar, pedirRenomear } from '../components/gestao';
import { MenuAgente } from '../components/studio';
import { estadoAgente, todosAgentes, useAgora, useProjetos } from '../state/projetos';

export default function Agentes() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const ags = todosAgentes(e, agora);
  const criar = <Link to="/agentes/novo" className="primary-button gallery-create">+ Criar agente</Link>;
  return (
    <AppShell titulo="Agentes" acoes={criar}>
      <main className="gallery-screen">
        <header className="gallery-head">
          <div><h1>Seus agentes</h1><p>Agentes criados pela {e.sora.nome} nas suas conversas e projetos, e os que você montou.</p></div>
        </header>
        {!ags.length && (
          <div className="gallery-empty">
            <SoraOrb size={96} color={e.sora.cor} state="idle" decorative />
            <h2>Nenhum agente ainda</h2>
            <p>Crie um agente individual ou peça um trabalho à {e.sora.nome} — ela monta a equipe.</p>
            {criar}
          </div>
        )}
        <div className="gallery-grid">
          {ags.map(a => {
            const st = estadoAgente(e, a.id, agora);
            const projeto = a.projetoId ? e.projetos.find(p => p.id === a.projetoId) : undefined;
            return (
              <article key={a.id} className="gallery-card card" style={{ '--agent': a.cor } as CSSProperties}>
                <MenuAgente agenteId={a.id} nome={a.nome} className="gallery-menu" semEditar itens={[
                  { rotulo: 'Conversar', onClick: () => navigate(`/chat/${a.id}`) },
                  { rotulo: 'Editar', onClick: () => navigate(`/agentes/${a.id}/editar`) },
                  { rotulo: 'Renomear', onClick: () => pedirRenomear({ tipo: 'agente', id: a.id }) },
                  { rotulo: 'Apagar', perigo: true, onClick: () => pedirApagar({ tipo: 'agente', id: a.id }) },
                ]} />
                <Link to={`/chat/${a.id}`} className="gallery-orb" aria-label={`Conversar com ${a.nome}`}>
                  <SoraOrb size={92} color={a.cor} movimento={a.tipoMovimento} decorative seed={a.nome.length}
                    state={st.status === 'trabalhando' ? 'working' : 'idle'} />
                </Link>
                <strong>{a.nome}</strong>
                <small>{a.funcao}</small>
                <span className="gallery-tag">{projeto ? projeto.titulo : 'Avulso'}</span>
                <span className={`gallery-status status-${st.status}`}>{st.rotulo || 'Disponível'}</span>
                <div className="gallery-actions">
                  <Link to={`/chat/${a.id}`} className="see-work">Conversar</Link>
                  <Link to={`/agentes/${a.id}/editar`} className="see-work">Editar</Link>
                </div>
              </article>
            );
          })}
        </div>
      </main>
    </AppShell>
  );
}
