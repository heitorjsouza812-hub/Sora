// Entrar / Criar conta (etapa 2, regra 4). Sem login, toda rota mostra esta tela.
// A Sora fica no centro, como na tela do 1º prompt; enquanto o pedido vai ao servidor ela pensa.
import { useState, type FormEvent } from 'react';
import { Button, Input } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { mensagemDeErro } from '../api/cliente';
import { cadastrar, entrar, SENHA_MINIMA, useSessao } from '../state/sessao';
import '../components/sessao/sessao.css';

type Aba = 'entrar' | 'cadastrar';

function conviteDaUrl(): string {
  try { return new URLSearchParams(window.location.search).get('convite') ?? ''; } catch { return ''; }
}

export default function Entrar() {
  const { erro: erroAbertura } = useSessao();
  const [aba, setAba] = useState<Aba>(() => (conviteDaUrl() ? 'cadastrar' : 'entrar'));
  const [nome, setNome] = useState('');
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [convite, setConvite] = useState(conviteDaUrl);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ouvindo, setOuvindo] = useState(false);

  const senhaCurta = aba === 'cadastrar' && senha.length > 0 && senha.length < SENHA_MINIMA;

  const trocar = (nova: Aba) => { setAba(nova); setErro(null); };

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (enviando) return;
    if (aba === 'cadastrar' && senha.length < SENHA_MINIMA) { setErro(`A senha precisa ter pelo menos ${SENHA_MINIMA} caracteres.`); return; }
    setErro(null);
    setEnviando(true);
    try {
      if (aba === 'entrar') await entrar(email, senha);
      else await cadastrar({ nome, email, senha, convite });
    } catch (falha) {
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  };

  const avisoTopo = erro ?? erroAbertura ?? null;

  return (
    <main className="sessao-tela" onFocus={() => setOuvindo(true)} onBlur={() => setOuvindo(false)}>
      <SoraOrb size={150} state={enviando ? 'thinking' : ouvindo ? 'listening' : 'idle'} lookAt={ouvindo ? { x: 0, y: 0.85 } : null} seed={0}
        title={enviando ? 'Sora pensando' : 'Sora'} />
      <h1>{aba === 'entrar' ? 'Entrar na Sora' : 'Criar sua conta'}</h1>
      <p className="sessao-sub">Sua ideia. Seus agentes. Tudo em uma conversa.</p>
      <div className="sessao-cartao">
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
          {aba === 'cadastrar' && <Input rotulo="Código de convite" name="convite" autoComplete="off" value={convite} onChange={e => setConvite(e.target.value)}
            ajuda="A Sora está em acesso antecipado: use o código que você recebeu." />}
          {avisoTopo && <p className="sessao-erro" role="alert">{avisoTopo}</p>}
          <Button type="submit" variante="primario" tamanho="G" bloco carregando={enviando}
            disabled={!email.trim() || !senha || (aba === 'cadastrar' && !nome.trim())}>
            {aba === 'entrar' ? 'Entrar' : 'Criar conta'}
          </Button>
        </form>
      </div>
      <p className="sessao-nota">Nada é publicado sem a sua aprovação.</p>
    </main>
  );
}
