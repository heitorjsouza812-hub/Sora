import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { Button } from '../components/base';
import { Modal } from '../components/overlay';
import { ModelDefaults, ProviderCard } from '../components/settings';
import '../components/settings/settings.css';
import { apagarTodasAsChaves, PROVEDORES_MODELO, useModelos } from '../state/modelos';
import { limparTudo } from '../state/projetos';
import { renovarCreditos, resumoCreditos, useCreditos } from '../state/creditos';

type Secao = 'modelos' | 'conta' | 'aparencia';
const SECOES: { id: Secao; rotulo: string }[] = [
  { id: 'modelos', rotulo: 'Modelos de IA' },
  { id: 'conta', rotulo: 'Conta' },
  { id: 'aparencia', rotulo: 'Aparência' },
];

export default function Configuracoes() {
  const [params] = useSearchParams();
  const [secao, setSecao] = useState<Secao>(() => SECOES.find(s => s.id === params.get('secao'))?.id ?? 'modelos');
  const creditos = resumoCreditos(useCreditos());
  const [confirmarLimpeza, setConfirmarLimpeza] = useState(false);
  const [confirmarChaves, setConfirmarChaves] = useState(false);
  const estado = useModelos();
  const navigate = useNavigate();
  // setas/Home/End entre as abas (padrão WAI-ARIA de tablist)
  const teclaAba = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = SECOES.findIndex(s => s.id === secao);
    const proximo = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? (i + 1) % SECOES.length
      : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? (i - 1 + SECOES.length) % SECOES.length
      : e.key === 'Home' ? 0 : e.key === 'End' ? SECOES.length - 1 : -1;
    if (proximo < 0) return;
    e.preventDefault();
    setSecao(SECOES[proximo].id);
    e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[proximo]?.focus();
  };
  return <AppShell titulo="Configurações" acoes={<span />}><main className="cfg-page">
    <div className="cfg-shell">
      <aside className="cfg-nav"><h1>Configurações</h1><div role="tablist" aria-label="Seções das configurações" aria-orientation="vertical" onKeyDown={teclaAba}>
        {SECOES.map(s => <button key={s.id} id={`cfg-aba-${s.id}`} role="tab" aria-selected={secao === s.id} aria-controls="cfg-painel" tabIndex={secao === s.id ? 0 : -1} onClick={() => setSecao(s.id)}>{s.rotulo}</button>)}
      </div></aside>
      <section className="cfg-main" id="cfg-painel" role="tabpanel" aria-labelledby={`cfg-aba-${secao}`}>
        {secao === 'modelos' ? <><header className="cfg-heading"><h2>Modelos de IA</h2><p>Conecte os provedores que a Sora e seus agentes podem usar. Você escolhe o modelo padrão e pode personalizar cada agente.</p></header>
          <div className="cfg-provider-grid">{PROVEDORES_MODELO.map(p => <ProviderCard key={p.id} provedor={p} configuracao={estado.provedores[p.id]} />)}</div>
          <ModelDefaults estado={estado} />
          <section className="cfg-security"><h3>Segurança das suas chaves</h3><p>Suas chaves ficam salvas apenas neste dispositivo. Em produção, elas serão guardadas com criptografia no servidor.</p><Button className="cfg-btn-perigo" onClick={() => setConfirmarChaves(true)}>Apagar todas as chaves</Button></section>
        </> : secao === 'conta' ? <><header className="cfg-heading"><h2>Conta</h2><p>Gerencie os dados da sua conta e do seu plano.</p></header><section className="cfg-plano" aria-labelledby="cfg-plano-titulo"><div className="cfg-plano__topo"><div><span className="cfg-eyebrow">Plano atual</span><h3 id="cfg-plano-titulo">Plano Pro</h3></div><strong>{creditos.restantes.toLocaleString('pt-BR')} de {creditos.limite.toLocaleString('pt-BR')} créditos</strong></div><progress className="cfg-plano__barra" max={creditos.limite} value={creditos.restantes} aria-label="Créditos restantes" /><p>{creditos.esgotado ? 'Seus créditos acabaram. Os agentes voltam a trabalhar quando o ciclo renovar ou quando você mudar de plano.' : 'Cada passo concluído por um agente usa créditos. O saldo renova todo mês.'}</p><ul className="cfg-planos"><li><strong>Grátis</strong><span>300 créditos/mês</span></li><li data-atual><strong>Pro</strong><span>2.000 créditos/mês</span><small>Seu plano</small></li><li><strong>Empresa</strong><span>Créditos sob medida</span></li></ul><Button onClick={renovarCreditos}>Renovar créditos agora (simulação)</Button></section><section className="cfg-account"><div><h3>Dados da Sora</h3><p>Apague projetos, conversas e agentes criados neste navegador. As conexões de modelos não serão alteradas.</p></div><Button className="cfg-btn-perigo" onClick={() => setConfirmarLimpeza(true)}>Apagar todos os dados</Button></section></> : <><header className="cfg-heading"><h2>Aparência</h2><p>Personalize como a Sora aparece para você.</p></header><div className="cfg-placeholder">Esta seção estará disponível em breve.</div></>}
      </section>
    </div>
    <Modal open={confirmarLimpeza} onClose={() => setConfirmarLimpeza(false)} title="Apagar todos os dados?" description="Esta ação não pode ser desfeita." size="sm" footer={<div className="cfg-modal-actions"><Button onClick={() => setConfirmarLimpeza(false)}>Cancelar</Button><Button variante="perigo" onClick={() => { limparTudo(); setConfirmarLimpeza(false); navigate('/'); }}>Apagar todos os dados</Button></div>}><p className="cfg-modal-copy">Todos os projetos, chats e agentes serão removidos deste navegador.</p></Modal>
    <Modal open={confirmarChaves} onClose={() => setConfirmarChaves(false)} title="Apagar todas as chaves?" description="As conexões com os provedores serão removidas." size="sm" footer={<div className="cfg-modal-actions"><Button onClick={() => setConfirmarChaves(false)}>Cancelar</Button><Button variante="perigo" onClick={() => { apagarTodasAsChaves(); setConfirmarChaves(false); }}>Apagar chaves</Button></div>}><p className="cfg-modal-copy">Todas as chaves salvas neste navegador serão apagadas. Seus projetos e agentes continuam.</p></Modal>
  </main></AppShell>;
}
