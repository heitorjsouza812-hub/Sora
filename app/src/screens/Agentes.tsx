// Galeria de agentes (item "Agentes" da barra lateral). "Criar agente" → /agentes/novo (construtor).
// Vazio (item 48): modelos prontos que abrem o construtor pré-preenchido (/agentes/novo?modelo=<id>).
import type { CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/base';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { pedirApagar, pedirRenomear } from '../components/gestao';
import { MenuAgente } from '../components/builder';
import { MODELOS_AGENTE } from '../components/projetos';
import { estadoAgente, todosAgentes, useAgora, useProjetos } from '../state/projetos';
import '../components/projetos/projetos.css';

const Mais = () => <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>;

export default function Agentes() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const ags = todosAgentes(e, agora);
  const criar = (tamanho: 'P' | 'M') => (
    <Button asChild variante="primario" tamanho={tamanho} iconeEsquerda={<Mais />}><Link to="/agentes/novo">Criar agente</Link></Button>
  );
  return (
    <AppShell titulo="Agentes" acoes={criar('P')}>
      <main className="gallery-screen">
        <header className="gallery-head">
          <div><h1>Seus agentes</h1><p>Agentes criados pela {e.sora.nome} nas suas conversas e projetos, e os que você montou.</p></div>
        </header>
        {!ags.length && (
          <div className="pj-vazio">
            <SoraOrb size={110} color={e.sora.cor} state="idle" decorative />
            <h3>Nenhum agente ainda</h3>
            <p>Comece por um modelo pronto — ele abre no construtor já preenchido — ou peça um trabalho à {e.sora.nome}, que ela monta a equipe.</p>
            <ul className="pj-modelos" aria-label="Modelos de agente">
              {MODELOS_AGENTE.map((m, i) => (
                <li key={m.id}>
                  <Link className="pj-modelo pj-modelo--orb" to={`/agentes/novo?modelo=${m.id}`}>
                    <SoraOrb size={36} color={e.sora.cor} movimento={m.rascunho.tipoMovimento} glow={false} decorative seed={i + 20} />
                    <span className="pj-modelo__texto"><strong>{m.rotulo}</strong><span>{m.descricao}</span></span>
                  </Link>
                </li>
              ))}
            </ul>
            <div className="pj-vazio__acao">{criar('M')}</div>
          </div>
        )}
        <div className="gallery-grid">
          {ags.map(a => {
            const st = estadoAgente(e, a.id, agora);
            const projeto = a.projetoId ? e.projetos.find(p => p.id === a.projetoId) : undefined;
            return (
              <article key={a.id} className="gallery-card agent-card card" style={{ '--agent': a.cor } as CSSProperties}>
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
                  <Button asChild tamanho="P"><Link to={`/chat/${a.id}`}>Conversar</Link></Button>
                  <Button asChild tamanho="P" variante="fantasma"><Link to={`/agentes/${a.id}/editar`}>Editar</Link></Button>
                </div>
              </article>
            );
          })}
        </div>
      </main>
    </AppShell>
  );
}
