// Detalhe do bot na ilha: identidade, estado e os pedidos "Precisa de você" que são dele.
// A conversa de verdade (e o microfone) ficam na tela do bot (`/bots/:id`) no app principal.
import { CartaoPrecisaDeVoce } from '../pendencias/CartaoPrecisaDeVoce';
import { SoraOrb } from '../mascot';
import { abrirNoApp } from '../../desktop/ponte';
import { useIlha } from './ilhaEstado';
import './ilha-partes.css';

const ROTULO_ESTADO: Record<string, string> = {
  livre: 'Livre',
  trabalhando: 'Trabalhando',
  precisa_de_voce: 'Precisa de você',
};

export function DetalheAgente({ agenteId, onVoltar }: { agenteId: string; onVoltar: () => void }) {
  const { bonecos, precisaDeVoce } = useIlha();
  const agente = bonecos.find(item => item.id === agenteId);
  const pedidosDoBot = precisaDeVoce.filter(p => p.botId === agenteId);

  if (!agente) return <div className="ilha-agente-vazio"><p>Este bot não existe mais.</p><button type="button" onClick={onVoltar}>Voltar</button></div>;

  return (
    <section className="ilha-agente" aria-labelledby="ilha-agente-nome">
      <div className="ilha-agente__lateral">
        <button type="button" className="ilha-voltar" onClick={onVoltar}>← Voltar</button>
        <SoraOrb size={88} color={agente.cor} state={agente.orb} title={agente.nome} />
        <div className="ilha-agente__identidade">
          <h2 id="ilha-agente-nome" style={{ color: agente.cor }}>{agente.nome}</h2>
          <p>{agente.funcao}</p>
          <span>{ROTULO_ESTADO[agente.estado] ?? agente.estado}</span>
        </div>
      </div>
      <div className="ilha-agente__principal">
        {pedidosDoBot.length > 0 ? (
          <div className="pend-lista">{pedidosDoBot.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} />)}</div>
        ) : (
          <p className="ilha-agente__sem-resultado">{agente.estado === 'trabalhando' ? 'Trabalhando agora.' : 'Nada pendente deste bot.'}</p>
        )}
        <div className="ilha-agente__acoes">
          <button type="button" className="ilha-botao" onClick={() => void abrirNoApp(`/bots/${agente.id}`)}>Abrir chat do bot</button>
        </div>
      </div>
    </section>
  );
}

export default DetalheAgente;
