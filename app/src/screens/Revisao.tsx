// Revisão do projeto: entregas por agente, Aprovar e publicar / Pedir ajuste (versões comparadas).
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { RevisaoProjeto } from '../components/review';
import { abrirProjeto, aprovarProjeto, estadoProjeto, pedirAjuste, useAgora, useProjetos } from '../state/projetos';

export default function Revisao() {
  const { projetoId = '' } = useParams();
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const p = e.projetos.find(x => x.id === projetoId);
  if (!p) return <Navigate to="/" replace />;
  const fase = estadoProjeto(e, p, agora).fase;
  return (
    <AppShell titulo={`Revisão · ${p.titulo}`} acoes={<button type="button" className="share-button" onClick={() => { abrirProjeto(p.id); navigate('/chat/sora'); }}>Voltar ao chat</button>}>
      <div className="review-screen">
        {fase === 'pensando' || fase === 'planejando' || fase === 'coordenando'
          ? <p className="review-wait" role="status">A equipe ainda está trabalhando. As entregas aparecem aqui quando ficarem prontas.</p>
          : null}
        <RevisaoProjeto
          projeto={p}
          agentes={e.agentes}
          entregas={p.entregas}
          entregasAnteriores={p.entregasAnteriores}
          aprovado={Boolean(p.aprovadoEm)}
          onAprovar={id => aprovarProjeto(id)}
          onPedirAjuste={(texto, agenteId) => { pedirAjuste(p.id, texto, agenteId); abrirProjeto(p.id); navigate('/chat/sora'); }}
        />
      </div>
    </AppShell>
  );
}
