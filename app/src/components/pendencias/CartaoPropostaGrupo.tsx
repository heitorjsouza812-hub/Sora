import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Input } from '../base';
import { mensagemDeErro } from '../../api/cliente';
import { aceitarPropostaGrupo, ajustarPropostaGrupo, recusarPropostaGrupo } from '../../api/grupos';
import { carregarBots } from '../../state/bots';
import { receberGrupo } from '../../state/grupos';
import type { BotDaProposta, PropostaGrupo } from './tipos';
import './pendencias.css';

export function CartaoPropostaGrupo({ proposta, compacto = false }: { proposta: PropostaGrupo; compacto?: boolean }) {
  const [nome, setNome] = useState(proposta.nome);
  const [bots, setBots] = useState<BotDaProposta[]>(proposta.bots);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  const [resolvida, setResolvida] = useState<'aceita' | 'recusada' | null>(null);
  const navegar = useNavigate();
  const selecionados = bots.filter(bot => bot.selecionado);
  const alternar = (indice: number) => setBots(lista => lista.map((bot, atual) => atual === indice ? { ...bot, selecionado: !bot.selecionado } : bot));
  const executar = async (acao: 'aceitar' | 'recusar') => {
    setEnviando(true); setErro('');
    try {
      if (acao === 'aceitar') {
        await ajustarPropostaGrupo(proposta.id, { nome: nome.trim(), bots });
        const grupo = await aceitarPropostaGrupo(proposta.id);
        // Os bots novos nascem só agora: barra lateral e grupo aparecem já, e o grupo abre.
        receberGrupo(grupo);
        void carregarBots().catch(() => undefined);
        setResolvida('aceita');
        if (grupo.id) navegar(`/grupos/${grupo.id}`);
        return;
      }
      await recusarPropostaGrupo(proposta.id);
      setResolvida('recusada');
    } catch (falha) {
      setErro(mensagemDeErro(falha) || 'Não foi possível concluir a proposta.');
    } finally { setEnviando(false); }
  };

  if (resolvida) return <p className="pend-resolvida" role="status">{resolvida === 'aceita' ? 'Grupo criado. A Sora está reunindo os bots.' : 'Proposta recusada. Nenhum bot foi criado.'}</p>;
  return (
    <section className={`pend-card pend-proposta${compacto ? ' pend-compacto' : ''}`} aria-label="Proposta de grupo">
      <header className="pend-cabeca"><span className="pend-sinal" aria-hidden="true" /><strong>A Sora propõe um grupo</strong></header>
      <Input rotulo="Nome do grupo" value={nome} onChange={evento => setNome(evento.target.value)} maxLength={80} disabled={enviando} />
      {proposta.motivo && <p className="pend-texto">{proposta.motivo}</p>}
      <fieldset className="pend-bots"><legend>Bots do grupo</legend>
        {bots.map((bot, indice) => <label key={`${bot.id ?? 'novo'}-${indice}`}>
          <input type="checkbox" checked={bot.selecionado} disabled={enviando} onChange={() => alternar(indice)} />
          <i style={{ background: bot.cor }} aria-hidden="true" />
          <span><b>{bot.nome}</b><small>{bot.funcao} · {bot.novo ? 'novo' : 'já existe'}</small></span>
        </label>)}
      </fieldset>
      <p className="pend-nota">Bots marcados como novos só serão criados depois da sua confirmação.</p>
      <div className="pend-acoes" role="group" aria-label="Decisão da proposta">
        <Button tamanho="M" variante="primario" disabled={enviando || !nome.trim() || selecionados.length < 2 || selecionados.length > 5} onClick={() => void executar('aceitar')}>Montar grupo</Button>
        <Button tamanho="M" variante="perigo" disabled={enviando} onClick={() => void executar('recusar')}>Recusar</Button>
      </div>
      {(selecionados.length < 2 || selecionados.length > 5) && <p className="pend-erro" role="alert">Escolha de 2 a 5 bots.</p>}
      {erro && <p className="pend-erro" role="alert">{erro}</p>}
    </section>
  );
}
