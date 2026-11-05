// Teste real (2026-11-02): a entrega "Navegação" (1 captura + título e URL) aparecia no chat com TRÊS peças
// inventadas ("O novo começa aqui.", "Sua nova pausa favorita.", "Abrimos!"). Regra: sem simulação.
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const buscarAutenticado = vi.hoisted(() => vi.fn());
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), buscarAutenticado }));

import type { AgenteSora, EntregaGerada } from '../../../state/projetos';
import { DeliveryContent } from '../../review/Entregas';
import { Miniaturas } from '../../work/ChamadaFerramenta';
import { EntregaCard } from '../EntregaCard';

const ANEXO = '7f1c2a9e-4b2d-4c1e-9a7b-1f2e3d4c5b6a';
const agente = { id: 'a1', projetoId: 'p1', nome: 'Atlas', funcao: 'Pesquisa', cor: '#56A8FF' } as AgenteSora;
// como o app guarda depois de GET /v1/conversas/{id}/entregas: conteudo = { dados, fontes, pendencias }
const conteudo = { dados: { captura: { anexo_id: ANEXO, nome: 'captura.png', url: `/v1/anexos/${ANEXO}` }, titulo: 'Domain Name Services', url: 'https://www.iana.org/domains' }, fontes: ['https://www.iana.org/domains'], pendencias: [] };
const navegacao: EntregaGerada = { id: 'e1', agenteId: 'a1', tipo: 'imagem', titulo: 'Navegação', resumo: '1 captura', conteudo, ...conteudo };
const INVENTADOS = ['O novo começa aqui.', 'Sua nova pausa favorita.', 'Abrimos!', 'Bora conferir?'];

function semPecaInventada() {
  for (const t of INVENTADOS) expect(screen.queryByText(t)).toBeNull();
  expect(screen.queryByRole('img', { name: /^Peça \d/ })).toBeNull();
}

afterEach(() => { buscarAutenticado.mockReset(); });

describe('imagens das entregas', () => {
  it('card do chat mostra a captura real (blob autenticado) e nenhuma peça inventada', async () => {
    buscarAutenticado.mockResolvedValue({ blob: async () => new Blob(['x'], { type: 'image/png' }) });
    URL.createObjectURL = vi.fn(() => 'blob:cap'); URL.revokeObjectURL = vi.fn();
    render(<EntregaCard entrega={navegacao} agente={agente} />);
    semPecaInventada();
    const img = await screen.findByRole('img');
    expect(img.getAttribute('src')).toBe('blob:cap');
    expect(buscarAutenticado).toHaveBeenCalledWith(`/v1/anexos/${ANEXO}`, expect.anything());
    expect(screen.getAllByRole('img')).toHaveLength(1);
    expect(screen.getByText('https://www.iana.org/domains')).toBeTruthy();
  });

  it('entrega de imagem sem imagem não desenha miniatura', () => {
    render(<EntregaCard entrega={{ tipo: 'imagem', titulo: 'Peças', resumo: '3 peças', conteudo: { dados: 'só descrição' } }} agente={agente} />);
    semPecaInventada();
    expect(screen.queryAllByRole('img')).toHaveLength(0);
    expect(screen.getByText('Esta entrega não trouxe imagem.')).toBeTruthy();
  });

  it('revisão e painel Trabalho também não inventam', async () => {
    buscarAutenticado.mockResolvedValue({ blob: async () => new Blob(['x'], { type: 'image/png' }) });
    URL.createObjectURL = vi.fn(() => 'blob:cap'); URL.revokeObjectURL = vi.fn();
    const { unmount } = render(<DeliveryContent entrega={{ tipo: 'imagem', titulo: 'Peças', resumo: '3 peças' }} color="#AC80FF" />);
    semPecaInventada();
    expect(screen.queryAllByRole('img')).toHaveLength(0);
    unmount();
    const { container } = render(<Miniaturas resultado={{ resumo: '3 imagens geradas' }} cor="#AC80FF" />);
    expect(container.innerHTML).toBe('');
    render(<DeliveryContent entrega={navegacao} color="#56A8FF" />);
    await waitFor(() => expect(screen.getAllByRole('img')).toHaveLength(1));
    semPecaInventada();
  });
});
