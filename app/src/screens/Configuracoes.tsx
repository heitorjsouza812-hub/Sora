import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { Modal } from '../components/overlay';
import { ModelDefaults, ProviderCard } from '../components/settings';
import '../components/settings/settings.css';
import { apagarTodasAsChaves, PROVEDORES_MODELO, useModelos } from '../state/modelos';
import { limparTudo } from '../state/projetos';

type Secao = 'modelos' | 'conta' | 'aparencia';
export default function Configuracoes() {
  const [secao, setSecao] = useState<Secao>('modelos');
  const [confirmarLimpeza, setConfirmarLimpeza] = useState(false);
  const estado = useModelos();
  const navigate = useNavigate();
  return <AppShell titulo="Configurações" acoes={<span />}><main className="cfg-page">
    <div className="cfg-shell">
      <aside className="cfg-nav"><h1>Configurações</h1><div role="tablist" aria-label="Seções das configurações">
        <button role="tab" aria-selected={secao === 'modelos'} onClick={() => setSecao('modelos')}>Modelos de IA</button>
        <button role="tab" aria-selected={secao === 'conta'} onClick={() => setSecao('conta')}>Conta</button>
        <button role="tab" aria-selected={secao === 'aparencia'} onClick={() => setSecao('aparencia')}>Aparência</button>
      </div></aside>
      <section className="cfg-main">
        {secao === 'modelos' ? <><header className="cfg-heading"><h2>Modelos de IA</h2><p>Conecte os provedores que a Sora e seus agentes podem usar. Você escolhe o modelo padrão e pode personalizar cada agente.</p></header>
          <div className="cfg-provider-grid">{PROVEDORES_MODELO.map(p => <ProviderCard key={p.id} provedor={p} configuracao={estado.provedores[p.id]} />)}</div>
          <ModelDefaults estado={estado} />
          <section className="cfg-security"><h3>Segurança das suas chaves</h3><p>Suas chaves ficam salvas apenas neste dispositivo. Em produção, elas serão guardadas com criptografia no servidor.</p><button type="button" className="cfg-button cfg-button-danger" onClick={() => { if (window.confirm('Apagar todas as chaves salvas neste navegador?')) apagarTodasAsChaves(); }}>Apagar todas as chaves</button></section>
        </> : secao === 'conta' ? <><header className="cfg-heading"><h2>Conta</h2><p>Gerencie os dados da sua conta e do seu plano.</p></header><section className="cfg-account"><div><h3>Dados da Sora</h3><p>Apague projetos, conversas e agentes criados neste navegador. As conexões de modelos não serão alteradas.</p></div><button type="button" className="cfg-button cfg-button-danger" onClick={() => setConfirmarLimpeza(true)}>Apagar todos os dados</button></section></> : <><header className="cfg-heading"><h2>Aparência</h2><p>Personalize como a Sora aparece para você.</p></header><div className="cfg-placeholder">Esta seção estará disponível em breve.</div></>}
      </section>
    </div>
    <Modal open={confirmarLimpeza} onClose={() => setConfirmarLimpeza(false)} title="Apagar todos os dados?" description="Esta ação não pode ser desfeita." size="sm" footer={<div className="cfg-modal-actions"><button type="button" className="cfg-button" onClick={() => setConfirmarLimpeza(false)}>Cancelar</button><button type="button" className="cfg-button cfg-button-danger-solid" onClick={() => { limparTudo(); setConfirmarLimpeza(false); navigate('/'); }}>Apagar todos os dados</button></div>}><p className="cfg-modal-copy">Todos os projetos, chats e agentes serão removidos deste navegador.</p></Modal>
  </main></AppShell>;
}

