import { lazy, Suspense, type ComponentType } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { SoraOrb } from './components/mascot';
import Home from './screens/Home';
import SoraChat from './screens/SoraChat';
import AgentChat from './screens/AgentChat';
import Agentes from './screens/Agentes';
import Revisao from './screens/Revisao';
import Plugins from './screens/Plugins';
import Mobile from './screens/Mobile';
import { ConfiguracoesProvisoria, EditorAgenteProvisorio, ProjetosProvisoria } from './screens/Provisorias';
import './components/ui/sora.css';

const OrbLab = lazy(() => import('./screens/OrbLab'));

// Telas de outros integrantes: entram sozinhas quando o arquivo existir (senão, a provisória).
// Projetos.tsx (Brisa) · Configuracoes.tsx e CriarAgente.tsx (Forja)
const externas = import.meta.glob<{ default: ComponentType }>(['./screens/Projetos.tsx', './screens/Configuracoes.tsx', './screens/CriarAgente.tsx']);
const tela = (arquivo: string, provisoria: ComponentType) => {
  const carregar = externas[`./screens/${arquivo}`];
  return carregar ? lazy(carregar) : provisoria;
};
const Projetos = tela('Projetos.tsx', ProjetosProvisoria);
const Configuracoes = tela('Configuracoes.tsx', ConfiguracoesProvisoria);
const CriarAgente = tela('CriarAgente.tsx', EditorAgenteProvisorio);

const carregando = <main className="orb-route-loading"><SoraOrb size={96} state="thinking" title="Carregando" /></main>;

// Rotas: / (Novo chat) · /projeto/:projetoId (chat da Sora / projeto) · /projetos · /agentes (galeria)
//        /agentes/novo · /agentes/:id/editar (construtor) · /chat/:agente · /revisao/:projetoId
//        /configuracoes · /plugins · /celular · /lab/orb
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
    <Route path="/celular" element={<Mobile />} />
    <Route path="/lab/orb" element={<OrbLab />} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense>;
}

export default function App() {
  return <BrowserRouter><AppRoutes /></BrowserRouter>;
}
