import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AgenteSora, ProjetoSora } from '../../../state/projetos';
import { ProjetoAprovado } from '../ProjetoAprovado';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));

describe('projeto aprovado', () => {
  it('confirma a aprovação sem inventar publicação em plugin', () => {
    const agente: AgenteSora = {
      id: 'a1', projetoId: 'p1', nome: 'Ravi', funcao: 'Texto', cor: '#56A8FF',
      tipoMovimento: 'ondas', ferramentas: [], status: 'concluido', verbo: 'Escrevendo',
      espera: 'Aguardando', instrucoes: '', avulso: false, criadoEm: 1,
    };
    const projeto: ProjetoSora = {
      id: 'p1', tipo: 'projeto', titulo: 'Campanha', pedido: '', modelo: '', assunto: '',
      resposta: '', criadoEm: 1, tarefas: [], agenteIds: ['a1'], entregas: {},
      marcos: { plano: 1, nascimentos: [], trabalho: 1, fim: 1 }, versao: 1, aprovadoEm: 1,
    };
    render(<ProjetoAprovado projeto={projeto} agentes={[agente]} entregas={{
      a1: { tipo: 'texto', titulo: 'Legendas', resumo: '3 textos' },
    }} />);
    expect(screen.getByText('Entregas aprovadas')).toBeInTheDocument();
    expect(screen.queryByText(/publicado|Instagram|Google Drive/i)).not.toBeInTheDocument();
  });
});
