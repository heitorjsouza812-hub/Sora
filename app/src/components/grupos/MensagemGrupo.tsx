import { AnexosResposta } from '../ui/AnexosResposta';
import { useState } from 'react';
import { buscarAutenticado } from '../../api/cliente';
import type { AnexoGrupo, MensagemGrupoApi } from '../../api/grupos';
import { SoraOrb } from '../mascot';
import { Markdown } from '../ui/Markdown';
import { COR_SORA, useAutorDaMensagem } from './useAutorDaMensagem';
import './grupos.css';

// /v1/anexos/{id} exige o token, então o arquivo vira blob e é baixado com o nome que o servidor manda.
export function BotaoAnexo({ anexo }: { anexo: AnexoGrupo }) {
  const [baixando, setBaixando] = useState(false);
  const [falhou, setFalhou] = useState(false);
  const baixar = async () => {
    setBaixando(true); setFalhou(false);
    try {
      const resposta = await buscarAutenticado(`/v1/anexos/${anexo.id}`);
      const disposicao = resposta.headers.get('content-disposition') ?? '';
      const nome = decodeURIComponent(disposicao.match(/filename\*=UTF-8''([^;]+)/i)?.[1] ?? disposicao.match(/filename="?([^";]+)"?/i)?.[1] ?? anexo.nome);
      const url = URL.createObjectURL(await resposta.blob());
      const link = document.createElement('a');
      link.href = url; link.download = nome; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setFalhou(true); }
    finally { setBaixando(false); }
  };
  return <button type="button" className="grp-anexo" onClick={() => void baixar()} disabled={baixando} title={falhou ? 'Não foi possível baixar. Tente de novo.' : 'Baixar arquivo'}>{baixando ? 'Baixando…' : anexo.nome}{falhou && ' · falhou'}</button>;
}

/** Mascote pequeno do autor: o mesmo corpo da Sora, na cor e no movimento do bot. */
export function OrbDoAutor({ cor, movimento, tamanho = 26, trabalhando = false, semente = 0 }: { cor?: string; movimento?: Parameters<typeof SoraOrb>[0]['movimento']; tamanho?: number; trabalhando?: boolean; semente?: number }) {
  return <SoraOrb size={tamanho} color={cor ?? COR_SORA} movimento={movimento} state={trabalhando ? 'working' : 'idle'} glow={false} decorative seed={semente} />;
}

export function MensagemGrupo({ mensagem, todas, soraId, onResponder }: { mensagem: MensagemGrupoApi; todas: MensagemGrupoApi[]; soraId: string | undefined; onResponder: (mensagem: MensagemGrupoApi) => void }) {
  const autor = useAutorDaMensagem(mensagem, soraId);
  const anterior = mensagem.respondeA ? todas.find(item => item.id === mensagem.respondeA) : null;
  const doUsuario = mensagem.autor === 'usuario';
  // Atividade (repasse, "Você parou a tarefa") é uma linha de registro, não uma fala.
  if (mensagem.tipo === 'repasse') return <li className="grp-msg grp-atividade" data-autor={mensagem.autor} data-tipo="repasse" data-chave={mensagem.id}>
    {(autor.bot || autor.ehSora) && <OrbDoAutor cor={autor.cor} movimento={autor.bot?.movimento} tamanho={20} semente={mensagem.sequencia} />}<span>{mensagem.texto}</span>
  </li>;
  return <li className="grp-msg" data-autor={autor.ehSora ? 'sora' : mensagem.autor} data-tipo={mensagem.tipo} data-chave={mensagem.id}>
    {!doUsuario && <header>
      {(autor.bot || autor.ehSora) && <OrbDoAutor cor={autor.cor} movimento={autor.bot?.movimento} semente={mensagem.sequencia} />}
      <b style={{ color: autor.cor }}>{autor.nome}</b>{mensagem.tipo === 'resultado' && <span>entregou</span>}
    </header>}
    {anterior && <span className="grp-resposta">Em resposta a {anterior.texto.slice(0, 80)}</span>}
    {mensagem.texto.trim() && (doUsuario
      ? <p className="grp-corpo grp-corpo-usuario">{mensagem.texto}</p>
      : <div className="grp-corpo"><Markdown texto={mensagem.texto} /></div>)}
    {!!mensagem.anexos.length && <AnexosResposta anexos={mensagem.anexos} />}
    <span className="grp-msg-acoes"><button type="button" onClick={() => onResponder(mensagem)}>Responder</button></span>
  </li>;
}
