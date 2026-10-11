// Atalhos globais + paleta (item 46). Monte UMA vez dentro do BrowserRouter (AppShell).
//   Ctrl/⌘+K       abre/fecha a paleta (funciona até dentro de campos de texto)
//   Ctrl/⌘+Shift+O novo chat
//   /              foca o campo de mensagem (fora de campos de texto)
//   Ctrl/⌘+.       já é do PainelLateral — aqui não é registrado de novo
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { novoChat } from '../../state/projetos';
import { definirIlhaPrefs, lerIlhaPrefs } from '../ilha/ilhaEstado';
import { abrirIlha, alternarIlha } from '../ilha/ilhaUi';
import { alternarPaleta, digitando, fecharPaleta, focarCampoMensagem, usePaletaAberta } from './atalhos';
import { PaletaComandos } from './PaletaComandos';

export function Comandos() {
  const aberta = usePaletaAberta();
  const navigate = useNavigate();

  useEffect(() => {
    const tecla = (ev: KeyboardEvent) => {
      if (ev.defaultPrevented || ev.isComposing) return;
      const mod = ev.ctrlKey || ev.metaKey;
      const k = ev.key.toLowerCase();
      if (mod && !ev.shiftKey && !ev.altKey && k === 'k') { ev.preventDefault(); alternarPaleta(); return; }
      if (mod && ev.shiftKey && !ev.altKey && k === 'o') { ev.preventDefault(); fecharPaleta(); novoChat(); navigate('/'); return; }
      if (mod && ev.shiftKey && !ev.altKey && k === 's') {
        ev.preventDefault();
        fecharPaleta();
        if (!lerIlhaPrefs().visivel) { definirIlhaPrefs({ visivel: true }); abrirIlha(); }
        else alternarIlha();
        return;
      }
      if (ev.key === '/' && !mod && !ev.altKey && !digitando(ev.target) && !document.querySelector('[aria-modal="true"]')) {
        if (focarCampoMensagem()) ev.preventDefault();
      }
    };
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [navigate]);

  // sair da rota fecha a paleta (ex.: voltar no navegador com ela aberta)
  useEffect(() => () => fecharPaleta(), []);

  return aberta ? <PaletaComandos /> : null;
}
