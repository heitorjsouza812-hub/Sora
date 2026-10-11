// Destino simulado de cada entrega aprovada (sem back-end): onde foi publicada/salva e quando.
import type { AgenteSora, EntregaGerada, ProjetoSora } from '../../state/projetos';

export interface Destino {
  plugin: 'Instagram' | 'Google Drive' | 'Notion' | 'Google Agenda';
  texto: string;          // ex.: "Instagram · agendado sáb, 17 out · 9h"
  status: 'Agendado' | 'Salvo';
}

const fmtDia = new Intl.DateTimeFormat('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' });

/** Próximo sábado às 9h depois do momento da aprovação. */
export function proximoSabado9h(de: number) {
  const d = new Date(de);
  d.setHours(9, 0, 0, 0);
  const dias = (6 - d.getDay() + 7) % 7 || (d.getTime() <= de ? 7 : 0);
  d.setDate(d.getDate() + dias);
  return d;
}

const quando = (de: number) => `${fmtDia.format(proximoSabado9h(de)).replace(/\./g, '')} · 9h`;
const pasta = (p: ProjetoSora) => p.titulo.split(' · ')[0] || p.titulo;

export function destinoDaEntrega(entrega: EntregaGerada, agente: AgenteSora | undefined, projeto: ProjetoSora): Destino {
  const aprovadoEm = projeto.aprovadoEm ?? Date.now();
  const usa = (nome: string) => agente?.ferramentas.includes(nome) ?? false;
  switch (entrega.tipo) {
    case 'imagem':
      return { plugin: 'Instagram', texto: `Instagram · agendado ${quando(aprovadoEm)}`, status: 'Agendado' };
    case 'calendario': {
      const n = Number(entrega.resumo.match(/\d+/)?.[0]) || entrega.itens?.length || 0;
      return usa('Google Agenda')
        ? { plugin: 'Google Agenda', texto: `Google Agenda · ${n || 'todos os'} posts a partir de ${quando(aprovadoEm)}`, status: 'Agendado' }
        : { plugin: 'Instagram', texto: `Instagram · ${n || 'todos os'} posts a partir de ${quando(aprovadoEm)}`, status: 'Agendado' };
    }
    case 'links':
      return usa('Notion')
        ? { plugin: 'Notion', texto: `Notion · página “${entrega.titulo}”`, status: 'Salvo' }
        : { plugin: 'Google Drive', texto: `Google Drive · pasta ${pasta(projeto)}`, status: 'Salvo' };
    default:
      return { plugin: 'Google Drive', texto: `Google Drive · pasta ${pasta(projeto)}`, status: 'Salvo' };
  }
}
