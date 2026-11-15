// Qual navegador o bot usa (Vitral-6): só dele, compartilhado, sem login ou um perfil nomeado.
// Troca na hora pelo PUT /v1/agentes/{id}/navegador; sem `agenteId` (bot ainda não salvo) só explica o padrão.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { definirNavegadorDoBot, type TipoNavegadorBot } from '../../api/telas';
import * as pecas from '../../state/pecas';
import './formComputador.css';

const EXPLICACAO: Record<string, string> = {
  agente: 'O bot tem um navegador só dele, com os próprios logins. Outros bots não enxergam nada dele.',
  compartilhado: 'O bot usa o mesmo navegador e os mesmos logins que os outros bots que escolheram “Compartilhado”.',
  efemero: 'Cada visita abre uma aba nova, sem login salvo.',
  perfil: 'O bot usa um perfil com login salvo que você criou em Configurações. Sites novos pedem a sua aprovação.',
};
const valorDe = (n: pecas.NavegadorDoAgente) => n.tipo === 'perfil' && n.perfil_id ? `perfil:${n.perfil_id}` : n.tipo;

export function NavegadorDoBot({ agenteId }: { agenteId?: string }) {
  const [atual, setAtual] = useState<pecas.NavegadorDoAgente | null>(null);
  const [perfis, setPerfis] = useState<pecas.PerfilNavegador[]>([]);
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  useEffect(() => {
    if (!agenteId) return; let vivo = true;
    Promise.all([pecas.lerNavegadorDoAgente(agenteId), pecas.listarPerfisNavegador()])
      .then(([n, p]) => { if (vivo) { setAtual(n); setPerfis(p.filter(x => x.tipo === 'nomeado')); } })
      .catch(e => { if (vivo) setErro(mensagemDeErro(e)); });
    return () => { vivo = false; };
  }, [agenteId]);
  if (!agenteId) return <p className="wk-cfg-nota">Todo bot novo nasce com um navegador só dele. Você pode trocar depois de salvar.</p>;
  const trocar = async (valor: string) => {
    setSalvando(true); setErro('');
    try {
      setAtual(valor.startsWith('perfil:') ? await definirNavegadorDoBot(agenteId, 'perfil', valor.slice(7)) : await definirNavegadorDoBot(agenteId, valor as TipoNavegadorBot));
    } catch (e) { setErro(mensagemDeErro(e)); } finally { setSalvando(false); }
  };
  return (
    <label className="bld-wide">
      <span>Navegador do bot</span>
      <select value={atual ? valorDe(atual) : 'agente'} disabled={!atual || salvando} onChange={e => void trocar(e.target.value)} aria-label="Navegador do bot">
        <option value="agente">Só deste bot</option>
        <option value="compartilhado">Compartilhado</option>
        <option value="efemero">Sem login (aba descartável)</option>
        {perfis.map(p => <option key={p.perfil_id} value={`perfil:${p.perfil_id}`}>{p.nome}</option>)}
        {atual?.tipo === 'perfil' && atual.perfil_id && !perfis.some(p => p.perfil_id === atual.perfil_id) && <option value={`perfil:${atual.perfil_id}`}>{atual.perfil_nome ?? 'Perfil'}</option>}
      </select>
      <small>{EXPLICACAO[atual?.tipo ?? 'agente']}</small>
      {erro && <small className="wk-nav-erro" role="alert">{erro}</small>}
    </label>
  );
}
