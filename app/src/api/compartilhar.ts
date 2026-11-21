// Compartilhar, exportar e importar bot (Onda 3). O link público mostra o "retrato" do bot
// (nome, função, cor, instruções, rotinas e habilidades escolhidas); nunca conversas, memória,
// arquivos ou chaves.
import { api, buscarAutenticado } from './cliente';
import type { Movimento } from '../types';

export interface RotinaCompartilhada { titulo: string; pedido: string; tipo: 'cron' | 'intervalo'; expressao: string; fuso: string; silencioso: boolean }
export interface HabilidadeCompartilhada { nome: string; descricao: string; corpo: string }
export interface BotRetrato {
  nome: string; funcao: string; papel: string; cor: string; movimento: Movimento; instrucoes: string;
  ferramentas: string[]; rotinas: RotinaCompartilhada[]; habilidades: HabilidadeCompartilhada[];
}
export interface Compartilhamento { codigo: string; url: string; usos: number; criado_em: string; bot: BotRetrato }
export interface BotPublico { codigo: string; criado_em: string; bot: BotRetrato }
export interface OpcoesRetrato { habilidades: string[]; com_rotinas: boolean }
export interface Importado { agente_id: string; nome: string; rotinas: number; habilidades: number; avisos: string[] }

export const verCompartilhamento = (botId: string) => api.get<Compartilhamento | null>(`/v1/bots/${encodeURIComponent(botId)}/compartilhamento`);
export const compartilharBot = (botId: string, opcoes: OpcoesRetrato) => api.post<Compartilhamento>(`/v1/bots/${encodeURIComponent(botId)}/compartilhamento`, opcoes);
export const pararDeCompartilhar = (botId: string) => api.delete<void>(`/v1/bots/${encodeURIComponent(botId)}/compartilhamento`);
export const verBotPublico = (codigo: string) => api.get<BotPublico>(`/v1/publico/bots/${encodeURIComponent(codigo)}`);
export const importarBotLink = (codigo: string) => api.post<Importado>('/v1/bots/importar-link', { codigo });

export async function importarBotArquivo(arquivo: File): Promise<Importado> {
  const corpo = new FormData();
  corpo.append('arquivo', arquivo, arquivo.name);
  const resposta = await buscarAutenticado('/v1/bots/importar', { method: 'POST', body: corpo });
  return resposta.json() as Promise<Importado>;
}

/** Baixa o .zip do bot (mesmas opções do link). */
export async function exportarBot(botId: string, nome: string, opcoes: OpcoesRetrato): Promise<void> {
  const resposta = await buscarAutenticado(`/v1/bots/${encodeURIComponent(botId)}/exportar`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opcoes),
  });
  const url = URL.createObjectURL(await resposta.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = `${nome.toLowerCase().replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'bot'}.sora-bot.zip`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
