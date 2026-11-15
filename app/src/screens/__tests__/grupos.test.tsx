import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('border-beam', () => ({ BorderBeam: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('voice-glow', () => ({
  VoiceBeam: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  useMicrophone: () => ({ state: 'idle', stream: null, start: vi.fn(), stop: vi.fn() }),
}));
vi.stubGlobal('matchMedia', (q: string) => ({ matches: false, media: q, addEventListener: () => {}, removeEventListener: () => {} }));
vi.mock('../../components/mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
vi.mock('../../components/layout/AppShell', () => ({ AppShell: ({ children, acoes }: { children: ReactNode; acoes?: ReactNode }) => <div>{acoes}{children}</div> }));

const api = vi.hoisted(() => ({
  listarGrupos: vi.fn(), listarMensagensGrupo: vi.fn(), listarTarefasGrupo: vi.fn(), listarPedidosAtencao: vi.fn(),
  definirMembrosDoGrupo: vi.fn(), reatribuirTarefaGrupo: vi.fn(), cancelarTarefaGrupo: vi.fn(), arquivarGrupo: vi.fn(),
}));
vi.mock('../../api/grupos', async (importar) => ({ ...(await importar<typeof import('../../api/grupos')>()), ...api }));
const listarBots = vi.hoisted(() => vi.fn());
vi.mock('../../api/bots', async (importar) => ({ ...(await importar<typeof import('../../api/bots')>()), listarBots }));

import type { GrupoApi, TarefaGrupoApi } from '../../api/grupos';
import { _reiniciarAtencaoParaTestes } from '../../state/atencao';
import { _reiniciarBotsParaTestes } from '../../state/bots';
import { _reiniciarGruposParaTestes } from '../../state/grupos';
import { _definirEstadoParaTestes, _reiniciarProjetosParaTestes, lerEstado } from '../../state/projetos';
import Grupos from '../Grupos';

const bot = (id: string, nome: string, cor: string) => ({ id, tipo: 'individual', nome, funcao: `Função de ${nome}`, cor, movimento: 'gira', ferramentas: [], estado: 'livre' });
const BOTS = [bot('b1', 'Atlas', '#56A8FF'), bot('b2', 'Luna', '#AC80FF'), bot('b3', 'Nina', '#46E8A8')];
const grupo = (parcial: Partial<GrupoApi> = {}): GrupoApi => ({ id: 'g1', nome: 'Lançamento', membros: ['sora', 'b1', 'b2'], liderId: 'sora', precisaDeVoce: false, trabalhando: false, ...parcial });
const tarefa = (parcial: Partial<TarefaGrupoApi> = {}): TarefaGrupoApi => ({ id: 't1', grupoId: 'g1', donoId: 'b1', status: 'parada', revisao: 1, acoes: ['retomar', 'reatribuir', 'cancelar'], ...parcial });

function abrir(caminho = '/grupos/g1') {
  return render(<MemoryRouter initialEntries={[caminho]}><Routes>
    <Route path="/grupos" element={<Grupos />} /><Route path="/grupos/:grupoId" element={<Grupos />} />
    <Route path="/" element={<p>Conversa com a Sora</p>} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  _reiniciarGruposParaTestes(); _reiniciarBotsParaTestes(); _reiniciarAtencaoParaTestes(); _reiniciarProjetosParaTestes();
  Object.values(api).forEach(fn => fn.mockReset());
  listarBots.mockReset().mockResolvedValue(BOTS);
  api.listarGrupos.mockResolvedValue([grupo()]);
  api.listarMensagensGrupo.mockResolvedValue([]);
  api.listarTarefasGrupo.mockResolvedValue([]);
  api.listarPedidosAtencao.mockResolvedValue([]);
});

describe('grupos sem bots', () => {
  it('mostra um único caminho, "Criar um bot", sem abrir modal sem saída', async () => {
    listarBots.mockResolvedValue([]); api.listarGrupos.mockResolvedValue([]);
    abrir('/grupos');
    expect(await screen.findByText('Grupos reúnem seus bots')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /Criar um bot/ })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /Novo grupo/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Criar um bot' }));
    expect(await screen.findByText('Conversa com a Sora')).toBeTruthy();
  });

  it('com 1 bot o modal explica e leva a criar outro', async () => {
    listarBots.mockResolvedValue([BOTS[0]]); api.listarGrupos.mockResolvedValue([]);
    abrir('/grupos');
    await screen.findByText('Nenhum grupo ainda');
    fireEvent.click(screen.getByRole('button', { name: 'Novo grupo' }));
    expect(await screen.findByText(/Você tem só 1 bot/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Criar um bot' }));
    expect(await screen.findByText('Conversa com a Sora')).toBeTruthy();
  });
});

describe('grupo com menos de 2 bots (B3)', () => {
  it('mostra o aviso, trava o campo e destrava depois de adicionar bots', async () => {
    api.listarGrupos.mockResolvedValue([grupo({ membros: ['sora', 'b1'], precisaDeBots: true })]);
    api.definirMembrosDoGrupo.mockResolvedValue(grupo({ membros: ['sora', 'b1', 'b3'], precisaDeBots: false }));
    abrir();
    expect(await screen.findByText(/Este grupo precisa de pelo menos 2 bots/)).toBeTruthy();
    expect(screen.queryByLabelText(/Mensagem para o grupo/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar bots' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Bots do grupo' });
    fireEvent.click(within(dialogo).getByLabelText(/Nina/));
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Salvar bots' }));
    await waitFor(() => expect(api.definirMembrosDoGrupo).toHaveBeenCalledWith('g1', ['b1', 'b3']));
    expect(await screen.findByLabelText(/Mensagem para o grupo/)).toBeTruthy();
    expect(screen.queryByText(/Este grupo precisa de pelo menos 2 bots/)).toBeNull();
  });

  it('antes de o backend mandar o campo, o aviso sai da contagem de bots', async () => {
    api.listarGrupos.mockResolvedValue([grupo({ membros: ['sora', 'b1'] })]);
    abrir();
    expect(await screen.findByRole('button', { name: 'Adicionar bots' })).toBeTruthy();
    expect(screen.queryByLabelText(/Mensagem para o grupo/)).toBeNull();
  });
});

describe('gerir o grupo', () => {
  it('mantém de 2 a 5 bots no menu Gerir bots', async () => {
    abrir();
    fireEvent.click(await screen.findByRole('button', { name: 'Menu do grupo' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Gerir bots' }));
    const dialogo = await screen.findByRole('dialog', { name: 'Bots do grupo' });
    fireEvent.click(within(dialogo).getByLabelText(/Luna/));
    expect((within(dialogo).getByRole('button', { name: 'Salvar bots' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('arquiva depois de confirmar e volta à lista', async () => {
    api.arquivarGrupo.mockResolvedValue(undefined);
    abrir();
    fireEvent.click(await screen.findByRole('button', { name: 'Menu do grupo' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Arquivar grupo' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Arquivar grupo' }));
    await waitFor(() => expect(api.arquivarGrupo).toHaveBeenCalledWith('g1'));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Grupo Lançamento' })).toBeNull());
  });

  it('tarefa parada: Reatribuir passa para outro bot e Cancelar cancela', async () => {
    api.listarTarefasGrupo.mockResolvedValue([tarefa()]);
    api.reatribuirTarefaGrupo.mockResolvedValue([tarefa({ donoId: 'b2', revisao: 2, status: 'na_fila', acoes: ['parar'] })]);
    api.cancelarTarefaGrupo.mockResolvedValue([tarefa({ status: 'cancelada', revisao: 3, acoes: [] })]);
    abrir();
    const tarefas = await screen.findByRole('region', { name: 'Tarefas do grupo' });
    expect(within(tarefas).getByText('Parada')).toBeTruthy();
    fireEvent.click(within(tarefas).getByRole('button', { name: 'Reatribuir' }));
    fireEvent.change(within(tarefas).getByLabelText(/Passar a tarefa de Atlas para/), { target: { value: 'b2' } });
    fireEvent.click(within(tarefas).getByRole('button', { name: 'Passar tarefa' }));
    await waitFor(() => expect(api.reatribuirTarefaGrupo).toHaveBeenCalledWith('t1', 'b2'));
    // reatribuída, a tarefa volta para a fila e sai desta lista (quem trabalha aparece na faixa de trabalho)
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Tarefas do grupo' })).toBeNull());
  });

  it('Cancelar chama a rota da tarefa e a tarefa sai da lista', async () => {
    api.listarTarefasGrupo.mockResolvedValue([tarefa()]);
    api.cancelarTarefaGrupo.mockResolvedValue([tarefa({ status: 'cancelada', revisao: 3, acoes: [] })]);
    abrir();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(api.cancelarTarefaGrupo).toHaveBeenCalledWith('t1'));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Tarefas do grupo' })).toBeNull());
  });

  it('quem trabalha ganha a faixa com o último passo e o Parar à mão', async () => {
    api.listarTarefasGrupo.mockResolvedValue([tarefa({ status: 'rodando', acoes: ['parar'] })]);
    const e = lerEstado();
    _definirEstadoParaTestes({ ...e, execucoes: [{ id: 'x1', agenteId: 'b1', inicio: 1, roteiro: [{ id: 'p1', agenteId: 'b1', tipo: 'ferramenta', texto: 'Pesquisando concorrentes', status: 'executando', inicio: 1 }] } as never] });
    abrir();
    expect(await screen.findByText('trabalhando · Pesquisando concorrentes')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Parar Atlas' })).toBeTruthy();
  });

  it('o grupo mostra só a conversa (sem segunda lista) e /grupos lista e abre', async () => {
    const { container, unmount } = abrir();
    await screen.findByRole('region', { name: 'Grupo Lançamento' });
    expect(container.querySelector('.grp-lista')).toBeNull();
    unmount();
    abrir('/grupos');
    fireEvent.click(await screen.findByRole('button', { name: /Lançamento/ }));
    expect(await screen.findByRole('region', { name: 'Grupo Lançamento' })).toBeTruthy();
  });
});
