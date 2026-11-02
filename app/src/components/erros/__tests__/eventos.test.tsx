import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  _definirEstadoParaTestes,
  _reiniciarProjetosParaTestes,
  capturarSnapshot,
} from '../../../state/projetos';
import { FaixaErroEventos } from '../Erros';

afterEach(() => _reiniciarProjetosParaTestes());

describe('aviso do canal de eventos', () => {
  it('mostra ao usuário quando o limite de streams responde 429', () => {
    _definirEstadoParaTestes({
      ...capturarSnapshot(),
      erroEventos: 'Conexões de eventos demais abertas. Feche alguma aba e tente de novo.',
    });
    render(<FaixaErroEventos />);
    expect(screen.getByRole('alert')).toHaveTextContent('Atualizações ao vivo pausadas.');
    expect(screen.getByRole('alert')).toHaveTextContent('Feche alguma aba');
  });
});
