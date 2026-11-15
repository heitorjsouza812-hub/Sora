import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, expect, it } from 'vitest';
import { NotificacoesDesktop } from './NotificacoesDesktop';

beforeEach(() => localStorage.clear());
it('começa ligada e guarda a escolha', () => {
  render(<NotificacoesDesktop />);
  const controle = screen.getByRole('checkbox', { name: /notificações/i });
  expect(controle).toBeChecked();
  fireEvent.click(controle);
  expect(localStorage.getItem('sora.notificacoes.v1')).toBe('false');
});
