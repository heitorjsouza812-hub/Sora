import { useEffect, useRef } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { CartaoRascunhoBot } from '../components/builder';
import { CartaoPrecisaDeVoce } from '../components/pendencias/CartaoPrecisaDeVoce';
import { CartaoPropostaGrupo } from '../components/pendencias/CartaoPropostaGrupo';
import { MessageComposer } from '../components/ui/MessageComposer';
import { MensagemChat } from '../components/ui/MensagemChat';
import { ZonaSoltar } from '../components/anexos';
import { usePrecisaDeVoce } from '../state/atencao';
import { useSoraId } from '../state/bots';
import { carregarPropostasPendentes, carregarRascunhosPendentes, useCartoesSora } from '../state/sora';
import {
  abrirProjeto, anexarEnvio, conversarComSora, gerandoNa, mensagensDa, pararGeracao,
  projetoAtivo, textoVisivel, useAgora, useProjetos,
} from '../state/projetos';

export default function SoraChat() {
  const estado = useProjetos();
  const agora = useAgora();
  const cartoes = useCartoesSora();
  const atencao = usePrecisaDeVoce();
  const soraId = useSoraId();
  const fimRef = useRef<HTMLDivElement>(null);
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
  // Rola só a lista da conversa (scrollIntoView rolaria também a casca e esconderia a barra do topo).
  useEffect(() => { const lista = fimRef.current?.parentElement; if (lista) lista.scrollTop = lista.scrollHeight; }, [assinatura, cartoes.rascunhos.length, cartoes.propostas.length, pedidosDaSora.length]);

  const gerando = !!projeto && gerandoNa(estado, projeto.id, agora);
  const pensando = !!projeto?.mensagensPendentes && !gerando;

  return <AppShell>
    <main className="conversation sora-main-chat" aria-label="Conversa com a Sora">
      <ZonaSoltar className="conversation-drop">
        <div className="conversation-area">
          <div className="conversation-scroll" aria-live="polite" aria-relevant="additions">
            {!mensagens.length && !pensando && <section className="sora-chat-empty">
              <SoraOrb size={150} color="#E2ECFF" state="idle" title="Sora" />
              <h1>Converse com a Sora</h1>
              <p>Explique o que você precisa. Ela pode criar um bot, reunir um grupo ou ajudar diretamente.</p>
            </section>}
            {mensagens.map(mensagem => <div className="chat-item" key={mensagem.id}>
              <MensagemChat m={mensagem} agora={agora} nome={mensagem.autor === 'usuario' ? undefined : 'Sora'} avatar={mensagem.autor === 'usuario' ? undefined : <SoraOrb size={30} color="#E2ECFF" state={textoVisivel(mensagem, agora).gerando ? 'thinking' : 'idle'} glow={false} decorative seed={31} />} />
            </div>)}
            {pensando && <div className="assistant-row thinking-row"><SoraThinking size={56} color="#E2ECFF" label="Sora está pensando…" /></div>}
            {cartoes.rascunhos.map(rascunho => <CartaoRascunhoBot key={rascunho.id} rascunho={rascunho} />)}
            {cartoes.propostas.map(proposta => <CartaoPropostaGrupo key={proposta.id} proposta={proposta} />)}
            {pedidosDaSora.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} />)}
            <div ref={fimRef} />
          </div>
        </div>
        <div className="chat-composer">
          <MessageComposer placeholder="Mensagem para a Sora…" compact
            processing={pensando}
            onSend={(texto, anexos) => { void anexarEnvio(anexos, enviados => conversarComSora(texto, undefined, enviados)); }}
            gerando={gerando} onParar={() => projeto && pararGeracao(projeto.id)} />
        </div>
      </ZonaSoltar>
    </main>
  </AppShell>;
}
