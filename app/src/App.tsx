import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { SoraOrb } from './components/mascot';
import { SoraProvider } from './state/SoraContext';
import Home from './screens/Home';
import SoraChat from './screens/SoraChat';
import AgentChat from './screens/AgentChat';
import Plugins from './screens/Plugins';
import Mobile from './screens/Mobile';
import './components/ui/sora.css';

const OrbLab = lazy(() => import('./screens/OrbLab'));

function useCompactLayout() {
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 767px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 767px)');
    const update = () => setCompact(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return compact;
}

function AppRoutes() {
  const compact = useCompactLayout();
  const location = useLocation();
  if (compact && location.pathname !== '/lab/orb') return <Mobile />;
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

// Rotas (as telas serão criadas pelo agente "Forja"):
//   /               Novo chat (tela inicial)
//   /chat/sora      Chat da Sora (plano + equipe)
//   /chat/:agente   Chat de um agente
//   /plugins        Plugins
//   /celular        Versão celular
//   /lab/orb        Laboratório do mascote (agente "Prisma")
export default function App() {
  return <BrowserRouter><SoraProvider><AppRoutes /></SoraProvider></BrowserRouter>;
}
