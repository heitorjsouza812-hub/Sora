import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ModelDefaults, ProviderCard } from '../components/settings';
import '../components/settings/settings.css';
import { apagarTodasAsChaves, PROVEDORES_MODELO, useModelos } from '../state/modelos';

type Secao = 'modelos' | 'conta' | 'aparencia';
export default function Configuracoes() {
  const [secao, setSecao] = useState<Secao>('modelos');
  const estado = useModelos();
  return <main className="cfg-page">
    <div className="cfg-shell">
      <aside className="cfg-nav"><Link className="cfg-back" to="/">← Voltar para a Sora</Link><h1>Configurações</h1><div role="tablist" aria-label="Seções das configurações">
        <button role="tab" aria-selected={secao === 'modelos'} onClick={() => setSecao('modelos')}>Modelos de IA</button>
        <button role="tab" aria-selected={secao === 'conta'} onClick={() => setSecao('conta')}>Conta</button>
        <button role="tab" aria-selected={secao === 'aparencia'} onClick={() => setSecao('aparencia')}>Aparência</button>
      </div></aside>
      <section className="cfg-main">
        {secao === 'modelos' ? <><header className="cfg-heading"><h2>Modelos de IA</h2><p>Conecte os provedores que a Sora e seus agentes podem usar. Você escolhe o modelo padrão e pode personalizar cada agente.</p></header>
          <div className="cfg-provider-grid">{PROVEDORES_MODELO.map(p => <ProviderCard key={p.id} provedor={p} configuracao={estado.provedores[p.id]} />)}</div>
          <ModelDefaults estado={estado} />
          <section className="cfg-security"><h3>Segurança das suas chaves</h3><p>Suas chaves ficam salvas apenas neste dispositivo. Em produção, elas serão guardadas com criptografia no servidor.</p><button type="button" className="cfg-button cfg-button-danger" onClick={() => { if (window.confirm('Apagar todas as chaves salvas neste navegador?')) apagarTodasAsChaves(); }}>Apagar todas as chaves</button></section>
        </> : <><header className="cfg-heading"><h2>{secao === 'conta' ? 'Conta' : 'Aparência'}</h2><p>{secao === 'conta' ? 'Gerencie os dados da sua conta e do seu plano.' : 'Personalize como a Sora aparece para você.'}</p></header><div className="cfg-placeholder">Esta seção estará disponível em breve.</div></>}
      </section>
    </div>
  </main>;
}

