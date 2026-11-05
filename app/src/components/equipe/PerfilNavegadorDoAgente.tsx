// Qual perfil do navegador este agente usa (Leme): sem login (aba descartável), compartilhado
// ou um perfil nomeado com login salvo. Troca pelo PUT /v1/agentes/{id}/navegador.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import * as pecas from '../../state/pecas';
import './equipe.css';

const SEM_LOGIN = 'efemero';
const COMPARTILHADO = 'compartilhado';
const valorDe = (n: pecas.NavegadorDoAgente) => n.tipo === 'perfil' && n.perfil_id ? `perfil:${n.perfil_id}` : n.tipo;

export function PerfilNavegadorDoAgente({ agenteId }: { agenteId: string }) {
  const [atual, setAtual] = useState<pecas.NavegadorDoAgente | null>(null);
  const [perfis, setPerfis] = useState<pecas.PerfilNavegador[]>([]);
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    let vivo = true;
    Promise.all([pecas.lerNavegadorDoAgente(agenteId), pecas.listarPerfisNavegador()])
      .then(([n, p]) => { if (vivo) { setAtual(n); setPerfis(p.filter(x => x.tipo === 'nomeado')); } })
      .catch(e => { if (vivo) setErro(mensagemDeErro(e)); });
    return () => { vivo = false; };
  }, [agenteId]);

  const trocar = async (valor: string) => {
    setSalvando(true); setErro('');
    try {
      const novo = valor.startsWith('perfil:') ? await pecas.definirNavegadorDoAgente(agenteId, 'perfil', valor.slice(7))
        : await pecas.definirNavegadorDoAgente(agenteId, valor as typeof SEM_LOGIN | typeof COMPARTILHADO);
      setAtual(novo);
    } catch (e) { setErro(mensagemDeErro(e)); } finally { setSalvando(false); }
  };

  return (
    <section className="eq-navegador" aria-label="Navegador do agente">
      <label>
        <span className="eyebrow tools-label">Navegador</span>
        <select value={atual ? valorDe(atual) : COMPARTILHADO} disabled={!atual || salvando} onChange={e => void trocar(e.target.value)} aria-label="Perfil do navegador deste agente">
          <option value={COMPARTILHADO}>Compartilhado entre os agentes</option>
          <option value={SEM_LOGIN}>Sem login (aba descartável)</option>
          {atual?.tipo === 'agente' && <option value="agente">Exclusivo deste agente</option>}
          {perfis.map(p => <option key={p.perfil_id} value={`perfil:${p.perfil_id}`}>{p.nome}</option>)}
          {atual?.tipo === 'perfil' && atual.perfil_id && !perfis.some(p => p.perfil_id === atual.perfil_id) && <option value={`perfil:${atual.perfil_id}`}>{atual.perfil_nome ?? 'Perfil'}</option>}
        </select>
      </label>
      <p className="eq-nota">{atual?.tipo === SEM_LOGIN ? 'Cada visita abre uma aba nova, sem login salvo e sem pedir aprovação de site.' : 'Num perfil com login, sites novos pedem a sua aprovação antes de abrir.'} Rotinas sempre usam aba sem login.</p>
      {erro && <p className="eq-erro" role="alert">{erro}</p>}
    </section>
  );
}
