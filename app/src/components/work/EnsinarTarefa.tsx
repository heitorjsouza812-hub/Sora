// "Ensinar" (Onda 3): com a aba assumida, você faz a tarefa e a Sora anota os passos (sem senha e
// sem dado pessoal). Ao concluir, o rascunho da habilidade abre para você ler, ajustar e salvar.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { cancelarEnsino, comecarAEnsinar, concluirEnsino, verGravacao, type Gravacao, type RascunhoHabilidade } from '../../api/ensinar';
import { criarHabilidade } from '../../state/pecas';
import { Button, Input, Textarea, toast } from '../base';
import { Modal } from '../overlay';

export function EnsinarTarefa({ abaId, assumida }: { abaId: string; assumida: boolean }) {
  const [gravacao, setGravacao] = useState<Gravacao>({ gravando: false, passos: [] });
  const [objetivo, setObjetivo] = useState('');
  const [rascunho, setRascunho] = useState<RascunhoHabilidade | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');

  // gravação que já estava ligada (a tela foi recarregada no meio)
  useEffect(() => {
    let vivo = true;
    void verGravacao(abaId).then(g => { if (vivo && g.gravando) setGravacao(g); }).catch(() => undefined);
    return () => { vivo = false; };
  }, [abaId]);

  // os passos chegam do worker: relê a cada 2 s enquanto grava
  useEffect(() => {
    if (!gravacao.gravando) return;
    let vivo = true;
    const t = setInterval(() => { void verGravacao(abaId).then(g => { if (vivo) setGravacao(g); }).catch(() => undefined); }, 2000);
    return () => { vivo = false; clearInterval(t); };
  }, [abaId, gravacao.gravando]);

  const agir = async (f: () => Promise<void>) => {
    setOcupado(true); setErro('');
    try { await f(); } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const salvar = () => agir(async () => {
    if (!rascunho) return;
    await criarHabilidade({ nome: rascunho.nome.trim(), descricao: rascunho.descricao.trim(), corpo: rascunho.corpo });
    setRascunho(null);
    toast({ mensagem: 'Habilidade salva. Os bots usam quando você pedir essa tarefa.', tom: 'sucesso' });
  });

  if (!gravacao.gravando && !assumida && !rascunho) return null;
  return <div className="wk-ensinar">
    {!gravacao.gravando ? assumida && <>
      <Button tamanho="M" variante="secundario" disabled={ocupado} onClick={() => void agir(async () => { setGravacao(await comecarAEnsinar(abaId)); setObjetivo(''); })}>Ensinar esta tarefa</Button>
      <small>Faça a tarefa na aba e a Sora anota os passos para virar uma habilidade. Senhas e dados pessoais não são anotados.</small>
    </> : <section className="wk-ensinar-gravando" aria-label="Gravando a tarefa">
      <p role="status"><span className="wk-ensinar-ponto" aria-hidden="true" /> Gravando · {gravacao.passos.length} {gravacao.passos.length === 1 ? 'passo' : 'passos'}</p>
      {gravacao.passos.length > 0 && <ol>{gravacao.passos.slice(-5).map((p, i) => <li key={`${i}-${p}`}>{p}</li>)}</ol>}
      <Input rotulo="O que essa tarefa faz?" value={objetivo} maxLength={300} onChange={e => setObjetivo(e.target.value)} placeholder="Ex.: Emitir a nota fiscal do pedido" />
      <div className="wk-tela-acoes">
        <Button tamanho="M" variante="primario" disabled={ocupado || !objetivo.trim()} onClick={() => void agir(async () => { setRascunho(await concluirEnsino(abaId, objetivo.trim())); setGravacao({ gravando: false, passos: [] }); })}>Concluir</Button>
        <Button tamanho="M" variante="fantasma" disabled={ocupado} onClick={() => void agir(async () => { await cancelarEnsino(abaId); setGravacao({ gravando: false, passos: [] }); })}>Cancelar</Button>
      </div>
    </section>}
    {erro && <small className="wk-nav-erro" role="alert">{erro}</small>}
    <Modal open={!!rascunho} onClose={() => setRascunho(null)} title="Nova habilidade" size="lg"
      description="Leia os passos antes de salvar: os nomes dos botões vieram da página. Ajuste o que quiser."
      footer={<div className="cfg-modal-actions"><Button disabled={ocupado} onClick={() => setRascunho(null)}>Descartar</Button><Button variante="primario" carregando={ocupado} disabled={!rascunho?.nome.trim()} onClick={() => void salvar()}>Salvar habilidade</Button></div>}>
      {rascunho && <div className="wk-ensinar-rascunho">
        <Input rotulo="Nome" value={rascunho.nome} maxLength={80} onChange={e => setRascunho({ ...rascunho, nome: e.target.value })} />
        <Input rotulo="Quando usar" value={rascunho.descricao} maxLength={300} onChange={e => setRascunho({ ...rascunho, descricao: e.target.value })} />
        <Textarea rotulo="Passo a passo" rows={14} value={rascunho.corpo} onChange={e => setRascunho({ ...rascunho, corpo: e.target.value })} />
      </div>}
    </Modal>
  </div>;
}
