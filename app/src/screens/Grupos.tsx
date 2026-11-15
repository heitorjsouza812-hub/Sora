import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { mensagemDeErro } from '../api/cliente';
import { renomearGrupo, type MensagemGrupoApi } from '../api/grupos';
import { AppShell } from '../components/layout/AppShell';
import { Button, Input } from '../components/base';
import { Modal } from '../components/overlay';
import { SoraOrb } from '../components/mascot';
import { ZonaSoltar } from '../components/anexos';
import { IrParaFim } from '../components/ui/IrParaFim';
import { ShimmerText } from '../components/ui/ShimmerText';
import { useRolagemFim } from '../components/ui/useRolagemFim';
import { useIrParaMensagem } from '../components/ui/useIrParaMensagem';
import { CompositorGrupo } from '../components/grupos/CompositorGrupo';
import { EditarBotsDoGrupo, MenuDoGrupo } from '../components/grupos/GerirGrupo';
import { FaixaDeTrabalho, MembrosGrupo } from '../components/grupos/MembrosGrupo';
import { MensagemGrupo, OrbDoAutor } from '../components/grupos/MensagemGrupo';
import { NovoGrupo } from '../components/grupos/NovoGrupo';
import { TarefasGrupo } from '../components/grupos/TarefasGrupo';
import { useMembrosDoGrupo } from '../components/grupos/useMembrosDoGrupo';
import { ListaPedidos } from '../components/pendencias/saida';
import { carregarBots, useBots } from '../state/bots';
import { carregarGrupos, carregarMensagensDoGrupo, carregarTarefasDoGrupo, grupoPrecisaDeBots, lerGrupos, receberGrupo, useGrupos } from '../state/grupos';
import { carregarPrecisaDeVoce, usePrecisaDeVoce } from '../state/atencao';
import '../components/grupos/grupos.css';
import '../components/grupos/pagina.css';

const rotuloBots = (n: number) => `Sora + ${n} ${n === 1 ? 'bot' : 'bots'}`;

/** `/grupos/:id`: só a conversa. A lista de grupos vive na barra lateral e em `/grupos`. */
function PaginaGrupo({ grupoId }: { grupoId: string }) {
  const navigate = useNavigate();
  const estado = useGrupos();
  const atencao = usePrecisaDeVoce();
  const bots = useBots();
  const grupo = estado.lista.find(item => item.id === grupoId);
  const membros = useMembrosDoGrupo(grupo?.membros ?? [], grupoId, grupo?.liderId);
  const mensagens = estado.mensagens[grupoId] ?? [];
  const pedidos = atencao.lista.filter(pedido => pedido.grupoId === grupoId);
  const [resposta, setResposta] = useState<MensagemGrupoApi | null>(null);
  const [renomeando, setRenomeando] = useState(false);
  const [nome, setNome] = useState('');
  const [editandoBots, setEditandoBots] = useState(false);
  const [erro, setErro] = useState('');
  const ultima = mensagens.at(-1);
  const { ref: rolagemRef, onScroll: aoRolar, noFim, novas, irParaFim, seguirFim } = useRolagemFim(mensagens.map(item => item.id), `${ultima?.id ?? ''}:${ultima?.texto.length ?? 0}`);
  const [prontoEm, setProntoEm] = useState<string | null>(null);
  // Grupo carrega de 100 em 100 para a frente; a busca da paleta pode apontar para uma mensagem mais adiante.
  const carregarMais = useCallback(async () => {
    const antes = lerGrupos().mensagens[grupoId]?.length ?? 0;
    await carregarMensagensDoGrupo(grupoId);
    return (lerGrupos().mensagens[grupoId]?.length ?? 0) > antes;
  }, [grupoId]);
  useIrParaMensagem(prontoEm === grupoId, carregarMais);
  useEffect(() => {
    void carregarMensagensDoGrupo(grupoId).then(() => setProntoEm(grupoId)).catch(falha => { setProntoEm(grupoId); setErro(mensagemDeErro(falha)); });
    void carregarTarefasDoGrupo(grupoId).catch(() => undefined);
  }, [grupoId]);
  if (!grupo) return <AppShell titulo="Grupo"><div className="grp-vazio"><p>{estado.carregado ? 'Este grupo não foi encontrado.' : 'Carregando o grupo…'}</p>{estado.carregado && <Button tamanho="M" variante="secundario" onClick={() => navigate('/grupos')}>Voltar aos grupos</Button>}</div></AppShell>;

  const lider = grupo.liderId ?? grupo.membros[0];
  const botsDoGrupo = bots.filter(bot => grupo.membros.includes(bot.id) && bot.id !== lider);
  const precisaDeBots = grupoPrecisaDeBots(grupo);
  const escrevendo = botsDoGrupo.filter(bot => membros.situacaoDe(bot.id) === 'trabalhando');
  const salvarNome = async () => {
    const valor = nome.trim();
    if (!valor || valor === grupo.nome) { setRenomeando(false); return; }
    try { receberGrupo(await renomearGrupo(grupo.id, valor)); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
    setRenomeando(false);
  };
  const acoes = <>
    <MembrosGrupo membros={grupo.membros} liderId={grupo.liderId} grupoId={grupo.id} estado={membros} onAdicionarBots={() => setEditandoBots(true)} />
    <MenuDoGrupo grupo={grupo} onRenomear={() => { setNome(grupo.nome); setRenomeando(true); }} onGerirBots={() => setEditandoBots(true)} />
  </>;

  return <AppShell titulo={grupo.nome} subtitulo={rotuloBots(botsDoGrupo.length)} acoes={acoes}>
    <section className="grp-pagina" aria-label={`Grupo ${grupo.nome}`}>
      <div className="grp-avisos">
        <FaixaDeTrabalho estado={membros} />
        <TarefasGrupo grupoId={grupo.id} membros={grupo.membros} liderId={grupo.liderId} tarefas={estado.tarefas[grupo.id]} />
        {precisaDeBots && <div className="grp-aviso" role="status">
          <p><b>Este grupo precisa de pelo menos 2 bots.</b> Ele ficou com {botsDoGrupo.length === 0 ? 'nenhum' : botsDoGrupo.length}. Adicione bots para voltar a conversar.</p>
          <Button tamanho="M" variante="primario" onClick={() => setEditandoBots(true)}>Adicionar bots</Button>
        </div>}
      </div>
      <main className="conversation grp-conversa" aria-label={`Conversa do grupo ${grupo.nome}`}>
        <ZonaSoltar className="conversation-drop" desativada={precisaDeBots}>
          <div className="conversation-area">
            <div className="conversation-scroll" ref={rolagemRef} onScroll={aoRolar} aria-live="polite" aria-relevant="additions">
              {mensagens.length === 0 && <p className="grp-nota grp-vazio-conversa">Converse com o grupo. Use @bot para direcionar ou @todos para chamar a equipe inteira.</p>}
              {mensagens.map(mensagem => <MensagemGrupo key={mensagem.id} mensagem={mensagem} todas={mensagens} soraId={lider} onResponder={setResposta} ultima={mensagem.id === ultima?.id} />)}
              {escrevendo.map(bot => <div key={bot.id} className="chat-item grp-escrevendo" role="status"><OrbDoAutor cor={bot.cor} movimento={bot.movimento} tamanho={28} trabalhando semente={bot.nome.length} /><ShimmerText>{`${bot.nome} está escrevendo…`}</ShimmerText></div>)}
            </div>
            {!noFim && <IrParaFim novas={novas} onClick={irParaFim} />}
          </div>
          <div className="grp-rodape">
            <ListaPedidos className="grp-atencao" pedidos={pedidos} semGrupo />
            {precisaDeBots
              ? <p className="grp-travado" role="status">O campo de mensagem volta quando o grupo tiver pelo menos 2 bots.</p>
              : <CompositorGrupo grupoId={grupo.id} botsDoGrupo={botsDoGrupo} resposta={resposta} onCancelarResposta={() => setResposta(null)} onEnviado={() => setErro('')} aoSeguirFim={seguirFim} />}
            {erro && <p className="grp-erro grp-erro-faixa" role="alert">{erro}</p>}
          </div>
        </ZonaSoltar>
      </main>
    </section>
    <EditarBotsDoGrupo grupo={grupo} aberto={editandoBots} onFechar={() => setEditandoBots(false)} />
    <Modal open={renomeando} onClose={() => setRenomeando(false)} title="Renomear grupo" size="sm"
      footer={<><Button tamanho="M" variante="fantasma" onClick={() => setRenomeando(false)}>Cancelar</Button><Button tamanho="M" variante="primario" disabled={!nome.trim()} onClick={() => void salvarNome()}>Salvar</Button></>}>
      <Input rotulo="Nome do grupo" value={nome} maxLength={80} autoFocus onChange={evento => setNome(evento.target.value)} onKeyDown={evento => { if (evento.key === 'Enter') void salvarNome(); }} />
    </Modal>
  </AppShell>;
}

/** `/grupos`: a lista, com "Novo grupo" como ação principal. */
function ListaDeGrupos() {
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
  const vazio = grupos.carregado && !grupos.erro && grupos.lista.length === 0;
  const novo = <Button tamanho="M" variante="primario" onClick={() => setNovoAberto(true)}>Novo grupo</Button>;
  return <AppShell titulo="Grupos" acoes={semBots || vazio ? undefined : novo}>
    <main className="grp-lista-pagina">
      {semBots
        ? <div className="grp-vazio"><SoraOrb size={96} color="#E2ECFF" state="idle" decorative />
          <h2>Grupos reúnem seus bots</h2>
          <p>Você ainda não tem nenhum bot. Peça à Sora para criar o primeiro; depois, junte de 2 a 5 bots num grupo com a Sora como chefe de equipe.</p>
          <Button tamanho="M" variante="primario" onClick={() => navigate('/')}>Criar um bot</Button></div>
        : vazio
          ? <div className="grp-vazio"><SoraOrb size={96} color="#E2ECFF" state="idle" decorative />
            <h2>Nenhum grupo ainda</h2>
            <p>Reúna de 2 a 5 bots para trabalharem juntos, com a Sora como chefe de equipe.</p>
            <Button tamanho="M" variante="primario" onClick={() => setNovoAberto(true)}>Novo grupo</Button></div>
          : <div className="grp-lista-coluna">
            {grupos.carregando && !grupos.carregado && <p className="grp-nota" role="status">Carregando grupos…</p>}
            {grupos.erro && <p className="grp-erro" role="alert">{grupos.erro}</p>}
            <ul className="grp-linhas" aria-label="Grupos">{grupos.lista.map(grupo => {
              const lider = grupo.liderId ?? grupo.membros[0];
              const doGrupo = grupo.membros.filter(id => id !== lider).map(id => bots.find(bot => bot.id === id)).filter(bot => bot !== undefined);
              const situacao = grupo.precisaDeBots ? 'Precisa de bots' : grupo.precisaDeVoce ? 'Precisa de você' : grupo.trabalhando ? 'Trabalhando' : '';
              return <li key={grupo.id}><button type="button" className="grp-linha" onClick={() => navigate(`/grupos/${grupo.id}`)}>
                <span className="grp-linha-texto"><b>{grupo.nome}</b><small>{rotuloBots(Math.max(0, grupo.membros.length - 1))}</small></span>
                <span className="grp-linha-pilha" aria-hidden="true"><OrbDoAutor tamanho={28} semente={3} />{doGrupo.slice(0, 4).map(bot => <OrbDoAutor key={bot.id} cor={bot.cor} movimento={bot.movimento} tamanho={28} semente={bot.nome.length} />)}</span>
                {situacao && <em data-precisa={grupo.precisaDeVoce}>{situacao}</em>}
              </button></li>;
            })}</ul>
          </div>}
    </main>
    <NovoGrupo aberto={novoAberto} onFechar={() => setNovoAberto(false)} onCriado={id => navigate(`/grupos/${id}`)} />
  </AppShell>;
}

export default function Grupos() {
  const { grupoId } = useParams();
  return grupoId ? <PaginaGrupo key={grupoId} grupoId={grupoId} /> : <ListaDeGrupos />;
}
