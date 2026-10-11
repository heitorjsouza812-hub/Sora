// Janela "ilha" do app de desktop (Tauri): só a Ilha da Sora, transparente, colada no topo da tela.
// A pílula fica centralizada no alto da janela de 800×460; fora do retângulo informado os cliques
// atravessam para o que estiver embaixo. Navegação ("Abrir chat", "Revisar"…) vai para a janela principal.
import { useEffect } from 'react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { ToastProvider } from '../base';
import { abrirNoApp, aoAlternarIlha, informarRetanguloIlha, type Retangulo } from '../../desktop/ponte';
import { definirIlhaPrefs, lerIlhaPrefs } from './ilhaEstado';
import { abrirIlha, alternarIlha } from './ilhaUi';
import { Ilha } from './Ilha';
import '../ui/sora.css';
import './ilha-desktop.css';

/** Rota "parada" da janela da ilha; qualquer outra rota é um pedido para abrir no app principal. */
const BASE = '/ilha';

function Encaminhador() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (pathname === BASE) return;
    void abrirNoApp(pathname + search).catch(() => {});
    navigate(BASE, { replace: true });
  }, [pathname, search, navigate]);
  return null;
}

const informar = (r: Retangulo) => { void informarRetanguloIlha(r).catch(() => {}); };

export function IlhaDesktop() {
  useEffect(() => {
    document.documentElement.classList.add('janela-ilha');
    document.title = 'Ilha da Sora';
  }, []);

  // atalho global Ctrl+Shift+S / bandeja: liga a ilha se estiver desligada, senão abre/fecha
  useEffect(() => aoAlternarIlha(() => {
    if (!lerIlhaPrefs().visivel) { definirIlhaPrefs({ visivel: true }); abrirIlha(); }
    else alternarIlha();
  }), []);

  return (
    <MemoryRouter initialEntries={[BASE]}>
      <Encaminhador />
      <Ilha desktop onRetangulo={informar} />
      <ToastProvider />
    </MemoryRouter>
  );
}

export default IlhaDesktop;
