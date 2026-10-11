import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ToastProvider } from './components/base';
import { SoraOrb } from './components/mascot';
import Home from './screens/Home';
import SoraChat from './screens/SoraChat';
import AgentChat from './screens/AgentChat';
import Agentes from './screens/Agentes';
import Projetos from './screens/Projetos';
import Revisao from './screens/Revisao';
import Plugins from './screens/Plugins';
import { PonteNavegacao } from './desktop/PonteNavegacao';
import './components/ui/sora.css';

// Telas menos visitadas: carregadas sob demanda.
const CriarAgente = lazy(() => import('./screens/CriarAgente'));
const Configuracoes = lazy(() => import('./screens/Configuracoes'));
// Só em desenvolvimento (em produção redirecionam para /).
const OrbLab = import.meta.env.DEV ? lazy(() => import('./screens/OrbLab')) : null;
const Mobile = import.meta.env.DEV ? lazy(() => import('./screens/Mobile')) : null;
const Catalogo = import.meta.env.DEV ? lazy(() => import('./screens/Catalogo')) : null;

const carregando = <main className="orb-route-loading"><SoraOrb size={96} state="thinking" title="Carregando" /></main>;

// Rotas: / (Novo chat) · /projeto/:projetoId (chat da Sora / projeto) · /projetos · /agentes (galeria)
//        /agentes/novo · /agentes/:id/editar (construtor) · /chat/:agente · /revisao/:projetoId
//        /configuracoes · /plugins · [DEV] /celular · /lab/orb · /lab/ui (catálogo de componentes)
function AppRoutes() {
  return <Suspense fallback={carregando}><Routes>
    <Route path="/" element={<Home />} />
    <Route path="/projeto/:projetoId" element={<SoraChat />} />
    <Route path="/chat/sora" element={<SoraChat />} />
    <Route path="/chat/:agente" element={<AgentChat />} />
    <Route path="/projetos" element={<Projetos />} />
    <Route path="/agentes" element={<Agentes />} />
    <Route path="/agentes/novo" element={<CriarAgente />} />
    <Route path="/agentes/:id/editar" element={<CriarAgente />} />
    <Route path="/revisao/:projetoId" element={<Revisao />} />
    <Route path="/configuracoes" element={<Configuracoes />} />
    <Route path="/plugins" element={<Plugins />} />
    {Mobile && <Route path="/celular" element={<Mobile />} />}
    {OrbLab && <Route path="/lab/orb" element={<OrbLab />} />}
    {Catalogo && <Route path="/lab/ui" element={<Catalogo />} />}
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense>;
}

export default function App() {
  return <BrowserRouter><AppRoutes /><PonteNavegacao /><ToastProvider /></BrowserRouter>;
}
