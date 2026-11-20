// Sessão do usuário (etapa 2, regra 3): quem está logado, via GET /v1/eu.
// Na abertura tenta renovar em silêncio (cookie no navegador; cofre do sistema no desktop).
import { useSyncExternalStore } from 'react';
import { toast } from '../components/base';
import {
  aoAvisoDeSessao, aoSessaoEncerrada, api, buscarAutenticado, corpoRenovacaoDesktop, ehErroApi, guardarTokens, limparSessaoLocal,
  renovarSessao, temTokenAcesso, type TokensSaida,
} from '../api/cliente';

export type Prioridade = 'custo' | 'velocidade' | 'qualidade';

export interface Usuario {
  nome: string;
  email: string;
  prioridade: Prioridade;
  tem_provedor: boolean;
}

export type EstadoSessao =
  | { estado: 'carregando'; usuario?: undefined; erro?: string }
  | { estado: 'anonimo'; usuario?: undefined; erro?: string }
  | { estado: 'logado'; usuario: Usuario; erro?: undefined };

export interface DadosCadastro { nome: string; email: string; senha: string; convite?: string }

/** Mínimo de caracteres da senha (igual ao backend). */
export const SENHA_MINIMA = 10;

let atual: EstadoSessao = { estado: 'carregando' };
const ouvintes = new Set<() => void>();

function definir(novo: EstadoSessao): void {
  atual = novo;
  for (const cb of [...ouvintes]) cb();
}

function assinar(cb: () => void): () => void {
  ouvintes.add(cb);
  return () => { ouvintes.delete(cb); };
}

export const lerSessao = (): EstadoSessao => atual;

export function useSessao(): EstadoSessao {
  return useSyncExternalStore(assinar, lerSessao, lerSessao);
}

// Cofre do sistema não guardou o login: a sessão segue em memória e o usuário é avisado.
aoAvisoDeSessao(mensagem => { toast({ mensagem, tom: 'aviso', duracao: 8000 }); });

// Renovação falhou em qualquer chamada → volta para Entrar.
aoSessaoEncerrada(() => { if (atual.estado !== 'anonimo') definir({ estado: 'anonimo' }); });

/** Refaz GET /v1/eu (ex.: depois de conectar um provedor, para atualizar tem_provedor). */
export async function recarregarSessao(): Promise<void> {
  const usuario = await api.get<Usuario>('/v1/eu');
  definir({ estado: 'logado', usuario });
}

let iniciando: Promise<void> | null = null;

/** Abertura do app: tenta renovar em silêncio e buscar o usuário. Chamadas repetidas reaproveitam a mesma. */
export function iniciarSessao(): Promise<void> {
  if (!iniciando) {
    iniciando = (async () => {
      try {
        const ok = temTokenAcesso() || await renovarSessao();
        if (!ok) { definir({ estado: 'anonimo' }); return; }
        await recarregarSessao();
      } catch (e) {
        // Servidor fora do ar: mostra Entrar com o aviso (o usuário tenta de novo por lá).
        definir({ estado: 'anonimo', erro: ehErroApi(e) && e.status === 0 ? e.mensagem : undefined });
      } finally {
        iniciando = null;
      }
    })();
  }
  return iniciando;
}

/** POST /v1/auth/entrar e carrega o usuário. Lança ErroApi (mostrar e.mensagem). */
export async function entrar(email: string, senha: string): Promise<void> {
  const tokens = await api.post<TokensSaida>('/v1/auth/entrar', { email: email.trim(), senha }, { semAuth: true });
  await guardarTokens(tokens);
  await recarregarSessao();
}

/** POST /v1/auth/cadastrar e já entra. Lança ErroApi. */
export async function cadastrar(dados: DadosCadastro): Promise<void> {
  const convite = dados.convite?.trim();
  await api.post<void>('/v1/auth/cadastrar', {
    nome: dados.nome.trim(),
    email: dados.email.trim(),
    senha: dados.senha,
    ...(convite ? { convite } : {}),
  }, { semAuth: true });
  await entrar(dados.email, dados.senha);
}

/** POST /v1/auth/sair. Mesmo se o servidor falhar, a sessão local é esquecida. */
export async function sair(): Promise<void> {
  try {
    await api.post<void>('/v1/auth/sair', await corpoRenovacaoDesktop(), { semAuth: true });
  } catch { /* sair sempre funciona do lado do app */ }
  await limparSessaoLocal();
  definir({ estado: 'anonimo' });
}

/** POST /v1/auth/esqueci-senha. O servidor responde igual exista a conta ou não. Lança ErroApi
 *  (429 = muitos pedidos; 503 = e-mail desligado no servidor). */
export async function pedirLinkDeSenha(email: string): Promise<void> {
  await api.post<void>('/v1/auth/esqueci-senha', { email: email.trim() }, { semAuth: true });
}

/** POST /v1/auth/redefinir-senha. Encerra todas as sessões da conta; quem estava entrado aqui sai. */
export async function redefinirSenha(token: string, senhaNova: string): Promise<void> {
  await api.post<void>('/v1/auth/redefinir-senha', { token, senha_nova: senhaNova }, { semAuth: true });
  if (atual.estado === 'logado') {
    await limparSessaoLocal();
    definir({ estado: 'anonimo' });
  }
}

/** POST /v1/conta/senha. Os outros aparelhos saem; este continua entrado. Lança ErroApi. */
export async function trocarSenha(senhaAtual: string, senhaNova: string): Promise<void> {
  await api.post<void>('/v1/conta/senha', { senha_atual: senhaAtual, senha_nova: senhaNova });
}

/** POST /v1/conta/exportar {senha} → baixa o .zip com todos os dados da conta (LGPD). Lança ErroApi. */
export async function baixarMeusDados(senha: string): Promise<void> {
  const resposta = await buscarAutenticado('/v1/conta/exportar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ senha }),
  });
  const disposicao = resposta.headers.get('content-disposition') ?? '';
  const nome = disposicao.match(/filename="?([^";]+)"?/i)?.[1] ?? 'sora-meus-dados.zip';
  const url = URL.createObjectURL(await resposta.blob());
  const link = document.createElement('a');
  link.href = url; link.download = nome; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Token do link de senha nova: vem no fragmento (`#token=…`), que o navegador não manda ao servidor. */
export function tokenDoLink(hash: string): string {
  try { return new URLSearchParams(hash.replace(/^#/, '')).get('token') ?? ''; } catch { return ''; }
}

/** DELETE /v1/conta {senha}. Lança ErroApi (ex.: senha errada). */
export async function apagarConta(senha: string): Promise<void> {
  await api.delete<void>('/v1/conta', { senha });
  await limparSessaoLocal();
  definir({ estado: 'anonimo' });
}

/** Só para testes. */
export function _reiniciarSessaoParaTestes(): void {
  atual = { estado: 'carregando' };
  iniciando = null;
}
