import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AUTOMATICO, gravarPreferencias, lerPreferencias, type PreferenciasConversa } from '../api/preferenciasConversa';
import { mensagemDeErro } from '../api/cliente';

export interface ControlePreferencias {
  valor: PreferenciasConversa;
  mudar: (valor: PreferenciasConversa, confirmar?: boolean) => void;
  ocupado?: boolean;
  erro?: string;
}
const Contexto = createContext<ControlePreferencias>({ valor: AUTOMATICO, mudar: () => {} });
// Contexto e hook são a mesma unidade de estado do compositor.
// oxlint-disable-next-line react/only-export-components
export const usePreferenciasConversa = () => useContext(Contexto);

export function PreferenciasDaConversa({ conversaId, botId, children }: { conversaId?: string; botId?: string; children: ReactNode }) {
  const caminho = conversaId && !conversaId.startsWith('local-') ? `/v1/conversas/${conversaId}/preferencias` : botId ? `/v1/agentes/${botId}` : '';
  const [estado, setEstado] = useState({ caminho: '', valor: AUTOMATICO, ocupado: false, erro: '' });
  const geracao = useRef(0);
  useEffect(() => {
    const atual = ++geracao.current;
    if (!caminho) return;
    void lerPreferencias(caminho).then(valor => {
      if (geracao.current === atual) setEstado({ caminho, valor: valor ?? AUTOMATICO, ocupado: false, erro: valor === null ? 'Preferências ainda indisponíveis. Usando Automático.' : '' });
    }).catch(e => { if (geracao.current === atual) setEstado({ caminho, valor: AUTOMATICO, ocupado: false, erro: mensagemDeErro(e) }); });
    return () => { geracao.current = atual + 1; };
  }, [caminho]);
  const valor = estado.caminho === caminho ? estado.valor : AUTOMATICO;
  const ocupado = !!caminho && (estado.caminho !== caminho || estado.ocupado);
  const mudar = async (novo: PreferenciasConversa, confirmar = false) => {
    if (!caminho || ocupado) return;
    const atual = geracao.current;
    setEstado({ caminho, valor, ocupado: true, erro: '' });
    try {
      const salvo = await gravarPreferencias(caminho, novo, confirmar);
      if (atual === geracao.current) setEstado({ caminho, valor: salvo ?? AUTOMATICO, ocupado: false, erro: salvo === null ? 'Preferências ainda indisponíveis. Usando Automático.' : '' });
    } catch (e) { if (atual === geracao.current) setEstado({ caminho, valor, ocupado: false, erro: mensagemDeErro(e) }); }
  };
  return <Contexto.Provider value={{ valor, mudar, ocupado: ocupado || !caminho, erro: estado.caminho === caminho ? estado.erro : '' }}>{children}</Contexto.Provider>;
}

export function SeloAcessoTotal() {
  const { valor } = usePreferenciasConversa();
  return valor.permissao === 'total' ? <span className="seletor-selo" role="status">Acesso total</span> : null;
}
