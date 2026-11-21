// Agenda das rotinas: o mês com o que vai rodar (previstas) e o que já rodou (feitas). Clicar num
// dia de hoje em diante mostra o dia e deixa criar uma rotina nele (só nesse dia, toda semana ou
// todo dia, no horário escolhido).
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { chaveDoDia, inicioDaGrade, obterAgenda, type Agenda } from '../../api/agenda';
import { criarRotina } from '../../state/pecas';
import { useBots } from '../../state/bots';
import { Button } from '../base';
import './rotinas.css';

const SEMANA = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
const MES = new Intl.DateTimeFormat('pt-BR', { month: 'long', year: 'numeric' });
const DIA_LONGO = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
const HORA = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' });
const MARCA_FEITA: Record<string, string> = { enviada: '✓', silenciosa: '✓', falhou: '!', executando: '…' };
type Repetir = 'uma' | 'semana' | 'dia';

interface ItemDia { chave: string; hora: string; titulo: string; feita?: string; quando: number }

export function AgendaRotinas({ aoCriar }: { aoCriar?: () => void }) {
  const [hoje] = useState(() => new Date());
  const [mes, setMes] = useState(() => new Date(hoje.getFullYear(), hoje.getMonth(), 1));
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [dia, setDia] = useState<Date | null>(null);
  const [versao, setVersao] = useState(0);

  const inicio = useMemo(() => inicioDaGrade(mes), [mes]);
  const dias = useMemo(() => Array.from({ length: 42 }, (_, i) => new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + i)), [inicio]);

  useEffect(() => {
    let vivo = true;
    const fim = new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + 42);
    obterAgenda(inicio, fim).then(a => { if (vivo) { setAgenda(a); setErro(null); } }).catch(e => { if (vivo) setErro(mensagemDeErro(e)); });
    return () => { vivo = false; };
  }, [inicio, versao]);

  const porDia = useMemo(() => {
    const mapa = new Map<string, ItemDia[]>();
    const por = (iso: string, titulo: string, feita?: string) => {
      const d = new Date(iso);
      const chave = chaveDoDia(d);
      const lista = mapa.get(chave) ?? [];
      lista.push({ chave: `${iso}-${titulo}`, hora: HORA.format(d), titulo, feita, quando: d.getTime() });
      mapa.set(chave, lista);
    };
    (agenda?.feitas ?? []).forEach(f => por(f.iniciada_em, f.titulo, f.status));
    (agenda?.previstas ?? []).forEach(p => por(p.quando, p.titulo));
    for (const lista of mapa.values()) lista.sort((a, b) => a.quando - b.quando);
    return mapa;
  }, [agenda]);

  const mudarMes = (delta: number) => { setDia(null); setMes(m => new Date(m.getFullYear(), m.getMonth() + delta, 1)); };
  const ehHoje = (d: Date) => chaveDoDia(d) === chaveDoDia(hoje);
  const passou = (d: Date) => chaveDoDia(d) < chaveDoDia(hoje);
  const itensDoDia = dia ? porDia.get(chaveDoDia(dia)) ?? [] : [];

  return <section className="agenda" aria-label="Agenda das rotinas">
    <header className="agenda-topo">
      <Button tamanho="P" variante="fantasma" onClick={() => mudarMes(-1)} aria-label="Mês anterior">‹</Button>
      <strong>{MES.format(mes)}</strong>
      <Button tamanho="P" variante="fantasma" onClick={() => mudarMes(1)} aria-label="Próximo mês">›</Button>
      <Button tamanho="P" variante="fantasma" onClick={() => { setDia(null); setMes(new Date(hoje.getFullYear(), hoje.getMonth(), 1)); }}>Hoje</Button>
    </header>
    {erro && <p className="mem-erro" role="alert">{erro}</p>}
    <div className="agenda-grade" role="grid" aria-label={`Rotinas de ${MES.format(mes)}`}>
      {SEMANA.map(s => <span key={s} className="agenda-semana" role="columnheader">{s}</span>)}
      {dias.map(d => {
        const itens = porDia.get(chaveDoDia(d)) ?? [];
        const foraDoMes = d.getMonth() !== mes.getMonth();
        return <button key={chaveDoDia(d)} type="button" role="gridcell" className="agenda-dia"
          data-fora={foraDoMes || undefined} data-hoje={ehHoje(d) || undefined} aria-pressed={dia ? chaveDoDia(dia) === chaveDoDia(d) : false}
          aria-label={`${DIA_LONGO.format(d)}: ${itens.length ? `${itens.length} rotina(s)` : 'nenhuma rotina'}`}
          onClick={() => setDia(d)}>
          <span className="agenda-numero">{d.getDate()}</span>
          {itens.slice(0, 2).map(i => <span key={i.chave} className="agenda-item" data-feita={i.feita ? i.feita : undefined}>{i.feita ? MARCA_FEITA[i.feita] ?? '' : i.hora} {i.titulo}</span>)}
          {itens.length > 2 && <span className="agenda-mais">+{itens.length - 2}</span>}
          {itens.length > 0 && <span className="agenda-ponto" aria-hidden="true" />}
        </button>;
      })}
    </div>
    {dia && <div className="agenda-detalhe">
      <strong>{DIA_LONGO.format(dia)}</strong>
      {itensDoDia.length === 0 ? <small>Nada marcado neste dia.</small> :
        <ul>{itensDoDia.map(i => <li key={i.chave}><span>{i.hora}</span><span>{i.titulo}</span><span>{i.feita ? (i.feita === 'falhou' ? 'Falhou' : 'Rodou') : 'Vai rodar'}</span></li>)}</ul>}
      {!passou(dia) && <NovaNoDia dia={dia} aoCriar={() => { setVersao(v => v + 1); aoCriar?.(); }} />}
    </div>}
  </section>;
}

function NovaNoDia({ dia, aoCriar }: { dia: Date; aoCriar: () => void }) {
  const bots = useBots();
  const [titulo, setTitulo] = useState('');
  const [pedido, setPedido] = useState('');
  const [hora, setHora] = useState('09:00');
  const [repetir, setRepetir] = useState<Repetir>('uma');
  const [bot, setBot] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const criar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!titulo.trim() || !pedido.trim()) return;
    const [h, m] = hora.split(':').map(Number);
    const tempo = repetir === 'uma'
      ? { em: new Date(dia.getFullYear(), dia.getMonth(), dia.getDate(), h, m).toISOString() }
      : { cron: `${m} ${h} * * ${repetir === 'semana' ? dia.getDay() : '*'}` };
    setOcupado(true); setAviso(null);
    try {
      await criarRotina({ titulo: titulo.trim(), pedido: pedido.trim(), fuso: Intl.DateTimeFormat().resolvedOptions().timeZone, ...(bot ? { agente_id: bot } : {}), ...tempo });
      setTitulo(''); setPedido(''); setAviso('Rotina criada.');
      aoCriar();
    } catch (e) { setAviso(mensagemDeErro(e)); } finally { setOcupado(false); }
  };

  return <form className="agenda-nova" onSubmit={e => void criar(e)} aria-label="Nova rotina neste dia">
    <input aria-label="Título da rotina" placeholder="Título (ex.: Conferir pedidos)" value={titulo} maxLength={120} onChange={e => setTitulo(e.target.value)} />
    <textarea aria-label="O que fazer" placeholder="O que o bot deve fazer…" rows={2} value={pedido} onChange={e => setPedido(e.target.value)} />
    <div className="agenda-nova__linha">
      <input aria-label="Hora" type="time" value={hora} onChange={e => setHora(e.target.value)} />
      <select aria-label="Repetir" value={repetir} onChange={e => setRepetir(e.target.value as Repetir)}>
        <option value="uma">Só neste dia</option>
        <option value="semana">Toda semana neste dia</option>
        <option value="dia">Todo dia a partir de agora</option>
      </select>
      <select aria-label="Quem faz" value={bot} onChange={e => setBot(e.target.value)}>
        <option value="">Sora</option>
        {bots.map(b => <option key={b.id} value={b.id}>{b.nome}</option>)}
      </select>
    </div>
    <div className="agenda-nova__linha"><Button type="submit" variante="primario" tamanho="P" carregando={ocupado} disabled={ocupado || !titulo.trim() || !pedido.trim()}>Criar rotina</Button>{aviso && <small role="status">{aviso}</small>}</div>
  </form>;
}
