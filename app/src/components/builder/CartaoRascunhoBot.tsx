import { useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api/cliente';
import { confirmarRascunhoBot, descartarRascunhoBot, type AjustesRascunhoBot } from '../../api/bots';
import { COR_SORA, MOVIMENTOS, PALETA_AGENTES } from '../../data/planejador';
import { FERRAMENTAS_AGENTE, rotuloFerramenta } from '../../data/ferramentas';
import { marcarRascunhoDecididoAqui, type RascunhoNoChat } from '../../state/sora';
import { carregarBots } from '../../state/bots';
import { iniciarProjetos } from '../../state/projetos';
import type { Movimento } from '../../types';
import { SoraOrb } from '../mascot';
import { toast } from '../base';
import { DIAS_DA_SEMANA, FREQUENCIAS, lerAgendamento, montarAgendamento, type Frequencia } from './rotinaAmigavel';
import './builder.css';

export interface CartaoRascunhoBotProps { rascunho: RascunhoNoChat }

/** Ferramenta fora do catálogo (conector, plugin): mostra um nome legível, nunca o id cru. */
const rotulo = (id: string) => { const r = rotuloFerramenta(id); return r === id ? id.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()) : r; };

export function CartaoRascunhoBot({ rascunho }: CartaoRascunhoBotProps) {
  const [ajustes, setAjustes] = useState<AjustesRascunhoBot>({
    nome: rascunho.nome, funcao: rascunho.funcao, cor: rascunho.cor, instrucoes: rascunho.instrucoes,
    ferramentas: [...rascunho.ferramentas], rotina: rascunho.rotina,
  });
  const [agenda, setAgenda] = useState(() => lerAgendamento(rascunho.rotina?.agendamento));
  const [descricaoRotina, setDescricaoRotina] = useState(rascunho.rotina?.descricao ?? '');
  const [movimento, setMovimento] = useState<Movimento | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [resolvido, setResolvido] = useState<'criado' | 'descartado' | null>(null);
  const [botId, setBotId] = useState('');
  const [erro, setErro] = useState('');
  const alterar = <K extends keyof AjustesRascunhoBot>(campo: K, valor: AjustesRascunhoBot[K]) => setAjustes(atual => ({ ...atual, [campo]: valor }));

  const corAtual = (ajustes.cor ?? rascunho.cor).toUpperCase();
  const cores = [...new Set([corAtual, ...PALETA_AGENTES])].filter(c => c !== COR_SORA.toUpperCase());
  const escolhidas = ajustes.ferramentas ?? [];
  const ids = [...new Set([...FERRAMENTAS_AGENTE.map(f => f.id), ...escolhidas])];
  const alternarFerramenta = (id: string) => alterar('ferramentas', escolhidas.includes(id) ? escolhidas.filter(f => f !== id) : [...escolhidas, id]);
  const fuso = rascunho.rotina?.fuso ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const textoRotina = agenda.frequencia === 'nenhuma' ? 'Sem rotina' : agenda.frequencia === 'personalizada' ? 'Horário já definido' : `${FREQUENCIAS.find(f => f.id === agenda.frequencia)?.rotulo} · ${agenda.hora}`;

  /** `undefined` = inválida (já mostrou o erro); `null` = sem rotina. */
  const montarRotina = (): AjustesRascunhoBot['rotina'] | undefined => {
    if (agenda.frequencia === 'nenhuma') return null;
    if (agenda.frequencia === 'personalizada') return rascunho.rotina ? { ...rascunho.rotina, descricao: descricaoRotina.trim() || rascunho.rotina.descricao } : null;
    const agendamento = montarAgendamento(agenda);
    if (!agendamento) { setErro('Escolha um horário válido para a rotina.'); return undefined; }
    if (!descricaoRotina.trim()) { setErro('Diga o que o bot deve fazer na rotina.'); return undefined; }
    return { descricao: descricaoRotina.trim(), agendamento, fuso };
  };

  const confirmar = async () => {
    if (!ajustes.nome?.trim() || !ajustes.funcao?.trim()) { setErro('Preencha o nome e a função do bot.'); return; }
    setErro('');
    const rotina = montarRotina();
    if (rotina === undefined) return;
    marcarRascunhoDecididoAqui(rascunho.id);
    setSalvando(true);
    try {
      const bot = await confirmarRascunhoBot(rascunho.id, { ...ajustes, rotina });
      setBotId(bot.id);
      setResolvido('criado');
      // O backend escolhe o movimento pela função; se a pessoa escolheu outro, ajusta logo em seguida.
      if (movimento && movimento !== bot.movimento) await api.patch(`/v1/agentes/${bot.id}`, { movimento }).catch(() => undefined);
      // A barra lateral e a conversa 1:1 usam stores diferentes. Recarregue as duas
      // para o bot confirmado poder ser aberto imediatamente, sem atualizar a página.
      await Promise.all([
        carregarBots().catch(() => undefined),
        iniciarProjetos().catch(() => undefined),
      ]);
      toast({ mensagem: `${bot.nome} foi criado`, tom: 'sucesso' });
    } catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível criar o bot.'); }
    finally { setSalvando(false); }
  };
  const descartar = async () => {
    marcarRascunhoDecididoAqui(rascunho.id);
    setSalvando(true); setErro('');
    try { await descartarRascunhoBot(rascunho.id); setResolvido('descartado'); }
    catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível descartar o rascunho.'); }
    finally { setSalvando(false); }
  };

  const decisao = resolvido ?? (rascunho.resolucao ? (rascunho.resolucao.status === 'confirmado' ? 'criado' : 'descartado') : null);
  const idDoBot = botId || rascunho.resolucao?.agenteId || '';
  if (decisao) return <article className="bot-draft-card is-resolved" style={{ '--agent': corAtual } as CSSProperties} role="status">{decisao === 'criado' && <i aria-hidden="true">✓</i>}<strong>{decisao === 'criado' ? 'Bot criado' : 'Rascunho descartado'}</strong><span>{ajustes.nome}</span>{decisao === 'criado' && idDoBot && <Link className="st-btn-ghost" to={`/bots/${idDoBot}`} aria-label={`Abrir conversa com ${ajustes.nome}`}>Abrir conversa</Link>}</article>;

  return <article className="bot-draft-card" style={{ '--agent': corAtual } as CSSProperties} aria-label={`Rascunho do bot ${ajustes.nome}`}>
    <header><SoraOrb size={40} color={corAtual} movimento={movimento ?? 'gira'} state={salvando ? 'thinking' : 'idle'} glow={false} decorative seed={19} /><div><span>Rascunho de bot</span><strong>{ajustes.nome || 'Novo bot'}</strong></div></header>
    <p>Confira as seções abaixo. O bot só nasce quando você confirmar.</p>
    <div className="bot-draft-sections">
      <details open><summary>Identidade <span>{ajustes.funcao}</span></summary><div className="bot-draft-grid">
        <label>Nome<input value={ajustes.nome ?? ''} onChange={e => alterar('nome', e.target.value)} /></label>
        <label>Função<input value={ajustes.funcao ?? ''} onChange={e => alterar('funcao', e.target.value)} /></label>
        <div className="bot-draft-wide" role="group" aria-label="Cor"><span className="bot-draft-label">Cor</span><div className="bot-draft-swatches">
          {cores.map(c => <button key={c} type="button" className={corAtual === c ? 'is-on' : ''} style={{ '--choice': c } as CSSProperties} aria-label={`Cor ${c}`} aria-pressed={corAtual === c} onClick={() => alterar('cor', c)} />)}
        </div></div>
        <div className="bot-draft-wide" role="group" aria-label="Movimento"><span className="bot-draft-label">Movimento</span><div className="bot-draft-chips">
          <button type="button" aria-pressed={movimento === null} className={movimento === null ? 'is-on' : ''} onClick={() => setMovimento(null)}>Automático</button>
          {MOVIMENTOS.map(m => <button key={m.id} type="button" title={m.descricao} aria-pressed={movimento === m.id} className={movimento === m.id ? 'is-on' : ''} onClick={() => setMovimento(m.id)}>{m.nome}</button>)}
        </div></div>
      </div></details>
      <details><summary>Instruções <span>{ajustes.instrucoes ? 'Configuradas' : 'A definir'}</span></summary><label><span className="sr-only">Instruções</span><textarea rows={4} value={ajustes.instrucoes ?? ''} onChange={e => alterar('instrucoes', e.target.value)} /></label></details>
      <details><summary>Ferramentas <span>{escolhidas.length ? `${escolhidas.length} ${escolhidas.length === 1 ? 'escolhida' : 'escolhidas'}` : 'Padrão'}</span></summary>
        <div className="bot-draft-chips bot-draft-tools" role="group" aria-label="Ferramentas do bot">
          {ids.map(id => <button key={id} type="button" aria-pressed={escolhidas.includes(id)} className={escolhidas.includes(id) ? 'is-on' : ''} onClick={() => alternarFerramenta(id)}>{rotulo(id)}</button>)}
        </div></details>
      <details><summary>Rotina <span>{textoRotina}</span></summary><div className="bot-draft-grid bot-draft-rotina">
        <label>Quando<select value={agenda.frequencia} onChange={e => setAgenda(a => ({ ...a, frequencia: e.target.value as Frequencia }))}>
          {FREQUENCIAS.map(f => <option key={f.id} value={f.id}>{f.rotulo}</option>)}
          {agenda.frequencia === 'personalizada' && <option value="personalizada">Horário já definido</option>}
        </select></label>
        {(agenda.frequencia === 'diario' || agenda.frequencia === 'uteis' || agenda.frequencia === 'semanal') && <label>Hora<input type="time" value={agenda.hora} onChange={e => setAgenda(a => ({ ...a, hora: e.target.value }))} /></label>}
        {agenda.frequencia === 'semanal' && <label>Dia<select value={agenda.dia} onChange={e => setAgenda(a => ({ ...a, dia: Number(e.target.value) }))}>{DIAS_DA_SEMANA.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>}
        {agenda.frequencia !== 'nenhuma' && <label className="bot-draft-wide">O que fazer<input value={descricaoRotina} onChange={e => setDescricaoRotina(e.target.value)} placeholder="Ex.: Resumir as novidades e me avisar" /></label>}
      </div></details>
    </div>
    {erro && <p className="bot-draft-error" role="alert">{erro}</p>}
    <footer><button type="button" className="st-btn-ghost" disabled={salvando} onClick={() => void descartar()}>Descartar</button><button type="button" className="st-btn-primary" disabled={salvando} onClick={() => void confirmar()}>{salvando ? 'Criando…' : 'Criar bot'}</button></footer>
  </article>;
}
