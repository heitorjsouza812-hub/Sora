import { ConversaVoz } from '../components/ui/ConversaVoz';
import { mensagemDeErro } from '../api/cliente';
import { toast } from '../components/base';
// Chat de um agente (de uma equipe ou avulso): o trabalho dele ao vivo + conversa direta.
// À direita: abas "Trabalho" (painel de passos) e "Perfil" (orb, status, progresso, ferramentas).
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { abrirEditorAgente } from '../components/builder';
import { EntregaCard } from '../components/ui/EntregaCard';
import { MedidorContexto } from '../components/equipe/MedidorContexto';
import { FilaDoAgente } from '../components/equipe/FilaDoAgente';
import { PendenciasDoAgente } from '../components/equipe/PendenciasDoAgente';
import { PerfilNavegadorDoAgente } from '../components/equipe/PerfilNavegadorDoAgente';
import { CartaoPendencia } from '../components/pendencias/Pendencias';
import { CartaoPrecisaDeVoce } from '../components/pendencias/CartaoPrecisaDeVoce';
import { MessageComposer } from '../components/ui/MessageComposer';
import { IconButton, Button } from '../components/base';
import { ProgressBar } from '../components/ui/ProgressBar';
import { ShimmerText } from '../components/ui/ShimmerText';
import { useCelular, useMedia } from '../components/ui/useMedia';
import { PainelTrabalho } from '../components/work';
import { FERRAMENTAS_BASE, rotuloFerramenta } from '../data/ferramentas';
import { ZonaSoltar } from '../components/anexos';
import { CardErroModelo, definirErroSimulado, useErroSimulado } from '../components/erros';
import { PainelLateral } from '../components/layout/PainelLateral';
import { usePainelLateral } from '../components/layout/usePainelLateral';
import { ActivityIcon, TeamIcon } from '../components/ui/Icons';
import { IrParaFim } from '../components/ui/IrParaFim';
import { HistoricoConversa } from '../components/ui/HistoricoConversa';
import { TelaCarregando } from '../components/sessao';
import { MensagemChat } from '../components/ui/MensagemChat';
import { useRolagemFim } from '../components/ui/useRolagemFim';
import { useIrParaMensagemDaConversa } from '../components/ui/useIrParaMensagem';
import { usePrecisaDeVoce } from '../state/atencao';
import { AvisosMemoria, PainelMemoria } from '../components/memoria';
import { PainelRotinas } from '../components/rotinas/PainelRotinas';
import {
  anexarEnvio, enviarParaAgente, pendenciasDa, estadoAgente, execucoesDoAgente, gerandoNa, mensagensDa, pararConversa, passosDoAgente, textoVisivel, useAgora, useProjetos,
  type AgenteSora, type EstadoProjetos,
} from '../state/projetos';

type Item = { t: number; key: string; node: ReactNode };


function Perfil({ e, a, agora }: { e: EstadoProjetos; a: AgenteSora; agora: number }) {
  const [novaPendencia, setNovaPendencia] = useState(false);
  const st = estadoAgente(e, a.id, agora);
  const passos = passosDoAgente(e, a.id, agora).filter(p => p.tipo === 'ferramenta');
  const estadoFerramenta = (nome: string) => {
    const ps = passos.filter(p => p.ferramenta === nome);
    if (ps.some(p => p.status === 'executando')) return 'Em uso';
    if (ps.length) return 'Usado';
    return e.pluginsConectados.includes(nome) ? 'Conectado' : 'Disponível';
  };
  const base: readonly string[] = FERRAMENTAS_BASE;
  const ferramentas = [...new Set([...a.ferramentas, ...passos.map(p => p.ferramenta ?? '')])].filter(n => n && !base.includes(n));
  return (
    <div className="agent-profile">
      <p className="eyebrow tools-label">Função</p><p>{a.funcao}</p>
      <Button variante="fantasma" tamanho="P" onClick={() => abrirEditorAgente(a.id)}>Editar bot</Button>
      {st.status === 'trabalhando' && <><div className="progress-title"><span>Progresso</span><b>{st.progresso}%</b></div>
      <ProgressBar value={st.progresso} color={a.cor} label={a.nome} status={st.rotulo} /></>}
      <p className="eyebrow tools-label">Ferramentas</p>
      <div className="tools-list">
        {ferramentas.map(nome => {
          const s = estadoFerramenta(nome);
          return <div key={nome}><ActivityIcon /><strong>{rotuloFerramenta(nome)}</strong><span className={s === 'Em uso' ? 'agent-color' : ''}>{s}</span></div>;
        })}
        {!ferramentas.length && <p className="tools-empty">Nenhuma ferramenta usada ainda.</p>}
      </div>
      <MedidorContexto agenteId={a.id} />
      <FilaDoAgente agenteId={a.id} />
      <PerfilNavegadorDoAgente agenteId={a.id} />
      <div className="agent-pendencias" data-criando={novaPendencia}>
        <Button variante="fantasma" tamanho="P" aria-expanded={novaPendencia} onClick={() => setNovaPendencia(!novaPendencia)}>{novaPendencia ? 'Fechar formulário' : '+ Nova pendência'}</Button>
        <PendenciasDoAgente agenteId={a.id} />
      </div>
      <div className="agent-resources"><PainelRotinas key={`r-${a.id}`} agenteId={a.id} /><PainelMemoria key={`m-${a.id}`} agenteId={a.id} /></div>
      {a.instrucoes && <><p className="eyebrow tools-label">Instruções</p><p className="agent-instructions">{a.instrucoes}</p></>}
    </div>
  );
}

export default function AgentChat() {
  const { agente: id = '' } = useParams();
  const [params] = useSearchParams();
  const e = useProjetos();
  const atencao = usePrecisaDeVoce();
  const agora = useAgora();
  const celular = useCelular();
  const painelEmFolha = useMedia('(max-width: 1199px)');
  const a = e.agentes[id];
  const st = a ? estadoAgente(e, a.id, agora) : null;
  const painel = usePainelLateral('sora.painel.agente', 'trabalho');
  const [folha, setFolha] = useState(params.get('painel') === 'trabalho');
  const [faixaVoz, setFaixaVoz] = useState<HTMLElement | null>(null);
  const { setAba } = painel;
  // "Ver trabalho" vindo de outra tela (?painel=trabalho) abre direto na aba Trabalho
  useEffect(() => { if (params.get('painel') === 'trabalho') setAba('trabalho'); }, [params, setAba]);
  const abaAtual = painel.aba;
  const verTrabalho = () => { painel.setAba('trabalho'); painel.setRecolhido(false); setFolha(true); };

  const erroModelo = useErroSimulado() === 'modelo';
  const itens: Item[] = [];
  if (a) {
    const xs = execucoesDoAgente(e, a.id).filter(x => x.inicio <= agora);
    // quem entregou para este agente (handoff na equipe)
    const anterior = e.execucoes.find(x => x.roteiro.some(r => r.tipo === 'handoff' && r.paraAgenteId === a.id));
    const h = anterior?.roteiro.find(r => r.tipo === 'handoff' && r.paraAgenteId === a.id);
    const de = anterior ? e.agentes[anterior.agenteId] : undefined;
    if (anterior && h && de) {
      itens.push({ t: h.inicio, key: 'recebeu', node: (
        <div className="handoff-banner" style={{ '--agent': de.cor } as CSSProperties}><strong>{de.nome}</strong> {h.texto.replace(/^Enviou/, 'enviou').replace(` para ${a.nome}`, '')} <span aria-hidden="true">↘</span></div>
      ) });
    }
    xs.forEach(x => {
      const prompt = x.roteiro.find(r => r.tipo === 'prompt');
      if (prompt && prompt.origem !== 'usuario') {
        itens.push({ t: x.inicio, key: `p-${x.id}`, node: (
          <div className="assistant-row"><SoraOrb size={34} color={e.sora.cor} state="coordinating" glow={false} decorative seed={71} /><p><strong>{e.sora.nome}</strong>&nbsp; {prompt.texto}</p></div>
        ) });
      }
      const fim = Math.max(x.inicio, ...x.roteiro.map(r => r.fim ?? r.inicio));
      if (x.status === 'executando') {
        const atual = [...x.roteiro].reverse().find(r => r.tipo !== 'prompt');
        itens.push({ t: agora, key: `w-${x.id}`, node: (
          <div className="pensando-linha" role="status">
            <SoraOrb size={28} color={a.cor} movimento={a.tipoMovimento} state="working" glow={false} decorative seed={3} />
            <ShimmerText>{atual?.tipo === 'ferramenta' ? `${atual.texto}… (${atual.acao})` : atual?.texto ?? `${a.verbo}…`}</ShimmerText>
            {!celular && <button type="button" className="ver-passos" onClick={verTrabalho}>Ver passos</button>}
          </div>
        ) });
      } else if (x.tarefaId) {
        const proj = x.projetoId ? e.projetos.find(p => p.id === x.projetoId) : undefined;
        const ent = proj?.entregas[a.id];
        itens.push({ t: fim, key: `e-${x.id}`, node: <>
          <div className="assistant-row agent-copy"><SoraOrb size={34} color={a.cor} movimento={a.tipoMovimento} state="done" glow={false} decorative seed={4} /><p><strong className="agent-color">{a.nome}</strong>&nbsp; Pronto! {ent ? `${ent.titulo}: ${ent.resumo}.` : ''}</p></div>
          {ent && <div className="agent-delivery"><EntregaCard entrega={ent} agente={a} /></div>}
        </> });
      }
    });
    // Pergunta/aprovação desta conversa já vem como pendência (cartão com prazo e "Sempre permitir");
    // a lista de atenção traz o mesmo id, então só entra o que não está nas pendências.
    const pendencias = pendenciasDa(e, a.conversaId);
    const idsPendencias = new Set(pendencias.map(x => x.id));
    pendencias.forEach(x => itens.push({ t: 1e15 + x.desde, key: `pend-${x.id}`, node: <CartaoPendencia p={x} cor={a.cor} /> }));
    atencao.lista.filter(pedido => pedido.botId === a.id && !idsPendencias.has(pedido.id)).forEach((pedido, indice) => itens.push({ t: 1e15 + 10_000 + indice, key: `atencao-${pedido.id}`, node: <CartaoPrecisaDeVoce pedido={pedido} /> }));
    const todas = mensagensDa(e, a.id, agora);
    // erro simulado do modelo: a resposta depois da última pergunta vira o card de erro
    const pergunta = erroModelo ? todas.filter(m => m.autor === 'usuario').pop() : undefined;
    if (pergunta) itens.push({
      t: pergunta.criadoEm + 1, key: 'erro-modelo',
      node: <CardErroModelo cor={a.cor} autor={a.nome} onTentarDeNovo={() => definirErroSimulado(null)} />,
    });
    // esperando o primeiro pedaço da resposta: o orb do bot com o texto em shimmer (nada de spinner)
    if (!erroModelo && gerandoNa(e, a.id, agora) && !todas.some(m => m.gerando) && !itens.some(i => i.key.startsWith('w-'))) {
      itens.push({ t: 1e15 - 1, key: 'pensando', node: <div className="pensando-linha"><SoraThinking size={28} color={a.cor} label={`${a.nome} está escrevendo…`} /></div> });
    }
    const ultimaRespostaId = [...todas].reverse().find(m => m.autor !== 'usuario')?.id;
    (pergunta ? todas.filter(m => m.autor === 'usuario' || m.criadoEm <= pergunta.criadoEm) : todas).forEach(m => itens.push({
      t: m.criadoEm, key: m.id,
      node: m.autor === 'usuario' ? <MensagemChat m={m} agora={agora} respostaDe={{ nome: a.nome, cor: a.cor, avatar: <SoraOrb size={24} color={a.cor} movimento={a.tipoMovimento} state="idle" glow={false} decorative seed={5} /> }} />
        : m.autor === 'sora'
          ? <MensagemChat m={m} agora={agora} ultima={m.id === ultimaRespostaId} nome={e.sora.nome} avatar={<SoraOrb size={24} color={e.sora.cor} state="coordinating" glow={false} decorative seed={72} />} />
          : <MensagemChat m={m} agora={agora} ultima={m.id === ultimaRespostaId} nome={a.nome} cor={a.cor}
            avatar={<SoraOrb size={24} color={a.cor} movimento={a.tipoMovimento} state={textoVisivel(m, agora).gerando ? 'working' : 'idle'} glow={false} decorative seed={5} />} />,
    }));
  }
  itens.sort((x, y) => x.t - y.t);
  const gerando = !!a && !erroModelo && gerandoNa(e, a.id, agora);
  const assinatura = a ? mensagensDa(e, a.id, agora).reduce((n, m) => n + textoVisivel(m, agora).texto.length, 0) : 0;
  const { ref: rolagemRef, onScroll: aoRolar, noFim, novas, irParaFim, seguirFim } = useRolagemFim(itens.map(i => i.key), assinatura);

  useIrParaMensagemDaConversa(a?.conversaId);
  if (e.carregando) return <TelaCarregando />;
  if (id === 'sora') return <Navigate to="/" replace />;
  if (!a || !st) return <Navigate to="/" replace />;

  return (
    <AppShell agenteId={a.id} menuItens={[{ rotulo: 'Ver trabalho', onClick: verTrabalho }]} acoes={<IconButton aria-label="Painel Trabalho" aria-pressed={painelEmFolha ? folha : !painel.recolhido} icone={<ActivityIcon />} onClick={() => painelEmFolha ? setFolha(!folha) : painel.setRecolhido(!painel.recolhido)} />}>
      <div className={`workspace-grid agent-workspace ${painel.recolhido ? 'panel-collapsed' : ''}`} style={{ '--agent': a.cor } as CSSProperties}>
        <main className="conversation" aria-label={`Conversa com ${a.nome}`}>
          <ZonaSoltar className="conversation-drop">
          <div className="conversation-area">
          <div className="conversation-scroll agent-scroll" ref={rolagemRef} onScroll={aoRolar} aria-live="polite" aria-relevant="additions">
            <HistoricoConversa conversaId={a.conversaId} />
            {!itens.length && (
              <div className="agent-empty">
                <SoraOrb size={112} color={a.cor} movimento={a.tipoMovimento} state="idle" seed={61} title={a.nome} />
                <h2>{a.avulso ? `Converse com ${a.nome}` : st.rotulo}</h2>
                <p>{a.avulso ? `${a.funcao}. Mande uma mensagem e acompanhe os passos no painel Trabalho.` : 'O trabalho aparecerá aqui assim que a etapa anterior for concluída.'}</p>
              </div>
            )}
            {itens.map(i => <div key={i.key} className="chat-item" data-chave={i.key}>{i.node}</div>)}
          </div>
          {!noFim && <IrParaFim novas={novas} onClick={irParaFim} />}
          </div>
          <div className="chat-composer">
            <AvisosMemoria agenteId={a.id} />
            <div ref={setFaixaVoz} className="conversa-voz-faixa" />
            <MessageComposer placeholder={`Mensagem para ${a.nome}…`} processing={st.status === 'trabalhando'} voz
              acoesDireita={<ConversaVoz key={a.id} agenteId={a.id} cor={a.cor} movimento={a.tipoMovimento} faixa={faixaVoz} />}
              onSend={(t, anexos) => { void anexarEnvio(anexos, enviados => enviarParaAgente(a.id, t, undefined, true, enviados)); seguirFim(); }}
              gerando={gerando} onParar={() => { void pararConversa(a.id).catch(erro => toast({ mensagem: mensagemDeErro(erro), tom: 'erro' })); }} />
          </div>
          </ZonaSoltar>
        </main>
        <PainelLateral
          peloCabecalho
          rotulo={`Painel de ${a.nome}`}
          aba={abaAtual} onAba={painel.setAba} recolhido={painel.recolhido} onRecolher={painel.setRecolhido}
          folhaAberta={folha} onFolha={setFolha}
          resumo={st.status === 'trabalhando' ? `${a.verbo}…` : st.rotulo || a.funcao}
          abas={[
            { id: 'trabalho', rotulo: 'Trabalho', icone: <ActivityIcon />, vivo: st.status === 'trabalhando' ? a.cor : null,
              conteudo: <PainelTrabalho agenteIds={[a.id]} agenteId={a.id} semSeletor className="side-work" /> },
            { id: 'perfil', rotulo: 'Recursos', icone: <TeamIcon />, conteudo: <Perfil e={e} a={a} agora={agora} /> },
          ]}
        />
      </div>
    </AppShell>
  );
}
