import { useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { cancelarTarefaGrupo, reatribuirTarefaGrupo, retomarTarefaGrupo, type StatusTarefaGrupo, type TarefaGrupoApi } from '../../api/grupos';
import { useBots } from '../../state/bots';
import { acoesDaTarefa, receberTarefasDoGrupo, tarefasAbertasDoGrupo } from '../../state/grupos';
import { Button, Select } from '../base';
import { OrbDoAutor } from './MensagemGrupo';
import './grupos.css';

const ROTULO_STATUS: Record<StatusTarefaGrupo, string> = {
  na_fila: 'Na fila', rodando: 'Trabalhando', aguardando_filhas: 'Esperando as subtarefas', parada: 'Parada', concluida: 'Concluída', falhou: 'Falhou', cancelada: 'Cancelada',
};

function rotulo(tarefa: TarefaGrupoApi): string {
  if (tarefa.status === 'parada' && tarefa.motivo === 'aguardando_decisao') return 'Aguardando sua decisão';
  return ROTULO_STATUS[tarefa.status] ?? tarefa.status;
}

/** Tarefas abertas do grupo. Parada ou com falha: Retomar, Reatribuir a outro bot ou Cancelar. */
export function TarefasGrupo({ grupoId, membros, liderId, tarefas }: { grupoId: string; membros: string[]; liderId?: string | null; tarefas: Record<string, TarefaGrupoApi> | undefined }) {
  const bots = useBots();
  const [ocupada, setOcupada] = useState('');
  const [reatribuindo, setReatribuindo] = useState('');
  const [novoDono, setNovoDono] = useState('');
  const [erro, setErro] = useState('');
  // Quem trabalha ou espera na fila já aparece na faixa de trabalho (com Parar); aqui só o que pede uma decisão.
  const abertas = tarefasAbertasDoGrupo(tarefas).filter(tarefa => tarefa.grupoId === grupoId && tarefa.status !== 'rodando' && tarefa.status !== 'na_fila');
  if (!abertas.length) return null;
  const botsDoGrupo = bots.filter(bot => membros.includes(bot.id) && bot.id !== (liderId ?? membros[0]));
  const nomeDe = (id: string) => botsDoGrupo.find(bot => bot.id === id)?.nome ?? bots.find(bot => bot.id === id)?.nome ?? 'Bot';

  const executar = async (tarefaId: string, acao: () => Promise<TarefaGrupoApi[]>) => {
    setOcupada(tarefaId); setErro('');
    try { receberTarefasDoGrupo(await acao()); setReatribuindo(''); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setOcupada(''); }
  };

  return <section className="grp-tarefas" aria-label="Tarefas do grupo">
    <h3>Tarefas abertas</h3>
    <ul>
      {abertas.map(tarefa => {
        const acoes = acoesDaTarefa(tarefa);
        const dono = botsDoGrupo.find(bot => bot.id === tarefa.donoId);
        const outros = botsDoGrupo.filter(bot => bot.id !== tarefa.donoId);
        return <li key={tarefa.id} data-status={tarefa.status}>
          <OrbDoAutor cor={dono?.cor} movimento={dono?.movimento} tamanho={22} trabalhando={tarefa.status === 'rodando'} semente={tarefa.revisao} />
          <span className="grp-tarefa-texto"><b>{nomeDe(tarefa.donoId)}</b><small>{rotulo(tarefa)}</small></span>
          <span className="grp-tarefa-acoes">
            {acoes.includes('retomar') && <Button tamanho="P" variante="secundario" disabled={ocupada === tarefa.id} onClick={() => void executar(tarefa.id, () => retomarTarefaGrupo(tarefa.id))}>Retomar</Button>}
            {acoes.includes('reatribuir') && outros.length > 0 && <Button tamanho="P" variante="secundario" disabled={ocupada === tarefa.id} aria-expanded={reatribuindo === tarefa.id} onClick={() => { setReatribuindo(atual => atual === tarefa.id ? '' : tarefa.id); setNovoDono(outros[0]?.id ?? ''); }}>Reatribuir</Button>}
            {acoes.includes('cancelar') && <Button tamanho="P" variante="perigo" disabled={ocupada === tarefa.id} onClick={() => void executar(tarefa.id, () => cancelarTarefaGrupo(tarefa.id))}>Cancelar</Button>}
          </span>
          {reatribuindo === tarefa.id && <form className="grp-reatribuir" onSubmit={evento => { evento.preventDefault(); if (novoDono) void executar(tarefa.id, () => reatribuirTarefaGrupo(tarefa.id, novoDono)); }}>
            <Select rotulo={`Passar a tarefa de ${nomeDe(tarefa.donoId)} para`} value={novoDono} onChange={evento => setNovoDono(evento.target.value)} opcoes={outros.map(bot => ({ valor: bot.id, rotulo: bot.nome }))} />
            <Button type="submit" tamanho="P" variante="primario" disabled={!novoDono || ocupada === tarefa.id}>Passar tarefa</Button>
          </form>}
        </li>;
      })}
    </ul>
    {erro && <p className="grp-erro" role="alert">{erro}</p>}
  </section>;
}
