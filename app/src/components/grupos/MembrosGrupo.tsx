import { useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { pararBotNoGrupo, retomarTarefaGrupo } from '../../api/grupos';
import { useBots } from '../../state/bots';
import { estadoDoMembro, receberTarefasDoGrupo, useGrupos } from '../../state/grupos';
import { passosDoAgente, useProjetos } from '../../state/projetos';
import { usePrecisaDeVoce } from '../../state/atencao';
import { OrbDoAutor } from './MensagemGrupo';
import './grupos.css';

const ROTULO_MEMBRO = { trabalhando: 'Trabalhando', parado: 'Parado', livre: 'Livre', precisa_de_voce: 'Precisa de você' } as const;

/** Quem está no grupo: a Sora (chefe) e os bots, cada um com o orb na própria cor, o estado e o último passo. */
export function MembrosGrupo({ membros, grupoId, liderId }: { membros: string[]; grupoId: string; liderId?: string | null }) {
  const bots = useBots();
  const tarefas = useGrupos().tarefas[grupoId];
  const atencao = usePrecisaDeVoce();
  const projetos = useProjetos();
  // Mantém a ordem escolhida pelo usuário (membros[0] é a Sora, mostrada à parte).
  const noGrupo = membros.filter(id => id !== (liderId ?? membros[0])).map(id => bots.find(bot => bot.id === id)).filter(bot => bot !== undefined);
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
    <ul className="grp-membros" aria-label="Membros do grupo">
      <li className="grp-membro"><OrbDoAutor tamanho={30} semente={3} /><span><b>Sora</b><small>Chefe de equipe</small></span></li>
      {noGrupo.map(bot => {
        const situacao = estadoDe(bot.id);
        const ultimo = passosDoAgente(projetos, bot.id, 0).at(-1)?.texto.trim();
        return <li className="grp-membro" key={bot.id} data-estado={situacao}>
          <OrbDoAutor cor={bot.cor} movimento={bot.movimento} tamanho={30} trabalhando={situacao === 'trabalhando'} semente={bot.nome.length} />
          <span><b style={{ color: bot.cor }}>{bot.nome}</b><small>{ROTULO_MEMBRO[situacao]}</small>{ultimo && <small className="grp-ultimo" title={ultimo}>Último passo: {ultimo}</small>}</span>
          {situacao === 'parado'
            ? <button type="button" aria-label={`Retomar ${bot.nome}`} disabled={parando === bot.id} onClick={() => void retomar(bot.id)}>{parando === bot.id ? 'Retomando…' : 'Retomar'}</button>
            : <button type="button" aria-label={`Parar ${bot.nome}`} disabled={situacao !== 'trabalhando' || parando === bot.id} onClick={() => void parar(bot.id)}>{parando === bot.id ? 'Parando…' : 'Parar'}</button>}
        </li>;
      })}
    </ul>
    {erro && <p className="grp-erro grp-erro-faixa" role="alert">{erro}</p>}
  </>;
}
