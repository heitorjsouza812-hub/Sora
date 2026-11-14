import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { ToastProvider } from './components/base';
const SoraChat = lazy(() => import('./screens/SoraChat'));
const AgentChat = lazy(() => import('./screens/AgentChat'));
const Agentes = lazy(() => import('./screens/Agentes'));
const Grupos = lazy(() => import('./screens/Grupos'));
import { PonteNavegacao } from './desktop/PonteNavegacao';
import { PonteSessao } from './desktop/PonteSessao';
import { GateSessao, TelaCarregando } from './components/sessao';
import './components/ui/sora.css';

// Telas menos visitadas: carregadas sob demanda.
const CriarAgente = lazy(() => import('./screens/CriarAgente'));
const Configuracoes = lazy(() => import('./screens/Configuracoes'));
// Só em desenvolvimento (em produção redirecionam para /).
const OrbLab = import.meta.env.DEV ? lazy(() => import('./screens/OrbLab')) : null;
const Mobile = import.meta.env.DEV ? lazy(() => import('./screens/Mobile')) : null;
const Catalogo = import.meta.env.DEV ? lazy(() => import('./screens/Catalogo')) : null;

function RedirecionarBotAntigo() {
  const { agente = '' } = useParams();
  return <Navigate to={`/bots/${agente}`} replace />;
}

// Entrada da etapa 5: Sora, bots persistentes e grupos. As rotas antigas apenas redirecionam.
function AppRoutes() {
  return <Suspense fallback={<TelaCarregando />}><Routes>
    <Route path="/" element={<SoraChat />} />
    <Route path="/bots" element={<Agentes />} />
    <Route path="/bots/:agente" element={<AgentChat />} />
    <Route path="/bots/:id/editar" element={<CriarAgente />} />
    <Route path="/grupos" element={<Grupos />} />
    <Route path="/grupos/:grupoId" element={<Grupos />} />
    <Route path="/configuracoes" element={<Configuracoes />} />
    <Route path="/plugins" element={<Navigate to="/" replace />} />
    <Route path="/chat/sora" element={<Navigate to="/" replace />} />
    <Route path="/chat/:agente" element={<RedirecionarBotAntigo />} />
    <Route path="/agentes" element={<Navigate to="/bots" replace />} />
    <Route path="/agentes/novo" element={<Navigate to="/" replace />} />
    <Route path="/agentes/:id/editar" element={<CriarAgente />} />
    <Route path="/canais/*" element={<Navigate to="/grupos" replace />} />
    <Route path="/projeto/:id" element={<Navigate to="/" replace />} />
    <Route path="/projetos" element={<Navigate to="/" replace />} />
    <Route path="/revisao/:id" element={<Navigate to="/" replace />} />
    {Mobile && <Route path="/celular" element={<Mobile />} />}
    {OrbLab && <Route path="/lab/orb" element={<OrbLab />} />}
    {Catalogo && <Route path="/lab/ui" element={<Catalogo />} />}
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense>;
}

export default function App() {
  return <BrowserRouter><PonteSessao /><GateSessao><AppRoutes /><PonteNavegacao /></GateSessao><ToastProvider /></BrowserRouter>;
}
