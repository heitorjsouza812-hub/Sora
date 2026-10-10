// Modelo de dados — CLAUDE.md §5.3
export type Status = 'aguardando' | 'trabalhando' | 'concluido' | 'erro';
export type Movimento = 'gira' | 'vibracao' | 'espiral' | 'ondas';

export interface Usuario { id: string; nome: string; empresa: string; plano: string }
export interface Projeto { id: string; usuarioId: string; titulo: string; status: Status }
export interface Mensagem {
  id: string; projetoId: string;
  autor: 'usuario' | 'sora' | string; // string = agenteId
  texto: string; anexos?: string[]; criadoEm: number;
}
export interface Tarefa {
  id: string; planoId: string; titulo: string; ordem: number;
  dependeDe: string[]; agenteId: string; status: Status; progresso: number;
}
export interface Plano { id: string; projetoId: string; tarefas: Tarefa[] }
export interface Agente {
  id: string; projetoId: string; nome: string; funcao: string; cor: string;
  tipoMovimento: Movimento; ferramentas: string[]; status: Status;
  verbo: string;      // ex.: "Pesquisando"
  espera: string;     // ex.: "Aguardando referências"
}
export interface Entrega {
  id: string; tarefaId: string; agenteId: string;
  tipo: 'links' | 'imagem' | 'texto' | 'calendario'; conteudo: unknown; versao: number;
}
export interface Plugin { id: string; nome: string; categoria: string; conectado: boolean }

// ---- Rodada 3: equipes geradas, agentes avulsos e painel "Trabalho" ----

/** Um passo do trabalho de um agente, exibido ao vivo no painel "Trabalho". */
export interface PassoTrabalho {
  id: string;
  agenteId: string;
  tipo: 'prompt' | 'pensamento' | 'ferramenta' | 'entrega' | 'handoff';
  texto: string;
  ferramenta?: string;                  // nome do plugin (ex.: "Perplexity")
  acao?: string;                        // ex.: "perplexity.buscar"
  parametros?: Record<string, unknown>;
  resultado?: ResultadoPasso;
  status: 'executando' | 'concluido' | 'erro';
  inicio: number;                       // ms (epoch)
  fim?: number;
  paraAgenteId?: string;                // handoff: quem recebe
  origem?: 'sora' | 'usuario';          // prompt: quem pediu
}

export interface ResultadoPasso {
  resumo: string;                       // ex.: "4 links"
  links?: { titulo: string; dominio: string }[];
  imagens?: string[];                   // URLs (ou vazio → miniatura gerada na cor do agente)
  itens?: string[];                     // linhas de texto (títulos, tópicos…)
}
