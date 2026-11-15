import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const ctl = vi.hoisted(() => ({
  agentes: {} as Record<string, unknown>,
  st: { status: 'ocioso' } as { status: string },
  porBot: {} as Record<string, number>,
}));

vi.mock('../../../state/projetos', () => ({
  useProjetos: () => ({ sora: { nome: 'Sora', cor: '#E2ECFF' }, projetos: [], agentes: ctl.agentes }),
  useAgora: () => 0,
  novoChat: vi.fn(),
  estadoAgente: () => ctl.st,
  estadoProjeto: vi.fn(),
}));
vi.mock('../../../state/atencao', () => ({
  usePrecisaDeVoce: () => ({ lista: [], porBot: ctl.porBot, porGrupo: {} }),
  carregarPrecisaDeVoce: vi.fn(async () => {}),
}));
vi.mock('../Sidebar', () => ({ Sidebar: () => null, ContaRodape: () => null, MarcaSora: () => null, Navegacao: () => null }));
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
vi.mock('../../comandos', () => ({ Comandos: () => null }));
vi.mock('../../erros', () => ({ FaixaErroEventos: () => null, FaixaSemConexao: () => null }));
vi.mock('../../builder', () => ({ EditorAgenteHost: () => null, MenuAgente: ({ nome }: { nome: string }) => <button type="button" aria-label={`Opções de ${nome}`} /> }));
vi.mock('../../gestao', () => ({ GestaoHost: () => null }));

import { AppShell } from '../AppShell';

const bot = { id: 'b1', nome: 'Bot de pesquisa', funcao: 'Pesquisa', verbo: 'Pesquisando', cor: '#56A8FF', tipoMovimento: 'gira' };
const montar = (props: Parameters<typeof AppShell>[0]) => render(<MemoryRouter><AppShell {...props} /></MemoryRouter>);

beforeEach(() => { ctl.agentes = { b1: bot }; ctl.st = { status: 'ocioso' }; ctl.porBot = {}; });

describe('cabeçalho da tela (etapa 6)', () => {
  it('na Sora (/) não repete a identidade no desktop e mantém o menu "…"', () => {
    const { container } = montar({ children: <p>x</p> });
    expect(container.querySelector('.topbar-identity.is-sora')).not.toBeNull(); // escondido por CSS no desktop, visível no celular
    expect(screen.getByRole('button', { name: 'Opções de Sora' })).toBeInTheDocument();
    expect(container.querySelector('.topbar-estado')).toBeNull();
  });

  it('no bot, o estado vem na mesma linha do nome: nada quando disponível', () => {
    const { container } = montar({ agenteId: 'b1', children: <p>x</p> });
    expect(screen.getByText('Bot de pesquisa')).toBeInTheDocument();
    expect(container.querySelector('.topbar-estado')).toBeEmptyDOMElement();
  });

  it('no bot, mostra "· Pesquisando" quando trabalha e "· Precisa de você" quando espera', () => {
    ctl.st = { status: 'trabalhando' };
    const { container, unmount } = montar({ agenteId: 'b1', children: <p>x</p> });
    expect(container.querySelector('.topbar-estado')).toHaveTextContent('· Pesquisando');
    unmount();
    ctl.porBot = { b1: 2 };
    const outra = montar({ agenteId: 'b1', children: <p>x</p> });
    expect(outra.container.querySelector('.topbar-estado')).toHaveTextContent('· Precisa de você');
    expect(outra.container.querySelector('.topbar-estado')).toHaveAttribute('role', 'status');
  });

  it('telas com título mostram o título uma vez, com apoio opcional, e sem menu "…" de bot', () => {
    const { container } = montar({ titulo: 'Grupos', subtitulo: 'Sora + 2 bots', children: <p>x</p> });
    expect(screen.getAllByText('Grupos')).toHaveLength(1);
    expect(container.querySelector('.topbar-sub')).toHaveTextContent('· Sora + 2 bots');
    expect(screen.queryByRole('button', { name: /Opções de/ })).toBeNull();
  });

  it('a divisória só aparece quando o conteúdo rola por baixo do cabeçalho', () => {
    const { container } = montar({ children: <div className="rolador" style={{ overflow: 'auto' }}>conteúdo</div> });
    const topo = container.querySelector('.topbar') as HTMLElement;
    const rolador = container.querySelector('.rolador') as HTMLElement;
    topo.getBoundingClientRect = () => ({ bottom: 52, top: 0 }) as DOMRect;
    rolador.getBoundingClientRect = () => ({ top: 52 }) as DOMRect;
    expect(topo).not.toHaveAttribute('data-rolou');
    rolador.scrollTop = 80; fireEvent.scroll(rolador);
    expect(topo).toHaveAttribute('data-rolou');
    rolador.scrollTop = 0; fireEvent.scroll(rolador);
    expect(topo).not.toHaveAttribute('data-rolou');
  });
});
