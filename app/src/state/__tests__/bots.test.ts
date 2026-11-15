import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../../api/cliente';
import { _reiniciarBotsParaTestes, carregarBots, estadoDoBot } from '../bots';

describe('estado dos bots', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    _reiniciarBotsParaTestes();
  });

  it('prioriza o estado precisa de voce', () => {
    expect(estadoDoBot({ estado: 'precisa_de_voce' })).toBe('precisa_de_voce');
    expect(estadoDoBot({ estado: 'trabalhando' })).toBe('trabalhando');
    expect(estadoDoBot({ estado: 'livre' })).toBe('livre');
  });

  it('carrega somente bots reais pelo adaptador', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce([
      { id: 'sora', tipo: 'sora', nome: 'Sora', funcao: 'Chefe', cor: '#E2ECFF', movimento: 'gira', ferramentas: [], estado: 'livre' },
      { id: 'bot-1', tipo: 'individual', nome: 'Lume', funcao: 'Pesquisa', cor: '#56A8FF', movimento: 'vibracao', ferramentas: ['buscar_web'], estado: 'trabalhando' },
      // Especialista interno criado por uma conversa: não é bot.
      { id: 'esp-1', tipo: 'especialista', nome: 'Redator', funcao: 'Textos', cor: '#46E8A8', movimento: 'ondas', ferramentas: [], estado: 'livre' },
    ]);

    await expect(carregarBots()).resolves.toEqual([
      expect.objectContaining({ id: 'bot-1', nome: 'Lume', estado: 'trabalhando', ferramentas: ['buscar_web'] }),
    ]);
  });
});
