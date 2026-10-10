// Modelos prontos dos estados vazios (item 48): projetos para a Sora e agentes para o construtor.
import type { Movimento } from '../../types';

export interface ModeloProjeto { id: string; rotulo: string; descricao: string; pedido: string }

export const MODELOS_PROJETO: ModeloProjeto[] = [
  { id: 'campanha', rotulo: 'Campanha de lançamento', descricao: 'Referências, peças e calendário de posts',
    pedido: 'Crie uma campanha de lançamento para minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.' },
  { id: 'landing', rotulo: 'Landing page', descricao: 'Seções, textos persuasivos e visual',
    pedido: 'Monte uma landing page para o meu curso online: estrutura das seções, textos persuasivos e visual das telas.' },
  { id: 'pesquisa', rotulo: 'Pesquisa de mercado', descricao: 'Concorrentes, preços e oportunidades',
    pedido: 'Faça uma pesquisa de mercado sobre academias no meu bairro, com concorrentes, preços e oportunidades.' },
  { id: 'roteiro', rotulo: 'Roteiro de vídeo', descricao: 'Cenas, falas e legendas de 60 s',
    pedido: 'Escreva o roteiro de um vídeo de 60 segundos para o Instagram apresentando a minha loja, com cenas e legendas.' },
  { id: 'posts', rotulo: 'Posts da semana', descricao: 'Ideias, legendas e agenda de 7 dias',
    pedido: 'Planeje os posts da semana para o Instagram da minha loja: ideias, legendas e um calendário de publicação.' },
  { id: 'emails', rotulo: 'Resumo de e-mails', descricao: 'Resumo da semana e respostas sugeridas',
    pedido: 'Resuma meus e-mails da semana, destaque o que é urgente e sugira respostas para cada um.' },
];

/** Rascunho parcial que o construtor (/agentes/novo?modelo=<id>) usa para pré-preencher. */
export interface ModeloAgente {
  id: string;
  rotulo: string;
  descricao: string;
  rascunho: {
    nome: string; funcao: string; descricaoCurta: string; instrucoes: string; ferramentas: string[];
    tipoMovimento: Movimento; tom: 'objetivo' | 'amigavel' | 'criativo' | 'tecnico'; frasesIniciais: string[];
  };
}

export const MODELOS_AGENTE: ModeloAgente[] = [
  { id: 'redator-legendas', rotulo: 'Redator de legendas', descricao: 'Legendas e hashtags para o Instagram',
    rascunho: { nome: 'Pipa', funcao: 'Redator de legendas', descricaoCurta: 'Escreve legendas curtas e divertidas para o Instagram.',
      instrucoes: 'Escreva legendas curtas, com tom leve e próximo, uma chamada para ação e até 5 hashtags relevantes. Ofereça duas opções por post.',
      ferramentas: ['ChatGPT', 'Instagram'], tipoMovimento: 'ondas', tom: 'criativo',
      frasesIniciais: ['Escreva a legenda do post de amanhã', 'Sugira hashtags para a minha loja'] } },
  { id: 'pesquisador', rotulo: 'Pesquisador', descricao: 'Busca fontes, compara e resume',
    rascunho: { nome: 'Teo', funcao: 'Pesquisador', descricaoCurta: 'Pesquisa na web e entrega um resumo com fontes.',
      instrucoes: 'Pesquise fontes confiáveis, compare os dados e entregue um resumo em tópicos com os links usados.',
      ferramentas: ['Perplexity', 'Google Drive', 'Notion'], tipoMovimento: 'vibracao', tom: 'objetivo',
      frasesIniciais: ['Pesquise os concorrentes do meu bairro', 'Resuma as tendências do meu setor'] } },
  { id: 'designer', rotulo: 'Designer', descricao: 'Peças visuais no Canva e no Figma',
    rascunho: { nome: 'Lia', funcao: 'Designer', descricaoCurta: 'Cria peças visuais seguindo a identidade da marca.',
      instrucoes: 'Crie peças seguindo as cores e fontes da marca. Mostre 3 variações e explique a escolha de cada uma.',
      ferramentas: ['Canva', 'Figma', 'Higgsfield'], tipoMovimento: 'espiral', tom: 'criativo',
      frasesIniciais: ['Crie um post de inauguração', 'Faça uma capa para os destaques'] } },
  { id: 'atendente-whatsapp', rotulo: 'Atendente de WhatsApp', descricao: 'Respostas rápidas e cordiais aos clientes',
    rascunho: { nome: 'Bia', funcao: 'Atendente de WhatsApp', descricaoCurta: 'Responde clientes com cordialidade e rapidez.',
      instrucoes: 'Responda com cordialidade e frases curtas. Informe horário, endereço e preços. Se não souber, avise que um humano vai responder.',
      ferramentas: ['WhatsApp', 'Google Agenda'], tipoMovimento: 'gira', tom: 'amigavel',
      frasesIniciais: ['Qual o horário de funcionamento?', 'Vocês fazem entrega?'] } },
];

export const modeloAgente = (id: string | null | undefined) => MODELOS_AGENTE.find((m) => m.id === id);
