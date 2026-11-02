import { buscarAutenticado } from './cliente';

export interface AnexoRemoto {
  anexo_id: string;
  nome: string;
  tipo: string;
  tamanho: number;
}

export async function enviarAnexo(arquivo: File, signal?: AbortSignal): Promise<AnexoRemoto> {
  const corpo = new FormData();
  corpo.append('arquivo', arquivo, arquivo.name);
  const resposta = await buscarAutenticado('/v1/anexos', { method: 'POST', body: corpo, signal });
  return resposta.json() as Promise<AnexoRemoto>;
}
