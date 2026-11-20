// Configurações → Conta → Senha (§8.2): troca conferindo a senha atual. Os outros aparelhos saem
// da conta; este continua entrado.
import { useState, type FormEvent } from 'react';
import { Button, toast } from '../base';
import { Modal } from '../overlay';
import { mensagemDeErro } from '../../api/cliente';
import { SENHA_MINIMA, trocarSenha } from '../../state/sessao';

export function TrocarSenha() {
  const [aberto, setAberto] = useState(false);
  const [atual, setAtual] = useState('');
  const [nova, setNova] = useState('');
  const [repetida, setRepetida] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');

  const fechar = () => {
    if (enviando) return;
    setAberto(false); setAtual(''); setNova(''); setRepetida(''); setErro('');
  };

  const enviar = async (e?: FormEvent) => {
    e?.preventDefault();
    if (enviando) return;
    if (nova.length < SENHA_MINIMA) { setErro(`A senha nova precisa ter pelo menos ${SENHA_MINIMA} caracteres.`); return; }
    if (nova !== repetida) { setErro('As duas senhas novas precisam ser iguais.'); return; }
    setErro(''); setEnviando(true);
    try {
      await trocarSenha(atual, nova);
      setEnviando(false);
      setAberto(false); setAtual(''); setNova(''); setRepetida('');
      toast({ mensagem: 'Senha trocada. Os outros aparelhos saíram da conta.', tom: 'sucesso' });
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  };

  return <>
    <section className="cfg-account cfg-account--neutra">
      <div><h3>Senha</h3><p>Troque a senha da conta. Os outros aparelhos saem e precisam entrar de novo.</p></div>
      <Button onClick={() => setAberto(true)}>Trocar senha</Button>
    </section>
    <Modal open={aberto} onClose={fechar} title="Trocar senha" size="sm"
      footer={<div className="cfg-modal-actions"><Button disabled={enviando} onClick={fechar}>Cancelar</Button><Button variante="primario" carregando={enviando} disabled={!atual || !nova || !repetida} onClick={() => { void enviar(); }}>Salvar senha nova</Button></div>}>
      <form className="cfg-senha" onSubmit={e => { void enviar(e); }} noValidate>
        <label className="cfg-delete-account"><span>Senha atual</span><input type="password" value={atual} onChange={e => setAtual(e.target.value)} autoComplete="current-password" /></label>
        <label className="cfg-delete-account"><span>Senha nova</span><input type="password" value={nova} onChange={e => setNova(e.target.value)} autoComplete="new-password" minLength={SENHA_MINIMA} aria-describedby="cfg-senha-ajuda" /><small id="cfg-senha-ajuda" className="cfg-senha__ajuda">Pelo menos {SENHA_MINIMA} caracteres.</small></label>
        <label className="cfg-delete-account"><span>Repita a senha nova</span><input type="password" value={repetida} onChange={e => setRepetida(e.target.value)} autoComplete="new-password" /></label>
        {erro && <p className="cfg-senha__erro" role="alert">{erro}</p>}
        <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
      </form>
    </Modal>
  </>;
}
