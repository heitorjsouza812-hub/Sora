// Senha nova pelo link do e-mail (§8.2): /redefinir-senha#token=…
// Abre com ou sem login (o GateSessao deixa passar). Trocar a senha encerra todas as sessões da conta,
// então no fim a pessoa entra de novo com a senha nova.
import { useEffect, useState, type FormEvent } from 'react';
import { Button, Input } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { mensagemDeErro } from '../api/cliente';
import { redefinirSenha, SENHA_MINIMA, tokenDoLink } from '../state/sessao';
import '../components/sessao/sessao.css';

function irParaEntrar(): void {
  window.location.assign('/');
}

export default function RedefinirSenha() {
  const [token] = useState(() => tokenDoLink(window.location.hash));
  const [senha, setSenha] = useState('');
  const [repetida, setRepetida] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pronto, setPronto] = useState(false);

  // O token sai da barra de endereço assim que é lido (não fica no histórico nem em print de tela).
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname);
  }, []);

  const curta = senha.length > 0 && senha.length < SENHA_MINIMA;
  const diferentes = repetida.length > 0 && repetida !== senha;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (enviando) return;
    if (senha.length < SENHA_MINIMA) { setErro(`A senha precisa ter pelo menos ${SENHA_MINIMA} caracteres.`); return; }
    if (senha !== repetida) { setErro('As duas senhas precisam ser iguais.'); return; }
    setErro(null);
    setEnviando(true);
    try {
      await redefinirSenha(token, senha);
      setPronto(true);
    } catch (falha) {
      setErro(mensagemDeErro(falha));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <main className="sessao-tela">
      <SoraOrb size={150} state={enviando ? 'thinking' : pronto ? 'done' : 'idle'} seed={0} title={enviando ? 'Sora pensando' : 'Sora'} />
      <h1>{pronto ? 'Senha nova criada' : 'Criar senha nova'}</h1>
      <p className="sessao-sub">{pronto ? 'Todos os aparelhos saíram da conta. Entre de novo com a senha nova.' : 'Depois de salvar, todos os aparelhos saem da conta.'}</p>
      <div className="sessao-cartao">
        {pronto ? (
          <Button variante="primario" tamanho="G" bloco onClick={irParaEntrar}>Entrar</Button>
        ) : !token ? (
          <div className="sessao-confirmacao">
            <p className="sessao-erro" role="alert">Este link está incompleto. Abra o link do e-mail de novo ou peça outro em “Esqueci minha senha”.</p>
            <Button variante="primario" tamanho="G" bloco onClick={irParaEntrar}>Ir para Entrar</Button>
          </div>
        ) : (
          <form onSubmit={enviar} noValidate aria-label="Criar senha nova">
            <Input rotulo="Senha nova" name="senha" type="password" autoComplete="new-password" required minLength={SENHA_MINIMA}
              value={senha} onChange={e => setSenha(e.target.value)} ajuda={`Pelo menos ${SENHA_MINIMA} caracteres.`}
              erro={curta ? `Faltam ${SENHA_MINIMA - senha.length} caracteres.` : undefined} />
            <Input rotulo="Repita a senha nova" name="repetida" type="password" autoComplete="new-password" required
              value={repetida} onChange={e => setRepetida(e.target.value)} erro={diferentes ? 'As senhas estão diferentes.' : undefined} />
            {erro && <p className="sessao-erro" role="alert">{erro}</p>}
            <Button type="submit" variante="primario" tamanho="G" bloco carregando={enviando} disabled={!senha || !repetida}>Salvar senha nova</Button>
            <button type="button" className="sessao-link sessao-link--centro" onClick={irParaEntrar}>Voltar para Entrar</button>
          </form>
        )}
      </div>
    </main>
  );
}
