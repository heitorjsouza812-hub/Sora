import { useState, type FormEvent } from 'react';
import { Button, Input } from '../base';
import { decidirPedidoAtencao } from '../../state/atencao';
import { BotoesAprovacao, CabecaPedido } from './decisao';
import { ROTULOS_DECISAO, aceitaSempreLiberar } from './rotulos';
import { useOrigemDoPedido } from './useOrigemDoPedido';
import type { PedidoAtencao } from './tipos';
import './pendencias.css';

export function CartaoPrecisaDeVoce({ pedido, compacto = false, semGrupo = false }: { pedido: PedidoAtencao; compacto?: boolean; semGrupo?: boolean }) {
  const [resposta, setResposta] = useState('');
  const origem = useOrigemDoPedido(pedido);
  const agir = (acao: string, valor?: string) => void decidirPedidoAtencao(pedido.id, acao, valor).catch(() => undefined);
  const responder = (evento: FormEvent) => {
    evento.preventDefault();
    const valor = resposta.trim();
    if (valor && !pedido.enviando) agir('responder', valor);
  };
  const textoOrigem = origem.nome ? <>{origem.nome}{origem.grupo && !semGrupo ? ` · grupo ${origem.grupo}` : ''}</> : undefined;

  return (
    <section className={`pend-card pend-precisa${compacto ? ' pend-compacto' : ''}`} aria-label="Precisa de você" data-pendencia={pedido.tipo}>
      <CabecaPedido cor={origem.cor} movimento={origem.movimento} origem={textoOrigem} />
      <div className="pend-conteudo">
        <h3>{pedido.titulo}</h3>
        <p className="pend-texto">{pedido.resumo}</p>
        {pedido.detalhes && <p className="pend-dano">{pedido.detalhes}</p>}
      </div>
      {pedido.tipo === 'pergunta' ? <>
        {!!pedido.opcoes?.length && <div className="pend-acoes" role="group" aria-label="Respostas">
          {pedido.opcoes.map((opcao, indice) => <Button key={opcao.valor} tamanho="M" variante={opcao.tom === 'perigo' ? 'perigo' : indice === 0 ? 'primario' : 'secundario'} disabled={pedido.enviando} onClick={() => agir('responder', opcao.valor)}>{opcao.rotulo}</Button>)}
        </div>}
        {pedido.aceitaRespostaLivre && <form className="pend-livre" onSubmit={responder}>
          <Input rotulo="Sua resposta" rotuloOculto value={resposta} onChange={evento => setResposta(evento.target.value)} placeholder="Escreva sua resposta…" disabled={pedido.enviando} />
          <Button type="submit" tamanho="M" variante="primario" disabled={!resposta.trim() || pedido.enviando}>Enviar</Button>
        </form>}
      </> : pedido.tipo === 'envio' ? <div className="pend-acoes" role="group" aria-label="Decisão">
        <Button tamanho="M" variante="primario" disabled={pedido.enviando} onClick={() => agir('enviar')}>{ROTULOS_DECISAO.enviar}</Button>
        <Button tamanho="M" variante="perigo" disabled={pedido.enviando} onClick={() => agir('descartar')}>{ROTULOS_DECISAO.descartar}</Button>
      </div> : <BotoesAprovacao desabilitado={pedido.enviando} onPermitir={() => agir('aprovar')} onSempre={aceitaSempreLiberar(pedido.acao) ? () => agir('sempre_permitir') : undefined} onRecusar={() => agir('recusar')} />}
      {pedido.erro && <p className="pend-erro" role="alert">{pedido.erro}</p>}
    </section>
  );
}
