// Janela "ilha" do app de desktop (Tauri): só a Ilha da Sora, transparente, colada no topo da tela.
// A pílula fica centralizada no alto da janela de 800×460; fora do retângulo informado os cliques
// atravessam para o que estiver embaixo. Navegação ("Abrir chat", "Revisar"…) vai para a janela principal.
import { useEffect } from 'react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { ToastProvider } from '../base';
import { abrirNoApp, aoAlternarIlha, aoEsconderIlha, aoMudarSessaoNoPrincipal, informarRetanguloIlha, type Retangulo } from '../../desktop/ponte';
import { definirIlhaPrefs, lerIlhaPrefs } from './ilhaEstado';
import { abrirIlha, alternarIlha, fecharIlha } from './ilhaUi';
import { Ilha } from './Ilha';
import { iniciarSessao, lerSessao, useSessao } from '../../state/sessao';
import { encerrarProjetos, iniciarProjetos } from '../../state/projetos';
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
  const sessao = useSessao();
  useEffect(() => {
    document.documentElement.classList.add('janela-ilha');
    document.title = 'Ilha da Sora';
  }, []);

  // A janela nativa tem memória JS própria e NÃO vê o cofre: o token de acesso vem da janela
  // principal (ver fazerRenovacao em api/cliente.ts e PonteNavegacao). Sem sessão lá, a ilha fica
  // vazia (não renderiza nada) e nenhuma rota é chamada.
  useEffect(() => {
    let ativa = true;
    void iniciarSessao().then(() => {
      if (ativa && lerSessao().estado === 'logado') return iniciarProjetos();
    });
    return () => { ativa = false; encerrarProjetos(); };
  }, []);

  // login/saída na janela principal: recomeça do zero com a sessão certa (renovações comuns do
  // token só chegam em silêncio, sem recarregar).
  useEffect(() => aoMudarSessaoNoPrincipal(token => {
    const { estado } = lerSessao();
    if ((token && estado === 'anonimo') || (!token && estado === 'logado')) window.location.reload();
  }), []);

  // atalho global Ctrl+Shift+S / bandeja: liga a ilha se estiver desligada, senão abre/fecha
  useEffect(() => aoAlternarIlha(() => {
    if (!lerIlhaPrefs().visivel) { definirIlhaPrefs({ visivel: true }); abrirIlha(); }
    else alternarIlha();
  }), []);

  // a janela nativa sumiu (o usuário voltou à Sora): fecha o painel para reaparecer compacta. A
  // janela da ilha não ganha foco ao aparecer, então o "blur" sozinho não fecharia o painel.
  useEffect(() => aoEsconderIlha(fecharIlha), []);

  return (
    <MemoryRouter initialEntries={[BASE]}>
      <Encaminhador />
      {sessao.estado === 'logado' && <Ilha desktop onRetangulo={informar} />}
      <ToastProvider />
    </MemoryRouter>
  );
}

export default IlhaDesktop;
