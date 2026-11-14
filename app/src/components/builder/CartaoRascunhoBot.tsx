import { useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { confirmarRascunhoBot, descartarRascunhoBot, type AjustesRascunhoBot } from '../../api/bots';
import { marcarRascunhoDecididoAqui, type RascunhoNoChat } from '../../state/sora';
import { carregarBots } from '../../state/bots';
import { iniciarProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { toast } from '../base';
import './builder.css';

export interface CartaoRascunhoBotProps { rascunho: RascunhoNoChat }

const listaFerramentas = (valor: string) => [...new Set(valor.split(',').map(item => item.trim()).filter(Boolean))];

export function CartaoRascunhoBot({ rascunho }: CartaoRascunhoBotProps) {
  const [ajustes, setAjustes] = useState<AjustesRascunhoBot>({
    nome: rascunho.nome, funcao: rascunho.funcao, cor: rascunho.cor, instrucoes: rascunho.instrucoes,
    ferramentas: [...rascunho.ferramentas], rotina: rascunho.rotina,
  });
  const [salvando, setSalvando] = useState(false);
  const [resolvido, setResolvido] = useState<'criado' | 'descartado' | null>(null);
  const [botId, setBotId] = useState('');
  const [erro, setErro] = useState('');
  const alterar = <K extends keyof AjustesRascunhoBot>(campo: K, valor: AjustesRascunhoBot[K]) => setAjustes(atual => ({ ...atual, [campo]: valor }));

  const confirmar = async () => {
    if (!ajustes.nome?.trim() || !ajustes.funcao?.trim()) { setErro('Preencha o nome e a função do bot.'); return; }
    marcarRascunhoDecididoAqui(rascunho.id);
    setSalvando(true); setErro('');
    try {
      const rotina = ajustes.rotina && (ajustes.rotina.descricao.trim() || ajustes.rotina.agendamento.trim()) ? ajustes.rotina : null;
      const bot = await confirmarRascunhoBot(rascunho.id, { ...ajustes, rotina });
      setBotId(bot.id);
      setResolvido('criado');
      // A barra lateral e a conversa 1:1 usam stores diferentes. Recarregue as duas
      // para o bot confirmado poder ser aberto imediatamente, sem atualizar a página.
      await Promise.all([
        carregarBots().catch(() => undefined),
        iniciarProjetos().catch(() => undefined),
      ]);
      toast({ mensagem: `${bot.nome} foi criado`, tom: 'sucesso' });
    } catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível criar o bot.'); }
    finally { setSalvando(false); }
  };
  const descartar = async () => {
    marcarRascunhoDecididoAqui(rascunho.id);
    setSalvando(true); setErro('');
    try { await descartarRascunhoBot(rascunho.id); setResolvido('descartado'); }
    catch (e) { setErro(e instanceof Error ? e.message : 'Não foi possível descartar o rascunho.'); }
    finally { setSalvando(false); }
  };

  const decisao = resolvido ?? (rascunho.resolucao ? (rascunho.resolucao.status === 'confirmado' ? 'criado' : 'descartado') : null);
  const idDoBot = botId || rascunho.resolucao?.agenteId || '';
  if (decisao) return <article className="bot-draft-card is-resolved" role="status"><strong>{decisao === 'criado' ? 'Bot criado' : 'Rascunho descartado'}</strong><span>{ajustes.nome}</span>{decisao === 'criado' && idDoBot && <Link className="st-btn-ghost" to={`/bots/${idDoBot}`}>Abrir conversa com {ajustes.nome}</Link>}</article>;

  return <article className="bot-draft-card" style={{ '--agent': ajustes.cor } as CSSProperties} aria-label={`Rascunho do bot ${ajustes.nome}`}>
    <header><SoraOrb size={46} color={ajustes.cor || rascunho.cor} movimento="gira" glow={false} decorative seed={19} /><div><span>Rascunho de bot</span><strong>{ajustes.nome || 'Novo bot'}</strong></div></header>
    <p>Confira as seções abaixo. O bot só nasce quando você confirmar.</p>
    <div className="bot-draft-sections">
      <details open><summary>Identidade <span>{ajustes.funcao}</span></summary><div className="bot-draft-grid">
        <label>Nome<input value={ajustes.nome ?? ''} onChange={e => alterar('nome', e.target.value)} /></label>
        <label>Função<input value={ajustes.funcao ?? ''} onChange={e => alterar('funcao', e.target.value)} /></label>
        <label className="bot-draft-color">Cor<input type="color" value={ajustes.cor ?? rascunho.cor} onChange={e => alterar('cor', e.target.value.toUpperCase())} /></label>
      </div></details>
      <details><summary>Instruções <span>{ajustes.instrucoes ? 'Configuradas' : 'A definir'}</span></summary><label><span className="sr-only">Instruções</span><textarea rows={4} value={ajustes.instrucoes ?? ''} onChange={e => alterar('instrucoes', e.target.value)} /></label></details>
      <details><summary>Ferramentas <span>{ajustes.ferramentas?.length ?? 0}</span></summary><label><span className="sr-only">Ferramentas separadas por vírgula</span><input value={(ajustes.ferramentas ?? []).join(', ')} onChange={e => alterar('ferramentas', listaFerramentas(e.target.value))} placeholder="buscar_web, navegador" /></label></details>
      <details><summary>Rotina <span>{ajustes.rotina ? 'Ativa' : 'Sem rotina'}</span></summary><div className="bot-draft-grid">
        <label>Descrição<input value={ajustes.rotina?.descricao ?? ''} onChange={e => alterar('rotina', { descricao: e.target.value, agendamento: ajustes.rotina?.agendamento ?? '', fuso: ajustes.rotina?.fuso ?? Intl.DateTimeFormat().resolvedOptions().timeZone })} /></label>
        <label>Agendamento<input value={ajustes.rotina?.agendamento ?? ''} onChange={e => alterar('rotina', { descricao: ajustes.rotina?.descricao ?? '', agendamento: e.target.value, fuso: ajustes.rotina?.fuso ?? Intl.DateTimeFormat().resolvedOptions().timeZone })} placeholder="0 9 * * 1-5" /></label>
      </div></details>
    </div>
    {erro && <p className="bot-draft-error" role="alert">{erro}</p>}
    <footer><button type="button" className="st-btn-ghost" disabled={salvando} onClick={() => void descartar()}>Descartar</button><button type="button" className="st-btn-primary" disabled={salvando} onClick={() => void confirmar()}>{salvando ? 'Criando…' : 'Criar bot'}</button></footer>
  </article>;
}
