// Conteúdo REAL de uma entrega para os cards (chat, revisão). O `conteudo` vem do agente (ferramenta
// `entregar`) em formato livre: { dados, fontes, pendencias }. Aqui só se lê o que está lá; o que não
// existe sai vazio (o card mostra um estado vazio honesto, nunca exemplo).
import type { EntregaGerada } from '../../state/projetos';

export interface LinkEntrega { titulo: string; url: string; dominio: string }

const TITULO_GENERICO = /^(refer[eê]ncias?|links?|fontes?|artigos?|p[aá]ginas?|sites?|resultados?|leia mais|saiba mais|aqui)\b/i;
const TITULO_LONGO = 48;

const CAMINHO_LONGO = 32;

/** "exemplo.com/a/b" (domínio + caminho, sem barra final nem ?query): o que distingue dois links.
 *  Caminho longo vira "exemplo.com/…/ultimo-trecho": o fim costuma ser o que difere. */
export function caminhoDoLink(l: Pick<LinkEntrega, 'url' | 'dominio'>): string {
  try {
    const caminho = new URL(l.url).pathname.replace(/\/+$/, '');
    if (!caminho || caminho === '/') return l.dominio;
    const inteiro = l.dominio + caminho;
    const partes = caminho.split('/').filter(Boolean);
    return inteiro.length > CAMINHO_LONGO && partes.length > 1 ? `${l.dominio}/…/${partes.at(-1)}` : inteiro;
  } catch { return l.dominio; }
}

/** Linha principal e secundária de um link. Título genérico ("Referência…") ou longo não distingue
 *  dois links numa tela estreita: aí a principal é o domínio/caminho e o título vai para baixo. */
export function rotuloDoLink(l: LinkEntrega): { principal: string; secundario: string } {
  const caminho = caminhoDoLink(l);
  const fraco = l.titulo === l.dominio || TITULO_GENERICO.test(l.titulo.trim()) || l.titulo.length > TITULO_LONGO;
  if (l.titulo === l.dominio) return { principal: caminho, secundario: '' };
  return fraco ? { principal: caminho, secundario: l.titulo } : { principal: l.titulo, secundario: caminho };
}
export interface EventoCalendario { quando: string; titulo: string }

type Entrada = Pick<EntregaGerada, 'conteudo' | 'links' | 'itens'>;

const MAX = 50;
const PROFUNDIDADE = 4;
const ehObjeto = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === 'object' && !Array.isArray(v);
const texto = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : undefined);
const primeiro = (o: Record<string, unknown>, chaves: string[]) => chaves.map(c => texto(o[c]) ?? (typeof o[c] === 'number' ? String(o[c]) : undefined)).find(Boolean);

/** `dados` da entrega (ou o próprio conteúdo, se veio sem o envelope). */
function dadosDe(e: Entrada): unknown {
  const c = e.conteudo;
  return ehObjeto(c) && 'dados' in c ? c.dados : c;
}

/** só http(s); anexo do backend não é link de referência */
function urlSegura(v: unknown): URL | null {
  const s = texto(v);
  if (!s || /\/v1\/anexos\//.test(s)) return null;
  try { const u = new URL(s); return u.protocol === 'https:' || u.protocol === 'http:' ? u : null; } catch { return null; }
}

export function linksDaEntrega(e: Entrada): LinkEntrega[] {
  const saida: LinkEntrega[] = []; const vistos = new Set<string>();
  const guardar = (u: URL | null, titulo?: string) => {
    if (!u || saida.length >= MAX || vistos.has(u.href)) return;
    vistos.add(u.href);
    const dominio = u.hostname.replace(/^www\./, '');
    saida.push({ url: u.href, dominio, titulo: titulo || dominio });
  };
  const andar = (v: unknown, nivel: number) => {
    if (nivel > PROFUNDIDADE) return;
    if (typeof v === 'string') { guardar(urlSegura(v)); return; }
    if (Array.isArray(v)) { for (const x of v) andar(x, nivel + 1); return; }
    if (!ehObjeto(v)) return;
    const url = ['url', 'link', 'href', 'fonte'].map(c => urlSegura(v[c])).find(Boolean) ?? null;
    if (url) guardar(url, primeiro(v, ['titulo', 'title', 'nome', 'texto']));
    for (const [c, x] of Object.entries(v)) if (!['url', 'link', 'href', 'fonte'].includes(c)) andar(x, nivel + 1);
  };
  for (const l of e.links ?? []) guardar(urlSegura(/^https?:\/\//.test(l.dominio) ? l.dominio : `https://${l.dominio}`), l.titulo);
  andar(dadosDe(e), 0);
  if (ehObjeto(e.conteudo)) andar(e.conteudo.fontes, 0);
  return saida;
}

/** Texto da entrega em parágrafos (string, lista de strings ou { texto | conteudo | corpo }). */
export function textosDaEntrega(e: Entrada): string[] {
  if (e.itens?.length) return e.itens;
  let d = dadosDe(e);
  if (ehObjeto(d)) d = primeiro(d, ['texto', 'conteudo', 'corpo', 'mensagem']) ?? d;
  if (typeof d === 'string') return d.split(/\n+/).map(s => s.trim()).filter(Boolean).slice(0, MAX);
  if (Array.isArray(d)) return d.map(x => (typeof x === 'string' ? x.trim() : ehObjeto(x) ? primeiro(x, ['texto', 'titulo', 'descricao']) ?? '' : '')).filter(Boolean).slice(0, MAX);
  return [];
}

/** Datas do calendário: itens com data (data | dia | quando | date) e o que acontece nela. */
export function eventosDaEntrega(e: Entrada): EventoCalendario[] {
  const saida: EventoCalendario[] = [];
  const andar = (v: unknown, nivel: number) => {
    if (nivel > PROFUNDIDADE || saida.length >= MAX) return;
    if (Array.isArray(v)) { for (const x of v) andar(x, nivel + 1); return; }
    if (!ehObjeto(v)) return;
    const quando = primeiro(v, ['data', 'dia', 'quando', 'date', 'horario']);
    const titulo = primeiro(v, ['titulo', 'tipo', 'tema', 'texto', 'descricao', 'legenda', 'title']);
    if (quando && titulo) { saida.push({ quando: /^\d{1,2}$/.test(quando) ? `Dia ${quando}` : quando, titulo }); return; }
    for (const x of Object.values(v)) andar(x, nivel + 1);
  };
  andar(dadosDe(e), 0);
  return saida;
}
