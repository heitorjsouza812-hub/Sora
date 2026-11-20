// Gate das rotas (etapa 2, regra 4): carregando → Sora pensando; sem login → Entrar;
// logado sem provedor → onboarding (exceto em /configuracoes ou depois de "Fazer isso depois").
// Em desenvolvimento, /lab/* passa direto (laboratórios do mascote e do catálogo).
import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { TelaCarregando } from './TelaCarregando';
import { iniciarSessao, useSessao } from '../../state/sessao';
import { useOnboardingPulado } from './onboardingPulado';
import { encerrarProjetos, iniciarProjetos } from '../../state/projetos';

const Entrar = lazy(() => import('../../screens/Entrar'));
const RedefinirSenha = lazy(() => import('../../screens/RedefinirSenha'));
const Onboarding = lazy(() => import('./Onboarding').then(m => ({ default: m.Onboarding })));

/** Link de senha nova do e-mail: abre com ou sem login. */
export const ROTA_SENHA_NOVA = '/redefinir-senha';

export function GateSessao({ children }: { children: ReactNode }) {
  const sessao = useSessao();
  const { pathname } = useLocation();
  const pulado = useOnboardingPulado();
  const senhaNova = pathname === ROTA_SENHA_NOVA;
  const livre = (import.meta.env.DEV && pathname.startsWith('/lab/')) || senhaNova;

  useEffect(() => { if (!livre) void iniciarSessao(); }, [livre]);
  useEffect(() => {
    if (sessao.estado !== 'logado' || livre) return;
    void iniciarProjetos();
    return encerrarProjetos;
  }, [sessao.estado, livre]);

  if (senhaNova) return <Suspense fallback={<TelaCarregando />}><RedefinirSenha /></Suspense>;
  if (livre) return <>{children}</>;
  if (sessao.estado === 'carregando') return <TelaCarregando />;
  if (sessao.estado === 'anonimo') return <Suspense fallback={<TelaCarregando />}><Entrar /></Suspense>;
  if (!sessao.usuario.tem_provedor && !pulado && pathname !== '/configuracoes') {
    return <Suspense fallback={<TelaCarregando />}><Onboarding /></Suspense>;
  }
  return <>{children}</>;
}
