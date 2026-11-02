import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));

import { _reiniciarProjetosParaTestes } from '../../../state/projetos';
import { AgentPreview } from '../AgentPreview';

afterEach(() => _reiniciarProjetosParaTestes());

describe('prévia do agente', () => {
  // Regression: ISSUE-003 — a prévia inventava uma resposta local com setTimeout
  // Found by /qa on 2026-11-02
  // Report: .gstack/qa-reports/qa-report-sora-local-2026-11-02.md
  it('não oferece resposta falsa antes de o agente ser salvo', () => {
    render(<AgentPreview agente={{ nome: 'Lume', funcao: 'Redatora', descricaoCurta: '', cor: '#56A8FF', tipoMovimento: 'gira', ferramentas: [], instrucoes: '', frasesIniciais: [], tom: 'objetivo', modelo: null }} />);
    expect(screen.getByText('Salve o agente para testar em uma conversa real.')).toBeVisible();
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.queryByText(/resposta simulada/i)).not.toBeInTheDocument();
  });
});
