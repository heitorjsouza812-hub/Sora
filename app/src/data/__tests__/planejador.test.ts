import { describe, expect, it } from 'vitest';
import { agenteDeDescricao, COR_SORA, PALETA_AGENTES, verboPara } from '../planejador';

describe('catálogo visual do construtor', () => {
  it('reserva a cor da Sora e oferece apenas cores de agentes', () => {
    expect(PALETA_AGENTES).not.toContain(COR_SORA);
    expect(new Set(PALETA_AGENTES).size).toBe(PALETA_AGENTES.length);
  });

  it('preenche somente um rascunho local; não produz plano nem roteiro simulado', () => {
    const rascunho = agenteDeDescricao('Pesquise concorrentes e referências de cafeterias');
    expect(rascunho).toMatchObject({ funcao: 'Pesquisa e referências', tipoMovimento: 'vibracao', ferramentas: [] });
    expect(rascunho).not.toHaveProperty('tarefas');
    expect(rascunho).not.toHaveProperty('roteiros');
  });

  it('mantém os verbos visuais do agente', () => {
    expect(verboPara('Pesquisa')).toBe('Pesquisando');
    expect(verboPara('Criação visual')).toBe('Criando');
  });
});
