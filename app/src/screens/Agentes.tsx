// Galeria opcional de bots. A criação começa sempre na conversa com a Sora.
import type { CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../components/base';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { pedirApagar, pedirRenomear } from '../components/gestao';
import { MenuAgente } from '../components/builder';
import { deixarPedidoInicial } from '../components/inicio';
import { estadoAgente, todosAgentes, useAgora, useProjetos } from '../state/projetos';
import '../components/projetos/projetos.css';

const Mais = () => <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>;

export default function Agentes() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  // Só bots persistentes (tipo individual); especialistas internos das conversas ficam fora.
  const ags = todosAgentes(e, agora).filter(a => a.avulso);
  const criar = (tamanho: 'P' | 'M') => (
    <Button asChild variante="primario" tamanho={tamanho} iconeEsquerda={<Mais />}><Link to="/">Criar com a Sora</Link></Button>
  );
  const primeiroBot = () => { deixarPedidoInicial('Quero um bot que '); navigate('/'); };
  return (
    <AppShell titulo="Bots" acoes={ags.length ? criar('P') : <span />}>
      <main className="gallery-screen">
        <header className="gallery-head">
          <div><h1>Seus bots</h1><p>Bots persistentes criados em conversa com a {e.sora.nome}.</p></div>
        </header>
        {!ags.length && (
          <div className="pj-vazio">
            <SoraOrb size={110} color={e.sora.cor} state="idle" decorative />
            <h3>Nenhum bot ainda</h3>
            <p>Converse com a {e.sora.nome}. Ela prepara um rascunho para você ajustar antes de criar.</p>
            <div className="pj-vazio__acao"><Button variante="primario" tamanho="M" iconeEsquerda={<Mais />} onClick={primeiroBot}>Criar meu primeiro bot</Button></div>
          </div>
        )}
        <div className="gallery-grid">
          {ags.map(a => {
            const st = estadoAgente(e, a.id, agora);
            return (
              <article key={a.id} className="gallery-card agent-card card" style={{ '--agent': a.cor } as CSSProperties}>
                <MenuAgente agenteId={a.id} nome={a.nome} className="gallery-menu" semEditar itens={[
                  { rotulo: 'Conversar', onClick: () => navigate(`/bots/${a.id}`) },
                  { rotulo: 'Editar', onClick: () => navigate(`/bots/${a.id}/editar`) },
                  { rotulo: 'Renomear', onClick: () => pedirRenomear({ tipo: 'agente', id: a.id }) },
                  { rotulo: 'Apagar', perigo: true, onClick: () => pedirApagar({ tipo: 'agente', id: a.id }) },
                ]} />
                <Link to={`/bots/${a.id}`} className="gallery-orb" aria-label={`Conversar com ${a.nome}`}>
                  <SoraOrb size={92} color={a.cor} movimento={a.tipoMovimento} decorative seed={a.nome.length}
                    state={st.status === 'trabalhando' ? 'working' : 'idle'} />
                </Link>
                <strong>{a.nome}</strong>
                <small>{a.funcao}</small>
                <span className={`gallery-status status-${st.status}`}>{st.rotulo || 'Disponível'}</span>
                <div className="gallery-actions">
                  <Button asChild tamanho="P"><Link to={`/bots/${a.id}`}>Conversar</Link></Button>
                  <Button asChild tamanho="P" variante="fantasma"><Link to={`/bots/${a.id}/editar`}>Editar</Link></Button>
                </div>
              </article>
            );
          })}
        </div>
      </main>
    </AppShell>
  );
}
