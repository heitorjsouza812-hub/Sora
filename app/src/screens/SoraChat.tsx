import { mensagemDeErro } from '../api/cliente';
import { toast } from '../components/base';
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { InicioSora, aoDeixarPedidoInicial, consumirPedidoInicial } from '../components/inicio';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { CartaoRascunhoBot } from '../components/builder';
import { CartaoPrecisaDeVoce } from '../components/pendencias/CartaoPrecisaDeVoce';
import { CartaoPropostaGrupo } from '../components/pendencias/CartaoPropostaGrupo';
import { MessageComposer } from '../components/ui/MessageComposer';
import { HistoricoConversa } from '../components/ui/HistoricoConversa';
import { IrParaFim } from '../components/ui/IrParaFim';
import { useRolagemFim } from '../components/ui/useRolagemFim';
import { useIrParaMensagemDaConversa } from '../components/ui/useIrParaMensagem';
import { MensagemChat } from '../components/ui/MensagemChat';
import { ZonaSoltar } from '../components/anexos';
import { usePrecisaDeVoce } from '../state/atencao';
import { useSoraId } from '../state/bots';
import { carregarPropostasPendentes, carregarRascunhosPendentes, useCartoesSora } from '../state/sora';
import {
  abrirProjeto, anexarEnvio, conversarComSora, gerandoNa, mensagensDa, pararConversa,
  projetoAtivo, textoVisivel, useAgora, useProjetos,
} from '../state/projetos';

export default function SoraChat() {
  const estado = useProjetos();
  const [rascunho, setRascunho] = useState('');
  const focoSinal = (useLocation().state as { focarCampo?: number } | null)?.focarCampo;
  useEffect(() => {
    const pedido = consumirPedidoInicial();
    // A galeria deixa o pedido em uma caixa externa ao React; consumir no efeito é seguro no StrictMode.
    // oxlint-disable-next-line react/set-state-in-effect
    if (pedido !== null) setRascunho(pedido);
    // tela já aberta: "Novo bot" do menu Criar novo deixa o pedido e avisa
    return aoDeixarPedidoInicial(() => { const novo = consumirPedidoInicial(); if (novo !== null) setRascunho(novo); });
  }, []);
  const agora = useAgora();
  const cartoes = useCartoesSora();
  const atencao = usePrecisaDeVoce();
  const soraId = useSoraId();
  const projeto = projetoAtivo(estado);

  useEffect(() => {
    void carregarRascunhosPendentes().catch(() => undefined);
    void carregarPropostasPendentes().catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!estado.carregando && !projeto && estado.projetos[0]) abrirProjeto(estado.projetos[0].id);
  }, [estado.carregando, estado.projetos, projeto]);

  const mensagens = projeto ? mensagensDa(estado, projeto.id, agora) : [];
  // Pergunta/aprovação da própria Sora chega com agente_id = id dela; fora de grupo, é deste chat.
  const pedidosDaSora = atencao.lista.filter(pedido => !pedido.grupoId && (!pedido.botId || pedido.botId === soraId));
  const assinatura = mensagens.map(mensagem => `${mensagem.id}:${textoVisivel(mensagem, agora).texto.length}`).join('|');
  const { ref: rolagemRef, onScroll: aoRolar, noFim, novas, irParaFim, seguirFim } = useRolagemFim(mensagens.map(m => m.id), assinatura + ':' + cartoes.rascunhos.length + ':' + cartoes.propostas.length + ':' + pedidosDaSora.length);

  useIrParaMensagemDaConversa(projeto?.id);
  const gerando = !!projeto && gerandoNa(estado, projeto.id, agora);
  const pensando = !!projeto?.mensagensPendentes && !gerando;

  return <AppShell>
    <main className="conversation sora-main-chat" aria-label="Conversa com a Sora">
      <ZonaSoltar className="conversation-drop">
        <div className="conversation-area">
          <div className="conversation-scroll" ref={rolagemRef} onScroll={aoRolar} aria-live="polite" aria-relevant="additions">
            <HistoricoConversa conversaId={projeto?.id} />
            {estado.carregando && <p role="status">Carregando conversa…</p>}
            {!mensagens.length && !pensando && <section className="sora-chat-empty">
              <SoraOrb size={150} color="#E2ECFF" state="idle" title="Sora" />
              <h1>Converse com a Sora</h1>
              <p>Explique o que você precisa. Ela pode criar um bot, reunir um grupo ou ajudar diretamente.</p>
              <InicioSora onPreencher={setRascunho} />
            </section>}
            {mensagens.map(mensagem => <div className="chat-item" data-chave={mensagem.id} key={mensagem.id}>
              <MensagemChat m={mensagem} agora={agora} nome={mensagem.autor === 'usuario' ? undefined : 'Sora'} avatar={mensagem.autor === 'usuario' ? undefined : <SoraOrb size={30} color="#E2ECFF" state={textoVisivel(mensagem, agora).gerando ? 'thinking' : 'idle'} glow={false} decorative seed={31} />} />
            </div>)}
            {pensando && <div className="assistant-row thinking-row"><SoraThinking size={56} color="#E2ECFF" label="Sora está pensando…" /></div>}
            {cartoes.rascunhos.map(rascunho => <CartaoRascunhoBot key={rascunho.id} rascunho={rascunho} />)}
            {cartoes.propostas.map(proposta => <CartaoPropostaGrupo key={proposta.id} proposta={proposta} />)}
            {pedidosDaSora.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} />)}
          </div>
          {!noFim && <IrParaFim novas={novas} onClick={irParaFim} />}
        </div>
        <div className="chat-composer">
          <MessageComposer placeholder="Mensagem para a Sora…" compact focoSinal={focoSinal} value={rascunho} onValueChange={setRascunho}
            processing={pensando}
            onSend={(texto, anexos) => { seguirFim(); void anexarEnvio(anexos, enviados => conversarComSora(texto, undefined, enviados)); }}
            gerando={gerando} onParar={() => { if (projeto) void pararConversa(projeto.id).catch(erro => toast({ mensagem: mensagemDeErro(erro), tom: 'erro' })); }} />
        </div>
      </ZonaSoltar>
    </main>
  </AppShell>;
}
