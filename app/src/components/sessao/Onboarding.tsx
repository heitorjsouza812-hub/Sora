// Onboarding "Conecte sua primeira API" (etapa 2, regra 4): logado sem provedor (tem_provedor=false).
// Reusa o cartão de provedor das Configurações (Lastro). Dá para pular para Configurações;
// o aviso continua na Home (AvisoSemProvedor) até conectar.
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import { ProviderCard } from '../settings';
import { PROVEDORES_MODELO } from '../../state/modelos';
import { recarregarSessao, sair, useSessao } from '../../state/sessao';
import { pularOnboarding } from './onboardingPulado';
import '../settings/settings.css';
import './sessao.css';

const IDS_ONBOARDING = ['openai', 'anthropic', 'gemini', 'groq', 'openrouter', 'openai-compativel'];

export function Onboarding() {
  const navigate = useNavigate();
  const { usuario } = useSessao();
  const [saindo, setSaindo] = useState(false);
  const provedores = IDS_ONBOARDING.flatMap(id => PROVEDORES_MODELO.filter(p => p.id === id));
  const primeiroNome = usuario?.nome.trim().split(/\s+/)[0];

  const pular = () => { pularOnboarding(); navigate('/configuracoes'); };
  const trocarConta = async () => {
    setSaindo(true);
    await sair();
    navigate('/');
  };

  return (
    <main className="sessao-tela onboarding">
      <SoraOrb size={120} state="idle" seed={0} title="Sora" />
      <h1>{primeiroNome ? `${primeiroNome}, conecte sua primeira API` : 'Conecte sua primeira API'}</h1>
      <p className="sessao-sub">A Sora e os agentes usam os modelos de IA da sua conta. A chave fica guardada com criptografia no servidor da Sora, nunca no navegador.</p>
      <section className="onboarding-lista" aria-label="Provedores de IA">
        {provedores.map((p, i) => <ProviderCard key={p.id} provedor={p} inicialmenteAberto={i === 0} onConectado={() => { void recarregarSessao(); }} />)}
      </section>
      <div className="onboarding-acoes">
        <Button variante="fantasma" onClick={pular}>Fazer isso depois em Configurações</Button>
        <Button variante="fantasma" carregando={saindo} onClick={() => { void trocarConta(); }}>Sair</Button>
      </div>
    </main>
  );
}
