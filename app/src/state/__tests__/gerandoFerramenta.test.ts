import { beforeEach, describe, expect, it } from 'vitest';
import { _reiniciarProjetosParaTestes, gerandoNa, lerEstado, type EstadoProjetos, type Execucao } from '../projetos';

const execucao = (parcial: Partial<Execucao>): Execucao => ({ id: 'e1', agenteId: 'b1', projetoId: 'c1', inicio: 0, roteiro: [], status: 'pendente', progresso: 0, ...parcial });
const comExecucoes = (...execucoes: Execucao[]): EstadoProjetos => ({ ...lerEstado(), execucoes });
beforeEach(() => _reiniciarProjetosParaTestes());

describe('"trabalhando" a partir dos eventos de etapa e passo', () => {
  it('sem execução aberta, não trabalha', () => {
    expect(gerandoNa(comExecucoes(), 'b1', 0)).toBe(false);
    expect(gerandoNa(comExecucoes(execucao({ status: 'concluida' })), 'b1', 0)).toBe(false);
  });
  it('etapa executando conta como trabalhando, no bot e na conversa', () => {
    const e = comExecucoes(execucao({ status: 'executando' }));
    expect(gerandoNa(e, 'b1', 0)).toBe(true);
    expect(gerandoNa(e, 'c1', 0)).toBe(true);
    expect(gerandoNa(e, 'outro', 0)).toBe(false);
  });
  it('passo de ferramenta ainda aberto conta, mesmo sem texto sendo escrito', () => {
    const passo = { id: 'p1', agenteId: 'b1', tipo: 'ferramenta', texto: 'Abrindo o navegador', status: 'executando', inicio: 0 } as unknown as Execucao['roteiro'][number];
    expect(gerandoNa(comExecucoes(execucao({ roteiro: [passo] })), 'b1', 0)).toBe(true);
    expect(gerandoNa(comExecucoes(execucao({ roteiro: [{ ...passo, status: 'concluido' } as never] })), 'b1', 0)).toBe(false);
  });
});
