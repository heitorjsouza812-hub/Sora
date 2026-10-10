import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { SoraOrb } from './components/mascot';
import { SoraProvider } from './state/SoraContext';
import Home from './screens/Home';
import SoraChat from './screens/SoraChat';
import AgentChat from './screens/AgentChat';
import Plugins from './screens/Plugins';
import Mobile from './screens/Mobile';
import './components/ui/sora.css';

const OrbLab = lazy(() => import('./screens/OrbLab'));

function AppRoutes() {
  return <Routes>
    <Route path="/" element={<Home />} />
    <Route path="/chat/sora" element={<SoraChat />} />
    <Route path="/chat/:agente" element={<AgentChat />} />
    <Route path="/plugins" element={<Plugins />} />
    <Route path="/celular" element={<Mobile />} />
    <Route path="/lab/orb" element={<Suspense fallback={<main className="orb-route-loading"><SoraOrb size={120} state="thinking" title="Carregando laboratório" /></main>}><OrbLab /></Suspense>} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}

export default function App() {
  return <BrowserRouter><SoraProvider><AppRoutes /></SoraProvider></BrowserRouter>;
}

