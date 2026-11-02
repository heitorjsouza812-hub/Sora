// Seções de Configurações da etapa 4: Memória, Rotinas, Conectores, Habilidades e Telegram.
// Tudo vem das rotas reais; erro do servidor aparece com a mensagem dele (sem simulação).
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import * as pecas from '../../state/pecas';
import { Button, Input, Textarea } from '../base';
import './pecas.css';

/** Lista carregada de uma rota, com recarregar e erro. */
function useLista<T>(carregar: () => Promise<T[]>) {
  const [itens, setItens] = useState<T[] | null>(null);
  const [erro, setErro] = useState('');
  const recarregar = useCallback(() => carregar().then(l => { setItens(l); setErro(''); }).catch(e => { setErro(mensagemDeErro(e)); setItens(l => l ?? []); }), [carregar]);
  useEffect(() => { void recarregar(); }, [recarregar]);
  return { itens, erro, recarregar };
}

/** Roda uma ação, mostra o erro e recarrega. */
function useAcao(recarregar: () => Promise<void>) {
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const rodar = async (f: () => Promise<unknown>) => {
    setOcupado(true); setErro('');
    try { await f(); await recarregar(); return true; } catch (e) { setErro(mensagemDeErro(e)); return false; } finally { setOcupado(false); }
  };
  return { erro, ocupado, rodar };
}

function Secao({ titulo, texto, children }: { titulo: string; texto: string; children: ReactNode }) {
  return <><header className="cfg-heading"><h2>{titulo}</h2><p>{texto}</p></header><div className="pc-secao">{children}</div></>;
}
const Erro = ({ texto }: { texto: string }) => texto ? <p className="pc-erro" role="alert">{texto}</p> : null;
const quando = (iso: string | null) => iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—';

export function SecaoMemoria() {
  const { itens, erro, recarregar } = useLista(pecas.listarMemorias);
  const acao = useAcao(recarregar);
  const [texto, setTexto] = useState('');
  const salvar = async (ev: FormEvent) => { ev.preventDefault(); if (texto.trim() && await acao.rodar(() => pecas.criarMemoria(texto.trim()))) setTexto(''); };
  return <Secao titulo="Memória" texto="O que a Sora e os agentes lembram sobre você entre conversas. Você pode acrescentar ou apagar qualquer item; senhas e chaves não são aceitas.">
    <form className="pc-form" onSubmit={ev => void salvar(ev)}>
      <Input rotulo="Nova lembrança" value={texto} onChange={e => setTexto(e.target.value)} maxLength={500} placeholder="Ex.: Minha cafeteria fica em Curitiba e fecha às segundas." />
      <Button type="submit" variante="primario" tamanho="M" disabled={!texto.trim() || acao.ocupado}>Guardar</Button>
    </form>
    <Erro texto={acao.erro || erro} />
    {itens === null ? <p role="status">Carregando memórias…</p> : !itens.length ? <p className="pc-vazio">Nada guardado ainda.</p> :
      <ul className="pc-lista">{itens.map(m => <li key={m.id}><span><p>{m.conteudo}</p><small>{m.origem === 'agente' ? 'Guardada por um agente' : 'Você'} · {quando(m.criada_em)}</small></span>
        <Button tamanho="M" variante="perigo" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.apagarMemoria(m.id))}>Esquecer</Button></li>)}</ul>}
  </Secao>;
}

const ROTULO_EXEC: Record<string, string> = { executando: 'Rodando', enviada: 'Enviada', silenciosa: 'Sem resposta', falhou: 'Falhou' };

function Execucoes({ rotinaId }: { rotinaId: string }) {
  const carregar = useCallback(() => pecas.execucoesDaRotina(rotinaId), [rotinaId]);
  const { itens, erro } = useLista(carregar);
  if (erro) return <Erro texto={erro} />;
  if (itens === null) return <p role="status">Carregando…</p>;
  if (!itens.length) return <p className="pc-vazio">Ainda não rodou.</p>;
  return <ul className="pc-execs">{itens.map(x => <li key={x.id}>{quando(x.iniciada_em)} · <b>{ROTULO_EXEC[x.status] ?? x.status}</b>{x.resumo ? ` — ${x.resumo}` : ''}{x.erro ? ` (${x.erro})` : ''}</li>)}</ul>;
}

export function SecaoRotinas() {
  const { itens, erro, recarregar } = useLista(pecas.listarRotinas);
  const acao = useAcao(recarregar);
  const [titulo, setTitulo] = useState(''); const [pedido, setPedido] = useState('');
  const [modo, setModo] = useState<'cron' | 'intervalo'>('intervalo'); const [cron, setCron] = useState('0 9 * * *'); const [aCada, setACada] = useState(1);
  const [unidade, setUnidade] = useState<'minutos' | 'horas' | 'dias'>('horas');
  const [aberta, setAberta] = useState<string | null>(null);
  const criar = async (ev: FormEvent) => {
    ev.preventDefault();
    const ok = await acao.rodar(() => pecas.criarRotina({ titulo: titulo.trim(), pedido: pedido.trim(), ...(modo === 'cron' ? { cron } : { a_cada: aCada, unidade }) }));
    if (ok) { setTitulo(''); setPedido(''); }
  };
  return <Secao titulo="Rotinas" texto="Pedidos que a Sora faz sozinha, no horário que você marcar. Rotinas rodam sem você olhando: só usam ferramentas seguras e o navegador sem logins salvos.">
    <form className="pc-form pc-form-coluna" onSubmit={ev => void criar(ev)}>
      <Input rotulo="Título" value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={80} />
      <Textarea rotulo="O que fazer" value={pedido} onChange={e => setPedido(e.target.value)} rows={3} />
      <div className="pc-linha">
        <label>Repetir<select value={modo} onChange={e => setModo(e.target.value as 'cron' | 'intervalo')}><option value="intervalo">A cada…</option><option value="cron">Expressão cron</option></select></label>
        {modo === 'cron' ? <label>Cron<input value={cron} onChange={e => setCron(e.target.value)} /></label>
          : <><label>Quantidade<input type="number" min={1} value={aCada} onChange={e => setACada(Math.max(1, Number(e.target.value) || 1))} /></label>
            <label>Unidade<select value={unidade} onChange={e => setUnidade(e.target.value as 'minutos' | 'horas' | 'dias')}><option value="minutos">minutos</option><option value="horas">horas</option><option value="dias">dias</option></select></label></>}
      </div>
      <Button type="submit" variante="primario" tamanho="M" disabled={!titulo.trim() || !pedido.trim() || acao.ocupado}>Criar rotina</Button>
    </form>
    <Erro texto={acao.erro || erro} />
    {itens === null ? <p role="status">Carregando rotinas…</p> : !itens.length ? <p className="pc-vazio">Nenhuma rotina ainda.</p> :
      <ul className="pc-lista">{itens.map(r => <li key={r.id} data-ativa={r.ativa}>
        <span><strong>{r.titulo}</strong><p>{r.pedido}</p><small>{r.tipo === 'cron' ? `cron ${r.expressao}` : r.tipo === 'intervalo' ? `a cada ${r.expressao}` : 'uma vez'} · próxima: {quando(r.proxima_execucao)} · última: {quando(r.ultima_execucao)}{r.ultimo_status ? ` (${ROTULO_EXEC[r.ultimo_status] ?? r.ultimo_status})` : ''}{!r.ativa ? ' · pausada' : ''}</small>
          {aberta === r.id && <Execucoes rotinaId={r.id} />}</span>
        <span className="pc-acoes">
          <Button tamanho="M" variante="secundario" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.alterarRotina(r.id, { ativa: !r.ativa }))}>{r.ativa ? 'Pausar' : 'Retomar'}</Button>
          <Button tamanho="M" variante="secundario" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.executarRotina(r.id))}>Rodar agora</Button>
          <Button tamanho="M" variante="secundario" onClick={() => setAberta(aberta === r.id ? null : r.id)}>{aberta === r.id ? 'Ocultar' : 'Histórico'}</Button>
          <Button tamanho="M" variante="perigo" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.apagarRotina(r.id))}>Apagar</Button>
        </span></li>)}</ul>}
  </Secao>;
}

export function SecaoConectores() {
  const { itens, erro, recarregar } = useLista(pecas.listarConectores);
  const acao = useAcao(recarregar);
  const [nome, setNome] = useState(''); const [url, setUrl] = useState(''); const [chave, setChave] = useState(''); const [valor, setValor] = useState('');
  const [teste, setTeste] = useState<Record<string, string>>({});
  const criar = async (ev: FormEvent) => {
    ev.preventDefault();
    const ok = await acao.rodar(() => pecas.criarConector({ nome: nome.trim(), url: url.trim(), ...(chave.trim() && valor ? { cabecalhos: { [chave.trim()]: valor } } : {}) }));
    if (ok) { setNome(''); setUrl(''); setChave(''); setValor(''); }
  };
  const testar = (id: string) => void acao.rodar(async () => {
    const r = await pecas.testarConector(id);
    setTeste(t => ({ ...t, [id]: r.ok ? `Funcionou: ${r.ferramentas.length} ferramenta(s).` : `Falhou: ${r.erro ?? 'sem detalhe'}` }));
  });
  return <Secao titulo="Conectores" texto="Servidores MCP externos que dão mais ferramentas aos agentes. Só endereços https públicos; os cabeçalhos (chaves de acesso) ficam guardados no servidor e nunca voltam para esta tela.">
    <form className="pc-form pc-form-coluna" onSubmit={ev => void criar(ev)}>
      <Input rotulo="Nome" value={nome} onChange={e => setNome(e.target.value)} maxLength={60} />
      <Input rotulo="Endereço (https)" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://servidor.exemplo.com/mcp" />
      <div className="pc-linha"><label>Cabeçalho (opcional)<input value={chave} onChange={e => setChave(e.target.value)} placeholder="Authorization" /></label>
        <label>Valor<input type="password" value={valor} onChange={e => setValor(e.target.value)} autoComplete="off" /></label></div>
      <Button type="submit" variante="primario" tamanho="M" disabled={!nome.trim() || !url.trim() || acao.ocupado}>Adicionar conector</Button>
    </form>
    <Erro texto={acao.erro || erro} />
    {itens === null ? <p role="status">Carregando conectores…</p> : !itens.length ? <p className="pc-vazio">Nenhum conector ainda.</p> :
      <ul className="pc-lista">{itens.map(c => <li key={c.id}>
        <span><strong>{c.nome}</strong><p>{c.url}</p><small>{c.estado === 'ok' ? `Funcionando · ${c.n_ferramentas} ferramenta(s)` : c.estado === 'erro' ? `Com erro${c.ultimo_erro ? `: ${c.ultimo_erro}` : ''}` : 'Ainda não testado'}{c.tem_cabecalhos ? ' · com cabeçalhos' : ''}{!c.ativo ? ' · desligado' : ''}</small>
          {teste[c.id] && <small role="status">{teste[c.id]}</small>}</span>
        <span className="pc-acoes">
          <Button tamanho="M" variante="secundario" disabled={acao.ocupado} onClick={() => testar(c.id)}>Testar</Button>
          <Button tamanho="M" variante="secundario" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.alterarConector(c.id, !c.ativo))}>{c.ativo ? 'Desligar' : 'Ligar'}</Button>
          <Button tamanho="M" variante="perigo" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.apagarConector(c.id))}>Remover</Button>
        </span></li>)}</ul>}
  </Secao>;
}

export function SecaoHabilidades() {
  const { itens, erro, recarregar } = useLista(pecas.listarHabilidades);
  const acao = useAcao(recarregar);
  const [nome, setNome] = useState(''); const [descricao, setDescricao] = useState(''); const [conteudo, setConteudo] = useState('');
  const criar = async (ev: FormEvent) => { ev.preventDefault(); if (await acao.rodar(() => pecas.criarHabilidade({ nome: nome.trim(), descricao: descricao.trim(), corpo: conteudo }))) { setNome(''); setDescricao(''); setConteudo(''); } };
  return <Secao titulo="Habilidades" texto="Instruções reutilizáveis. Digite /Nome numa conversa para usar uma habilidade, ou @Nome para chamá-la dentro de um pedido.">
    <form className="pc-form pc-form-coluna" onSubmit={ev => void criar(ev)}>
      <Input rotulo="Nome" value={nome} onChange={e => setNome(e.target.value)} maxLength={40} />
      <Input rotulo="Para que serve" value={descricao} onChange={e => setDescricao(e.target.value)} maxLength={200} />
      <Textarea rotulo="Instruções" value={conteudo} onChange={e => setConteudo(e.target.value)} rows={5} />
      <Button type="submit" variante="primario" tamanho="M" disabled={!nome.trim() || !descricao.trim() || !conteudo.trim() || acao.ocupado}>Criar habilidade</Button>
    </form>
    <Erro texto={acao.erro || erro} />
    {itens === null ? <p role="status">Carregando habilidades…</p> : !itens.length ? <p className="pc-vazio">Nenhuma habilidade ainda.</p> :
      <ul className="pc-lista">{itens.map(h => <li key={h.id}><span><strong>/{h.nome}</strong><p>{h.descricao}</p><small>{h.origem} · atualizada {quando(h.atualizada_em)}</small></span>
        <Button tamanho="M" variante="perigo" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.apagarHabilidade(h.id))}>Apagar</Button></li>)}</ul>}
  </Secao>;
}

export function SecaoTelegram() {
  const { itens, erro, recarregar } = useLista(pecas.listarCanaisExternos);
  const acao = useAcao(recarregar);
  const [codigo, setCodigo] = useState<pecas.CodigoVinculo | null>(null);
  const tg = itens?.find(c => c.canal === 'telegram');
  return <Secao titulo="Telegram" texto="Converse com a Sora pelo Telegram. Você gera um código aqui e manda ao bot da Sora.">
    <Erro texto={acao.erro || erro} />
    {itens === null ? <p role="status">Carregando…</p> : !tg || !tg.disponivel ? <p className="pc-vazio">O Telegram não está ligado neste servidor.</p> : <>
      <Button tamanho="M" variante="primario" disabled={acao.ocupado} onClick={() => void acao.rodar(async () => setCodigo(await pecas.gerarVinculoTelegram()))}>Gerar código de vínculo</Button>
      {codigo && <p className="pc-codigo" role="status">Envie ao bot: <code>{codigo.comando}</code> <small>(vale por {Math.round(codigo.expira_em_segundos / 60)} min)</small></p>}
      {!tg.vinculos.length ? <p className="pc-vazio">Nenhum chat vinculado.</p> :
        <ul className="pc-lista">{tg.vinculos.map(v => <li key={v.id}><span><strong>Chat {v.chat_id}</strong><small>Vinculado em {quando(v.criado_em)}</small></span>
          <Button tamanho="M" variante="perigo" disabled={acao.ocupado} onClick={() => void acao.rodar(() => pecas.removerVinculoTelegram(v.id))}>Desvincular</Button></li>)}</ul>}
    </>}
  </Secao>;
}
