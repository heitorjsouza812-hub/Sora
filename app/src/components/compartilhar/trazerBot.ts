// Depois de importar um bot (link ou .zip), traz o bot novo para o estado do app: a barra lateral e
// a tela do bot já o encontram ao navegar para /bots/:id.
import { listarBots } from '../../api/bots';
import { adicionarBot } from '../../state/bots';
import { registrarBot } from '../../state/projetos';

export async function trazerBotImportado(id: string): Promise<void> {
  const bot = (await listarBots()).find(b => b.id === id);
  if (bot) { adicionarBot(bot); registrarBot(bot); }
}
