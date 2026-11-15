import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
const mocks = vi.hoisted(() => ({ criar: vi.fn(), adicionar: vi.fn(), registrar: vi.fn(), enviar: vi.fn() }));
vi.mock('../../api/bots', () => ({ criarBotPorDescricao: mocks.criar }));
vi.mock('../../state/bots', () => ({ adicionarBot: mocks.adicionar }));
vi.mock('../../state/projetos', () => ({ registrarBot: mocks.registrar, enviarParaAgente: mocks.enviar }));
vi.mock('../../components/layout/AppShell', () => ({ AppShell: ({children}: {children: ReactNode}) => <>{children}</> }));
vi.mock('../../components/mascot', () => ({ SoraOrb: () => null, SoraThinking: ({label}: {label: string}) => <span>{label}</span> }));
vi.mock('../../components/ui/MessageComposer', () => ({ MessageComposer: ({value, onValueChange, onSend}: {value: string; onValueChange: (s: string) => void; onSend: (s: string) => void}) => <form onSubmit={e => {e.preventDefault(); onSend(value); onValueChange('');}}><textarea value={value} onChange={e => onValueChange(e.target.value)} /><button>Enviar</button></form> }));
import NovoBot from '../NovoBot';
function Rota() { const l = useLocation(); const n = useNavigate(); return <><output>{l.pathname}</output><button onClick={() => n('/bots/novo')}>Novo bot</button></>; }
function montar() { render(<MemoryRouter initialEntries={['/bots/novo']}><NovoBot /><Rota /></MemoryRouter>); }
beforeEach(() => { vi.clearAllMocks(); });
it('comeca limpa e limpa novamente ao clicar Novo bot', () => {
 montar(); expect(screen.getByRole('textbox')).toHaveValue('');
 fireEvent.change(screen.getByRole('textbox'), {target: {value: 'rascunho'}});
 fireEvent.click(screen.getByText('Novo bot')); expect(screen.getByRole('textbox')).toHaveValue('');
});
it('cria, registra, navega e envia o pedido original uma vez', async () => {
 const bot = { id: 'bot-1' }; mocks.criar.mockResolvedValue(bot); montar();
 fireEvent.change(screen.getByRole('textbox'), {target: {value: 'pesquise precos'}});
 fireEvent.click(screen.getByText('Enviar'));
 await waitFor(() => expect(mocks.enviar).toHaveBeenCalledWith('bot-1', 'pesquise precos'));
 expect(mocks.criar).toHaveBeenCalledTimes(1); expect(mocks.adicionar).toHaveBeenCalledWith(bot);
 expect(mocks.registrar).toHaveBeenCalledWith(bot); await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('/bots/bot-1'));
});
it('erro preserva o pedido e permite tentar novamente', async () => {
 mocks.criar.mockRejectedValue(new Error('Falha ao criar bot')); montar();
 fireEvent.change(screen.getByRole('textbox'), {target: {value: 'pesquise precos'}});
 fireEvent.click(screen.getByText('Enviar')); await screen.findByRole('alert');
 expect(screen.getByRole('textbox')).toHaveValue('pesquise precos'); expect(mocks.enviar).not.toHaveBeenCalled();
});
