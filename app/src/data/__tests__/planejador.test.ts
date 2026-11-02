import { describe, expect, it } from 'vitest';
import { COR_SORA, MOVIMENTOS, PALETA_AGENTES } from '../planejador';

describe('catálogo visual do construtor', () => {
  it('reserva a cor da Sora e oferece apenas cores de agentes', () => {
    expect(PALETA_AGENTES).not.toContain(COR_SORA);
    expect(new Set(PALETA_AGENTES).size).toBe(PALETA_AGENTES.length);
  });

  it('oferece os quatro movimentos do mascote', () => {
    expect(MOVIMENTOS.map(m => m.id)).toEqual(['gira', 'vibracao', 'espiral', 'ondas']);
  });
});
