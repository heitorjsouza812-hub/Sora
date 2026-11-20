// Janela "Relatar problema": o usuário conta o que houve; o diagnóstico (versão, tela, erros recentes,
// sem conversas nem dados pessoais) vai junto se ele deixar marcado e dá para ver antes de enviar.
import { useState } from 'react';
import { Button, Textarea, toast } from '../base';
import { Modal } from '../overlay';
import { mensagemDeErro } from '../../api/cliente';
import { enviarRelato } from '../../api/relatos';
import { montarDiagnostico } from '../../diagnostico';
import { fecharRelatarProblema, marcarRelatoEnviado, useRelatarAberto } from './estado';
import './relatos.css';

const MAX_TEXTO = 4000;

export function RelatarProblema() {
  // montada só enquanto aberta: cada abertura começa com o formulário limpo
  return useRelatarAberto() ? <JanelaRelato /> : null;
}

function JanelaRelato() {
  const [texto, setTexto] = useState('');
  const [comDiagnostico, setComDiagnostico] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  // fotografa o diagnóstico ao abrir: o que a pessoa vê é exatamente o que vai
  const [diagnostico] = useState(montarDiagnostico);

  const fechar = () => { if (!enviando) fecharRelatarProblema(); };

  const enviar = async () => {
    if (enviando || !texto.trim()) return;
    setErro(''); setEnviando(true);
    try {
      await enviarRelato(texto, comDiagnostico ? diagnostico : null);
      setEnviando(false);
      fecharRelatarProblema();
      marcarRelatoEnviado();
      toast({ mensagem: 'Relato enviado. Obrigado por avisar!', tom: 'sucesso' });
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  };

  return <Modal open onClose={fechar} title="Relatar problema" description="Conte o que aconteceu. O time da Sora lê cada relato." size="md"
    footer={<div className="cfg-modal-actions"><Button disabled={enviando} onClick={fechar}>Cancelar</Button><Button variante="primario" carregando={enviando} disabled={!texto.trim()} onClick={() => { void enviar(); }}>Enviar relato</Button></div>}>
    <div className="relato">
      <Textarea rotulo="O que aconteceu?" rows={5} maxLength={MAX_TEXTO} value={texto} onChange={e => setTexto(e.target.value)}
        placeholder="Ex.: cliquei em Permitir e o bot parou de responder."
        ajuda="Não escreva senhas nem dados de cartão. Se escrever, eles são escondidos antes de guardar." />
      <label className="relato__opcao">
        <input type="checkbox" checked={comDiagnostico} onChange={e => setComDiagnostico(e.target.checked)} />
        <span><strong>Enviar diagnóstico</strong><small>Versão do app, tela atual, tamanho da janela e os últimos erros. Sem conversas e sem dados pessoais.</small></span>
      </label>
      {comDiagnostico && <details className="relato__detalhes">
        <summary>Ver o que vai junto</summary>
        <pre>{JSON.stringify(diagnostico, null, 2)}</pre>
      </details>}
      {erro && <p className="relato__erro" role="alert">{erro}</p>}
    </div>
  </Modal>;
}
