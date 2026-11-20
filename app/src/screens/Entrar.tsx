// Entrar / Criar conta (etapa 2, regra 4). Sem login, toda rota mostra esta tela.
// A Sora fica no centro, como na tela do 1º prompt; enquanto o pedido vai ao servidor ela pensa.
// "Esqueci minha senha" pede o link de senha nova (§8.2): a resposta é a mesma exista a conta ou não.
import { useState, type FormEvent } from 'react';
import { Button, Input } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { mensagemDeErro } from '../api/cliente';
import { cadastrar, entrar, pedirLinkDeSenha, SENHA_MINIMA, useSessao } from '../state/sessao';
import '../components/sessao/sessao.css';

type Aba = 'entrar' | 'cadastrar' | 'esqueci';

function conviteDaUrl(): string {
  try { return new URLSearchParams(window.location.search).get('convite') ?? ''; } catch { return ''; }
}

const TITULOS: Record<Aba, string> = { entrar: 'Entrar na Sora', cadastrar: 'Criar sua conta', esqueci: 'Criar senha nova' };

export default function Entrar() {
  const { erro: erroAbertura } = useSessao();
  const [aba, setAba] = useState<Aba>(() => (conviteDaUrl() ? 'cadastrar' : 'entrar'));
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [convite, setConvite] = useState(conviteDaUrl);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [linkPedido, setLinkPedido] = useState(false);
  const [ouvindo, setOuvindo] = useState(false);

  const senhaCurta = aba === 'cadastrar' && senha.length > 0 && senha.length < SENHA_MINIMA;

  const trocar = (nova: Aba) => { setAba(nova); setErro(null); setLinkPedido(false); };

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (enviando) return;
    if (aba === 'cadastrar' && senha.length < SENHA_MINIMA) { setErro(`A senha precisa ter pelo menos ${SENHA_MINIMA} caracteres.`); return; }
    setErro(null);
    setEnviando(true);
    try {
      if (aba === 'entrar') await entrar(email, senha);
      else if (aba === 'cadastrar') await cadastrar({ nome, email, senha, convite });
      else { await pedirLinkDeSenha(email); setLinkPedido(true); setEnviando(false); }
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  };

  const avisoTopo = erro ?? erroAbertura ?? null;
  const podeEnviar = aba === 'esqueci' ? !!email.trim() : !!email.trim() && !!senha && (aba !== 'cadastrar' || !!nome.trim());

  return (
    <main className="sessao-tela" onFocus={() => setOuvindo(true)} onBlur={() => setOuvindo(false)}>
      <SoraOrb size={150} state={enviando ? 'thinking' : ouvindo ? 'listening' : 'idle'} lookAt={ouvindo ? { x: 0, y: 0.85 } : null} seed={0}
        title={enviando ? 'Sora pensando' : 'Sora'} />
      <h1>{TITULOS[aba]}</h1>
      <p className="sessao-sub">{aba === 'esqueci' ? 'Informe o e-mail da conta: mandamos um link que vale por 30 minutos.' : 'Sua ideia. Seus agentes. Tudo em uma conversa.'}</p>
      <div className="sessao-cartao">
        {aba === 'esqueci' ? (
          linkPedido ? (
            <div className="sessao-confirmacao" role="status">
              <p>Se existir uma conta com <strong>{email.trim()}</strong>, o link chega em alguns minutos. Confira também a caixa de spam.</p>
              <Button variante="primario" tamanho="G" bloco onClick={() => trocar('entrar')}>Voltar para Entrar</Button>
            </div>
          ) : (
            <form id="form-sessao" onSubmit={enviar} noValidate aria-label="Pedir link de senha nova">
              <Input rotulo="E-mail da conta" name="email" type="email" autoComplete="email" inputMode="email" required value={email} onChange={e => setEmail(e.target.value)} />
              {avisoTopo && <p className="sessao-erro" role="alert">{avisoTopo}</p>}
              <Button type="submit" variante="primario" tamanho="G" bloco carregando={enviando} disabled={!podeEnviar}>Enviar link</Button>
              <button type="button" className="sessao-link sessao-link--centro" onClick={() => trocar('entrar')}>Voltar para Entrar</button>
            </form>
          )
        ) : <>
          <div className="sessao-abas" role="tablist" aria-label="Entrar ou criar conta">
            <button type="button" role="tab" id="aba-entrar" aria-controls="form-sessao" aria-selected={aba === 'entrar'} onClick={() => trocar('entrar')}>Entrar</button>
            <button type="button" role="tab" id="aba-cadastrar" aria-controls="form-sessao" aria-selected={aba === 'cadastrar'} onClick={() => trocar('cadastrar')}>Criar conta</button>
          </div>
          <form id="form-sessao" role="tabpanel" aria-labelledby={aba === 'entrar' ? 'aba-entrar' : 'aba-cadastrar'} onSubmit={enviar} noValidate>
            {aba === 'cadastrar' && <Input rotulo="Nome" name="nome" autoComplete="name" required value={nome} onChange={e => setNome(e.target.value)} />}
            <Input rotulo="E-mail" name="email" type="email" autoComplete="email" inputMode="email" required value={email} onChange={e => setEmail(e.target.value)} />
            <Input rotulo="Senha" name="senha" type="password" required minLength={aba === 'cadastrar' ? SENHA_MINIMA : undefined}
              autoComplete={aba === 'entrar' ? 'current-password' : 'new-password'} value={senha} onChange={e => setSenha(e.target.value)}
              ajuda={aba === 'cadastrar' ? `Pelo menos ${SENHA_MINIMA} caracteres.` : undefined}
              erro={senhaCurta ? `Faltam ${SENHA_MINIMA - senha.length} caracteres.` : undefined} />
            {aba === 'entrar' && <button type="button" className="sessao-link" onClick={() => trocar('esqueci')}>Esqueci minha senha</button>}
            {aba === 'cadastrar' && <Input rotulo="Código de convite" name="convite" autoComplete="off" value={convite} onChange={e => setConvite(e.target.value)}
              ajuda="A Sora está em acesso antecipado: use o código que você recebeu." />}
            {avisoTopo && <p className="sessao-erro" role="alert">{avisoTopo}</p>}
            <Button type="submit" variante="primario" tamanho="G" bloco carregando={enviando} disabled={!podeEnviar}>
              {aba === 'entrar' ? 'Entrar' : 'Criar conta'}
            </Button>
          </form>
        </>}
      </div>
      <p className="sessao-nota">Nada é enviado sem a sua aprovação.</p>
    </main>
  );
}
