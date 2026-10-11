import { describe, expect, it } from 'vitest';
import { COR_SORA, PALETA_AGENTES, planejar } from '../planejador';

describe('data/planejador', () => {
  it.each([
    ['Crie uma campanha de lançamento para uma cafeteria', 'campanha'],
    ['Monte uma landing page para meu portfólio', 'site'],
    ['Faça uma pesquisa de mercado sobre cafeterias', 'pesquisa'],
    ['Resuma meus e-mails da caixa de entrada', 'emails'],
    ['Crie um vídeo para o TikTok', 'video'],
    ['Organize a festa de aniversário', 'generico'],
  ])('seleciona o modelo %s por palavra-chave', (pedido, modelo) => {
    expect(planejar(pedido).modelo).toBe(modelo);
  });

  it('atribui cores distintas à equipe e nunca usa a cor reservada da Sora', () => {
    const plano = planejar('Crie uma campanha de lançamento para minha cafeteria');
    const cores = plano.agentes.map((agente) => agente.cor.toUpperCase());

    expect(new Set(cores)).toHaveLength(cores.length);
    expect(cores).not.toContain(COR_SORA);
    expect(cores.every((cor) => PALETA_AGENTES.includes(cor as typeof PALETA_AGENTES[number]))).toBe(true);
  });

  it('evita cores já usadas quando há alternativas disponíveis', () => {
    const plano = planejar('Organize uma festa de aniversário simples', { coresEmUso: ['#56A8FF', '#AC80FF'] });

    expect(plano.agentes.map((agente) => agente.cor)).not.toContain('#56A8FF');
    expect(plano.agentes.map((agente) => agente.cor)).not.toContain('#AC80FF');
  });
});
