import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../mascot', () => ({
  SoraOrb: () => <span data-testid="sora-orb" />,
}));

import { Button } from '../Button';
import { Input } from '../Campos';
import { ToastProvider } from '../Toast';
import { toast } from '../toastStore';
import { Tooltip } from '../Tooltip';


describe('components/base', () => {
  it.each(['primario', 'secundario', 'fantasma', 'perigo'] as const)('renderiza variante %s do Button', (variante) => {
    render(<Button variante={variante}>Continuar</Button>);
    expect(screen.getByRole('button', { name: 'Continuar' })).toHaveClass(`b-btn--${variante}`);
  });

  it('marca Button carregando como ocupado e desabilitado', () => {
    render(<Button carregando>Salvar</Button>);
    const botao = screen.getByRole('button', { name: 'Salvar' });

    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('sora-orb')).toBeInTheDocument();
  });

  it('marca Input com erro como inválido e anuncia a mensagem', () => {
    render(<Input rotulo="Nome" erro="Informe seu nome" />);

    expect(screen.getByLabelText('Nome')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Informe seu nome');
  });

  it('abre Tooltip no foco por teclado e fecha com Esc', async () => {
    const user = userEvent.setup();
    render(<Tooltip conteudo="Ajuda rápida"><button type="button">Ajuda</button></Tooltip>);

    await user.tab();
    expect(screen.getByRole('tooltip')).toHaveTextContent('Ajuda rápida');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument());
  });

  it('executa a ação Desfazer do Toast', async () => {
    const user = userEvent.setup();
    const desfazer = vi.fn();
    render(<ToastProvider />);

    toast({ mensagem: 'Projeto apagado', acao: { rotulo: 'Desfazer', onClick: desfazer }, duracao: 0 });
    const botao = await screen.findByRole('button', { name: 'Desfazer' });
    await user.click(botao);

    expect(desfazer).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Desfazer' })).not.toBeInTheDocument());
  });
});
