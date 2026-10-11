// Planejador SIMULADO da Sora.
// Recebe o pedido do usuário e devolve uma equipe completa: título do projeto, tarefas em ordem,
// agentes (nome, função, cor, movimento, ferramentas, instruções) e o ROTEIRO de trabalho de cada
// agente (passos com tempos realistas) que alimenta o painel "Trabalho".
// Tudo é determinístico a partir do texto do pedido (mesmo pedido → mesma equipe).
import type { Agente, Entrega, Movimento, PassoTrabalho, ResultadoPasso } from '../types';

export const COR_SORA = '#E2ECFF';

/** Paleta dos agentes: bem distinta entre si e da Sora (#E2ECFF nunca entra aqui). */
export const PALETA_AGENTES = [
  '#56A8FF', // azul (Atlas)
  '#AC80FF', // violeta (Luna)
  '#46E8A8', // verde (Nina)
  '#FF8A5C', // laranja
  '#FF6FAE', // rosa
  '#FFD15C', // âmbar
  '#4FD6E8', // ciano
  '#A3E35A', // lima
  '#FF6B6B', // coral
  '#8C9BFF', // índigo
  '#E89BFF', // orquídea
  '#5CE0C6', // turquesa
] as const;

/** Banco de nomes curtos em PT-BR (nunca "Sora"). */
export const NOMES_AGENTES = [
  'Ravi', 'Íris', 'Caio', 'Lia', 'Téo', 'Bia', 'Davi', 'Mel', 'Noa', 'Gael', 'Zoe', 'Leo', 'Maya', 'Cora',
  'Iara', 'Tom', 'Lis', 'Rui', 'Duda', 'Juno', 'Elis', 'Otto', 'Vera', 'Ciro', 'Nara', 'Ian', 'Ayla', 'Enzo',
] as const;

export const MOVIMENTOS: { id: Movimento; nome: string; descricao: string }[] = [
  { id: 'vibracao', nome: 'Vibração', descricao: 'fina e rápida' },
  { id: 'espiral', nome: 'Espiral', descricao: 'torção em espiral' },
  { id: 'ondas', nome: 'Ondas', descricao: 'ondas na superfície' },
  { id: 'gira', nome: 'Gira', descricao: 'gira e cintila' },
];

// ---------- tipos do plano ----------

/** Passo de roteiro, com tempo relativo ao início do trabalho do agente. */
export interface PassoRoteiro {
  tipo: PassoTrabalho['tipo'];
  texto: string;
  ferramenta?: string;
  acao?: string;
  parametros?: Record<string, unknown>;
  resultado?: ResultadoPasso;
  paraAgenteId?: string;
  origem?: 'sora' | 'usuario';
  em: number;   // ms desde o início do trabalho do agente
  dur: number;  // ms
}

export interface EntregaGerada {
  tipo: Entrega['tipo'];
  titulo: string;   // ex.: "Pesquisa"
  resumo: string;   // ex.: "4 referências"
  itens?: string[];
  links?: { titulo: string; dominio: string }[];
  imagens?: string[];
}

/** Agente como a Sora o cria (o modelo de dados + instruções e quando foi criado). */
export interface AgenteSora extends Agente {
  instrucoes: string;
  avulso: boolean;      // criado no estúdio "Agentes" (fora de uma equipe)
  criadoEm: number;     // ms (epoch) — numa equipe, o momento em que "nasce" da Sora
}

export interface TarefaGerada {
  id: string; titulo: string; ordem: number; dependeDe: string[]; agenteId: string;
}

export interface EquipePlanejada {
  modelo: string;                 // id do modelo de equipe usado
  titulo: string;                 // título do projeto
  assunto: string;                // assunto extraído do pedido
  resposta: string;               // primeira resposta da Sora
  tarefas: TarefaGerada[];
  agentes: AgenteSora[];
  roteiros: Record<string, PassoRoteiro[]>;   // por agenteId
  entregas: Record<string, EntregaGerada>;    // por agenteId
}

// ---------- utilidades ----------

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const slug = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
export const novoId = (prefixo: string) => `${prefixo}-${Math.random().toString(36).slice(2, 8)}`;

/** Extrai um assunto curto do pedido: "…minha cafeteria: pesquise…" → "cafeteria". */
export function extrairAssunto(pedido: string) {
  const t = pedido.replace(/\s+/g, ' ').trim();
  const corta = (s: string) => {
    const palavras = s.trim().split(' ').filter(Boolean);
    let out = '';
    for (const p of palavras) { if ((out + ' ' + p).trim().length > 38) break; out = (out + ' ' + p).trim(); }
    return out.replace(/[\s,;:.!?-]+$/, '');
  };
  const posse = t.match(/\b(?:minhas?|meus?|nossas?|nossos?)\s+([^:.,;!?]{3,60})/i);
  if (posse) return corta(posse[1].split(/\s(?:e|com|que|para|pra)\s/)[0]);
  const sobre = t.match(/\b(?:sobre|para|pra)\s+(?:o |a |os |as |um |uma )?([^:.,;!?]{3,60})/i);
  if (sobre) return corta(sobre[1].split(/\s(?:e|com|que)\s/)[0]);
  return corta(t.replace(/^(crie|criar|faça|fazer|monte|montar|quero|preciso de|preciso)\s+/i, ''));
}

/** Verbo do status "trabalhando" a partir da função. */
export function verboPara(funcao: string) {
  const f = slug(funcao);
  if (/pesquis|coleta|refer|busca/.test(f)) return 'Pesquisando';
  if (/visual|design|criac|arte|imag|gera/.test(f)) return 'Criando';
  if (/texto|roteir|escrit|copy|legend|redac|conteud/.test(f)) return 'Escrevendo';
  if (/codig|desenvolv|program|front/.test(f)) return 'Programando';
  if (/anali|dado|metric/.test(f)) return 'Analisando';
  if (/edic|montag|video/.test(f)) return 'Editando';
  if (/resum|relator|sintes/.test(f)) return 'Resumindo';
  if (/triag|organiz|calend|planej/.test(f)) return 'Organizando';
  if (/revis/.test(f)) return 'Revisando';
  if (/ux|experien|fluxo/.test(f)) return 'Desenhando';
  return 'Trabalhando';
}

// ---------- catálogo de ações por ferramenta ----------

interface Ctx { assunto: string; titulo: string; papel: Papel }
interface Acao { acao: string; texto: string; parametros: Record<string, unknown>; resultado: ResultadoPasso; dur: number }

const DOMINIOS = ['behance.net', 'pinterest.com', 'instagram.com', 'canva.com', 'medium.com', 'nngroup.com', 'statista.com', 'g1.globo.com'];

function linksPara(ctx: Ctx, n = 4) {
  const base = ctx.papel.links ?? [`Referências de ${ctx.assunto}`, `Tendências para ${ctx.assunto} em 2026`, `Estudos de caso: ${ctx.assunto}`, `Boas práticas: ${ctx.assunto}`];
  const h = hash(ctx.assunto);
  return base.slice(0, n).map((titulo, i) => ({ titulo, dominio: DOMINIOS[(h + i * 3) % DOMINIOS.length] }));
}

const ACOES: Record<string, (c: Ctx) => Acao> = {
  Perplexity: c => ({ acao: 'perplexity.buscar', texto: 'Buscando na web', dur: 3200,
    parametros: { consulta: `${c.assunto} referências`, limite: 8, idioma: 'pt-BR' },
    resultado: { resumo: '4 links', links: linksPara(c) } }),
  'Google Drive': c => ({ acao: 'drive.salvar', texto: 'Salvando no Google Drive', dur: 1400,
    parametros: { pasta: `Sora/${c.titulo}`, arquivo: `${slug(c.papel.tarefa)}.pdf` }, resultado: { resumo: '1 arquivo salvo' } }),
  Notion: c => ({ acao: 'notion.criar_pagina', texto: 'Organizando no Notion', dur: 1800,
    parametros: { titulo: `${c.papel.tarefa} · ${c.assunto}`, blocos: 12 }, resultado: { resumo: 'Página criada', itens: [`${c.papel.tarefa} · ${c.assunto}`] } }),
  Figma: c => ({ acao: 'figma.criar_frame', texto: 'Montando frames no Figma', dur: 2600,
    parametros: { arquivo: c.titulo, frames: ['Desktop', 'Mobile', 'Componentes'], grade: 12 }, resultado: { resumo: '3 frames' } }),
  Higgsfield: c => ({ acao: 'higgsfield.gerar_imagem', texto: 'Gerando imagens', dur: 3400,
    parametros: { prompt: `${c.assunto}, luz natural, estilo editorial`, formato: '1:1', variacoes: 3 },
    resultado: { resumo: '3 imagens', imagens: c.papel.imagens ?? [] } }),
  Midjourney: c => ({ acao: 'midjourney.imaginar', texto: 'Explorando conceitos visuais', dur: 3000,
    parametros: { prompt: `${c.assunto} --ar 4:5 --style raw`, variacoes: 4 }, resultado: { resumo: '4 conceitos', imagens: c.papel.imagens ?? [] } }),
  Canva: c => ({ acao: 'canva.aplicar_modelo', texto: 'Aplicando a identidade no Canva', dur: 2200,
    parametros: { modelo: 'lançamento', marca: c.assunto, formatos: ['1080×1080', '1080×1920', 'A3'] }, resultado: { resumo: '3 formatos' } }),
  ChatGPT: c => ({ acao: 'chatgpt.redigir', texto: 'Redigindo textos', dur: 2600,
    parametros: { tom: 'próximo e direto', tamanho: 'curto', assunto: c.assunto }, resultado: { resumo: '6 textos', itens: c.papel.textos } }),
  Gemini: c => ({ acao: 'gemini.analisar', texto: 'Analisando os dados', dur: 2800,
    parametros: { fonte: 'resultados da coleta', foco: ['tendências', 'oportunidades'] }, resultado: { resumo: '5 insights', itens: c.papel.textos } }),
  Claude: c => ({ acao: 'claude.revisar', texto: 'Revisando o material', dur: 2200,
    parametros: { criterios: ['clareza', 'tom', 'ortografia'], assunto: c.assunto }, resultado: { resumo: 'Revisão concluída' } }),
  'Google Agenda': c => ({ acao: 'agenda.criar_eventos', texto: 'Montando o calendário', dur: 2000,
    parametros: { mes: 'novembro', eventos: 12, assunto: c.assunto }, resultado: { resumo: '12 datas' } }),
  Instagram: () => ({ acao: 'instagram.agendar_rascunhos', texto: 'Preparando rascunhos no Instagram', dur: 1800,
    parametros: { quantidade: 12, publicar: false }, resultado: { resumo: '12 rascunhos (não publicados)' } }),
  Gmail: () => ({ acao: 'gmail.buscar', texto: 'Lendo a caixa de entrada', dur: 2600,
    parametros: { consulta: 'is:unread newer_than:7d', limite: 50 }, resultado: { resumo: '38 e-mails' } }),
  'Planilhas Google': c => ({ acao: 'sheets.atualizar', texto: 'Registrando na planilha', dur: 1600,
    parametros: { planilha: c.titulo, aba: c.papel.tarefa, linhas: 24 }, resultado: { resumo: '24 linhas' } }),
  GitHub: c => ({ acao: 'github.criar_pr', texto: 'Abrindo pull request', dur: 2400,
    parametros: { repo: slug(c.assunto) || 'site', branch: 'sora/primeira-versao', arquivos: 14 }, resultado: { resumo: 'PR #1 aberto' } }),
  Vercel: c => ({ acao: 'vercel.publicar_preview', texto: 'Publicando prévia privada', dur: 2600,
    parametros: { projeto: slug(c.assunto) || 'site', ambiente: 'preview' }, resultado: { resumo: 'Prévia pronta (privada)' } }),
  Runway: c => ({ acao: 'runway.gerar_video', texto: 'Gerando cenas de vídeo', dur: 3600,
    parametros: { cenas: 4, duracao: '15s', estilo: c.assunto }, resultado: { resumo: '4 cenas', imagens: c.papel.imagens ?? [] } }),
  ElevenLabs: () => ({ acao: 'elevenlabs.narrar', texto: 'Gravando a narração', dur: 2400,
    parametros: { voz: 'Clara', idioma: 'pt-BR', velocidade: 1 }, resultado: { resumo: 'Narração de 0:28' } }),
  YouTube: () => ({ acao: 'youtube.enviar_rascunho', texto: 'Enviando como rascunho', dur: 2000,
    parametros: { visibilidade: 'privado', publicar: false }, resultado: { resumo: 'Rascunho enviado' } }),
  Slack: c => ({ acao: 'slack.enviar_resumo', texto: 'Preparando resumo no Slack', dur: 1400,
    parametros: { canal: '#geral', enviar: false, assunto: c.assunto }, resultado: { resumo: 'Mensagem pronta para aprovação' } }),
  Miro: c => ({ acao: 'miro.criar_quadro', texto: 'Desenhando o fluxo no Miro', dur: 2400,
    parametros: { quadro: c.titulo, telas: 6 }, resultado: { resumo: 'Fluxo com 6 telas' } }),
  Trello: c => ({ acao: 'trello.criar_cartoes', texto: 'Criando cartões no Trello', dur: 1600,
    parametros: { quadro: c.titulo, cartoes: 9 }, resultado: { resumo: '9 cartões' } }),
  Airtable: c => ({ acao: 'airtable.registrar', texto: 'Registrando no Airtable', dur: 1600,
    parametros: { base: c.titulo, registros: 18 }, resultado: { resumo: '18 registros' } }),
  'Hugging Face': c => ({ acao: 'huggingface.classificar', texto: 'Classificando com um modelo aberto', dur: 2400,
    parametros: { modelo: 'pt-sentimento', itens: 120, assunto: c.assunto }, resultado: { resumo: '120 itens classificados' } }),
};

function acaoPara(ferramenta: string, ctx: Ctx): Acao {
  const f = ACOES[ferramenta];
  if (f) return f(ctx);
  const s = slug(ferramenta).replace(/-/g, '_') || 'ferramenta';
  return { acao: `${s}.executar`, texto: `Usando ${ferramenta}`, dur: 2000, parametros: { tarefa: ctx.papel.tarefa, assunto: ctx.assunto }, resultado: { resumo: 'Concluído' } };
}

// ---------- modelos de equipe ----------

interface Papel {
  funcao: string;
  tarefa: string;                       // título da tarefa no plano
  ferramentas: string[];
  movimento: Movimento;
  espera: string;
  nome?: string;                        // fixo (modelo da campanha de exemplo)
  cor?: string;
  pedido: (a: string) => string;        // prompt que a Sora envia ao agente
  pensamentos: (a: string) => string[];
  entrega: (a: string) => EntregaGerada;
  handoff: string;                      // o que é passado ao próximo ("4 referências")
  links?: string[];
  imagens?: string[];
  textos?: string[];
}

interface Modelo {
  id: string;
  palavras: RegExp;
  titulo: (a: string) => string;
  resposta: (a: string) => string;
  papeis: (a: string, pedido: string) => Papel[];
}

const IMG = ['/campanha/post.jpg', '/campanha/story.jpg', '/campanha/post.jpg'];

const MODELOS: Modelo[] = [
  {
    id: 'video',
    palavras: /v[ií]deo|reels?\b|youtube|tiktok|roteiro|anima[cç]/i,
    titulo: a => `Vídeo · ${cap(a)}`,
    resposta: a => `Vou montar uma equipe para produzir o vídeo sobre ${a}.`,
    papeis: () => [
      { funcao: 'Roteiro', tarefa: 'Escrever roteiro', ferramentas: ['ChatGPT', 'Notion'], movimento: 'ondas', espera: 'Aguardando',
        pedido: a => `Escreva um roteiro de 30 s sobre ${a}, com gancho nos 3 primeiros segundos.`,
        pensamentos: a => [`Vou começar pelo gancho: o que faz alguém parar o scroll em ${a}?`, 'Dividir em 4 cenas curtas, com uma frase por cena.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Roteiro', resumo: '4 cenas', itens: ['Cena 1 · gancho', 'Cena 2 · problema', 'Cena 3 · solução', 'Cena 4 · chamada'] }),
        handoff: 'o roteiro', textos: ['Gancho em 3 s', 'Cena de bastidores', 'Prova social', 'Chamada final'] },
      { funcao: 'Geração de cenas', tarefa: 'Gerar cenas', ferramentas: ['Runway', 'Higgsfield'], movimento: 'espiral', espera: 'Aguardando roteiro',
        pedido: a => `Gere as 4 cenas do roteiro sobre ${a}, formato vertical 9:16.`,
        pensamentos: () => ['Manter a mesma luz e paleta em todas as cenas.', 'Gerar uma variação extra para a cena do gancho.'],
        entrega: () => ({ tipo: 'imagem', titulo: 'Cenas', resumo: '4 cenas', imagens: [] }),
        handoff: '4 cenas' },
      { funcao: 'Edição e narração', tarefa: 'Editar e narrar', ferramentas: ['ElevenLabs', 'YouTube'], movimento: 'vibracao', espera: 'Aguardando cenas',
        pedido: a => `Monte o vídeo sobre ${a} com narração em PT-BR e deixe como rascunho.`,
        pensamentos: () => ['Cortar no ritmo da narração, cenas de 6 a 8 s.', 'Legendas grandes para quem assiste sem som.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Vídeo', resumo: '0:30 · rascunho', itens: ['Vídeo 9:16 com legendas', 'Narração em PT-BR', 'Rascunho privado no YouTube'] }),
        handoff: 'o vídeo' },
    ],
  },
  {
    id: 'emails',
    palavras: /e-?mails?\b|caixa de entrada|inbox|gmail/i,
    titulo: () => 'Resumo dos e-mails',
    resposta: () => 'Vou montar uma equipe para triar e resumir seus e-mails.',
    papeis: () => [
      { funcao: 'Triagem', tarefa: 'Triar e-mails', ferramentas: ['Gmail', 'Planilhas Google'], movimento: 'vibracao', espera: 'Aguardando',
        pedido: () => 'Leia os e-mails não lidos dos últimos 7 dias e classifique por prioridade.',
        pensamentos: () => ['Separar o que exige resposta do que é só informativo.', 'Marcar remetentes recorrentes como prioridade.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Triagem', resumo: '38 e-mails', itens: ['7 urgentes', '12 aguardam resposta', '19 informativos'] }),
        handoff: '38 e-mails classificados' },
      { funcao: 'Resumo', tarefa: 'Resumir e sugerir respostas', ferramentas: ['ChatGPT', 'Slack'], movimento: 'ondas', espera: 'Aguardando triagem',
        pedido: () => 'Resuma os e-mails urgentes e sugira respostas curtas (sem enviar nada).',
        pensamentos: () => ['Um parágrafo por conversa, com o próximo passo em destaque.', 'Rascunhos de resposta ficam para sua aprovação.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Resumo', resumo: '7 resumos', itens: ['Fornecedor: confirmar entrega de sexta', 'Cliente: pedido de orçamento', 'Banco: atualização cadastral', 'Equipe: reunião remarcada'] }),
        handoff: 'os resumos', textos: ['Resposta ao fornecedor', 'Resposta ao cliente'] },
    ],
  },
  {
    id: 'site',
    palavras: /\bsite\b|landing|p[aá]gina|web ?app|aplicativo|loja virtual|e-?commerce|portf[oó]lio/i,
    titulo: a => `Site · ${cap(a)}`,
    resposta: a => `Vou montar uma equipe para criar o site de ${a}.`,
    papeis: () => [
      { funcao: 'UX e estrutura', tarefa: 'Definir estrutura', ferramentas: ['Miro', 'Notion'], movimento: 'ondas', espera: 'Aguardando',
        pedido: a => `Defina as seções e o fluxo do site de ${a}, pensando primeiro no celular.`,
        pensamentos: a => [`Quem visita o site de ${a} quer resolver o quê em 10 segundos?`, 'Hero, prova social, oferta, perguntas, contato.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Estrutura', resumo: '6 seções', itens: ['Hero com chamada', 'Benefícios', 'Depoimentos', 'Oferta', 'Perguntas frequentes', 'Contato'] }),
        handoff: 'a estrutura com 6 seções' },
      { funcao: 'Design visual', tarefa: 'Criar layout', ferramentas: ['Figma', 'Higgsfield'], movimento: 'espiral', espera: 'Aguardando estrutura',
        pedido: a => `Crie o layout do site de ${a} seguindo a estrutura, desktop e mobile.`,
        pensamentos: () => ['Tipografia grande no hero, bastante respiro.', 'Gerar uma imagem principal que conte a história.'],
        entrega: () => ({ tipo: 'imagem', titulo: 'Layout', resumo: '3 telas', imagens: [] }),
        handoff: '3 telas' },
      { funcao: 'Código', tarefa: 'Programar e publicar prévia', ferramentas: ['GitHub', 'Vercel'], movimento: 'vibracao', espera: 'Aguardando layout',
        pedido: a => `Implemente o layout do site de ${a} e publique uma prévia privada.`,
        pensamentos: () => ['Componentes reutilizáveis para cada seção.', 'Prévia privada: nada vai ao ar sem aprovação.'],
        entrega: () => ({ tipo: 'links', titulo: 'Prévia', resumo: '1 link privado', links: [{ titulo: 'Prévia do site', dominio: 'vercel.app' }] }),
        handoff: 'a prévia' },
    ],
  },
  {
    id: 'campanha',
    palavras: /campanh|marketing|lan[cç]a(mento|r)|divulg|an[uú]ncio|posts?\b|instagram|redes sociais/i,
    titulo: a => `Campanha · ${cap(a)}`,
    resposta: () => 'Vou organizar uma equipe para preparar sua campanha.',
    papeis: a => [
      { nome: 'Atlas', cor: '#56A8FF', funcao: 'Pesquisa e referências', tarefa: 'Pesquisar referências', ferramentas: ['Perplexity', 'Google Drive', 'Notion'],
        movimento: 'vibracao', espera: 'Aguardando',
        pedido: x => `Pesquise referências de campanhas de lançamento para ${x}.`,
        pensamentos: x => [`Vou buscar referências de ${x} independentes, com foco em identidade e tom.`, 'Selecionar as 4 mais fortes e organizar os links.'],
        entrega: () => ({ tipo: 'links', titulo: 'Pesquisa', resumo: '4 referências', links: linksPara({ assunto: a, titulo: '', papel: { links: LINKS_CAMPANHA(a) } as Papel }) }),
        handoff: '4 referências', links: LINKS_CAMPANHA(a) },
      { nome: 'Luna', cor: '#AC80FF', funcao: 'Criação visual', tarefa: 'Criar peças', ferramentas: ['Higgsfield', 'Figma', 'Canva'],
        movimento: 'espiral', espera: 'Aguardando referências',
        pedido: x => `Crie as peças da campanha de ${x} a partir das referências do Atlas.`,
        pensamentos: () => ['Paleta quente, fotos acolhedoras, tipografia moderna.', 'Três formatos: post, story e cartaz.'],
        entrega: () => ({ tipo: 'imagem', titulo: 'Peças', resumo: '3 peças', imagens: IMG }),
        handoff: '3 peças', imagens: IMG },
      { nome: 'Nina', cor: '#46E8A8', funcao: 'Textos e planejamento', tarefa: 'Organizar calendário', ferramentas: ['Notion', 'Google Agenda', 'Instagram'],
        movimento: 'ondas', espera: 'Aguardando peças',
        pedido: x => `Escreva as legendas e monte o calendário de posts da campanha de ${x}.`,
        pensamentos: () => ['Legendas curtas, com convite claro.', 'Distribuir 12 posts ao longo do mês, alternando formatos.'],
        entrega: () => ({ tipo: 'calendario', titulo: 'Calendário', resumo: '12 posts', itens: ['Post', 'Story', 'Reels'] }),
        handoff: 'o calendário', textos: ['Legenda do post de inauguração', 'Legenda do story'] },
    ],
  },
  {
    id: 'pesquisa',
    palavras: /pesquisa de mercado|mercado|concorr|benchmark|an[aá]lise|relat[oó]rio|pesquis|estudo/i,
    titulo: a => `Pesquisa · ${cap(a)}`,
    resposta: a => `Vou montar uma equipe para pesquisar o mercado de ${a}.`,
    papeis: () => [
      { funcao: 'Coleta de dados', tarefa: 'Coletar dados', ferramentas: ['Perplexity', 'Planilhas Google'], movimento: 'vibracao', espera: 'Aguardando',
        pedido: a => `Colete dados públicos sobre o mercado de ${a}: tamanho, concorrentes e preços.`,
        pensamentos: a => [`Começar pelos 5 principais concorrentes de ${a}.`, 'Registrar tudo numa planilha com fonte.'],
        entrega: () => ({ tipo: 'links', titulo: 'Coleta', resumo: '12 fontes', links: [] }),
        handoff: '12 fontes' },
      { funcao: 'Análise', tarefa: 'Analisar', ferramentas: ['Gemini', 'Planilhas Google'], movimento: 'gira', espera: 'Aguardando dados',
        pedido: a => `Analise os dados coletados sobre ${a} e encontre oportunidades.`,
        pensamentos: () => ['Comparar preço × posicionamento.', 'Procurar lacunas que ninguém atende bem.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Análise', resumo: '5 insights', itens: ['Preço médio em alta', 'Pouca oferta no delivery', 'Público jovem pouco atendido', 'Concorrência forte no centro', 'Fidelidade é diferencial'] }),
        handoff: '5 insights', textos: ['Oportunidade no delivery', 'Público jovem pouco atendido'] },
      { funcao: 'Relatório', tarefa: 'Escrever relatório', ferramentas: ['Notion', 'Google Drive'], movimento: 'ondas', espera: 'Aguardando análise',
        pedido: a => `Escreva um relatório executivo de 1 página sobre o mercado de ${a}.`,
        pensamentos: () => ['Começar pela conclusão; detalhes depois.', 'Um gráfico simples vale mais que três parágrafos.'],
        entrega: () => ({ tipo: 'texto', titulo: 'Relatório', resumo: '1 página', itens: ['Resumo executivo', 'Concorrentes', 'Oportunidades', 'Próximos passos'] }),
        handoff: 'o relatório' },
    ],
  },
];

const LINKS_CAMPANHA = (a: string) => [
  `Branding de ${a} independentes`, `Moodboard: ${a} e aconchego`, 'Campanhas de inauguração', `Paletas e tipografia para ${a}`,
];

function papeisGenericos(pedido: string): Papel[] {
  const palavras = pedido.trim().split(/\s+/).length;
  const n = palavras < 8 ? 2 : palavras > 26 ? 4 : 3;
  const todos: Papel[] = [
    { funcao: 'Pesquisa e contexto', tarefa: 'Entender o contexto', ferramentas: ['Perplexity', 'Notion'], movimento: 'vibracao', espera: 'Aguardando',
      pedido: x => `Levante o contexto e as referências necessárias para: ${x}.`,
      pensamentos: x => [`Primeiro, entender o que já existe sobre ${x}.`, 'Separar o essencial do acessório.'],
      entrega: () => ({ tipo: 'links', titulo: 'Contexto', resumo: '4 referências', links: [] }), handoff: 'o contexto' },
    { funcao: 'Execução', tarefa: 'Produzir', ferramentas: ['ChatGPT', 'Google Drive'], movimento: 'espiral', espera: 'Aguardando contexto',
      pedido: x => `Produza a primeira versão de: ${x}.`,
      pensamentos: () => ['Fazer uma versão completa antes de polir.', 'Deixar tudo salvo e organizado.'],
      entrega: () => ({ tipo: 'texto', titulo: 'Primeira versão', resumo: '1 documento', itens: ['Versão 1 completa'] }), handoff: 'a primeira versão',
      textos: ['Versão 1'] },
    { funcao: 'Organização', tarefa: 'Organizar próximos passos', ferramentas: ['Trello', 'Google Agenda'], movimento: 'gira', espera: 'Aguardando versão',
      pedido: x => `Organize as próximas etapas de: ${x}.`,
      pensamentos: () => ['Quebrar em tarefas pequenas, com responsável e data.'],
      entrega: () => ({ tipo: 'calendario', titulo: 'Plano', resumo: '9 tarefas', itens: ['Post'] }), handoff: 'o plano' },
    { funcao: 'Revisão e entrega', tarefa: 'Revisar e entregar', ferramentas: ['Claude', 'Slack'], movimento: 'ondas', espera: 'Aguardando',
      pedido: x => `Revise tudo sobre ${x} e prepare a entrega para aprovação.`,
      pensamentos: () => ['Checar clareza, tom e consistência.', 'Nada sai sem a aprovação do usuário.'],
      entrega: () => ({ tipo: 'texto', titulo: 'Revisão', resumo: 'Pronto para revisar', itens: ['Material revisado'] }), handoff: 'a revisão' },
  ];
  return n === 2 ? [todos[0], todos[3]] : n === 3 ? [todos[0], todos[1], todos[3]] : todos;
}

// ---------- montagem do roteiro ----------

/** Monta os passos de trabalho de um agente: prompt → pensamento → ferramentas → entrega → handoff. */
function montarRoteiro(papel: Papel, ctx: Ctx, ferramentas: string[], prompt: string, origem: 'sora' | 'usuario',
  proximo?: { id: string; nome: string }): PassoRoteiro[] {
  const passos: PassoRoteiro[] = [];
  let em = 0;
  const add = (p: Omit<PassoRoteiro, 'em'>, pausa = 250) => { passos.push({ ...p, em }); em += p.dur + pausa; };
  add({ tipo: 'prompt', texto: prompt, origem, dur: 500 });
  const pens = papel.pensamentos(ctx.assunto);
  add({ tipo: 'pensamento', texto: pens[0], dur: 1300 });
  const usadas = (ferramentas.length ? ferramentas : papel.ferramentas).slice(0, 3);
  usadas.forEach((f, i) => {
    const a = acaoPara(f, ctx);
    add({ tipo: 'ferramenta', texto: a.texto, ferramenta: f, acao: a.acao, parametros: a.parametros, resultado: a.resultado, dur: a.dur });
    if (i === 0 && pens[1]) add({ tipo: 'pensamento', texto: pens[1], dur: 1000 });
  });
  const e = papel.entrega(ctx.assunto);
  add({ tipo: 'entrega', texto: `Entregou ${e.titulo.toLowerCase()}: ${e.resumo}`, resultado: { resumo: e.resumo, itens: e.itens, links: e.links, imagens: e.imagens }, dur: 700 });
  if (proximo) add({ tipo: 'handoff', texto: `Enviou ${papel.handoff} para ${proximo.nome}`, paraAgenteId: proximo.id, dur: 500 }, 0);
  return passos;
}

export const duracaoRoteiro = (r: PassoRoteiro[]) => r.reduce((m, p) => Math.max(m, p.em + p.dur), 0);

// ---------- API ----------

function escolherNome(h: number, usados: Set<string>) {
  for (let i = 0; i < NOMES_AGENTES.length; i++) {
    const n = NOMES_AGENTES[(h + i * 7) % NOMES_AGENTES.length];
    if (!usados.has(n)) { usados.add(n); return n; }
  }
  const n = `Agente ${usados.size + 1}`; usados.add(n); return n;
}
function escolherCor(h: number, usadas: Set<string>, evitar: Set<string>) {
  const p = PALETA_AGENTES;
  for (const lista of [p.filter(c => !evitar.has(c)), p]) {
    for (let i = 0; i < lista.length; i++) {
      const c = lista[(h + i * 5) % lista.length];
      if (!usadas.has(c)) { usadas.add(c); return c; }
    }
  }
  return p[h % p.length];
}

export interface OpcoesPlanejar {
  /** nomes já usados por outros agentes (evita repetir) */
  nomesEmUso?: string[];
  /** cores já usadas por outros agentes (tenta evitar; dentro da equipe nunca repete) */
  coresEmUso?: string[];
  /** momento em que cada agente "nasce" (ms) — opcional; padrão Date.now() */
  criadoEm?: (indice: number) => number;
}

/** Planeja uma equipe inteira para o pedido. */
export function planejar(pedido: string, opcoes: OpcoesPlanejar = {}): EquipePlanejada {
  const assunto = extrairAssunto(pedido) || 'seu projeto';
  const modelo = MODELOS.find(m => m.palavras.test(pedido));
  const papeis = modelo ? modelo.papeis(assunto, pedido) : papeisGenericos(pedido);
  const titulo = modelo ? modelo.titulo(assunto) : cap(assunto);
  const h = hash(pedido);
  const nomes = new Set<string>(opcoes.nomesEmUso ?? []);
  const cores = new Set<string>();
  const evitar = new Set((opcoes.coresEmUso ?? []).map(c => c.toUpperCase()));
  const projetoId = novoId('proj');

  const agentes: AgenteSora[] = papeis.map((p, i) => {
    const nome = p.nome && !nomes.has(p.nome) ? (nomes.add(p.nome), p.nome) : escolherNome(h + i * 13, nomes);
    const cor = p.cor && !cores.has(p.cor) ? (cores.add(p.cor), p.cor) : escolherCor(h + i * 3, cores, evitar);
    return {
      id: novoId(slug(nome) || 'agente'), projetoId, nome, funcao: p.funcao, cor, tipoMovimento: p.movimento,
      ferramentas: [...p.ferramentas], status: 'aguardando', verbo: verboPara(p.funcao), espera: p.espera,
      instrucoes: p.pedido(assunto), avulso: false, criadoEm: opcoes.criadoEm?.(i) ?? Date.now(),
    };
  });

  const tarefas: TarefaGerada[] = papeis.map((p, i) => ({
    id: `${projetoId}-t${i + 1}`, titulo: p.tarefa, ordem: i + 1, dependeDe: i ? [`${projetoId}-t${i}`] : [], agenteId: agentes[i].id,
  }));

  const roteiros: Record<string, PassoRoteiro[]> = {};
  const entregas: Record<string, EntregaGerada> = {};
  papeis.forEach((p, i) => {
    const ag = agentes[i], prox = agentes[i + 1];
    const ctx: Ctx = { assunto, titulo, papel: p };
    roteiros[ag.id] = montarRoteiro(p, ctx, ag.ferramentas, p.pedido(assunto), 'sora', prox && { id: prox.id, nome: prox.nome });
    entregas[ag.id] = p.entrega(assunto);
  });

  return {
    modelo: modelo?.id ?? 'generico', titulo, assunto,
    resposta: modelo ? modelo.resposta(assunto) : `Vou montar uma equipe para: ${assunto}.`,
    tarefas, agentes, roteiros, entregas,
  };
}

/** Roteiro para uma mensagem direta do usuário a um agente (chat do agente / agente avulso). */
export function roteiroAvulso(agente: Pick<Agente, 'funcao' | 'ferramentas'> & { instrucoes?: string }, mensagem: string): PassoRoteiro[] {
  const assunto = extrairAssunto(mensagem) || 'o pedido';
  const papel: Papel = {
    funcao: agente.funcao, tarefa: agente.funcao, ferramentas: agente.ferramentas, movimento: 'gira', espera: '',
    pedido: () => mensagem,
    pensamentos: () => [`Entendi o pedido. Vou usar ${agente.ferramentas.slice(0, 2).join(' e ') || 'o que já sei'} para isso.`, 'Conferir o resultado antes de devolver.'],
    entrega: () => ({ tipo: 'texto', titulo: 'Resposta', resumo: 'Pronto para revisar', itens: [cap(assunto)] }),
    handoff: '',
  };
  return montarRoteiro(papel, { assunto, titulo: cap(assunto), papel }, agente.ferramentas, mensagem, 'usuario');
}

/** Rascunho de agente a partir de uma descrição livre (estúdio "Agentes", criação por conversa). */
export interface RascunhoAgente {
  nome: string; funcao: string; cor: string; tipoMovimento: Movimento; ferramentas: string[]; instrucoes: string;
}
export function agenteDeDescricao(descricao: string, opcoes: { nomesEmUso?: string[]; coresEmUso?: string[] } = {}): RascunhoAgente {
  const d = descricao.toLowerCase();
  const h = hash(descricao);
  const regras: [RegExp, string, string[], Movimento][] = [
    [/pesquis|refer|busca|tend[eê]nc/, 'Pesquisa e referências', ['Perplexity', 'Notion', 'Google Drive'], 'vibracao'],
    [/imag|visual|design|arte|logo|post|identidade/, 'Criação visual', ['Higgsfield', 'Figma', 'Canva'], 'espiral'],
    [/v[ií]deo|reels|roteiro|anima/, 'Vídeo', ['Runway', 'ElevenLabs', 'YouTube'], 'espiral'],
    [/e-?mail|caixa|inbox/, 'Triagem de e-mails', ['Gmail', 'ChatGPT', 'Slack'], 'vibracao'],
    [/c[oó]digo|site|program|deploy|app/, 'Código', ['GitHub', 'Vercel', 'Supabase'], 'vibracao'],
    [/dado|planilha|an[aá]lis|m[eé]tric|relat/, 'Análise de dados', ['Planilhas Google', 'Gemini', 'Airtable'], 'gira'],
    [/agenda|calend|reuni|organiz|tarefa/, 'Organização', ['Google Agenda', 'Trello', 'Notion'], 'gira'],
    [/texto|legenda|escrev|copy|blog|artigo/, 'Textos', ['ChatGPT', 'Notion', 'Claude'], 'ondas'],
  ];
  const r = regras.find(([re]) => re.test(d));
  const funcao = r?.[1] ?? 'Assistente';
  const nomeExplicito = descricao.match(/\b(?:chamad[oa]|nome(?:\s+de)?)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ú]{1,14})/);
  const nomes = new Set(opcoes.nomesEmUso ?? []);
  const evitar = new Set((opcoes.coresEmUso ?? []).map(c => c.toUpperCase()));
  return {
    nome: nomeExplicito?.[1] ?? escolherNome(h, nomes),
    funcao,
    cor: escolherCor(h, new Set(), evitar),
    tipoMovimento: r?.[3] ?? 'gira',
    ferramentas: r?.[2] ?? ['ChatGPT', 'Notion'],
    instrucoes: `Você é um agente de ${funcao.toLowerCase()}. ${descricao.trim()}${/[.!?]$/.test(descricao.trim()) ? '' : '.'} Responda em PT-BR, de forma clara e objetiva, e nunca publique nada sem a aprovação do usuário.`,
  };
}

// ---------- conversa simples (chat sem equipe) ----------

const VERBOS_TRABALHO = /^(?:(?:por favor|pode|você pode|vc pode|consegue|quero que você|preciso que você)[\s,]+)?(crie|cria|criar|fa[cç]a|faz|fazer|monte|montar|pesquise|pesquisar|escreva|escrever|planeje|planejar|organize|organizar|gere|gerar|prepare|preparar|resuma|resumir|analise|analisar|desenvolva|desenvolver|produza|produzir|lance|lan[cç]ar|elabore|elaborar|redija)\b/i;

/** O pedido pede TRABALHO (montar equipe) ou é só conversa? */
export function pedeTrabalho(texto: string) {
  const t = texto.trim();
  if (t.length < 4) return false;
  if (VERBOS_TRABALHO.test(t)) return true;
  if (/\b(quero|preciso de|gostaria de)\s+(um|uma|uns|umas)\b/i.test(t)) return true;
  return MODELOS.some(m => m.palavras.test(t)) && t.split(/\s+/).length >= 4;
}

/**
 * Resposta da Sora quando a mensagem é só conversa (sem criar agentes). Em markdown.
 * `variante` escolhe outra redação (usado pelo "Refazer").
 */
export function respostaConversa(texto: string, variante = 0) {
  const t = texto.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const pick = (opcoes: string[]) => opcoes[variante % opcoes.length];
  if (!t.trim()) return pick([
    'Recebi seus **anexos**. O que você quer que eu faça com eles? Posso **resumir**, **analisar** ou usar como **referência** para os agentes.',
    'Anexos recebidos! Me diga o objetivo — por exemplo, *"crie posts a partir destas fotos"* — e eu monto o plano.',
  ]);
  if (/^(oi|ola|ei|e ai|bom dia|boa tarde|boa noite)\b/.test(t)) return pick([
    'Oi! Eu sou a **Sora**. Me conte o que você precisa: posso só conversar ou montar uma **equipe de agentes** para fazer o trabalho.',
    'Olá! Que bom te ver por aqui. Diga o que você quer fazer — eu cuido do **plano** e dos **agentes**.',
    'Oi! Pronta para ajudar. Você pode, por exemplo:\n\n- pedir uma **campanha** completa;\n- pesquisar um **mercado**;\n- resumir seus **e-mails**.',
  ]);
  if (/obrigad|valeu/.test(t)) return pick([
    'Por nada! Se quiser, é só pedir a próxima tarefa.',
    'Imagina! Estou por aqui quando precisar. 🙂',
  ]);
  if (/c[o]digo|json|formato|exemplo de plano/.test(t)) return pick([
    'Por baixo dos panos, um plano é mais ou menos assim:\n\n```json\n{\n  "titulo": "Campanha · Cafeteria",\n  "tarefas": [\n    { "titulo": "Pesquisar referências", "agente": "Atlas" },\n    { "titulo": "Criar peças", "agente": "Luna" },\n    { "titulo": "Organizar calendário", "agente": "Nina" }\n  ]\n}\n```\n\nVocê não precisa escrever nada disso — é só descrever o que quer.',
    'Um exemplo de tarefa que eu entrego para um agente:\n\n```txt\nPesquise referências de campanhas de lançamento para cafeteria.\nFerramentas: Perplexity, Notion\n```',
  ]);
  if (/o que (voce|vc) (faz|sabe)|quem e voce|como funciona|ajuda/.test(t)) return pick([
    'Eu funciono assim:\n\n1. **Entendo** o seu pedido;\n2. monto um **plano** em tarefas;\n3. crio **agentes** especializados para cada uma;\n4. coordeno o trabalho e te mostro tudo **ao vivo**;\n5. você **revisa** — nada é publicado sem a sua aprovação.\n\nExperimente: *“Crie uma campanha para…”*.',
    'Alguns pedidos que funcionam bem:\n\n| Pedido | Equipe |\n|---|---|\n| Campanha de lançamento | pesquisa · criação · textos |\n| Site ou landing page | UX · design · código |\n| Pesquisa de mercado | coleta · análise · relatório |\n| Resumo de e-mails | triagem · resumo |\n\nÉ só descrever o que você quer.',
  ]);
  return pick([
    'Entendi. Quer que eu transforme isso em uma **tarefa**? Descreva o resultado que você espera e eu monto uma equipe de agentes para fazer.',
    'Posso ajudar com isso! Se você me disser **o que quer receber no fim** (um texto, uma pesquisa, peças…), eu organizo o plano e a equipe.',
    'Anotado. Para eu montar a equipe certa, me conte:\n\n- **o objetivo**;\n- **para quem** é;\n- **até quando** precisa.',
  ]);
}

/** Título curto de um chat a partir da primeira mensagem. */
export function tituloDoChat(texto: string) {
  const t = texto.replace(/\s+/g, ' ').trim();
  return cap(t.length > 42 ? `${t.slice(0, 40).trimEnd()}…` : t) || 'Nova conversa';
}
