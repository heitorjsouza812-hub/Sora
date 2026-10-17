// Sessão do usuário (etapa 2, regra 3): quem está logado, via GET /v1/eu.
// Na abertura tenta renovar em silêncio (cookie no navegador; cofre do sistema no desktop).
import { useSyncExternalStore } from 'react';
import {
  aoSessaoEncerrada, api, corpoRenovacaoDesktop, ehErroApi, guardarTokens, limparSessaoLocal,
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
