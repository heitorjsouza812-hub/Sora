// Configurações → Conta → Seus dados (LGPD, portabilidade): baixa um .zip com tudo o que a Sora
// guarda da conta. Pede a senha antes, como apagar a conta.
import { useState, type FormEvent } from 'react';
import { Button, toast } from '../base';
import { Modal } from '../overlay';
import { mensagemDeErro } from '../../api/cliente';
import { baixarMeusDados } from '../../state/sessao';

export function MeusDados() {
  const [aberto, setAberto] = useState(false);
  const [senha, setSenha] = useState('');
  const [baixando, setBaixando] = useState(false);
  const [erro, setErro] = useState('');

  const fechar = () => { if (baixando) return; setAberto(false); setSenha(''); setErro(''); };

  const baixar = async (e?: FormEvent) => {
    e?.preventDefault();
    if (baixando || !senha) return;
    setErro(''); setBaixando(true);
    try {
      await baixarMeusDados(senha);
      setBaixando(false);
      setAberto(false); setSenha('');
      toast({ mensagem: 'Seus dados foram baixados.', tom: 'sucesso' });
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setBaixando(false);
    }
  };

  return <>
    <section className="cfg-account cfg-account--neutra">
      <div><h3>Seus dados</h3><p>Baixe um arquivo .zip com suas conversas, bots, grupos, rotinas, memórias e arquivos. Senhas e chaves de API não saem do servidor.</p></div>
      <Button onClick={() => setAberto(true)}>Baixar meus dados</Button>
    </section>
    <Modal open={aberto} onClose={fechar} title="Baixar meus dados" description="Pode levar alguns segundos se você tiver muitos arquivos." size="sm"
      footer={<div className="cfg-modal-actions"><Button disabled={baixando} onClick={fechar}>Cancelar</Button><Button variante="primario" carregando={baixando} disabled={!senha} onClick={() => { void baixar(); }}>Baixar</Button></div>}>
      <form className="cfg-senha" onSubmit={e => { void baixar(e); }} noValidate>
        <label className="cfg-delete-account"><span>Confirme sua senha</span><input type="password" value={senha} onChange={e => setSenha(e.target.value)} autoComplete="current-password" /></label>
        {erro && <p className="cfg-senha__erro" role="alert">{erro}</p>}
        <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
      </form>
    </Modal>
  </>;
}
