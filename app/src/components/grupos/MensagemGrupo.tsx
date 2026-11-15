import { AnexosResposta } from '../ui/AnexosResposta';
import { useState, type CSSProperties, type ReactNode } from 'react';
import { buscarAutenticado } from '../../api/cliente';
import type { AnexoGrupo, MensagemGrupoApi } from '../../api/grupos';
import { SoraOrb } from '../mascot';
import { IconButton, Tooltip, toast } from '../base';
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

const Icone = {
  copiar: <svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>,
  responder: <svg viewBox="0 0 24 24"><path d="M10 7 4 12l6 5" /><path d="M4 12h9a7 7 0 0 1 7 7" /></svg>,
  mais: <svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></svg>,
};

function Acao({ rotulo, icone, onClick }: { rotulo: string; icone: ReactNode; onClick: () => void }) {
  return <Tooltip conteudo={rotulo}><IconButton aria-label={rotulo} icone={icone} tamanho="P" className="msg-acao" onClick={onClick} /></Tooltip>;
}

const copiar = (texto: string) => {
  void navigator.clipboard?.writeText(texto).then(() => toast({ mensagem: 'Copiado', tom: 'sucesso' }), () => toast({ mensagem: 'Não foi possível copiar', tom: 'erro' }));
};

/** Mensagem do grupo com o mesmo desenho do chat 1:1: bolha escura à direita para o usuário, resposta sem caixa;
 *  Copiar e Responder são ações de hover (no celular, pelo "…" ou sempre na última). */
export function MensagemGrupo({ mensagem, todas, soraId, onResponder, ultima = false }: { mensagem: MensagemGrupoApi; todas: MensagemGrupoApi[]; soraId: string | undefined; onResponder: (mensagem: MensagemGrupoApi) => void; ultima?: boolean }) {
  const autor = useAutorDaMensagem(mensagem, soraId);
  const [abertas, setAbertas] = useState(false);
  const anterior = mensagem.respondeA ? todas.find(item => item.id === mensagem.respondeA) : null;
  const doUsuario = mensagem.autor === 'usuario';
  // Atividade (repasse, "Você parou a tarefa") é uma linha de registro, não uma fala.
  if (mensagem.tipo === 'repasse') return <div id={`msg-${mensagem.id}`} data-msg-id={mensagem.id} className="chat-item grp-msg grp-atividade" data-autor={mensagem.autor} data-tipo="repasse" data-chave={mensagem.id}>
    {(autor.bot || autor.ehSora) && <OrbDoAutor cor={autor.cor} movimento={autor.bot?.movimento} tamanho={20} semente={mensagem.sequencia} />}<span>{mensagem.texto}</span>
  </div>;
  const citacao = anterior && <p className="grp-resposta">Em resposta a {anterior.texto.slice(0, 80)}</p>;
  const acoes = <div className="msg-acoes" role="toolbar" aria-label="Ações da mensagem">
    {mensagem.texto.trim() && <Acao rotulo="Copiar" icone={Icone.copiar} onClick={() => copiar(mensagem.texto)} />}
    <Acao rotulo="Responder" icone={Icone.responder} onClick={() => onResponder(mensagem)} />
  </div>;
  const mais = <IconButton className="msg-mais" aria-label="Mais ações" aria-expanded={abertas} tamanho="P" icone={Icone.mais} onClick={() => setAbertas(v => !v)} />;
  const classe = `chat-msg chat-item grp-msg ${doUsuario ? 'is-user' : 'is-assistant'}${abertas ? ' is-acoes-abertas' : ''}${ultima ? ' is-ultima' : ''}`;
  const atributos = { id: `msg-${mensagem.id}`, 'data-msg-id': mensagem.id, 'data-autor': autor.ehSora ? 'sora' : mensagem.autor, 'data-tipo': mensagem.tipo, 'data-chave': mensagem.id };
  if (doUsuario) return <div className={classe} {...atributos}>
    {citacao}
    <div className="user-linha">{acoes}{mais}{mensagem.texto.trim() ? <p className="user-message">{mensagem.texto}</p> : null}</div>
    {!!mensagem.anexos.length && <AnexosResposta anexos={mensagem.anexos} />}
  </div>;
  return <div className={classe} style={autor.cor ? { '--agent': autor.cor } as CSSProperties : undefined} {...atributos}>
    <div className="msg-cabeca">
      {(autor.bot || autor.ehSora) && <OrbDoAutor cor={autor.cor} movimento={autor.bot?.movimento} tamanho={24} semente={mensagem.sequencia} />}
      <strong className="msg-nome">{autor.nome}</strong>{mensagem.tipo === 'resultado' && <span className="msg-rotulo">entregou</span>}
    </div>
    <div className="msg-corpo">
      {citacao}
      {mensagem.texto.trim() && <Markdown texto={mensagem.texto} />}
      {!!mensagem.anexos.length && <AnexosResposta anexos={mensagem.anexos} />}
      <div className="msg-barra">{acoes}{mais}</div>
    </div>
  </div>;
}
