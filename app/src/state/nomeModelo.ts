// Nome curto e legível de um modelo, e a lista local dos "principais" (usada enquanto o servidor não manda `principal`).

const MARCAS: Record<string, string> = {
  gpt: 'GPT', oss: 'OSS', llama: 'Llama', gemini: 'Gemini', claude: 'Claude', gemma: 'Gemma', deepseek: 'DeepSeek',
  mistral: 'Mistral', mixtral: 'Mixtral', qwen: 'Qwen', grok: 'Grok', kimi: 'Kimi', glm: 'GLM', phi: 'Phi', command: 'Command',
};
// Sufixos que só dizem como o modelo foi publicado, não o que ele é.
const SUFIXOS = new Set(['latest', 'preview', 'instruct', 'versatile', 'it', 'exp', 'experimental', 'free', 'chat-v1']);
const DATAS = [/[-_.]20\d{2}[-_]?\d{2}[-_]?\d{2}$/, /[-_.]20\d{2}[-_]\d{2}$/, /[-_]\d{2}[-_]20\d{2}$/, /[-_]\d{2}[-_]\d{2}$/, /[-_]\d{4,5}$/, /[-_]00\d$/];

function semPrefixo(id: string): string {
  const semTag = id.trim().replace(/:(free|beta|extended|thinking|nitro)$/i, '');
  return semTag.slice(semTag.lastIndexOf('/') + 1);
}

function tirarSufixos(texto: string): string {
  let atual = texto;
  for (let volta = 0; volta < 6; volta++) {
    let proximo = atual;
    for (const data of DATAS) proximo = proximo.replace(data, '');
    proximo = proximo.replace(/[-_ ](latest|preview|instruct|versatile|it|exp|experimental)$/i, '');
    if (proximo === atual) break;
    atual = proximo;
  }
  return atual;
}

function formatar(ficha: string): string {
  if (/[A-Z]/.test(ficha)) return ficha;
  if (/^o\d/.test(ficha)) return ficha;
  if (/^\d+(\.\d+)?[bkm]$/.test(ficha)) return ficha.toUpperCase();
  if (/^\d+x\d+b$/.test(ficha)) return ficha.replace(/b$/, 'B');
  if (/^\d/.test(ficha)) return ficha;
  return MARCAS[ficha] ?? ficha.charAt(0).toLocaleUpperCase('pt-BR') + ficha.slice(1);
}

/** `openai/gpt-oss-120b` → "GPT-OSS 120B"; `gemini-2.5-flash` → "Gemini 2.5 Flash"; `claude-sonnet-4-5-20250929` → "Claude Sonnet 4.5". */
export function nomeCurtoDoModelo(idOuNome: string): string {
  const original = idOuNome.trim();
  if (!original) return original;
  let texto = tirarSufixos(semPrefixo(original));
  // "llama3.2:3b" e "llama3" → "llama 3.2 3b"
  texto = texto.replace(/^([a-z]{3,})(\d)/i, '$1-$2').replace(/:/g, '-');
  const fichas = texto.split(/[-_\s]+/).filter(f => f && !SUFIXOS.has(f.toLowerCase()));
  if (!fichas.length) return original;
  const juntas: string[] = [];
  for (let i = 0; i < fichas.length; i++) {
    const atual = fichas[i]!;
    const seguinte = fichas[i + 1];
    const minuscula = atual.toLowerCase();
    if (minuscula === 'gpt' && seguinte?.toLowerCase() === 'oss') { juntas.push('GPT-OSS'); i++; continue; }
    if (minuscula === 'gpt' && seguinte && /^\d/.test(seguinte)) { juntas.push(`GPT-${formatar(seguinte)}`); i++; continue; }
    if (/^\d{1,2}$/.test(atual) && /^\d{1,2}$/.test(fichas[i - 1] ?? '') && juntas.length) { juntas[juntas.length - 1] = `${juntas[juntas.length - 1]}.${atual}`; continue; }
    juntas.push(formatar(atual));
  }
  return juntas.join(' ') || original;
}

// ---- principais ---------------------------------------------------------------------------------------------------
const PRINCIPAIS: RegExp[] = [
  /^gpt-5/, /^gpt-4\.1/, /^gpt-4o/, /^o[134](-mini|-pro)?$/, /^gpt-oss/,
  /^claude-(opus|sonnet|haiku)-[4-9]/, /^claude-3-?[57]-(sonnet|haiku)/,
  /^gemini-(2\.5|3)/, /^llama-?(3\.3|3\.1|4)/, /^llama-3\.3-70b/, /^qwen/, /^kimi/,
  /^grok-[3-9]/, /^deepseek-(chat|reasoner|v)/, /^mistral-(large|medium|small)/, /^magistral/,
];
const NAO_PRINCIPAL = /(guard|image|tts|audio|live|embed|vision-preview|search|transcribe|realtime|nano-\d)/i;

export function ehModeloPrincipal(id: string): boolean {
  const limpo = semPrefixo(id).toLowerCase();
  return !NAO_PRINCIPAL.test(limpo) && PRINCIPAIS.some(re => re.test(limpo));
}

/** `principal` do servidor manda; sem ele, vale a lista local. Provedor sem nenhum principal (ou local) mostra tudo. */
export function separarPrincipais<T extends { modelo: string; principal?: boolean }>(modelos: T[], tudoPrincipal = false): { principais: T[]; outros: T[] } {
  if (tudoPrincipal) return { principais: modelos, outros: [] };
  const principais = modelos.filter(m => m.principal ?? ehModeloPrincipal(m.modelo));
  if (!principais.length) return { principais: modelos, outros: [] };
  return { principais, outros: modelos.filter(m => !principais.includes(m)) };
}
