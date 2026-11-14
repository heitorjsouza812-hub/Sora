import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { mensagemDeErro } from '../api/cliente';
import { renomearGrupo } from '../api/grupos';
import { AppShell } from '../components/layout/AppShell';
import { Button } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { ZonaSoltar } from '../components/anexos';
import { IrParaFim } from '../components/ui/IrParaFim';
import { useRolagemFim } from '../components/ui/useRolagemFim';
import { CompositorGrupo } from '../components/grupos/CompositorGrupo';
import { EditarBotsDoGrupo, MenuDoGrupo } from '../components/grupos/GerirGrupo';
import { MembrosGrupo } from '../components/grupos/MembrosGrupo';
import { MensagemGrupo } from '../components/grupos/MensagemGrupo';
import { NovoGrupo } from '../components/grupos/NovoGrupo';
import { TarefasGrupo } from '../components/grupos/TarefasGrupo';
import { CartaoPrecisaDeVoce } from '../components/pendencias/CartaoPrecisaDeVoce';
import { carregarBots, useBots } from '../state/bots';
import { carregarGrupos, carregarMensagensDoGrupo, carregarTarefasDoGrupo, grupoPrecisaDeBots, receberGrupo, useGrupos } from '../state/grupos';
import { carregarPrecisaDeVoce, usePrecisaDeVoce } from '../state/atencao';
import '../components/grupos/grupos.css';

function DetalheGrupo({ grupoId }: { grupoId: string }) {
  const navigate = useNavigate();
  const estado = useGrupos();
  const atencao = usePrecisaDeVoce();
  const bots = useBots();
  const grupo = estado.lista.find(item => item.id === grupoId);
  const mensagens = estado.mensagens[grupoId] ?? [];
  const pedidos = atencao.lista.filter(pedido => pedido.grupoId === grupoId);
  const [resposta, setResposta] = useState<import('../api/grupos').MensagemGrupoApi | null>(null);
  const [editandoNome, setEditandoNome] = useState(false);
  const [nome, setNome] = useState('');
  const [editandoBots, setEditandoBots] = useState(false);
  const [erro, setErro] = useState('');
  const ultima = mensagens.at(-1);
  const { ref: rolagemRef, onScroll: aoRolar, noFim, novas, irParaFim, seguirFim } = useRolagemFim(mensagens.map(item => item.id), `${ultima?.id ?? ''}:${ultima?.texto.length ?? 0}`);
  useEffect(() => {
    void carregarMensagensDoGrupo(grupoId).catch(falha => setErro(mensagemDeErro(falha)));
    void carregarTarefasDoGrupo(grupoId).catch(() => undefined);
  }, [grupoId]);
  if (!grupo) return <div className="grp-vazio"><p>{estado.carregado ? 'Este grupo não foi encontrado.' : 'Carregando o grupo…'}</p>{estado.carregado && <Button tamanho="M" variante="secundario" onClick={() => navigate('/grupos')}>Voltar aos grupos</Button>}</div>;

  const lider = grupo.liderId ?? grupo.membros[0];
  const botsDoGrupo = bots.filter(bot => grupo.membros.includes(bot.id) && bot.id !== lider);
  const precisaDeBots = grupoPrecisaDeBots(grupo);
  const salvarNome = async () => {
    const valor = nome.trim();
    if (!valor || valor === grupo.nome) { setNome(grupo.nome); setEditandoNome(false); return; }
    try { receberGrupo(await renomearGrupo(grupo.id, valor)); setEditandoNome(false); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
  };
  const renomear = () => { setNome(grupo.nome); setEditandoNome(true); };

  return <section className="grp-detalhe" aria-label={`Grupo ${grupo.nome}`}>
    <header className="grp-cabecalho">
      <button type="button" className="grp-voltar" aria-label="Voltar aos grupos" onClick={() => navigate('/grupos')}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 6-6 6 6 6" /></svg></button>
      <div className="grp-titulo">{editandoNome ? <span className="grp-titulo-edicao"><input aria-label="Nome do grupo" value={nome} maxLength={80} onChange={evento => setNome(evento.target.value)} onKeyDown={evento => { if (evento.key === 'Enter') void salvarNome(); if (evento.key === 'Escape') setEditandoNome(false); }} autoFocus /><Button tamanho="P" variante="primario" onClick={() => void salvarNome()}>Salvar</Button></span> : <h2>{grupo.nome}</h2>}<span className="grp-sobretitulo">Sora + {botsDoGrupo.length} {botsDoGrupo.length === 1 ? 'bot' : 'bots'}</span></div>
      <MenuDoGrupo grupo={grupo} onRenomear={renomear} onGerirBots={() => setEditandoBots(true)} />
    </header>
    <MembrosGrupo membros={grupo.membros} liderId={grupo.liderId} grupoId={grupo.id} />
    <TarefasGrupo grupoId={grupo.id} membros={grupo.membros} liderId={grupo.liderId} tarefas={estado.tarefas[grupo.id]} />
    {precisaDeBots && <div className="grp-aviso" role="status">
      <p><b>Este grupo precisa de pelo menos 2 bots.</b> Ele ficou com {botsDoGrupo.length === 0 ? 'nenhum' : botsDoGrupo.length}. Adicione bots para voltar a conversar.</p>
      <Button tamanho="M" variante="primario" onClick={() => setEditandoBots(true)}>Adicionar bots</Button>
    </div>}
    <ZonaSoltar className="grp-conversa" desativada={precisaDeBots}>
      <div className="grp-area">
        <div className="grp-rolagem" ref={rolagemRef} onScroll={aoRolar}>
          <ol className="grp-mensagens" aria-live="polite" aria-relevant="additions">
            {mensagens.length === 0 && <li className="grp-nota">Converse com o grupo. Use @bot para direcionar ou @todos para chamar a equipe inteira.</li>}
            {mensagens.map(mensagem => <MensagemGrupo key={mensagem.id} mensagem={mensagem} todas={mensagens} soraId={lider} onResponder={setResposta} />)}
          </ol>
        </div>
        {!noFim && <IrParaFim novas={novas} onClick={irParaFim} />}
      </div>
      <div className="grp-rodape">
        {!!pedidos.length && <div className="grp-atencao">{pedidos.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} semGrupo />)}</div>}
        {precisaDeBots
          ? <p className="grp-travado" role="status">O campo de mensagem volta quando o grupo tiver pelo menos 2 bots.</p>
          : <CompositorGrupo grupoId={grupo.id} botsDoGrupo={botsDoGrupo} resposta={resposta} onCancelarResposta={() => setResposta(null)} onEnviado={() => setErro('')} aoSeguirFim={seguirFim} />}
        {erro && <p className="grp-erro grp-erro-faixa" role="alert">{erro}</p>}
      </div>
    </ZonaSoltar>
    <EditarBotsDoGrupo grupo={grupo} aberto={editandoBots} onFechar={() => setEditandoBots(false)} />
  </section>;
}

export default function Grupos() {
  const { grupoId } = useParams();
  const navigate = useNavigate();
  const grupos = useGrupos();
  const bots = useBots();
  const [novoAberto, setNovoAberto] = useState(false);
  const [botsProntos, setBotsProntos] = useState(false);
  useEffect(() => {
    void carregarGrupos().catch(() => undefined);
    void carregarPrecisaDeVoce().catch(() => undefined);
    void carregarBots().catch(() => undefined).finally(() => setBotsProntos(true));
  }, []);
  // Sem nenhum bot não há o que agrupar: nada de modal sem saída, só o caminho para criar o primeiro.
  const semBots = botsProntos && bots.length === 0 && grupos.lista.length === 0;
  const novo = <Button tamanho="M" variante="secundario" onClick={() => setNovoAberto(true)}>Novo grupo</Button>;
  return <AppShell titulo="Grupos" acoes={semBots ? undefined : novo}>
    {semBots
      ? <main className="grp-pagina grp-pagina-vazia">
        <div className="grp-vazio"><SoraOrb size={110} color="#E2ECFF" state="idle" decorative />
          <h2>Grupos reúnem seus bots</h2>
          <p>Você ainda não tem nenhum bot. Peça à Sora para criar o primeiro; depois, junte de 2 a 5 bots num grupo com a Sora como chefe de equipe.</p>
          <Button tamanho="G" variante="primario" onClick={() => navigate('/')}>Criar um bot</Button></div>
      </main>
      : <main className="grp-pagina" data-aberto={!!grupoId}>
        <aside className="grp-lista" aria-label="Grupos"><header><h2>Grupos</h2></header>
          {grupos.carregando && !grupos.carregado && <p className="grp-nota" role="status">Carregando grupos…</p>}
          {grupos.erro && <p className="grp-erro" role="alert">{grupos.erro}</p>}
          {!grupos.carregando && grupos.carregado && grupos.lista.length === 0 && <p className="grp-nota">Nenhum grupo ainda. Reúna de 2 a 5 bots para trabalharem juntos com a Sora.</p>}
          <ul>{grupos.lista.map(grupo => <li key={grupo.id}><button type="button" aria-current={grupo.id === grupoId ? 'page' : undefined} onClick={() => navigate(`/grupos/${grupo.id}`)}><b>{grupo.nome}</b>{grupo.precisaDeVoce && <i className="grp-alerta" title="Precisa de você" />}<small>{grupo.precisaDeBots ? 'Precisa de bots' : grupo.trabalhando ? 'Trabalhando' : `${Math.max(0, grupo.membros.length - 1)} bots`}</small></button></li>)}</ul>
        </aside>
        {grupoId ? <DetalheGrupo key={grupoId} grupoId={grupoId} /> : <div className="grp-vazio grp-escolha-grupo"><SoraOrb size={96} color="#E2ECFF" state="idle" decorative /><p>Escolha um grupo ou crie um novo. A Sora coordena todos como chefe de equipe.</p></div>}
      </main>}
    <NovoGrupo aberto={novoAberto} onFechar={() => setNovoAberto(false)} onCriado={id => navigate(`/grupos/${id}`)} />
  </AppShell>;
}
