// Canais de equipe (Tear): conversa de um grupo de agentes com líder, tarefas e controles
// Parar / Retomar / Reatribuir / Cancelar, e "Apagados" (arquivados) com Restaurar.
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { Button, Input, Select } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { mensagemDeErro } from '../api/cliente';
import {
  agirNaTarefa, arquivarCanal, carregarCanais, carregarMensagensCanal, carregarTarefasCanal, criarCanal, enviarAoCanal, reagirA, reatribuirTarefa, restaurarCanal,
  useEquipe, type AcaoTarefa, type Canal, type TarefaCanal,
} from '../state/equipe';
import { useProjetos } from '../state/projetos';
import '../components/equipe/equipe.css';

const STATUS: Record<string, string> = { na_fila: 'Na fila', rodando: 'Trabalhando', aguardando_filhas: 'Esperando as subtarefas', parada: 'Parada', concluida: 'Concluída', falhou: 'Falhou', cancelada: 'Cancelada' };
const ROTULO_ACAO: Record<AcaoTarefa, string> = { parar: 'Parar', retomar: 'Retomar', reatribuir: 'Reatribuir', cancelar: 'Cancelar' };
const REACOES = ['👍', '🎉', '👀'];

function NovoCanal({ onCriado }: { onCriado: () => void }) {
  const p = useProjetos();
  const agentes = Object.values(p.agentes);
  const [nome, setNome] = useState('');
  const [membros, setMembros] = useState<string[]>([]);
  const [lider, setLider] = useState('');
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);
  const alternar = (id: string) => setMembros(m => m.includes(id) ? m.filter(x => x !== id) : [...m, id]);
  const enviar = async (ev: FormEvent) => {
    ev.preventDefault(); setErro(''); setEnviando(true);
    try { await criarCanal({ nome: nome.trim(), membros, lider_id: lider && membros.includes(lider) ? lider : null }); setNome(''); setMembros([]); setLider(''); onCriado(); }
    catch (e) { setErro(mensagemDeErro(e)); } finally { setEnviando(false); }
  };
  return (
    <form className="eq-novo" onSubmit={ev => void enviar(ev)} aria-label="Novo canal">
      <Input rotulo="Nome do canal" value={nome} onChange={e => setNome(e.target.value)} maxLength={80} />
      <fieldset><legend>Membros</legend>
        {agentes.length === 0 && <p className="eq-nota">Crie agentes primeiro para montar um canal.</p>}
        {agentes.map(a => <label key={a.id} className="eq-membro"><input type="checkbox" checked={membros.includes(a.id)} onChange={() => alternar(a.id)} /><i style={{ background: a.cor }} aria-hidden="true" />{a.nome}</label>)}
      </fieldset>
      <Select rotulo="Líder" value={lider} onChange={e => setLider(e.target.value)} vazio="Sem líder" opcoes={membros.map(id => ({ valor: id, rotulo: p.agentes[id]?.nome ?? id }))} />
      <Button type="submit" variante="primario" tamanho="M" disabled={!nome.trim() || !membros.length || enviando}>Criar canal</Button>
      {erro && <p className="eq-erro" role="alert">{erro}</p>}
    </form>
  );
}

function Tarefa({ t, canal }: { t: TarefaCanal; canal: Canal }) {
  const p = useProjetos();
  const [erro, setErro] = useState('');
  const [novoDono, setNovoDono] = useState('');
  const agir = async (f: () => Promise<void>) => { setErro(''); try { await f(); } catch (e) { setErro(mensagemDeErro(e)); } };
  const dono = p.agentes[t.donoId];
  return (
    <li className="eq-tarefa" data-status={t.status}>
      <span><b style={{ color: dono?.cor }}>{dono?.nome ?? 'Agente'}</b> · {STATUS[t.status] ?? t.status}{t.motivo ? ` (${t.motivo})` : ''}</span>
      <span className="eq-item-acoes">
        {t.acoes.filter(a => a !== 'reatribuir').map(a => <button key={a} type="button" onClick={() => void agir(() => agirNaTarefa(t.id, a as Exclude<AcaoTarefa, 'reatribuir'>))}>{ROTULO_ACAO[a]}</button>)}
        {t.acoes.includes('reatribuir') && <>
          <select aria-label="Novo responsável" value={novoDono} onChange={e => setNovoDono(e.target.value)}>
            <option value="">Reatribuir a…</option>
            {canal.membros.filter(m => m !== t.donoId).map(m => <option key={m} value={m}>{p.agentes[m]?.nome ?? m}</option>)}
          </select>
          <button type="button" disabled={!novoDono} onClick={() => void agir(() => reatribuirTarefa(t.id, novoDono))}>Reatribuir</button>
        </>}
      </span>
      {erro && <small className="eq-erro" role="alert">{erro}</small>}
    </li>
  );
}

function DetalheCanal({ canal }: { canal: Canal }) {
  const equipe = useEquipe();
  const p = useProjetos();
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState('');
  useEffect(() => { void carregarMensagensCanal(canal.id).catch(() => undefined); void carregarTarefasCanal(canal.id).catch(() => undefined); }, [canal.id]);
  const mensagens = equipe.mensagens[canal.id] ?? [];
  const tarefas = Object.values(equipe.tarefas).filter(t => t.canalId === canal.id && !['concluida', 'cancelada'].includes(t.status));
  const enviar = async (ev: FormEvent) => {
    ev.preventDefault(); const t = texto.trim(); if (!t) return; setErro('');
    try { await enviarAoCanal(canal.id, t); setTexto(''); } catch (e) { setErro(mensagemDeErro(e)); }
  };
  const lider = canal.liderId ? p.agentes[canal.liderId] : null;
  const alternarArquivo = () => (canal.arquivado ? restaurarCanal(canal.id) : arquivarCanal(canal.id)).then(() => carregarCanais(canal.arquivado)).catch(e => setErro(mensagemDeErro(e)));
  return (
    <section className="eq-detalhe" aria-label={`Canal ${canal.nome}`}>
      <header><h2>{canal.nome}</h2><small>{canal.membros.map(m => p.agentes[m]?.nome ?? '?').join(', ')}{lider ? ` · líder: ${lider.nome}` : ''}</small>
        <Button tamanho="M" variante="secundario" onClick={() => void alternarArquivo()}>{canal.arquivado ? 'Restaurar' : 'Apagar'}</Button>
      </header>
      {tarefas.length > 0 && <ul className="eq-tarefas" aria-label="Tarefas em andamento">{tarefas.map(t => <Tarefa key={t.id} t={t} canal={canal} />)}</ul>}
      <ol className="eq-mensagens" aria-live="polite">
        {mensagens.length === 0 && <li className="eq-nota">Nenhuma mensagem ainda. Escreva para a equipe abaixo.</li>}
        {mensagens.map(m => {
          const ag = m.agenteId ? p.agentes[m.agenteId] : null;
          const reacoes = equipe.reacoes[m.id] ?? {};
          return (
            <li key={m.id} className={`eq-msg eq-${m.tipo}`}>
              <b style={{ color: ag?.cor }}>{m.autor === 'usuario' ? 'Você' : m.autor === 'sistema' ? 'Sistema' : ag?.nome ?? 'Agente'}</b>
              <p>{m.texto}</p>
              <span className="eq-reacoes">
                {REACOES.map(r => <button key={r} type="button" aria-label={`Reagir com ${r}`} aria-pressed={!!reacoes[r]} onClick={() => void reagirA(m.id, r).catch(() => undefined)}>{r}{reacoes[r] ? ` ${reacoes[r]}` : ''}</button>)}
              </span>
            </li>
          );
        })}
      </ol>
      {!canal.arquivado && (
        <form className="eq-envio" onSubmit={ev => void enviar(ev)}>
          <Input rotulo="Mensagem para o canal" rotuloOculto value={texto} onChange={e => setTexto(e.target.value)} placeholder={`Mensagem para ${canal.nome}…`} />
          <Button type="submit" variante="primario" tamanho="M" disabled={!texto.trim()}>Enviar</Button>
        </form>
      )}
      {erro && <p className="eq-erro" role="alert">{erro}</p>}
    </section>
  );
}

export default function Canais() {
  const { canalId } = useParams();
  const navigate = useNavigate();
  const equipe = useEquipe();
  const [arquivados, setArquivados] = useState(false);
  const [criando, setCriando] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState('');
  useEffect(() => { carregarCanais(arquivados).catch(e => setErro(mensagemDeErro(e))).finally(() => setCarregando(false)); }, [arquivados]);
  const lista = useMemo(() => Object.values(equipe.canais).filter(c => c.arquivado === arquivados).sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')), [equipe.canais, arquivados]);
  const aberto = canalId ? equipe.canais[canalId] : undefined;
  return (
    <AppShell titulo="Canais de equipe" acoes={<span />}><main className="eq-pagina">
      <aside className="eq-lista" aria-label="Canais">
        <div className="eq-abas" role="group" aria-label="Filtro">
          <button type="button" aria-pressed={!arquivados} onClick={() => { setCarregando(true); setErro(''); setArquivados(false); }}>Canais</button>
          <button type="button" aria-pressed={arquivados} onClick={() => { setCarregando(true); setErro(''); setArquivados(true); }}>Apagados</button>
        </div>
        {!arquivados && <Button tamanho="M" variante="secundario" onClick={() => setCriando(v => !v)}>{criando ? 'Fechar' : 'Novo canal'}</Button>}
        {criando && <NovoCanal onCriado={() => { setCriando(false); void carregarCanais(false).catch(() => undefined); }} />}
        {carregando && <p className="eq-nota" role="status">Carregando canais…</p>}
        {erro && <p className="eq-erro" role="alert">{erro}</p>}
        {!carregando && !erro && !lista.length && <p className="eq-nota">{arquivados ? 'Nenhum canal apagado.' : 'Nenhum canal ainda. Crie um para colocar vários agentes para conversar e dividir tarefas.'}</p>}
        <ul>{lista.map(c => <li key={c.id}><button type="button" aria-current={c.id === canalId ? 'page' : undefined} onClick={() => navigate(`/canais/${c.id}`)}>{c.nome}<small>{c.membros.length} agentes</small></button></li>)}</ul>
      </aside>
      {aberto ? <DetalheCanal canal={aberto} /> : (
        <div className="eq-vazio"><SoraOrb size={96} color="#E2ECFF" state="idle" decorative /><p>Escolha um canal para ver as mensagens e as tarefas da equipe.</p></div>
      )}
    </main></AppShell>
  );
}
