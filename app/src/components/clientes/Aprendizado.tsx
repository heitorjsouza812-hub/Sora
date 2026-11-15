import { useState } from 'react';
import { canaisEmpresa, CATEGORIAS, type ConhecimentoEmpresa, type SugestaoEmpresa } from '../../api/canaisEmpresa';
import { receberEventoClientes, useRevisaoClientes } from '../../state/clientes';
import { useBots } from '../../state/bots';
import { carregarPrecisaDeVoce } from '../../state/atencao';
import { Button } from '../base';
import { Modal } from '../overlay';
import { EstadoConsulta, Origem, Paginacao, data, useAcao, useConsulta } from './comum';

const atualizar = () => receberEventoClientes({ tipo: 'conhecimento.atualizado' });
function ItemConhecimento({ item }: { item: ConhecimentoEmpresa }) {
  const [editar, setEditar] = useState(false), [apagar, setApagar] = useState(false);
  const [titulo, setTitulo] = useState(item.titulo), [conteudo, setConteudo] = useState(item.conteudo), [categoria, setCategoria] = useState(item.categoria);
  const { ocupado, erro, executar } = useAcao();
  return <article className="ce-faixa"><span className="ce-meta">{CATEGORIAS[item.categoria]} · {item.ocorrencias} ocorrências · {data(item.ultima_em)}</span><h3>{item.titulo}</h3><p>{item.conteudo}</p>
    {item.contraditorio && <p className="ce-alerta">Informações contraditórias — confira as versões e as origens.</p>}
    {!!item.anteriores.length && <details><summary>Versões anteriores ({item.anteriores.length})</summary>{item.anteriores.map((v, i) => <p key={i}>{v.conteudo} <small className="ce-meta">{data(v.em)}</small></p>)}</details>}
    <details><summary>Origens ({item.origens.length})</summary>{item.origens.map((o, i) => <Origem key={`${o.mensagem_id}:${i}`} canal={o.canal} link={o.link} em={o.em} />)}{!item.origens.length && <p className="ce-ajuda">Sem origem disponível.</p>}</details>
    {item.editado && <p className="ce-ajuda">Editado por você. O aprendizado automático não sobrescreve este conteúdo.</p>}
    {editar ? <form onSubmit={e => { e.preventDefault(); void executar(async () => { await canaisEmpresa.editarConhecimento(item.id, { titulo: titulo.trim(), conteudo: conteudo.trim(), categoria }); setEditar(false); atualizar(); }); }}><fieldset disabled={ocupado} className="ce-campos">
      <label>Título<input required maxLength={200} value={titulo} onChange={e => setTitulo(e.target.value)} /></label><label>Categoria<select value={categoria} onChange={e => setCategoria(e.target.value as ConhecimentoEmpresa['categoria'])}>{Object.entries(CATEGORIAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>Conteúdo<textarea required maxLength={800} value={conteudo} onChange={e => setConteudo(e.target.value)} /></label>
      <div className="ce-acoes"><Button type="submit" variante="primario" disabled={!titulo.trim() || !conteudo.trim()}>Salvar conhecimento</Button><Button onClick={() => setEditar(false)}>Cancelar</Button></div>
    </fieldset></form> : <div className="ce-acoes"><Button onClick={() => { setTitulo(item.titulo); setConteudo(item.conteudo); setCategoria(item.categoria); setEditar(true); }}>Editar conhecimento</Button><Button variante="perigo" onClick={() => setApagar(true)}>Apagar conhecimento</Button></div>}
    {erro && <p role="alert">{erro}</p>}
    <Modal open={apagar} onClose={() => { if (!ocupado) setApagar(false); }} title="Apagar este conhecimento?" description="O item será removido e não voltará automaticamente." size="sm" footer={<div className="ce-acoes"><Button disabled={ocupado} onClick={() => setApagar(false)}>Cancelar</Button><Button variante="perigo" carregando={ocupado} onClick={() => void executar(async () => { await canaisEmpresa.apagarConhecimento(item.id); setApagar(false); atualizar(); })}>Confirmar exclusão</Button></div>}><p>{item.titulo}</p>{erro && <p role="alert">{erro}</p>}</Modal>
  </article>;
}
export function CartaoSugestao({ sugestao, nomeBot, onAtualizar = atualizar }: { sugestao: SugestaoEmpresa; nomeBot: string; onAtualizar?: () => void }) {
  const [editar, setEditar] = useState(false), [texto, setTexto] = useState(sugestao.texto);
  const { ocupado, erro, executar } = useAcao();
  const decidir = (acao: 'aplicar' | 'descartar' | 'desfazer') => executar(async () => {
    await canaisEmpresa.decidirSugestao(sugestao.id, acao);
    onAtualizar(); void carregarPrecisaDeVoce().catch(() => undefined);
  });
  return <section className="ce-sugestao" aria-label={sugestao.status === 'pendente' ? 'Precisa de você' : 'Sugestão aplicada'}>
    <span className="ce-meta">{sugestao.status === 'pendente' ? 'Precisa de você' : 'Aplicada'} · {nomeBot} · {data(sugestao.criada_em)}</span><h3>{sugestao.titulo}</h3><p>{sugestao.motivo}</p>
    <p className="ce-ajuda">{sugestao.tipo === 'habilidade' ? `Habilidade compartilhada: ${sugestao.habilidade_nome ?? 'nova habilidade'}` : 'Trecho para as instruções do bot'} · {sugestao.conhecimento_ids.length} itens de conhecimento</p>
    {editar ? <form onSubmit={e => { e.preventDefault(); void executar(async () => { await canaisEmpresa.editarSugestao(sugestao.id, texto.trim()); setEditar(false); onAtualizar(); }); }}><fieldset disabled={ocupado} className="ce-campos"><label>Texto da sugestão<textarea required maxLength={8000} value={texto} onChange={e => setTexto(e.target.value)} /></label><div className="ce-acoes"><Button type="submit" disabled={!texto.trim()} variante="primario">Salvar edição</Button><Button onClick={() => setEditar(false)}>Cancelar</Button></div></fieldset></form> : <><pre>{sugestao.texto}</pre><div className="ce-acoes" role="group" aria-label="Decisão da sugestão">
      {sugestao.status === 'pendente' ? <><Button variante="primario" disabled={ocupado} onClick={() => void decidir('aplicar')}>Aplicar</Button><Button disabled={ocupado} onClick={() => { setTexto(sugestao.texto); setEditar(true); }}>Editar</Button><Button variante="perigo" disabled={ocupado} onClick={() => void decidir('descartar')}>Descartar</Button></> : <Button disabled={ocupado} onClick={() => void decidir('desfazer')}>Desfazer</Button>}
    </div></>}{erro && <p role="alert">{erro}</p>}
  </section>;
}
export function Aprendizado() {
  const [busca, setBusca] = useState(''), [categoria, setCategoria] = useState(''), [pagina, setPagina] = useState(0);
  const revisao = useRevisaoClientes(), bots = useBots();
  const consulta = useConsulta(`${busca}:${categoria}:${pagina}:${revisao.conhecimento}`, signal => canaisEmpresa.conhecimento(busca, categoria, pagina, signal));
  const sugestoes = useConsulta(`sugestoes:${revisao.conhecimento}`, canaisEmpresa.sugestoes);
  return <section><h2>O que a Sora aprendeu</h2><p className="ce-ajuda">Conhecimento extraído do atendimento, sem dados pessoais. As sugestões só mudam os bots quando você aplica.</p>
    <div className="ce-campos"><label>Buscar conhecimento<input type="search" maxLength={120} value={busca} onChange={e => { setBusca(e.target.value); setPagina(0); }} /></label><label>Tipo de conhecimento<select value={categoria} onChange={e => { setCategoria(e.target.value); setPagina(0); }}><option value="">Todos os tipos</option>{Object.entries(CATEGORIAS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
    <EstadoConsulta {...consulta} />{consulta.dados && <><p className="ce-meta">{consulta.dados.length} itens nesta página</p>{consulta.dados.map(item => <ItemConhecimento key={item.id} item={item} />)}{!consulta.dados.length && <p>{busca || categoria ? 'Nenhum conhecimento encontrado para este filtro.' : 'A Sora ainda não reuniu conhecimento do atendimento.'}</p>}{(pagina > 0 || consulta.dados.length >= 50) && <Paginacao pagina={pagina} quantidade={consulta.dados.length} onPagina={setPagina} />}</>}
    <section className="ce-faixa" aria-label="Sugestões de melhoria"><h2>Sugestões de melhoria</h2><EstadoConsulta {...sugestoes} />
      {sugestoes.dados?.filter(s => s.status === 'pendente' || s.status === 'aplicada').map(s => <CartaoSugestao key={s.id} sugestao={s} nomeBot={bots.find(b => b.id === s.agente_id)?.nome ?? 'Bot'} />)}
      {sugestoes.dados && !sugestoes.dados.some(s => s.status === 'pendente' || s.status === 'aplicada') && <p className="ce-ajuda">Nenhuma sugestão aguardando você.</p>}
    </section>
  </section>;
}
