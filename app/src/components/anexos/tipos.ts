// Anexos de mensagem (item 43) — tudo no navegador. Imagens ganham prévia via URL.createObjectURL;
// quem remove um anexo antes de enviar revoga a URL. Depois de enviado, o anexo é da mensagem.

export interface Anexo {
  id: string;
  nome: string;
  /** MIME (ex.: image/png); vazio quando o navegador não sabe */
  tipo: string;
  /** bytes */
  tamanho: number;
  /** blob: só para imagens (não sobrevive a recarregar a página) */
  urlPrevia?: string;
}

export const MAX_ANEXOS = 10;
export const MAX_BYTES = 20 * 1024 * 1024;

export const ehImagem = (a: Pick<Anexo, 'tipo'>) => a.tipo.startsWith('image/');

export function formatarTamanho(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} MB`;
}

/** rótulo curto do tipo: PDF, PNG, DOCX… */
export function rotuloTipo(a: Pick<Anexo, 'nome' | 'tipo'>) {
  const ext = a.nome.includes('.') ? a.nome.split('.').pop()! : '';
  if (ext && ext.length <= 5) return ext.toUpperCase();
  return a.tipo.split('/').pop()?.toUpperCase() || 'Arquivo';
}

let seq = 0;
const novoId = () => `anx-${Date.now().toString(36)}-${(++seq).toString(36)}`;

/** valida e converte arquivos; devolve os aceitos e as mensagens de erro */
export function prepararAnexos(arquivos: File[], jaTem: number): { novos: Anexo[]; erros: string[] } {
  const novos: Anexo[] = [];
  const erros: string[] = [];
  let grandes = 0;
  let excedentes = 0;
  for (const f of arquivos) {
    if (f.size > MAX_BYTES) { grandes++; continue; }
    if (jaTem + novos.length >= MAX_ANEXOS) { excedentes++; continue; }
    const tipo = f.type || '';
    novos.push({
      id: novoId(),
      nome: f.name || (tipo.startsWith('image/') ? `imagem-colada.${tipo.split('/')[1] ?? 'png'}` : 'arquivo'),
      tipo,
      tamanho: f.size,
      urlPrevia: tipo.startsWith('image/') ? URL.createObjectURL(f) : undefined,
    });
  }
  if (grandes) erros.push(grandes === 1 ? `Um arquivo passa de ${formatarTamanho(MAX_BYTES)} e não foi anexado.` : `${grandes} arquivos passam de ${formatarTamanho(MAX_BYTES)} e não foram anexados.`);
  if (excedentes) erros.push(`Máximo de ${MAX_ANEXOS} anexos por mensagem.`);
  return { novos, erros };
}

export function revogarAnexo(a: Anexo) {
  if (a.urlPrevia) URL.revokeObjectURL(a.urlPrevia);
}

// Ponte entre uma <ZonaSoltar> (área do chat) e o composer montado na tela.
export const EVENTO_ANEXAR = 'sora:anexar';
export function enviarAoComposer(arquivos: File[]) {
  window.dispatchEvent(new CustomEvent<File[]>(EVENTO_ANEXAR, { detail: arquivos }));
}
