// Revisão do projeto: entregas por agente, Aprovar e publicar / Pedir ajuste (versões comparadas);
// depois de aprovado, mostra o que foi publicado e os próximos passos.
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { Button } from '../components/base';
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
  const voltar = () => { abrirProjeto(p.id); navigate(`/projeto/${p.id}`); };
  const proxima = `Agende a próxima campanha seguindo o que funcionou em “${p.titulo}”: novas referências, peças e um calendário de posts para o próximo mês.`;
  return (
    <AppShell titulo={`Revisão · ${p.titulo}`} acoes={p.aprovadoEm ? undefined : <Button tamanho="P" onClick={voltar}>Voltar ao projeto</Button>}>
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
          onPedirAjuste={(texto, agenteId) => { pedirAjuste(p.id, texto, agenteId); voltar(); }}
          corSora={e.sora.cor}
          onVoltarProjeto={voltar}
          onAgendarProxima={() => navigate(`/projetos?pedido=${encodeURIComponent(proxima)}`)}
          onNovoProjeto={() => navigate('/projetos')}
        />
      </div>
    </AppShell>
  );
}
