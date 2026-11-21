import { useState, type CSSProperties, type FormEvent, type ReactNode } from 'react';
import { Button, Input } from '../base';
import { SoraOrb } from '../mascot';
import { decidirPedidoAtencao } from '../../state/atencao';
import { BotoesAprovacao, CabecaPedido } from './decisao';
import { ProporInstrucoes } from './ProporInstrucoes';
import { ROTULOS_DECISAO, tempoRelativo } from './rotulos';
import { registrarDecisao } from './registro';
import { useOrigemDoPedido } from './useOrigemDoPedido';
import type { PedidoAtencao } from './tipos';
import './pendencias.css';

interface Props {
  pedido: PedidoAtencao;
  compacto?: boolean;
  semGrupo?: boolean;
  /** Faixa da central: sem caixa, com a origem (orb, nome, hora) no lugar do rótulo "Precisa de você". */
  faixa?: boolean;
  /** Atalho à direita da linha de origem (só na faixa). */
  atalho?: ReactNode;
}

/** Senha segura (Onda 2): a senha vai direto para o campo da página do bot; o bot não a vê. O campo
 *  some depois do envio (o texto não fica no estado do app depois que o pedido sai da lista). */
function CampoSenhaSegura({ pedido }: { pedido: PedidoAtencao }) {
  const [senha, setSenha] = useState('');
  const [ver, setVer] = useState(false);
  const enviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (!senha || pedido.enviando) return;
    const valor = senha;
    setSenha('');
    registrarDecisao(pedido.id, 'preencher_senha');
    void decidirPedidoAtencao(pedido.id, 'preencher_senha', valor).catch(() => undefined);
  };
  const recusar = () => { registrarDecisao(pedido.id, 'recusar'); void decidirPedidoAtencao(pedido.id, 'recusar').catch(() => undefined); };
  return <form className="pend-senha" onSubmit={enviar} autoComplete="off">
    <label className="pend-senha__campo"><span>Senha</span>
      <span className="pend-senha__linha">
        <input type={ver ? 'text' : 'password'} value={senha} onChange={e => setSenha(e.target.value)} autoComplete="current-password" disabled={pedido.enviando} aria-describedby={`senha-ajuda-${pedido.id}`} />
        <button type="button" className="pend-senha__ver" aria-pressed={ver} onClick={() => setVer(v => !v)}>{ver ? 'Ocultar' : 'Mostrar'}</button>
      </span>
      <small id={`senha-ajuda-${pedido.id}`}>A senha não é guardada e o bot não a vê: ela vai direto para o campo da página.</small>
    </label>
    <div className="pend-acoes" role="group" aria-label="Decisão">
      <Button type="submit" tamanho="M" variante="primario" disabled={!senha || pedido.enviando}>Preencher</Button>
      <Button type="button" tamanho="M" variante="secundario" disabled={pedido.enviando} onClick={recusar}>Eu mesmo faço</Button>
    </div>
  </form>;
}

export function CartaoPrecisaDeVoce({ pedido, compacto = false, semGrupo = false, faixa = false, atalho }: Props) {
  const [resposta, setResposta] = useState('');
  const origem = useOrigemDoPedido(pedido);
  const agir = (acao: string, valor?: string) => { registrarDecisao(pedido.id, acao); void decidirPedidoAtencao(pedido.id, acao, valor).catch(() => undefined); };
  const responder = (evento: FormEvent) => {
    evento.preventDefault();
    const valor = resposta.trim();
    if (valor && !pedido.enviando) agir('responder', valor);
  };
  const hora = tempoRelativo(pedido.criadoEm);
  const grupo = origem.grupo && !semGrupo ? ` · grupo ${origem.grupo}` : '';
  const estilo = { '--cor': origem.cor } as CSSProperties;

  return (
    <section className={`pend-card pend-precisa${compacto ? ' pend-compacto' : ''}${faixa ? ' pend-faixa' : ''}`} style={estilo} aria-label="Precisa de você" aria-busy={pedido.enviando || undefined} data-pendencia={pedido.tipo} data-pedido-id={pedido.id} tabIndex={-1}>
      {faixa
        ? <header className="pend-origem-linha">
            <span className="pend-orb"><SoraOrb size={24} color={origem.cor} movimento={origem.movimento} state={pedido.enviando ? 'thinking' : 'idle'} glow={false} decorative seed={11} /></span>
            {origem.nome && <b className="pend-quem">{origem.nome}</b>}
            {(grupo || hora) && <span className="pend-quando">{grupo}{hora ? ` · ${hora}` : ''}</span>}
            {atalho}
          </header>
        : <CabecaPedido origem={compacto || grupo ? <>{origem.nome}{grupo}</> : undefined} hora={hora} />}
      <div className="pend-conteudo">
        <h3>{pedido.titulo}</h3>
        <p className="pend-texto">{pedido.resumo}</p>
        {pedido.proposta && <ProporInstrucoes proposta={pedido.proposta} />}
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
      </> : pedido.acao === 'preencher_senha' ? <CampoSenhaSegura pedido={pedido} />
      : pedido.tipo === 'envio' ? <div className="pend-acoes" role="group" aria-label="Decisão">
        <Button tamanho="M" variante="primario" disabled={pedido.enviando} onClick={() => agir('enviar')}>{ROTULOS_DECISAO.enviar}</Button>
        <Button tamanho="M" variante="perigo" disabled={pedido.enviando} onClick={() => agir('descartar')}>{ROTULOS_DECISAO.descartar}</Button>
      </div> : <BotoesAprovacao desabilitado={pedido.enviando} onPermitir={() => agir('aprovar')} onSempre={pedido.opcoes?.some(o => o.valor === 'sempre_permitir') ? () => agir('sempre_permitir') : undefined} onRecusar={() => agir('recusar')} />}
      {pedido.erro && <p className="pend-erro" role="alert">{pedido.erro}</p>}
    </section>
  );
}
