// Rotinas de um bot: criar (Todo dia / Dias úteis / Toda semana + hora), pausar/retomar, "Rodar agora",
// próxima execução e as 5 últimas.
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { DIAS_DA_SEMANA, FREQUENCIAS, lerAgendamento, montarAgendamento, type Frequencia } from '../builder/rotinaAmigavel';
import { alterarRotina, apagarRotina, criarRotina, executarRotina, listarRotinasDoAgente, ultimasExecucoes, type ExecucaoRotina, type Rotina } from '../../state/pecas';
import '../memoria/memoria.css';
import { GanchoRotina } from './GanchoRotina';

const ROTULO_STATUS: Record<ExecucaoRotina['status'], string> = { executando: 'Rodando', enviada: 'Enviada', silenciosa: 'Silenciosa', falhou: 'Falhou' };
const ROTULO_ORIGEM: Record<string, string> = { webhook: ' · webhook', manual: ' · à mão' };
const quando = (iso: string | null) => iso ? new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';

function descreverRotina(r: Rotina): string {
  if (r.tipo === 'cron') {
    const a = lerAgendamento(r.expressao);
    if (a.frequencia === 'diario') return `Todo dia às ${a.hora}`;
    if (a.frequencia === 'uteis') return `Dias úteis às ${a.hora}`;
    if (a.frequencia === 'semanal') return `${DIAS_DA_SEMANA[a.dia]}, às ${a.hora}`;
  }
  return r.tipo === 'unico' ? 'Uma vez' : 'Agenda personalizada';
}

function Linha({ r, aoMudar, aoErro }: { r: Rotina; aoMudar: (r: Rotina | null) => void; aoErro: (m: string) => void }) {
  const [aberta, setAberta] = useState(false);
  const [exec, setExec] = useState<ExecucaoRotina[] | null>(null);
  const [ocupada, setOcupada] = useState(false);
  const carregar = useCallback(() => ultimasExecucoes(r.id).then(setExec).catch(() => setExec([])), [r.id]);
  useEffect(() => { if (aberta) void carregar(); }, [aberta, carregar]);
  const rodar = async (f: () => Promise<void>) => { setOcupada(true); try { await f(); } catch (e) { aoErro(mensagemDeErro(e)); } finally { setOcupada(false); } };
  return <li className="rot-item">
    <div className="rot-topo">
      <button type="button" className="rot-titulo" aria-expanded={aberta} onClick={() => setAberta(v => !v)}><strong>{r.titulo}</strong></button>
      <span className={r.ativa ? 'rot-estado is-ativa' : 'rot-estado'}>{r.ativa ? 'Ativa' : 'Pausada'}</span>
    </div>
    <small>{descreverRotina(r)}{r.ativa && r.proxima_execucao ? ` · próxima: ${quando(r.proxima_execucao)}` : ''}</small>
    <div className="mem-acoes">
      <button type="button" disabled={ocupada} onClick={() => void rodar(async () => { aoMudar(await alterarRotina(r.id, { ativa: !r.ativa })); })}>{r.ativa ? 'Pausar' : 'Retomar'}</button>
      <button type="button" disabled={ocupada} onClick={() => void rodar(async () => { await executarRotina(r.id); setAberta(true); await carregar(); })}>Rodar agora</button>
      <button type="button" disabled={ocupada} onClick={() => void rodar(async () => { await apagarRotina(r.id); aoMudar(null); })}>Apagar</button>
    </div>
    {aberta && <div className="rot-execs">
      <p className="rot-pedido">{r.pedido}</p>
      {exec === null ? <small>Carregando…</small> : exec.length === 0 ? <small>Ainda não rodou.</small> :
        <ul>{exec.map(x => <li key={x.id}><span>{quando(x.iniciada_em)}{ROTULO_ORIGEM[x.origem ?? ''] ?? ''}</span><span className={x.status === 'falhou' ? 'rot-falhou' : ''}>{ROTULO_STATUS[x.status]}</span></li>)}</ul>}
      <GanchoRotina rotinaId={r.id} />
    </div>}
  </li>;
}

export function PainelRotinas({ agenteId }: { agenteId: string }) {
  const [itens, setItens] = useState<Rotina[] | null>(null);
  const [criando, setCriando] = useState(false);
  const [titulo, setTitulo] = useState('');
  const [pedido, setPedido] = useState('');
  const [frequencia, setFrequencia] = useState<Frequencia>('diario');
  const [hora, setHora] = useState('09:00');
  const [dia, setDia] = useState(1);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let ativo = true;
    listarRotinasDoAgente(agenteId).then(l => { if (ativo) setItens(l); }).catch(e => { if (ativo) { setItens([]); setErro(mensagemDeErro(e)); } });
    return () => { ativo = false; };
  }, [agenteId]);

  const cron = frequencia === 'nenhuma' ? null : montarAgendamento({ frequencia, hora, dia });
  const criar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!cron || !titulo.trim() || !pedido.trim()) return;
    setOcupado(true); setErro(null);
    try {
      const r = await criarRotina({ agente_id: agenteId, titulo: titulo.trim(), pedido: pedido.trim(), cron, fuso: Intl.DateTimeFormat().resolvedOptions().timeZone });
      setItens(l => [r, ...(l ?? [])]); setCriando(false); setTitulo(''); setPedido('');
    } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const mudou = (id: string) => (r: Rotina | null) => setItens(l => (l ?? []).flatMap(x => x.id !== id ? [x] : r ? [r] : []));

  return <section className="painel-mem" aria-label="Rotinas do bot">
    <p className="eyebrow tools-label">Rotinas</p>
    {itens === null ? <p className="tools-empty">Carregando…</p> : itens.length === 0 ? <p className="tools-empty">Nenhuma rotina deste bot.</p> :
      <ul className="mem-lista">{itens.map(r => <Linha key={r.id} r={r} aoMudar={mudou(r.id)} aoErro={setErro} />)}</ul>}
    {criando ? <form className="mem-edicao" onSubmit={e => void criar(e)}>
      <input aria-label="Título da rotina" placeholder="Título (ex.: Resumo da manhã)" value={titulo} maxLength={120} onChange={e => setTitulo(e.target.value)} />
      <textarea aria-label="O que o bot deve fazer" placeholder="O que o bot deve fazer a cada vez…" rows={3} value={pedido} onChange={e => setPedido(e.target.value)} />
      <div className="rot-quando">
        <select aria-label="Frequência" value={frequencia} onChange={e => setFrequencia(e.target.value as Frequencia)}>{FREQUENCIAS.filter(f => f.id !== 'nenhuma').map(f => <option key={f.id} value={f.id}>{f.rotulo}</option>)}</select>
        {frequencia === 'semanal' && <select aria-label="Dia da semana" value={dia} onChange={e => setDia(Number(e.target.value))}>{DIAS_DA_SEMANA.map((n, i) => <option key={n} value={i}>{n}</option>)}</select>}
        <input aria-label="Hora" type="time" value={hora} onChange={e => setHora(e.target.value)} />
      </div>
      <div><button type="button" onClick={() => setCriando(false)}>Cancelar</button><button type="submit" disabled={ocupado || !cron || !titulo.trim() || !pedido.trim()}>Criar rotina</button></div>
    </form> : <button type="button" className="mem-add" onClick={() => setCriando(true)}>+ Nova rotina</button>}
    {erro && <p className="mem-erro" role="alert">{erro}</p>}
  </section>;
}
