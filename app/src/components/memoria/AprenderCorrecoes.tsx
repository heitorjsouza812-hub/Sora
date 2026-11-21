// "Aprender com correções" (Onda 3): a cada N mensagens suas, a Sora relê a conversa com um modelo
// barato e guarda o que você corrigiu ou pediu para valer sempre ("Guardei isto", com Desfazer).
import { useEffect, useState } from 'react';
import { api, mensagemDeErro } from '../../api/cliente';

interface Aprendizado { a_cada: number; opcoes: number[] }

const rotulo = (n: number) => n === 0 ? 'Desligado' : `A cada ${n} mensagens suas`;

export function AprenderCorrecoes() {
  const [estado, setEstado] = useState<Aprendizado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let vivo = true;
    api.get<Aprendizado>('/v1/memorias/aprendizado').then(r => { if (vivo) setEstado(r); }).catch(e => { if (vivo) setErro(mensagemDeErro(e)); });
    return () => { vivo = false; };
  }, []);

  const mudar = async (a_cada: number) => {
    setOcupado(true); setErro(null);
    try { setEstado(await api.put<Aprendizado>('/v1/memorias/aprendizado', { a_cada })); }
    catch (e) { setErro(mensagemDeErro(e)); }
    finally { setOcupado(false); }
  };

  return <div className="pc-form pc-form-coluna aprender">
    <label className="pc-campo-select"><span><strong>Aprender com correções</strong></span>
      <select value={estado?.a_cada ?? ''} disabled={!estado || ocupado} onChange={e => void mudar(Number(e.target.value))}>
        {(estado?.opcoes ?? []).map(n => <option key={n} value={n}>{rotulo(n)}</option>)}
      </select>
    </label>
    <p className="pc-form-hint">A Sora relê a conversa de tempos em tempos e guarda o que você corrigiu ou pediu para valer sempre (ex.: “da próxima vez, use tópicos”). Só conta o que você escreveu, nunca o que o bot ou uma página disse. Usa um pouco da cota do seu modelo; conversas privadas ficam de fora.</p>
    {erro && <p className="pc-erro" role="alert">{erro}</p>}
  </div>;
}
