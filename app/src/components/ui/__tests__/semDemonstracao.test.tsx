// Rodada 10: nada de conteúdo de demonstração aparecendo como real. O card de calendário desenhava 12
// eventos fixos (Post/Story/Reels), o de links escrevia "N referências organizadas por X" e o de texto só
// repetia o resumo, ignorando o `conteudo` real ({ dados, fontes, pendencias }) que o backend devolve.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));
import { AgentConfigForm } from '../../builder/AgentConfigForm';
import { DeliveryContent } from '../../review/Entregas';
import type { AgenteSora, EntregaGerada } from '../../../state/projetos';
import { EntregaCard } from '../EntregaCard';

const agente = { id: 'a1', projetoId: 'p1', nome: 'Atlas', funcao: 'Pesquisa', cor: '#56A8FF' } as AgenteSora;
const comConteudo = (tipo: EntregaGerada['tipo'], dados: unknown, fontes: string[] = []): EntregaGerada => {
  const conteudo = { dados, fontes, pendencias: [] };
  return { id: tipo, tipo, titulo: tipo, resumo: 'resumo do agente', conteudo, ...conteudo };
};
const DEMO = ['Post', 'Story', 'Reels'];

describe('cards de entrega sem demonstração', () => {
  it('calendário mostra as datas reais e nunca a grade de exemplo', () => {
    const { unmount } = render(<EntregaCard entrega={comConteudo('calendario', [{ data: '10/11', titulo: 'Abertura da loja' }, { dia: 12, tipo: 'Promoção de sexta' }])} agente={agente} />);
    expect(screen.getByText('Abertura da loja')).toBeTruthy();
    expect(screen.getByText('Dia 12')).toBeTruthy();
    for (const t of DEMO) expect(screen.queryByText(t)).toBeNull();
    unmount();
    render(<EntregaCard entrega={comConteudo('calendario', 'sem datas aqui')} agente={agente} />);
    for (const t of DEMO) expect(screen.queryByText(t)).toBeNull();
    expect(screen.getByText('Esta entrega não trouxe datas.')).toBeTruthy();
  });

  it('links mostram os links reais (dados + fontes); sem links, estado vazio', () => {
    const { unmount } = render(<EntregaCard entrega={comConteudo('links', [{ titulo: 'Referência A', url: 'https://example.com/a' }], ['https://exemplo.org/b'])} agente={agente} />);
    expect(screen.getByRole('link', { name: /Referência A/ }).getAttribute('href')).toBe('https://example.com/a');
    expect(screen.getByRole('link', { name: /exemplo\.org/ }).getAttribute('href')).toBe('https://exemplo.org/b');
    expect(screen.queryByText(/organizadas por/)).toBeNull();
    unmount();
    render(<EntregaCard entrega={comConteudo('links', [])} agente={agente} />);
    expect(screen.queryByText(/organizadas por/)).toBeNull();
    expect(screen.getByText('Esta entrega não trouxe links.')).toBeTruthy();
  });

  it('texto mostra o texto entregue, não o resumo repetido', () => {
    render(<EntregaCard entrega={comConteudo('texto', 'Primeiro parágrafo.\n\nSegundo parágrafo.')} agente={agente} />);
    expect(screen.getByText('Primeiro parágrafo.')).toBeTruthy();
    expect(screen.getByText('Segundo parágrafo.')).toBeTruthy();
  });

  it('revisão usa o mesmo conteúdo real', () => {
    const { unmount } = render(<DeliveryContent entrega={comConteudo('links', [{ titulo: 'Referência A', url: 'https://example.com/a' }])} color="#56A8FF" />);
    expect(screen.getByRole('link', { name: /Referência A/ })).toBeTruthy();
    unmount();
    const { unmount: fechar } = render(<DeliveryContent entrega={comConteudo('calendario', [{ data: '10/11', titulo: 'Abertura da loja' }])} color="#56A8FF" />);
    expect(screen.getByText('Abertura da loja')).toBeTruthy();
    fechar();
    render(<DeliveryContent entrega={comConteudo('texto', { texto: 'Legenda final' })} color="#56A8FF" />);
    expect(screen.getByText('Legenda final')).toBeTruthy();
  });

  it('construtor oferece só ferramentas que o backend aceita', () => {
    const rascunho = { nome: 'Teo', funcao: 'Pesquisador', descricaoCurta: '', cor: '#56A8FF', tipoMovimento: 'gira' as const, ferramentas: [], instrucoes: '', frasesIniciais: [], tom: 'objetivo' as const, modelo: null };
    render(<MemoryRouter><AgentConfigForm rascunho={rascunho} onChange={() => undefined} /></MemoryRouter>);
    expect(screen.getByLabelText('Buscar na web')).toBeTruthy();
    for (const falsa of ['Perplexity', 'Notion', 'Figma', 'Canva', 'Gmail']) expect(screen.queryByText(falsa)).toBeNull();
  });
});

describe('links parecidos no card (celular)', () => {
  it('dois títulos genéricos ficam distinguíveis pelo caminho, visível na 1ª linha', () => {
    render(<EntregaCard entrega={comConteudo('links', [
      { titulo: 'Referência de exemplo A', url: 'https://example.com/a' },
      { titulo: 'Referência de exemplo B', url: 'https://example.com/b' },
    ])} agente={agente} />);
    const [a, b] = screen.getAllByRole('link');
    expect(a.querySelector('span')?.textContent).toBe('↗ example.com/a');
    expect(b.querySelector('span')?.textContent).toBe('↗ example.com/b');
    expect(a.querySelector('small')?.textContent).toBe('Referência de exemplo A');
  });
});
