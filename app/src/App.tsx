import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { SoraOrb } from './components/mascot/SoraOrb';

// Rotas (as telas serão criadas pelo agente "Forja"):
//   /               Novo chat (tela inicial)
//   /chat/sora      Chat da Sora (plano + equipe)
//   /chat/:agente   Chat de um agente
//   /plugins        Plugins
//   /celular        Versão celular
//   /lab/orb        Laboratório do mascote (agente "Prisma")
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="*" element={<div style={{ display: 'grid', placeItems: 'center', height: '100%' }}><SoraOrb size={240} /></div>} />
      </Routes>
    </BrowserRouter>
  );
}
