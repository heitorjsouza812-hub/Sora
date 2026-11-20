// Chaves extras de uma conexão (ex.: duas contas grátis da Groq). Quando a chave principal bate no
// limite, a conversa continua no MESMO modelo com a próxima chave, e a troca aparece na linha do tempo.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { adicionarChaveExtra, listarChavesExtras, MAX_CHAVES_EXTRAS, removerChaveExtra, type ChaveExtra } from '../../api/reservas';
import { Button } from '../base';

export function ChavesExtras({ provedorId, prefixo }: { provedorId: string; prefixo?: string }) {
  const [chaves, setChaves] = useState<ChaveExtra[]>([]);
  const [nova, setNova] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [retorno, setRetorno] = useState('');

  useEffect(() => {
    let vivo = true;
    listarChavesExtras(provedorId).then(lista => { if (vivo) setChaves(lista); }).catch(() => { /* a lista aparece na próxima abertura */ });
    return () => { vivo = false; };
  }, [provedorId]);

  const adicionar = async () => {
    if (!nova.trim() || ocupado) return;
    setOcupado(true); setRetorno('');
    try {
      const criada = await adicionarChaveExtra(provedorId, nova);
      setChaves(lista => [...lista, criada]);
      setNova('');
      setRetorno('Chave testada e adicionada.');
    } catch (erro) { setRetorno(mensagemDeErro(erro)); }
    finally { setOcupado(false); }
  };

  const remover = async (id: string) => {
    setOcupado(true); setRetorno('');
    try { await removerChaveExtra(provedorId, id); setChaves(lista => lista.filter(c => c.id !== id)); setRetorno('Chave removida do servidor.'); }
    catch (erro) { setRetorno(mensagemDeErro(erro)); }
    finally { setOcupado(false); }
  };

  const cheio = chaves.length >= MAX_CHAVES_EXTRAS;
  return <div className="cfg-chaves-extras">
    <span className="cfg-eyebrow">Chaves extras</span>
    <small>Quando a chave principal bate no limite do provedor, a Sora continua no mesmo modelo com a próxima chave. Até {MAX_CHAVES_EXTRAS}.</small>
    {chaves.length > 0 && <ul aria-label="Chaves extras guardadas">
      {chaves.map(c => <li key={c.id}><span>{c.chave_final ? `Chave …${c.chave_final}` : 'Chave guardada'}</span>
        <Button variante="fantasma" tamanho="P" disabled={ocupado} onClick={() => { void remover(c.id); }} aria-label={`Remover chave …${c.chave_final ?? ''}`}>Remover</Button></li>)}
    </ul>}
    {!cheio && <form className="cfg-add-modelo" onSubmit={e => { e.preventDefault(); void adicionar(); }}>
      <label><span className="sr-only">Outra chave da API</span><input type="password" value={nova} onChange={e => setNova(e.target.value)} placeholder={`Adicionar outra chave: ${prefixo ?? ''}…`} autoComplete="off" spellCheck={false} disabled={ocupado} /></label>
      <Button type="submit" disabled={ocupado || !nova.trim()}>Testar e adicionar</Button>
    </form>}
    {retorno && <small role="status">{retorno}</small>}
  </div>;
}
