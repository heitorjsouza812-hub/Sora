import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { idDaAncora, LIMITE_CARGAS, seletorDaMensagem, useIrParaMensagem } from '../useIrParaMensagem';

vi.mock('../../base', () => ({ toast: vi.fn() }));
vi.mock('../../../state/projetos', () => ({ carregarMensagens: vi.fn(), lerEstado: vi.fn(), useProjetos: vi.fn() }));
import { toast } from '../../base';

function Lista({ hash, ids, mais }: { hash: string; ids: string[]; mais: () => Promise<boolean> }) {
  useIrParaMensagem(true, mais);
  return <div>{ids.map(id => <p key={id} data-msg-id={id}>mensagem {id}</p>)}<span>{hash}</span></div>;
}

describe('âncora #msg-<id>', () => {
  let rolar: ReturnType<typeof vi.fn>;
  beforeEach(() => { rolar = vi.fn(); Element.prototype.scrollIntoView = rolar as never; });
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('lê o id do hash e monta o seletor', () => {
    expect(idDaAncora('#msg-abc%20d')).toBe('abc d');
    expect(idDaAncora('#outra')).toBeNull();
    expect(seletorDaMensagem('a"b')).toContain('a\\"b');
  });
  it('rola até a mensagem carregada e a destaca', async () => {
    const mais = vi.fn().mockResolvedValue(false);
    render(<MemoryRouter initialEntries={['/#msg-m2']}><Lista hash="x" ids={['m1', 'm2']} mais={mais} /></MemoryRouter>);
    // espera pelo efeito, não por um tempo fixo: com a máquina carregada 60 ms não bastavam
    await waitFor(() => expect(rolar).toHaveBeenCalledTimes(1));
    expect(screen.getByText('mensagem m2').classList.contains('msg-destaque')).toBe(true);
    expect(screen.getByText('mensagem m1').classList.contains('msg-destaque')).toBe(false);
    expect(mais).not.toHaveBeenCalled();
  });
  it('carrega anteriores até achar, com limite, e avisa se não achar', async () => {
    const mais = vi.fn().mockResolvedValue(true);
    render(<MemoryRouter initialEntries={['/#msg-sumida']}><Lista hash="x" ids={['m1']} mais={mais} /></MemoryRouter>);
    await waitFor(() => expect(toast).toHaveBeenCalled(), { timeout: 8000 });
    expect(mais).toHaveBeenCalledTimes(LIMITE_CARGAS);
    expect(rolar).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ mensagem: expect.stringContaining('Não encontrei') }));
  });
  it('para ao não haver mais mensagens', async () => {
    const mais = vi.fn().mockResolvedValue(false);
    render(<MemoryRouter initialEntries={['/#msg-sumida']}><Lista hash="x" ids={['m1']} mais={mais} /></MemoryRouter>);
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(mais).toHaveBeenCalledTimes(1);
  });
});
