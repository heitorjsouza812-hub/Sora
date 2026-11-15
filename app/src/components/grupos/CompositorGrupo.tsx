import { useRef, useState, type KeyboardEvent } from 'react';
import { enviarAnexo } from '../../api/anexos';
import { ErroApi, mensagemDeErro } from '../../api/cliente';
import { lembrarNomeDoAnexo, type MensagemGrupoApi } from '../../api/grupos';
import type { BotResumo } from '../../state/bots';
import { carregarGrupos, enviarMensagemAoGrupo } from '../../state/grupos';
import type { Anexo } from '../anexos';
import { MessageComposer } from '../ui/MessageComposer';
import { OrbDoAutor } from './MensagemGrupo';
import { completarMencao, opcoesDeMencao, type OpcaoMencao } from './mencoes';
import './grupos.css';

/** Campo do grupo: o mesmo compositor do chat 1:1 (Shift+Enter, colar e soltar arquivo, anexos) mais menções com teclado. */
export function CompositorGrupo({ grupoId, botsDoGrupo, resposta, onCancelarResposta, onEnviado, aoSeguirFim }: {
  grupoId: string;
  botsDoGrupo: BotResumo[];
  resposta: MensagemGrupoApi | null;
  onCancelarResposta: () => void;
  onEnviado: () => void;
  aoSeguirFim?: () => void;
}) {
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState('');
  const [indice, setIndice] = useState(0);
  const [fechadoEm, setFechadoEm] = useState<string | null>(null);
  const envolucro = useRef<HTMLDivElement>(null);
  const opcoes = fechadoEm === texto ? [] : opcoesDeMencao(texto, botsDoGrupo);
  const ativo = Math.min(indice, Math.max(0, opcoes.length - 1));

  const mencionar = (opcao: OpcaoMencao) => {
    setTexto(atual => completarMencao(atual, opcao.nome));
    envolucro.current?.querySelector('textarea')?.focus();
  };
  // Em captura, para vir antes do Enter do compositor (que enviaria a mensagem).
  const teclas = (evento: KeyboardEvent<HTMLDivElement>) => {
    if (!opcoes.length || evento.nativeEvent.isComposing) return;
    const tomar = () => { evento.preventDefault(); evento.stopPropagation(); };
    if (evento.key === 'ArrowDown') { tomar(); setIndice((ativo + 1) % opcoes.length); }
    else if (evento.key === 'ArrowUp') { tomar(); setIndice((ativo - 1 + opcoes.length) % opcoes.length); }
    else if (evento.key === 'Enter' || evento.key === 'Tab') { tomar(); mencionar(opcoes[ativo]); }
    else if (evento.key === 'Escape') { tomar(); setFechadoEm(texto); }
  };

  const enviar = async (conteudo: string, anexos: Anexo[]) => {
    setErro('');
    aoSeguirFim?.();
    try {
      const ids: string[] = [];
      for (const anexo of anexos) {
        if (!anexo.arquivo) throw new Error(`O arquivo ${anexo.nome} precisa ser selecionado novamente.`);
        const enviado = await enviarAnexo(anexo.arquivo);
        lembrarNomeDoAnexo(enviado.anexo_id, enviado.nome);
        ids.push(enviado.anexo_id);
      }
      await enviarMensagemAoGrupo(grupoId, { texto: conteudo, respondeA: resposta?.id, anexos: ids });
      onCancelarResposta();
      onEnviado();
    } catch (falha) {
      // O compositor já esvaziou o campo: devolve o texto para o usuário não perder o que escreveu.
      setTexto(atual => atual || conteudo);
      setErro(`${mensagemDeErro(falha)}${anexos.length ? ' Anexe os arquivos de novo.' : ''}`);
      // 409 = o grupo ficou sem bots suficientes: relê a lista para o aviso aparecer.
      if (falha instanceof ErroApi && falha.status === 409) void carregarGrupos(true).catch(() => undefined);
    }
  };

  const abrirMencao = () => {
    setTexto(atual => /(?:^|s)@[^s]*$/.test(atual) ? atual : `${atual}${atual && !/s$/.test(atual) ? ' ' : ''}@`);
    setFechadoEm(null); setIndice(0);
    envolucro.current?.querySelector('textarea')?.focus();
  };

  return <div className="chat-composer grp-envio" ref={envolucro} onKeyDownCapture={teclas}>
    {resposta && <div className="grp-respondendo"><span>Respondendo a {resposta.texto.slice(0, 90)}</span><button type="button" className="grp-icone" onClick={onCancelarResposta}>Cancelar</button></div>}
    {!!opcoes.length && <div className="grp-mencoes" role="listbox" aria-label="Mencionar">
      {opcoes.map((opcao, posicao) => <button type="button" role="option" aria-selected={posicao === ativo} data-ativo={posicao === ativo} key={opcao.id} onMouseDown={evento => evento.preventDefault()} onClick={() => mencionar(opcao)}>
        {opcao.id === 'todos' ? <i className="grp-menc-todos" aria-hidden="true" /> : <OrbDoAutor cor={opcao.cor} tamanho={24} semente={opcao.nome.length} />}
        <span>@{opcao.nome}</span>
      </button>)}
    </div>}
    <MessageComposer placeholder="Mensagem para o grupo…" compact value={texto} onValueChange={valor => { setTexto(valor); setFechadoEm(null); setIndice(0); }} onSend={(conteudo, anexos) => void enviar(conteudo, anexos)}
      acoesDireita={<button type="button" className="icon-button grp-arroba" aria-label="Mencionar um bot" title="Mencionar um bot (@)" onClick={abrirMencao}>@</button>} />
    {erro && <p className="grp-erro" role="alert">{erro}</p>}
  </div>;
}
