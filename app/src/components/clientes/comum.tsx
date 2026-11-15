import { useEffect, useRef, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { Button } from '../base';
import { SoraOrb } from '../mascot';

export function useConsulta<T>(chave: string, carregar: (signal: AbortSignal) => Promise<T>): { dados?: T; erro?: string; carregando: boolean; recarregar: () => void } {
  const carregarRef = useRef(carregar); carregarRef.current = carregar;
  const [tentativa, tentar] = useState(0);
  const [estado, definir] = useState<{ chave: string; dados?: T; erro?: string; carregando: boolean }>({ chave, carregando: true });
  useEffect(() => {
    const abort = new AbortController();
    definir({ chave, carregando: true });
    void carregarRef.current(abort.signal).then(dados => {
      if (!abort.signal.aborted) definir({ chave, dados, carregando: false });
    }).catch(erro => { if (!abort.signal.aborted) definir({ chave, erro: mensagemDeErro(erro), carregando: false }); });
    return () => abort.abort();
  }, [chave, tentativa]);
  return { ...(estado.chave === chave ? estado : { carregando: true }), recarregar: () => tentar(n => n + 1) };
}
export function useAcao() {
  const [ocupado, setOcupado] = useState(false), [erro, setErro] = useState('');
  const trava = useRef(false);
  const executar = async (acao: () => Promise<unknown>) => {
    if (trava.current) return;
    trava.current = true; setOcupado(true); setErro('');
    try { await acao(); } catch (e) { setErro(mensagemDeErro(e)); }
    finally { trava.current = false; setOcupado(false); }
  };
  return { ocupado, erro, executar };
}
export function EstadoConsulta({ carregando, erro, recarregar }: { carregando: boolean; erro?: string; recarregar: () => void }) {
  return <>{carregando && <p className="ce-status" role="status"><SoraOrb size={28} state="thinking" decorative />Carregando…</p>}{erro && <div role="alert"><p>{erro}</p><Button onClick={recarregar}>Tentar de novo</Button></div>}</>;
}
export const data = (valor: string | null) => valor ? new Date(valor.length === 10 ? `${valor}T12:00:00` : valor).toLocaleDateString('pt-BR') : 'Sem data';
export const nomeCanal = (canal: string) => canal === 'slack' ? 'Slack' : canal === 'whatsapp' ? 'WhatsApp Business' : canal;
export function Origem({ link, canal, em }: { link?: string | null; canal: string; em?: string | null }) {
  // Links vieram de mensagens externas: nunca aceitar javascript/data/URLs relativas.
  const seguro = link && /^https?:\/\//i.test(link);
  return <span className="ce-meta">{seguro ? <a href={link} target="_blank" rel="noopener noreferrer">Origem no {nomeCanal(canal)}</a> : `Origem: ${nomeCanal(canal)}`}{em ? ` · ${data(em)}` : ''}</span>;
}
export function Paginacao({ pagina, quantidade, onPagina }: { pagina: number; quantidade: number; onPagina: (pagina: number) => void }) {
  return <nav className="ce-acoes" aria-label="Paginação"><Button disabled={!pagina} onClick={() => onPagina(pagina - 1)}>Anterior</Button><span>Página {pagina + 1}</span><Button disabled={quantidade < 50} onClick={() => onPagina(pagina + 1)}>Próxima</Button></nav>;
}
