// Novo chat: a Sora grande acima de "Em que posso te ajudar hoje?" (como na demo).
// Chegada (~1,6 s, só na 1ª abertura da sessão) → ocioso; ouvindo (olha para o campo) ao digitar ou
// com o microfone ao vivo; ao enviar: pensando + pulso, encolhe e vai para a conversa.
// A barra lateral continua vazia até o primeiro envio.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { MessageComposer } from '../components/ui/MessageComposer';
import type { SVGProps } from 'react';
import { TeamIcon } from '../components/ui/Icons';
import { anexarEnvio, criarAgenteIndependente, criarProjeto, novoChat, useProjetos } from '../state/projetos';
import type { Anexo } from '../components/anexos';
import { AvisoSemProvedor } from '../components/sessao';

const sugestoes: [string, string][] = [
  ['Criar campanha', 'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.'],
  ['Pesquisar mercado', 'Faça uma pesquisa de mercado sobre cafeterias no meu bairro, com concorrentes e preços.'],
  ['Planejar posts', 'Planeje os posts do mês para o Instagram da minha loja.'],
  ['Resumir e-mails', 'Resuma meus e-mails da semana e sugira respostas.'],
];

/** A chegada só acontece na primeira abertura da sessão (lido uma vez por carga da página). */
let chegadaPendente = (() => {
  try {
    if (sessionStorage.getItem('sora.chegou')) return false;
    sessionStorage.setItem('sora.chegou', '1');
    return true;
  } catch { return false; }
})();

/** Uma pessoa só (o agente independente), para diferenciar do ícone de equipe. */
const AgenteIcon = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" aria-hidden="true" {...props}><circle cx="12" cy="8.5" r="3.6" /><path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" /></svg>;

/** Como o pedido é atendido: a Sora monta uma EQUIPE (vira uma pasta em CHATS) ou cria UM agente independente. */
type ModoEnvio = 'equipe' | 'agente';
const CHAVE_MODO = 'sora.modo-envio.v1';
const lerModo = (): ModoEnvio => { try { return localStorage.getItem(CHAVE_MODO) === 'agente' ? 'agente' : 'equipe'; } catch { return 'equipe'; } };

function SeletorModo({ modo, onChange }: { modo: ModoEnvio; onChange: (m: ModoEnvio) => void }) {
  const opcoes: [ModoEnvio, string, string, typeof TeamIcon][] = [
    ['equipe', 'Equipe', 'A Sora monta uma equipe de agentes (fica numa pasta em Chats)', TeamIcon],
    ['agente', 'Agente independente', 'A Sora cria um único agente para este pedido (aparece solto em Chats)', AgenteIcon],
  ];
  return (
    <div className="modo-envio" role="radiogroup" aria-label="Quem faz o trabalho"
      onKeyDown={(ev) => {
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(ev.key)) return;
        ev.preventDefault();
        const m = modo === 'equipe' ? 'agente' : 'equipe';
        onChange(m);
        ev.currentTarget.querySelector<HTMLButtonElement>(`[data-modo="${m}"]`)?.focus();
      }}>
      {opcoes.map(([id, rotulo, dica, Icone]) => (
        <button key={id} type="button" role="radio" data-modo={id} aria-checked={modo === id} tabIndex={modo === id ? 0 : -1}
          title={dica} aria-label={rotulo} onClick={() => onChange(id)}><Icone /><span>{rotulo}</span></button>
      ))}
    </div>
  );
}

export default function Home() {
  const [chegando, setChegando] = useState(() => chegadaPendente);
  const [ouvindo, setOuvindo] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [partindo, setPartindo] = useState(false);
  const [pulso, setPulso] = useState(0);
  const [texto, setTexto] = useState('');
  const [modo, setModo] = useState<ModoEnvio>(lerModo);
  const escolherModo = (m: ModoEnvio) => { setModo(m); try { localStorage.setItem(CHAVE_MODO, m); } catch { /* só nesta sessão */ } };
  const timers = useRef<number[]>([]);
  const navigate = useNavigate();
  const { sora } = useProjetos();

  useEffect(() => { chegadaPendente = false; novoChat(); }, []);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  const enviar = (pedido: string, anexos: Anexo[] = []) => {
    if (enviado) return;
    setEnviado(true);
    setOuvindo(false);
    setPulso((p) => p + 1);
    timers.current = [
      window.setTimeout(() => setPartindo(true), 650),
      window.setTimeout(() => {
        // a conversa (e o item em CHATS) só nasce agora, junto com a ida para o chat
        if (modo === 'agente') {
          const ag = anexarEnvio(anexos, () => criarAgenteIndependente(pedido));
          navigate(`/chat/${ag.id}`);
          return;
        }
        const p = anexarEnvio(anexos, () => criarProjeto(pedido, undefined, { tipo: 'chat' }));
        navigate(`/projeto/${p.id}`);
      }, 1150),
    ];
  };

  const estado = enviado ? 'thinking' : chegando ? 'arriving' : ouvindo ? 'listening' : 'idle';

  return (
    <AppShell titulo="Novo chat" acoes={<span />}>
      <main className="home-screen">
        <div className={`hero-orb ${partindo ? 'orb-departing' : ''}`}>
          <SoraOrb
            size={260}
            color={sora.cor}
            state={estado}
            lookAt={ouvindo ? { x: -0.1, y: 0.85 } : null}
            pulseKey={pulso}
            seed={0}
            onArrived={() => setChegando(false)}
            title={enviado ? `${sora.nome} pensando` : `${sora.nome} pronta para ajudar`}
          />
        </div>
        <h1>Em que posso te ajudar hoje?</h1>
        <AvisoSemProvedor />
        <div className="hero-composer">
          <MessageComposer
            placeholder={modo === 'agente' ? 'Descreva o que o agente deve fazer…' : `Peça qualquer coisa à ${sora.nome}…`}
            tools
            value={texto}
            onValueChange={setTexto}
            processing={enviado}
            onActivity={(ativo) => { if (!enviado) setOuvindo(ativo); }}
            onSend={enviar}
            extras={<SeletorModo modo={modo} onChange={escolherModo} />}
          />
        </div>
        <div className="suggestions" aria-label="Sugestões">
          {sugestoes.map(([rotulo, pedido]) => <button type="button" key={rotulo} onClick={() => setTexto(pedido)}>{rotulo}</button>)}
        </div>
      </main>
    </AppShell>
  );
}
