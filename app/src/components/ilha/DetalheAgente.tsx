import { useState, type CSSProperties, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { enviarParaAgente, passosDoAgente, useAgora, useProjetos } from '../../state/projetos';
import type { PassoTrabalho } from '../../types';
import { SoraOrb } from '../mascot';
import { useIlha } from './ilhaEstado';
import './ilha-partes.css';

function RotuloPasso({ passo }: { passo: PassoTrabalho }) {
  return <span className={passo.acao ? 'ilha-agente__acao' : 'ilha-agente__texto-passo'}>{passo.acao ?? passo.texto}</span>;
}

function Resultado({ passo }: { passo: PassoTrabalho }) {
  const resultado = passo.resultado;
  if (!resultado) return <p className="ilha-agente__sem-resultado">O resultado aparecerá aqui quando este passo terminar.</p>;
  return (
    <div className="ilha-agente__resultado">
      <strong>{resultado.resumo}</strong>
      {resultado.links?.length ? <ul>{resultado.links.map((link) => <li key={`${link.titulo}-${link.dominio}`}><span>{link.titulo}</span><small>{link.dominio}</small></li>)}</ul> : null}
      {resultado.itens?.length ? <ul>{resultado.itens.map((item) => <li key={item}>{item}</li>)}</ul> : null}
      {resultado.imagens?.length ? <div className="ilha-agente__imagens">{resultado.imagens.map((src, i) => <img key={`${src}-${i}`} src={src} alt={`Resultado ${i + 1}`} />)}</div> : null}
    </div>
  );
}

export function DetalheAgente({ agenteId, onVoltar }: { agenteId: string; onVoltar: () => void }) {
  const navigate = useNavigate();
  const estado = useProjetos();
  const agora = useAgora();
  const { agentes } = useIlha();
  const agente = agentes.find((item) => item.id === agenteId);
  const passos = passosDoAgente(estado, agenteId, agora);
  const passoAtual = [...passos].reverse().find((passo) => passo.status === 'executando') ?? passos.at(-1) ?? null;
  const [mensagem, setMensagem] = useState('');

  if (!agente) return <div className="ilha-agente-vazio"><p>Este agente não está no projeto mostrado.</p><button type="button" onClick={onVoltar}>Voltar</button></div>;

  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    const texto = mensagem.trim();
    if (!texto) return;
    enviarParaAgente(agente.id, texto);
    setMensagem('');
  };

  return (
    <section className="ilha-agente" style={{ '--ilha-agente': agente.cor } as CSSProperties} aria-labelledby="ilha-agente-nome">
      <div className="ilha-agente__lateral">
        <button type="button" className="ilha-voltar" onClick={onVoltar}>← Voltar</button>
        <SoraOrb size={88} color={agente.cor} state={agente.orb} movimento={agente.movimento} title={agente.nome} />
        <div className="ilha-agente__identidade"><h2 id="ilha-agente-nome">{agente.nome}</h2><p>{agente.funcao}</p><span>{agente.rotulo}</span></div>
        <ol className="ilha-agente__passos" aria-label={`Passos de ${agente.nome}`}>
          {passos.map((passo) => <li key={passo.id} aria-current={passo.status === 'executando' ? 'step' : undefined}>
            {passo.status === 'executando'
              ? <SoraOrb size={16} color={agente.cor} state="working" movimento={agente.movimento} glow={false} decorative />
              : <span className={`ilha-agente__check ilha-agente__check--${passo.status}`} aria-hidden="true">{passo.status === 'concluido' ? '✓' : '!'}</span>}
            <span><RotuloPasso passo={passo} /></span>
          </li>)}
        </ol>
      </div>
      <div className="ilha-agente__principal">
        <div className="ilha-agente__progresso"><span><b>Progresso</b><small>{agente.progresso}%</small></span><progress max="100" value={agente.progresso} aria-label={`Progresso de ${agente.nome}: ${agente.progresso}%`} /></div>
        <article className="ilha-agente__passo-atual">
          <span className="ilha-eyebrow">{passoAtual?.status === 'executando' ? 'Executando agora' : 'Último passo'}</span>
          <h3 className={!passoAtual ? 'ilha-agente__estado-vazio' : undefined}>{passoAtual ? <RotuloPasso passo={passoAtual} /> : 'Aguardando o primeiro passo'}</h3>
          {passoAtual?.texto && passoAtual.texto !== passoAtual.acao && <p>{passoAtual.texto}</p>}
          {passoAtual?.parametros && <><h4>Parâmetros</h4><pre>{JSON.stringify(passoAtual.parametros, null, 2)}</pre></>}
          {passoAtual && <><h4>Resultado</h4><Resultado passo={passoAtual} /></>}
        </article>
        <div className="ilha-agente__acoes">
          <button type="button" className="ilha-botao ilha-botao--secundario" onClick={() => navigate(`/chat/${agente.id}`)}>Abrir chat do agente</button>
          <form onSubmit={enviar}>
            <label htmlFor={`ilha-mensagem-${agente.id}`}>Mensagem para {agente.nome}</label>
            <div><input id={`ilha-mensagem-${agente.id}`} value={mensagem} onChange={(evento) => setMensagem(evento.target.value)} placeholder={`Mensagem para ${agente.nome}…`} /><button type="submit" disabled={!mensagem.trim()} aria-label={`Enviar mensagem para ${agente.nome}`}>↑</button></div>
          </form>
        </div>
      </div>
    </section>
  );
}
