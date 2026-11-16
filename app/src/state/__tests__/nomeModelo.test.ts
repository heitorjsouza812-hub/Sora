import { describe, expect, it } from 'vitest';
import { ehModeloPrincipal, nomeCurtoDoModelo, separarPrincipais } from '../nomeModelo';

describe('nome curto do modelo', () => {
  it.each([
    ['openai/gpt-oss-120b', 'GPT-OSS 120B'],
    ['openai/gpt-oss-20b', 'GPT-OSS 20B'],
    ['gemini-2.5-flash', 'Gemini 2.5 Flash'],
    ['models/gemini-2.5-flash-lite', 'Gemini 2.5 Flash Lite'],
    ['gemini-2.0-flash-001', 'Gemini 2.0 Flash'],
    ['claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5'],
    ['claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet'],
    ['claude-opus-5-5', 'Claude Opus 5.5'],
    ['gpt-4o-mini', 'GPT-4o Mini'],
    ['gpt-5', 'GPT-5'],
    ['gpt-4-0613', 'GPT-4'],
    ['o3-mini', 'o3 Mini'],
    ['llama-3.3-70b-versatile', 'Llama 3.3 70B'],
    ['meta-llama/llama-3.1-8b-instruct:free', 'Llama 3.1 8B'],
    ['deepseek-chat', 'DeepSeek Chat'],
    ['mistral-large-latest', 'Mistral Large'],
    ['grok-3-mini', 'Grok 3 Mini'],
    ['llama3.2:3b', 'Llama 3.2 3B'],
    ['gemini-2.5-flash-preview-09-2025', 'Gemini 2.5 Flash'],
  ])('%s → %s', (id, esperado) => expect(nomeCurtoDoModelo(id)).toBe(esperado));

  it('nome bonito não é estragado e id desconhecido fica legível', () => {
    expect(nomeCurtoDoModelo('GPT-OSS 120B')).toBe('GPT-OSS 120B');
    expect(nomeCurtoDoModelo('Lince Grande')).toBe('Lince Grande');
    expect(nomeCurtoDoModelo('openai/lince-grande')).toBe('Lince Grande');
    expect(nomeCurtoDoModelo('')).toBe('');
  });
});

describe('modelos principais', () => {
  it('reconhece os principais conhecidos e deixa de fora variantes de áudio, imagem e vetor', () => {
    expect(['openai/gpt-oss-120b', 'gemini-2.5-pro', 'claude-sonnet-4-5-20250929', 'gpt-5-mini', 'llama-3.3-70b-versatile'].every(ehModeloPrincipal)).toBe(true);
    expect(['gemini-2.5-flash-image', 'gpt-4o-audio-preview', 'text-embedding-3', 'gemini-1.0-pro'].some(ehModeloPrincipal)).toBe(false);
  });

  it('o campo do servidor vence a lista local; sem nenhum principal mostra tudo; local mostra tudo', () => {
    const lista = [{ modelo: 'gemini-2.5-pro' }, { modelo: 'x-exotico', principal: true }, { modelo: 'gemini-2.5-flash', principal: false }];
    const { principais, outros } = separarPrincipais(lista);
    expect(principais.map(m => m.modelo)).toEqual(['gemini-2.5-pro', 'x-exotico']);
    expect(outros.map(m => m.modelo)).toEqual(['gemini-2.5-flash']);
    const sem = [{ modelo: 'a' }, { modelo: 'b' }];
    expect(separarPrincipais(sem).principais).toHaveLength(2);
    expect(separarPrincipais(lista, true).outros).toHaveLength(0);
  });
});
