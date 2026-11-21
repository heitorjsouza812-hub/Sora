import { mensagemDeErro } from '../api/cliente';
import { toast } from '../components/base';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { InicioSora, aoDeixarPedidoInicial, consumirPedidoInicial } from '../components/inicio';
import { animarDescida, fantasma } from '../components/inicio/descida';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { CartaoRascunhoBot } from '../components/builder';
import { CartaoPrecisaDeVoce } from '../components/pendencias/CartaoPrecisaDeVoce';
import { CartaoPendencia } from '../components/pendencias/Pendencias';
import { AvisosMemoria } from '../components/memoria';
import { CartaoPropostaGrupo } from '../components/pendencias/CartaoPropostaGrupo';
import { MessageComposer } from '../components/ui/MessageComposer';
import { HistoricoConversa } from '../components/ui/HistoricoConversa';
import { IrParaFim } from '../components/ui/IrParaFim';
import { useRolagemFim } from '../components/ui/useRolagemFim';
import { useCelular } from '../components/ui/useMedia';
import { useIrParaMensagemDaConversa } from '../components/ui/useIrParaMensagem';
import { MensagemChat } from '../components/ui/MensagemChat';
import { ZonaSoltar } from '../components/anexos';
import { usePrecisaDeVoce } from '../state/atencao';
import { useSoraId } from '../state/bots';
import { carregarPropostasPendentes, carregarRascunhosPendentes, useCartoesSora } from '../state/sora';
import {
  abrirProjeto, anexarEnvio, conversarComSora, gerandoNa, mensagensDa, mandarAgora, pararConversa, pendenciasDa,
  projetoAtivo, textoVisivel, useAgora, useProjetos,
} from '../state/projetos';

// O mascote "chega" só na primeira abertura da sessão (CLAUDE.md §3.2); depois fica em repouso.
let jaChegou = false;

export default function SoraChat() {
  const estado = useProjetos();
  const celular = useCelular();
  const [rascunho, setRascunho] = useState('');
  const [focoLocal, setFocoLocal] = useState(0);
  const [ouvindo, setOuvindo] = useState(false);
  const [chegando, setChegando] = useState(!jaChegou);
  const focoSinal = Math.max(focoLocal, (useLocation().state as { focarCampo?: number } | null)?.focarCampo ?? 0) || undefined;
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
  // Cartões da cadeia (aprovação, pergunta, domínio) chegam com `conversa_id` e valem aqui mesmo que o pedido seja de um especialista.
  const pendencias = projeto ? pendenciasDa(estado, projeto.id) : [];
  const idsPendencias = new Set(pendencias.map(x => x.id));
  const pedidosDaSora = atencao.lista.filter(pedido => !pedido.grupoId && (!pedido.botId || pedido.botId === soraId) && !idsPendencias.has(pedido.id));
  const assinatura = mensagens.map(mensagem => `${mensagem.id}:${textoVisivel(mensagem, agora).texto.length}`).join('|');
  const { ref: rolagemRef, onScroll: aoRolar, noFim, novas, irParaFim, seguirFim } = useRolagemFim(mensagens.map(m => m.id), assinatura + ':' + cartoes.rascunhos.length + ':' + cartoes.propostas.length + ':' + pedidosDaSora.length + ':' + pendencias.length);

  useIrParaMensagemDaConversa(projeto?.id);
  const gerando = !!projeto && gerandoNa(estado, projeto.id, agora);
  // esperando o primeiro pedaço da resposta: a linha "pensando" (orb + texto em shimmer)
  // com cartão esperando o usuário, ninguém está "pensando": o trabalho parou até a decisão
  const pensando = gerando && !mensagens.some(m => m.gerando) && !pendencias.length && !pedidosDaSora.length;
  const ultimaRespostaId = [...mensagens].reverse().find(m => m.autor !== 'usuario')?.id;

  // Estado vazio: orb e compositor juntos no centro. Depois do 1º envio o compositor desce (FLIP).
  const vazio = !estado.carregando && !mensagens.length && !pensando && !cartoes.rascunhos.length && !cartoes.propostas.length && !pedidosDaSora.length && !pendencias.length;
  const compositor = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const rodapeVazio = useRef<HTMLDivElement>(null);
  const antes = useRef<{ rect: DOMRect; altura: number } | null>(null);
  const enviouDoCentro = useRef(false);
  useLayoutEffect(() => {
    const el = compositor.current;
    if (!el) return;
    if (vazio) return;
    const de = antes.current; antes.current = null;
    if (de && enviouDoCentro.current && !celular) animarDescida(el, de.rect, de.altura);
    enviouDoCentro.current = false;
  }, [vazio, celular]);

  const enviar = (texto: string, anexos: Parameters<typeof anexarEnvio>[0]) => {
    if (vazio && !celular && compositor.current) { // o que sai de cena fica como cópia por 120–320 ms
      antes.current = { rect: compositor.current.getBoundingClientRect(), altura: compositor.current.querySelector('.composer')?.getBoundingClientRect().height ?? 0 };
      enviouDoCentro.current = true;
      fantasma(hero.current, { orb: true });
      fantasma(rodapeVazio.current);
    }
    seguirFim();
    void anexarEnvio(anexos, enviados => conversarComSora(texto, undefined, enviados));
  };

  return <AppShell conversaId={projeto?.id} preferenciasBotId={soraId}>
    <main className={`conversation sora-main-chat${vazio ? ' is-vazio' : ''}${estado.carregando ? ' is-carregando' : ''}`} aria-label="Conversa com a Sora">
      <ZonaSoltar className="conversation-drop">
        <div className="conversation-area">
          {vazio && <section className="sora-hero" ref={hero} aria-label="Início da conversa">
            <div className="sora-hero-orb">
              <SoraOrb size={celular ? 96 : 120} color="#E2ECFF" state={chegando ? 'arriving' : ouvindo ? 'listening' : 'idle'} onArrived={() => { jaChegou = true; setChegando(false); }} title="Sora" />
            </div>
            <h1>Em que posso te ajudar hoje?</h1>
          </section>}
          <div className="conversation-scroll" ref={rolagemRef} onScroll={aoRolar} aria-live="polite" aria-relevant="additions">
            <HistoricoConversa conversaId={projeto?.id} />
            {estado.carregando && <p role="status" className="sr-only">Carregando conversa…</p>}
            {mensagens.map(mensagem => <div className="chat-item" data-chave={mensagem.id} key={mensagem.id}>
              <MensagemChat m={mensagem} agora={agora} ultima={mensagem.id === ultimaRespostaId} respostaDe={{ nome: 'Sora', avatar: <SoraOrb size={24} color="#E2ECFF" state="idle" glow={false} decorative seed={31} /> }} nome={mensagem.autor === 'usuario' ? undefined : 'Sora'} avatar={mensagem.autor === 'usuario' ? undefined : <SoraOrb size={24} color="#E2ECFF" state={textoVisivel(mensagem, agora).gerando ? 'thinking' : 'idle'} glow={false} decorative seed={31} />} />
            </div>)}
            {pensando && <div className="pensando-linha"><SoraThinking size={28} color="#E2ECFF" label="Sora está pensando…" /></div>}
            {cartoes.rascunhos.map(rascunho => <CartaoRascunhoBot key={rascunho.id} rascunho={rascunho} />)}
            {cartoes.propostas.map(proposta => <CartaoPropostaGrupo key={proposta.id} proposta={proposta} />)}
            {pendencias.map(pendencia => <CartaoPendencia key={pendencia.id} p={pendencia} cor="#E2ECFF" />)}
            {pedidosDaSora.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} />)}
          </div>
          {!noFim && <IrParaFim novas={novas} onClick={irParaFim} />}
        </div>
        <div className="chat-composer" ref={compositor}>
          {soraId && <AvisosMemoria agenteId={soraId} />}
          <MessageComposer placeholder="Mensagem para a Sora…" grande={vazio && !celular} focoSinal={focoSinal} value={rascunho} onValueChange={setRascunho}
            processing={pensando} onActivity={setOuvindo}
            onSend={enviar}
            gerando={gerando} onParar={() => { if (projeto) void pararConversa(projeto.id).catch(erro => toast({ mensagem: mensagemDeErro(erro), tom: 'erro' })); }}
            onMandarAgora={t => { if (projeto) void mandarAgora(projeto.id, t).catch(erro => toast({ mensagem: mensagemDeErro(erro), tom: 'erro' })); }} />
        </div>
        {vazio && <div className="sora-vazio-rodape" ref={rodapeVazio}>
          <InicioSora onPreencher={texto => { setRascunho(texto); setFocoLocal(Date.now()); }} />
        </div>}
      </ZonaSoltar>
    </main>
  </AppShell>;
}
