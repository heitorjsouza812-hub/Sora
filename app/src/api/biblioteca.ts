// Biblioteca de arquivos (backend: app/api/biblioteca.py). Baixar continua em /v1/anexos/{id}.
import { api, buscarAutenticado } from './cliente';

export type Vista = 'todos' | 'recentes' | 'favoritos' | 'sem_pasta';
export type TipoArquivo = 'imagem' | 'documento' | 'outro';
export interface Arquivo { id: string; nome: string; tipo: string; tamanho: number; origem: string; pasta_id: string | null; favorito: boolean; criado_em: string }
export interface PaginaArquivos { itens: Arquivo[]; proximo: string | null }
export interface Pasta { id: string; nome: string; total: number; criada_em: string }
export interface FiltroArquivos { vista?: Vista; pastaId?: string; tipo?: TipoArquivo; busca?: string; antes?: string }

export function listarArquivos(f: FiltroArquivos = {}): Promise<PaginaArquivos> {
  const q = new URLSearchParams();
  if (f.pastaId) q.set('pasta_id', f.pastaId); else if (f.vista && f.vista !== 'todos') q.set('vista', f.vista);
  if (f.tipo) q.set('tipo', f.tipo);
  if (f.busca?.trim()) q.set('busca', f.busca.trim());
  if (f.antes) q.set('antes', f.antes);
  const consulta = q.toString();
  return api.get<PaginaArquivos>(`/v1/biblioteca/arquivos${consulta ? `?${consulta}` : ''}`);
}
export const alterarArquivo = (id: string, patch: { pasta_id?: string | null; favorito?: boolean }) =>
  api.patch<Arquivo>(`/v1/biblioteca/arquivos/${encodeURIComponent(id)}`, patch);
export const listarPastas = () => api.get<Pasta[]>('/v1/biblioteca/pastas');
export const criarPasta = (nome: string) => api.post<Pasta>('/v1/biblioteca/pastas', { nome: nome.trim() });
export const renomearPasta = (id: string, nome: string) => api.patch<Pasta>(`/v1/biblioteca/pastas/${encodeURIComponent(id)}`, { nome: nome.trim() });
export const apagarPasta = (id: string) => api.delete<void>(`/v1/biblioteca/pastas/${encodeURIComponent(id)}`);

/** Blob do arquivo (o download exige o token, então não dá para usar o endereço direto). */
export async function blobDoArquivo(id: string): Promise<Blob> {
  return (await buscarAutenticado(`/v1/anexos/${encodeURIComponent(id)}`)).blob();
}

const unidades = ['B', 'KB', 'MB', 'GB'];
export function tamanhoLegivel(bytes: number): string {
  let valor = bytes, i = 0;
  while (valor >= 1024 && i < unidades.length - 1) { valor /= 1024; i += 1; }
  return `${i === 0 ? valor : valor.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} ${unidades[i]}`;
}
