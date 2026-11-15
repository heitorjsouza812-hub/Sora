import { useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { pararBotNoGrupo, retomarTarefaGrupo } from '../../api/grupos';
import { useBots } from '../../state/bots';
import { estadoDoMembro, receberTarefasDoGrupo, useGrupos } from '../../state/grupos';
import { passosDoAgente, useProjetos } from '../../state/projetos';
import { usePrecisaDeVoce } from '../../state/atencao';

export type SituacaoMembro = 'trabalhando' | 'parado' | 'livre' | 'precisa_de_voce';

/** Quem está no grupo (os bots, na ordem escolhida; a Sora é a líder) e o que cada um faz agora. */
export function useMembrosDoGrupo(membros: string[], grupoId: string, liderId?: string | null) {
  const bots = useBots();
  const tarefas = useGrupos().tarefas[grupoId];
  const atencao = usePrecisaDeVoce();
  const projetos = useProjetos();
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
  const situacaoDe = (botId: string): SituacaoMembro => {
    const doGrupo = estadoDoMembro(tarefas, botId);
    if (doGrupo !== 'livre') return doGrupo;
    return atencao.lista.some(pedido => pedido.botId === botId && pedido.grupoId === grupoId) ? 'precisa_de_voce' : 'livre';
  };
  const ultimoPassoDe = (botId: string) => passosDoAgente(projetos, botId, 0).at(-1)?.texto.trim();
  return { noGrupo, situacaoDe, ultimoPassoDe, parar, retomar, parando, erro };
}
