import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { buscarAutenticado, mensagemDeErro } from '../api/cliente';
import { enviarAnexo } from '../api/anexos';
import { lembrarNomeDoAnexo, pararBotNoGrupo, renomearGrupo, retomarTarefaGrupo, type AnexoGrupo, type MensagemGrupoApi } from '../api/grupos';
import { AppShell } from '../components/layout/AppShell';
import { Button, Input } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { NovoGrupo } from '../components/grupos/NovoGrupo';
import { CartaoPrecisaDeVoce } from '../components/pendencias/CartaoPrecisaDeVoce';
import { useBots } from '../state/bots';
import { carregarGrupos, carregarMensagensDoGrupo, carregarTarefasDoGrupo, enviarMensagemAoGrupo, estadoDoMembro, receberGrupo, receberTarefasDoGrupo, useGrupos } from '../state/grupos';
import { carregarPrecisaDeVoce, usePrecisaDeVoce } from '../state/atencao';
import '../components/grupos/grupos.css';

const semAcento = (valor: string) => valor.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');

const ROTULO_MEMBRO = { trabalhando: 'Trabalhando', parado: 'Parado', livre: 'Livre', precisa_de_voce: 'Precisa de você' } as const;

function MembrosDoGrupo({ membros, grupoId }: { membros: string[]; grupoId: string }) {
  const bots = useBots();
  const tarefas = useGrupos().tarefas[grupoId];
  const atencao = usePrecisaDeVoce();
  // Mantém a ordem escolhida pelo usuário (membros[0] é a Sora, mostrada à parte).
  const noGrupo = membros.map(id => bots.find(bot => bot.id === id)).filter(bot => bot !== undefined);
  const [parando, setParando] = useState('');
  const [erro, setErro] = useState('');
  const parar = async (botId: string) => {
    setParando(botId); setErro('');
    try { receberTarefasDoGrupo(await pararBotNoGrupo(grupoId, botId)); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setParando(''); }
  };
  const retomar = async (botId: string) => {
    setParando(botId); setErro('');
    try {
      const paradas = Object.values(tarefas ?? {}).filter(tarefa => tarefa.donoId === botId && tarefa.status === 'parada');
      for (const tarefa of paradas) receberTarefasDoGrupo(await retomarTarefaGrupo(tarefa.id));
    } catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setParando(''); }
  };
  const estadoDe = (botId: string) => {
    const doGrupo = estadoDoMembro(tarefas, botId);
    if (doGrupo !== 'livre') return doGrupo;
    return atencao.lista.some(pedido => pedido.botId === botId && pedido.grupoId === grupoId) ? 'precisa_de_voce' : 'livre';
  };
  return <>
    <div className="grp-membros" aria-label="Membros do grupo">
      <div className="grp-membro"><i className="grp-orb grp-orb-sora" aria-hidden="true" /><span><b>Sora</b><small>Chefe de equipe</small></span></div>
      {noGrupo.map(bot => { const situacao = estadoDe(bot.id); return <div className="grp-membro" key={bot.id} data-estado={situacao}>
        <i className="grp-orb" style={{ background: bot.cor, color: bot.cor }} aria-hidden="true" />
        <span><b>{bot.nome}</b><small>{ROTULO_MEMBRO[situacao]}</small></span>
        {situacao === 'parado'
          ? <button type="button" aria-label={`Retomar ${bot.nome}`} disabled={parando === bot.id} onClick={() => void retomar(bot.id)}>{parando === bot.id ? 'Retomando…' : 'Retomar'}</button>
          : <button type="button" aria-label={`Parar ${bot.nome}`} disabled={situacao !== 'trabalhando' || parando === bot.id} onClick={() => void parar(bot.id)}>{parando === bot.id ? 'Parando…' : 'Parar'}</button>}
      </div>; })}
    </div>
    {erro && <p className="grp-erro" role="alert">{erro}</p>}
  </>;
}

// /v1/anexos/{id} exige o token, então o arquivo vira blob e é baixado com o nome que o servidor manda.
function BotaoAnexo({ anexo }: { anexo: AnexoGrupo }) {
  const [baixando, setBaixando] = useState(false);
  const [falhou, setFalhou] = useState(false);
  const baixar = async () => {
    setBaixando(true); setFalhou(false);
    try {
      const resposta = await buscarAutenticado(`/v1/anexos/${anexo.id}`);
      const disposicao = resposta.headers.get('content-disposition') ?? '';
      const nome = decodeURIComponent(disposicao.match(/filename\*=UTF-8''([^;]+)/i)?.[1] ?? disposicao.match(/filename="?([^";]+)"?/i)?.[1] ?? anexo.nome);
      const url = URL.createObjectURL(await resposta.blob());
      const link = document.createElement('a');
      link.href = url; link.download = nome; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setFalhou(true); }
    finally { setBaixando(false); }
  };
  return <button type="button" className="grp-anexo" onClick={() => void baixar()} disabled={baixando} title={falhou ? 'Não foi possível baixar. Tente de novo.' : 'Baixar arquivo'}>{baixando ? 'Baixando…' : anexo.nome}{falhou && ' · falhou'}</button>;
}

function Mensagem({ mensagem, todas, soraId, onResponder }: { mensagem: MensagemGrupoApi; todas: MensagemGrupoApi[]; soraId: string | undefined; onResponder: (mensagem: MensagemGrupoApi) => void }) {
  const bots = useBots();
  const bot = bots.find(item => item.id === mensagem.botId);
  // A Sora (líder, membros[0]) não está em useBots(); mensagem dela chega como autor "agente".
  const ehSora = mensagem.autor === 'sora' || (!!soraId && mensagem.botId === soraId);
  const anterior = mensagem.respondeA ? todas.find(item => item.id === mensagem.respondeA) : null;
  // Atividade (repasse, "Você parou a tarefa") é uma linha de registro, não uma fala.
  if (mensagem.tipo === 'repasse') return <li className="grp-msg grp-atividade" data-autor={mensagem.autor} data-tipo="repasse">
    {bot && <i className="grp-orb" style={{ background: bot.cor, color: bot.cor }} aria-hidden="true" />}{ehSora && <i className="grp-orb grp-orb-sora" aria-hidden="true" />}<span>{mensagem.texto}</span>
  </li>;
  const autor = mensagem.autor === 'usuario' ? 'Você' : ehSora ? 'Sora' : mensagem.autor === 'sistema' ? 'Sistema' : bot?.nome ?? 'Bot';
  return <li className="grp-msg" data-autor={ehSora ? 'sora' : mensagem.autor} data-tipo={mensagem.tipo}>
    <header>{ehSora ? <i className="grp-orb grp-orb-sora" aria-hidden="true" /> : bot ? <i className="grp-orb" style={{ background: bot.cor, color: bot.cor }} aria-hidden="true" /> : null}<b style={{ color: ehSora ? '#E2ECFF' : bot?.cor }}>{autor}</b>{mensagem.tipo === 'resultado' && <span>entregou</span>}</header>
    {anterior && <span className="grp-resposta">Em resposta a {anterior.texto.slice(0, 80)}</span>}
    <p>{mensagem.texto}</p>
    {!!mensagem.anexos.length && <div className="grp-anexos">{mensagem.anexos.map(anexo => <BotaoAnexo key={anexo.id} anexo={anexo} />)}</div>}
    <span className="grp-msg-acoes"><button type="button" onClick={() => onResponder(mensagem)}>Responder</button></span>
  </li>;
}

function DetalheGrupo({ grupoId }: { grupoId: string }) {
  const estado = useGrupos();
  const atencao = usePrecisaDeVoce();
  const bots = useBots();
  const grupo = estado.lista.find(item => item.id === grupoId);
  const mensagens = estado.mensagens[grupoId] ?? [];
  const pedidos = atencao.lista.filter(pedido => pedido.grupoId === grupoId);
  const [texto, setTexto] = useState('');
  const [resposta, setResposta] = useState<MensagemGrupoApi | null>(null);
  const [editandoNome, setEditandoNome] = useState(false);
  const [nome, setNome] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [anexos, setAnexos] = useState<AnexoGrupo[]>([]);
  const [subindo, setSubindo] = useState(false);
  const seletorArquivo = useRef<HTMLInputElement>(null);
  const listaMensagens = useRef<HTMLOListElement>(null);
  const ultimaMensagem = mensagens.at(-1)?.id;
  useEffect(() => {
    const lista = listaMensagens.current;
    if (lista) lista.scrollTop = lista.scrollHeight;
  }, [ultimaMensagem, grupoId]);
  useEffect(() => {
    void carregarMensagensDoGrupo(grupoId).catch(falha => setErro(mensagemDeErro(falha)));
    void carregarTarefasDoGrupo(grupoId).catch(() => undefined);
  }, [grupoId]);
  if (!grupo) return <div className="grp-vazio"><p>Este grupo não foi encontrado.</p></div>;

  const sugestoes = texto.match(/(?:^|\s)@([^\s]*)$/)?.[1];
  const botsDoGrupo = bots.filter(bot => grupo.membros.includes(bot.id));
  // O backend lê as menções do começo do texto (`@Nome Composto`, `@todos`); o app só completa o nome.
  const mencionar = (nomeBot: string) => setTexto(atual => atual.replace(/(?:^|\s)@[^\s]*$/, trecho => `${trecho.startsWith(' ') ? ' ' : ''}@${nomeBot} `));
  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    const conteudo = texto.trim();
    if (!conteudo) return;
    setEnviando(true); setErro('');
    try { await enviarMensagemAoGrupo(grupo.id, { texto: conteudo, respondeA: resposta?.id, anexos: anexos.map(anexo => anexo.id) }); setTexto(''); setResposta(null); setAnexos([]); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setEnviando(false); }
  };
  const anexar = async (arquivos: FileList | null) => {
    if (!arquivos?.length) return;
    setSubindo(true); setErro('');
    try {
      for (const arquivo of Array.from(arquivos).slice(0, 10 - anexos.length)) {
        const enviado = await enviarAnexo(arquivo);
        lembrarNomeDoAnexo(enviado.anexo_id, enviado.nome);
        setAnexos(atuais => [...atuais, { id: enviado.anexo_id, nome: enviado.nome }]);
      }
    } catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setSubindo(false); if (seletorArquivo.current) seletorArquivo.current.value = ''; }
  };
  const salvarNome = async () => {
    const valor = nome.trim();
    if (!valor || valor === grupo.nome) { setNome(grupo.nome); setEditandoNome(false); return; }
    try { receberGrupo(await renomearGrupo(grupo.id, valor)); setEditandoNome(false); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
  };

  return <section className="grp-detalhe" aria-label={`Grupo ${grupo.nome}`}>
    <header className="grp-cabecalho">
      <div>{editandoNome ? <span className="grp-titulo-edicao"><input aria-label="Nome do grupo" value={nome} maxLength={80} onChange={evento => setNome(evento.target.value)} onKeyDown={evento => { if (evento.key === 'Enter') void salvarNome(); if (evento.key === 'Escape') setEditandoNome(false); }} autoFocus /><Button tamanho="P" variante="primario" onClick={() => void salvarNome()}>Salvar</Button></span> : <h2>{grupo.nome}</h2>}<span className="grp-sobretitulo">Sora + {botsDoGrupo.length} bots</span></div>
      {!editandoNome && <Button tamanho="M" variante="secundario" onClick={() => { setNome(grupo.nome); setEditandoNome(true); }}>Renomear</Button>}
    </header>
    <MembrosDoGrupo membros={grupo.membros} grupoId={grupo.id} />
    <ol ref={listaMensagens} className="grp-mensagens" aria-live="polite">
      {mensagens.length === 0 && <li className="grp-nota">Converse com o grupo. Use @bot para direcionar ou @todos para chamar a equipe inteira.</li>}
      {mensagens.map(mensagem => <Mensagem key={mensagem.id} mensagem={mensagem} todas={mensagens} soraId={grupo.liderId ?? grupo.membros[0]}onResponder={setResposta} />)}
    </ol>
    <div>
      {!!pedidos.length && <div className="grp-atencao">{pedidos.map(pedido => <CartaoPrecisaDeVoce key={pedido.id} pedido={pedido} />)}</div>}
      <div className="grp-envio">
        {resposta && <div className="grp-respondendo"><span>Respondendo a {resposta.texto.slice(0, 90)}</span><button type="button" className="grp-icone" onClick={() => setResposta(null)}>Cancelar</button></div>}
        {sugestoes !== undefined && <div className="grp-mencoes" role="listbox" aria-label="Mencionar"><button type="button" onClick={() => mencionar('todos')}>@todos</button>{botsDoGrupo.filter(bot => semAcento(bot.nome).startsWith(semAcento(sugestoes))).map(bot => <button type="button" key={bot.id} onClick={() => mencionar(bot.nome)}>@{bot.nome}</button>)}</div>}
        {!!anexos.length && <div className="grp-anexos grp-anexos-envio">{anexos.map(anexo => <span key={anexo.id} className="grp-anexo">{anexo.nome}<button type="button" aria-label={`Remover ${anexo.nome}`} onClick={() => setAnexos(atuais => atuais.filter(item => item.id !== anexo.id))}>×</button></span>)}</div>}
        <form onSubmit={evento => void enviar(evento)}><input ref={seletorArquivo} type="file" multiple hidden onChange={evento => void anexar(evento.target.files)} /><Button type="button" tamanho="M" variante="secundario" disabled={subindo || anexos.length >= 10} onClick={() => seletorArquivo.current?.click()}>{subindo ? 'Anexando…' : 'Anexar'}</Button><Input rotulo="Mensagem para o grupo" rotuloOculto value={texto} onChange={evento => setTexto(evento.target.value)} placeholder={`Mensagem para ${grupo.nome}…`} /><Button type="submit" tamanho="M" variante="primario" disabled={!texto.trim() || enviando || subindo}>Enviar</Button></form>
        {erro && <p className="grp-erro" role="alert">{erro}</p>}
      </div>
    </div>
  </section>;
}

export default function Grupos() {
  const { grupoId } = useParams();
  const navigate = useNavigate();
  const grupos = useGrupos();
  const [novoAberto, setNovoAberto] = useState(false);
  useEffect(() => { void carregarGrupos().catch(() => undefined); void carregarPrecisaDeVoce().catch(() => undefined); }, []);
  const lista = useMemo(() => grupos.lista, [grupos.lista]);
  return <AppShell titulo="Grupos" acoes={<Button tamanho="M" variante="secundario" onClick={() => setNovoAberto(true)}>Novo grupo</Button>}>
    <main className="grp-pagina">
      <aside className="grp-lista" aria-label="Grupos"><header><h2>Grupos</h2><button className="grp-icone" type="button" aria-label="Novo grupo" onClick={() => setNovoAberto(true)}>＋</button></header>
        {grupos.carregando && <p className="grp-nota" role="status">Carregando grupos…</p>}
        {grupos.erro && <p className="grp-erro" role="alert">{grupos.erro}</p>}
        {!grupos.carregando && grupos.carregado && lista.length === 0 && <p className="grp-nota">Nenhum grupo ainda. Reúna de 2 a 5 bots para trabalharem juntos com a Sora.</p>}
        <ul>{lista.map(grupo => <li key={grupo.id}><button type="button" aria-current={grupo.id === grupoId ? 'page' : undefined} onClick={() => navigate(`/grupos/${grupo.id}`)}><b>{grupo.nome}</b>{grupo.precisaDeVoce && <i className="grp-alerta" title="Precisa de você" />}<small>{grupo.trabalhando ? 'Trabalhando' : `${Math.max(0, grupo.membros.length - 1)} bots`}</small></button></li>)}</ul>
      </aside>
      {grupoId ? <DetalheGrupo grupoId={grupoId} /> : <div className="grp-vazio"><SoraOrb size={96} color="#E2ECFF" state="idle" decorative /><p>Escolha um grupo ou crie um novo. A Sora coordena todos como chefe de equipe.</p></div>}
    </main>
    <NovoGrupo aberto={novoAberto} onFechar={() => setNovoAberto(false)} onCriado={id => navigate(`/grupos/${id}`)} />
  </AppShell>;
}
