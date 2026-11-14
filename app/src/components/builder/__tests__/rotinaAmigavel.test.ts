import { describe, expect, it } from 'vitest';
import { lerAgendamento, montarAgendamento } from '../rotinaAmigavel';

describe('rotinaAmigavel', () => {
  it('monta o cron de cada frequência', () => {
    expect(montarAgendamento({ frequencia: 'diario', hora: '09:00', dia: 1 })).toBe('0 9 * * *');
    expect(montarAgendamento({ frequencia: 'uteis', hora: '18:05', dia: 1 })).toBe('5 18 * * 1-5');
    expect(montarAgendamento({ frequencia: 'semanal', hora: '07:30', dia: 0 })).toBe('30 7 * * 0');
    expect(montarAgendamento({ frequencia: 'nenhuma', hora: '09:00', dia: 1 })).toBeNull();
    expect(montarAgendamento({ frequencia: 'diario', hora: '', dia: 1 })).toBeNull();
  });

  it('lê de volta o cron simples e marca o resto como personalizado', () => {
    expect(lerAgendamento('0 9 * * 1-5')).toEqual({ frequencia: 'uteis', hora: '09:00', dia: 1 });
    expect(lerAgendamento('30 7 * * 3')).toEqual({ frequencia: 'semanal', hora: '07:30', dia: 3 });
    expect(lerAgendamento('*/15 * * * *').frequencia).toBe('personalizada');
    expect(lerAgendamento(null).frequencia).toBe('nenhuma');
  });
});
