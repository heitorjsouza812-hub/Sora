import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Fontes hospedadas localmente (sem CDN do Google): Inter variável + Playfair Display (títulos das peças).
import '@fontsource-variable/inter';
import '@fontsource/playfair-display/latin-600.css';
import './index.css';
import './fontes.css';
import App from './App';
import { janelaAtual } from './desktop/ponte';

// App de desktop (Tauri): a janela "ilha" mostra só a Ilha da Sora (sem telas, sem barra lateral).
// Em desenvolvimento, /?janela=ilha no navegador abre a mesma vista para testar.
const ehIlha = janelaAtual === 'ilha'
  || (import.meta.env.DEV && new URLSearchParams(window.location.search).get('janela') === 'ilha');

const raiz = createRoot(document.getElementById('root')!);
if (ehIlha) {
  void import('./components/ilha/IlhaDesktop').then(({ IlhaDesktop }) => raiz.render(<StrictMode><IlhaDesktop /></StrictMode>));
} else {
  raiz.render(<StrictMode><App /></StrictMode>);
}
