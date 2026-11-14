import type { MensagemGrupoApi } from '../../api/grupos';
import { useBots } from '../../state/bots';

export const COR_SORA = '#E2ECFF';

/** Quem fala: a Sora (chefe, `membros[0]`, fora de `useBots`) ou um bot do grupo. */
export function useAutorDaMensagem(mensagem: Pick<MensagemGrupoApi, 'autor' | 'botId'>, soraId: string | undefined) {
  const bots = useBots();
  const bot = bots.find(item => item.id === mensagem.botId);
  const ehSora = mensagem.autor === 'sora' || (!!soraId && mensagem.botId === soraId);
  const nome = mensagem.autor === 'usuario' ? 'Você' : ehSora ? 'Sora' : mensagem.autor === 'sistema' ? 'Sistema' : bot?.nome ?? 'Bot';
  return { bot, ehSora, nome, cor: ehSora ? COR_SORA : bot?.cor };
}
