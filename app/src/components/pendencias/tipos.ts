export type AcaoPedidoAtencao = 'enviar' | 'descartar' | 'aprovar' | 'recusar' | 'responder';

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
  botId?: string | null;
  grupoId?: string | null;
  opcoes?: OpcaoAtencao[];
  aceitaRespostaLivre?: boolean;
  expiraEm?: string | null;
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
