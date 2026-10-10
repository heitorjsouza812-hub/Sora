import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Fontes hospedadas localmente (sem CDN do Google): Inter variável + Playfair Display (títulos das peças).
import '@fontsource-variable/inter';
import '@fontsource/playfair-display/latin-600.css';
import './index.css';
import './fontes.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
