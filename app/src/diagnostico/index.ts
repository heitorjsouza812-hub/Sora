// Diagnóstico do "Relatar problema": o que o app vê sem ler conversa nenhuma.
// Guarda os últimos 20 erros (da janela, de promessas sem tratamento e da API) já sem dado pessoal:
// e-mails, tokens, números longos (CPF, cartão, telefone) e o que vem depois de "senha" viram marcas.
// O servidor mascara de novo antes de gravar.
import { noDesktop } from '../desktop/ponte';

export type OrigemErro = 'janela' | 'promessa' | 'api' | 'app';
export interface ErroRecente { quando: string; origem: OrigemErro; mensagem: string }
export interface Diagnostico {
  versao_app: string;
  plataforma: 'web' | 'desktop' | 'celular';
  rota: string;
  navegador: string;
  tela: string;
  idioma: string;
  erros: ErroRecente[];
}

const MAX_ERROS = 20;
const MAX_MENSAGEM = 500;
const erros: ErroRecente[] = [];

const LIMPEZAS: [RegExp, string][] = [
  [/[^\s@<>()"']+@[^\s@<>()"']+\.[A-Za-z]{2,}/g, '[e-mail]'],
  [/Bearer\s+\S+/gi, 'Bearer [oculto]'],
  [/eyJ[\w-]+\.[\w-]+\.[\w-]+/g, '[oculto]'],
  [/\b(?:sk|gsk|xai|ghp|re)[-_][\w-]{8,}/g, '[oculto]'],
  [/((?:senha|password|token|chave|secret)\s*[:=]\s*)\S+/gi, '$1[oculto]'],
  [/\d[\d .\-/]{7,}\d/g, '[número]'],
];

/** Tira do texto o que pode ser dado pessoal ou segredo. */
export function limparTexto(texto: string): string {
  let limpo = texto;
  for (const [padrao, troca] of LIMPEZAS) limpo = limpo.replace(padrao, troca);
  return limpo.length > MAX_MENSAGEM ? `${limpo.slice(0, MAX_MENSAGEM - 1)}…` : limpo;
}

/** Guarda um erro recente (os mais velhos saem quando passa de 20). */
export function registrarErroRecente(origem: OrigemErro, mensagem: string): void {
  const texto = limparTexto(String(mensagem || 'Erro sem mensagem'));
  erros.push({ quando: new Date().toISOString(), origem, mensagem: texto });
  if (erros.length > MAX_ERROS) erros.splice(0, erros.length - MAX_ERROS);
}

export function errosRecentes(): ErroRecente[] { return [...erros]; }

let iniciado = false;

/** Ouve os erros da janela e as promessas sem tratamento (uma vez por app). */
export function iniciarDiagnostico(): void {
  if (iniciado || typeof window === 'undefined') return;
  iniciado = true;
  window.addEventListener('error', e => registrarErroRecente('janela', e.message || String(e.error ?? '')));
  window.addEventListener('unhandledrejection', e => {
    const motivo = e.reason as { message?: unknown } | undefined;
    registrarErroRecente('promessa', typeof motivo?.message === 'string' ? motivo.message : String(e.reason));
  });
}

/** Caminho sem consulta nem fragmento (o link de senha nova, por exemplo, leva o token no #). */
function rotaAtual(): string {
  try { return window.location.pathname.slice(0, 200); } catch { return ''; }
}

export function montarDiagnostico(): Diagnostico {
  const largura = typeof window !== 'undefined' ? window.innerWidth : 0;
  return {
    versao_app: String(import.meta.env.VITE_SORA_VERSAO ?? 'desenvolvimento').slice(0, 40),
    plataforma: noDesktop ? 'desktop' : largura > 0 && largura < 640 ? 'celular' : 'web',
    rota: rotaAtual(),
    navegador: (typeof navigator !== 'undefined' ? navigator.userAgent : '').slice(0, 300),
    tela: typeof window !== 'undefined' ? `${window.innerWidth}x${window.innerHeight}` : '',
    idioma: (typeof navigator !== 'undefined' ? navigator.language : '').slice(0, 20),
    erros: errosRecentes(),
  };
}

/** Só para testes. */
export function _limparDiagnosticoParaTestes(): void { erros.length = 0; }
