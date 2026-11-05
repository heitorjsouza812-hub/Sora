// Imagens REAIS de uma entrega. O `conteudo` vem do agente (ferramenta `entregar`) em formato livre:
// { dados, fontes, pendencias }, com a captura como { anexo_id, titulo, url }, "/v1/anexos/{id}" ou URL de
// imagem. Nada aqui inventa imagem: sem anexo nem URL de imagem, a lista sai vazia.
import type { EntregaGerada } from '../../state/projetos';

export interface ImagemEntrega {
  /** anexo do backend (carregado com token) */
  anexoId?: string;
  /** URL pública de imagem (https ou data:image) */
  src?: string;
  titulo?: string;
  /** página de onde veio a captura */
  url?: string;
}

const ANEXO = /\/v1\/anexos\/([0-9a-f-]{8,64})/i;
const ID_ANEXO = /^[0-9a-f-]{8,64}$/i;
const URL_IMAGEM = /^(https:\/\/\S+\.(png|jpe?g|gif|webp|avif)(\?\S*)?|data:image\/(png|jpe?g|gif|webp);base64,[a-z0-9+/=]+)$/i;
const MAX_IMAGENS = 12;
const MAX_PROFUNDIDADE = 6;

/** tira as chaves vazias (a legenda só leva o que existe) */
function semVazios<T extends object>(o: T): T {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as T;
}

const textoDe = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : undefined);

function daString(s: string): ImagemEntrega | null {
  const anexo = ANEXO.exec(s);
  if (anexo) return { anexoId: anexo[1] };
  if (URL_IMAGEM.test(s.trim())) return { src: s.trim() };
  return null;
}

export function imagensDaEntrega(entrega: Pick<EntregaGerada, 'imagens' | 'conteudo'>): ImagemEntrega[] {
  const achadas: ImagemEntrega[] = [];
  const vistas = new Set<string>();
  const guardar = (img: ImagemEntrega | null) => {
    if (!img || achadas.length >= MAX_IMAGENS) return;
    const chave = img.anexoId ?? img.src ?? '';
    if (!chave || vistas.has(chave)) return;
    vistas.add(chave); achadas.push(img);
  };
  type Legenda = { titulo?: string; url?: string };
  const andar = (v: unknown, nivel: number, herdada: Legenda = {}) => {
    if (nivel > MAX_PROFUNDIDADE || achadas.length >= MAX_IMAGENS) return;
    if (typeof v === 'string') { const img = daString(v); guardar(img && { ...img, ...semVazios(herdada) }); return; }
    if (Array.isArray(v)) { for (const x of v) andar(x, nivel + 1, herdada); return; }
    if (!v || typeof v !== 'object') return;
    const o = v as Record<string, unknown>;
    const id = textoDe(o.anexo_id) ?? textoDe(o.anexoId);
    // legenda: título e página (a "url" da captura é o próprio /v1/anexos/…, não serve de página);
    // o que faltar vem do objeto de fora (ex.: { titulo, url, captura: { anexo_id } })
    const pagina = [textoDe(o.pagina), textoDe(o.url_pagina), textoDe(o.url)].find(u => u && /^https?:\/\//i.test(u) && !URL_IMAGEM.test(u));
    const legenda = semVazios({
      titulo: textoDe(o.titulo) ?? textoDe(o.title) ?? herdada.titulo ?? textoDe(o.nome),
      url: pagina ?? herdada.url,
    });
    let usouLegenda = false;
    if (id && ID_ANEXO.test(id)) { guardar({ anexoId: id, ...legenda }); usouLegenda = true; }
    else {
      const direta = [o.imagem, o.src, o.url_imagem, o.captura, o.url].map(x => (typeof x === 'string' ? daString(x) : null)).find(Boolean);
      if (direta) { guardar({ ...direta, ...legenda }); usouLegenda = true; }
    }
    for (const [chave, x] of Object.entries(o)) {
      if (usouLegenda && ['anexo_id', 'anexoId', 'url', 'pagina', 'imagem', 'src', 'url_imagem', 'captura'].includes(chave)) continue;
      andar(x, nivel + 1, legenda);
    }
  };
  for (const s of entrega.imagens ?? []) guardar(daString(s));
  andar(entrega.conteudo, 0);
  return achadas;
}
