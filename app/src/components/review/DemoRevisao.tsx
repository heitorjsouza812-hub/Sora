import { useState } from 'react';
import type { AgenteSora, EntregaGerada, ProjetoSora } from '../../state/projetos';
import { RevisaoProjeto } from './RevisaoProjeto';
import './review.css';

const AGENTS: Record<string, AgenteSora> = {
  atlas: {
    id: 'atlas', projetoId: 'demo-review', nome: 'Atlas', funcao: 'Pesquisa e referências',
    cor: '#56A8FF', tipoMovimento: 'vibracao', ferramentas: ['Perplexity', 'Notion'],
    status: 'concluido', verbo: 'Pesquisando', espera: 'Aguardando', instrucoes: 'Encontre referências confiáveis.',
    avulso: false, criadoEm: 1,
  },
  luna: {
    id: 'luna', projetoId: 'demo-review', nome: 'Luna', funcao: 'Criação visual',
    cor: '#AC80FF', tipoMovimento: 'espiral', ferramentas: ['Figma', 'Canva'],
    status: 'concluido', verbo: 'Criando', espera: 'Aguardando referências', instrucoes: 'Crie peças acolhedoras.',
    avulso: false, criadoEm: 2,
  },
  nina: {
    id: 'nina', projetoId: 'demo-review', nome: 'Nina', funcao: 'Textos e calendário',
    cor: '#46E8A8', tipoMovimento: 'ondas', ferramentas: ['Notion', 'Google Agenda'],
    status: 'concluido', verbo: 'Escrevendo', espera: 'Aguardando peças', instrucoes: 'Escreva em tom próximo.',
    avulso: false, criadoEm: 3,
  },
};

const PREVIOUS: Record<string, EntregaGerada> = {
  atlas: {
    tipo: 'links', titulo: 'Pesquisa', resumo: '3 referências',
    links: [
      { titulo: 'Identidades para cafeterias', dominio: 'behance.net' },
      { titulo: 'Tendências de café especial', dominio: 'pinterest.com' },
      { titulo: 'Campanhas de inauguração', dominio: 'instagram.com' },
    ],
  },
  luna: { tipo: 'imagem', titulo: 'Peças da campanha', resumo: '2 peças', imagens: ['/campanha/post.jpg', '/campanha/story.jpg'] },
  nina: {
    tipo: 'texto', titulo: 'Textos', resumo: 'Legenda anterior',
    itens: ['Abrimos as portas! Venha provar nosso café especial na inauguração, sábado às 9h.'],
  },
};

const CURRENT: Record<string, EntregaGerada> = {
  atlas: {
    tipo: 'links', titulo: 'Pesquisa', resumo: '4 referências',
    links: [
      { titulo: 'Branding de cafeterias independentes', dominio: 'behance.net' },
      { titulo: 'Moodboard: café e aconchego', dominio: 'pinterest.com' },
      { titulo: 'Campanhas de inauguração', dominio: 'instagram.com' },
      { titulo: 'Paletas e tipografia para cafés', dominio: 'canva.com' },
    ],
  },
  luna: { tipo: 'imagem', titulo: 'Peças da campanha', resumo: '3 peças', imagens: ['/campanha/post.jpg', '/campanha/story.jpg'] },
  nina: {
    tipo: 'calendario', titulo: 'Calendário editorial', resumo: '6 publicações',
    itens: ['02 nov · Post de inauguração', '04 nov · Story dos bastidores', '06 nov · Reels do primeiro café', '09 nov · Carrossel do cardápio', '12 nov · Depoimento', '16 nov · Oferta da semana'],
  },
};

const BASE_PROJECT: ProjetoSora = {
  id: 'demo-review',
  titulo: 'Campanha da cafeteria',
  pedido: 'Crie uma campanha para lançar minha cafeteria.',
  modelo: 'campanha',
  assunto: 'cafeteria',
  resposta: 'Vou montar a equipe ideal.',
  criadoEm: 1,
  tarefas: [
    { id: 't1', titulo: 'Pesquisar referências', ordem: 1, dependeDe: [], agenteId: 'atlas' },
    { id: 't2', titulo: 'Criar peças', ordem: 2, dependeDe: ['t1'], agenteId: 'luna' },
    { id: 't3', titulo: 'Montar calendário', ordem: 3, dependeDe: ['t2'], agenteId: 'nina' },
  ],
  agenteIds: ['atlas', 'luna', 'nina'],
  entregas: CURRENT,
  marcos: { plano: 2, nascimentos: [3, 4, 5], trabalho: 6, fim: 7 },
  versao: 2,
};

export default function DemoRevisao() {
  const [project, setProject] = useState(BASE_PROJECT);
  const [lastAdjustment, setLastAdjustment] = useState('');

  return <main className="demo-review">
    <RevisaoProjeto
      projeto={project}
      agentes={AGENTS}
      entregasAnteriores={PREVIOUS}
      onAprovar={() => setProject((current) => ({ ...current, aprovadoEm: Date.now() }))}
      onPedirAjuste={(text, agentId) => {
        setLastAdjustment(`${text}${agentId ? ` · ${AGENTS[agentId]?.nome ?? agentId}` : ''}`);
        setProject((current) => ({ ...current, versao: current.versao + 1, aprovadoEm: undefined }));
      }}
    />
    {lastAdjustment && <output hidden>{lastAdjustment}</output>}
  </main>;
}

