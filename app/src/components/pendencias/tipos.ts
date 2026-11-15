export type AcaoPedidoAtencao = 'enviar' | 'descartar' | 'aprovar' | 'sempre_permitir' | 'recusar' | 'responder';

export interface OpcaoAtencao {
  rotulo: string;
  valor: string;
  tom?: 'principal' | 'perigo' | 'neutro';
}

/** Pedido que bloqueia um bot ou grupo até uma decisão explícita do usuário. */
export interface PedidoAtencao {
  id: string;
  tipo: 'envio' | 'aprovacao' | 'pergunta';
  titulo: string;
  resumo: string;
  detalhes?: string | null;
  /** Instruções novas propostas pelo bot (`propor_instrucoes`), para ler antes de aprovar. */
  proposta?: { instrucoes: string; diferenca?: string; motivo?: string } | null;
  botId?: string | null;
  grupoId?: string | null;
  /** Id técnico da ferramenta que pediu a aprovação (só decide se "Sempre permitir" existe). */
  acao?: string | null;
  opcoes?: OpcaoAtencao[];
  aceitaRespostaLivre?: boolean;
  expiraEm?: string | null;
  /** Quando o pedido nasceu (ms desde 1970); vazio quando o servidor não informa. */
  criadoEm?: number | null;
  enviando?: boolean;
  erro?: string | null;
}

export interface BotDaProposta {
  id?: string | null;
  nome: string;
  funcao: string;
  cor: string;
  novo: boolean;
  selecionado: boolean;
}

export interface PropostaGrupo {
  id: string;
  nome: string;
  motivo?: string | null;
  bots: BotDaProposta[];
  enviando?: boolean;
  erro?: string | null;
}
