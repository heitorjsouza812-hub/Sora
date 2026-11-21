// Página de um bot compartilhado (Onda 3): /compartilhado/:codigo. Abre com ou sem login; "Usar
// este bot" cria uma cópia na conta (sem login, leva antes para Entrar e volta para cá).
import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { mensagemDeErro } from '../api/cliente';
import { importarBotLink, verBotPublico, type BotPublico, type RotinaCompartilhada } from '../api/compartilhar';
import { Button, toast } from '../components/base';
import { SoraOrb } from '../components/mascot';
import { lerAgendamento, DIAS_DA_SEMANA } from '../components/builder/rotinaAmigavel';
import { rotuloFerramenta } from '../data/ferramentas';
import { useSessao } from '../state/sessao';
import { trazerBotImportado } from '../components/compartilhar/trazerBot';
import '../components/compartilhar/compartilhar.css';

function quando(r: RotinaCompartilhada): string {
  if (r.tipo === 'cron') {
    const a = lerAgendamento(r.expressao);
    if (a.frequencia === 'diario') return `Todo dia às ${a.hora}`;
    if (a.frequencia === 'uteis') return `Dias úteis às ${a.hora}`;
    if (a.frequencia === 'semanal') return `${DIAS_DA_SEMANA[a.dia]}, às ${a.hora}`;
    return 'Agenda personalizada';
  }
  const s = Number(r.expressao);
  return s % 86400 === 0 ? `A cada ${s / 86400} dia(s)` : s % 3600 === 0 ? `A cada ${s / 3600} hora(s)` : `A cada ${Math.round(s / 60)} minuto(s)`;
}

export default function Compartilhado() {
  // Sem login, o portão mostra esta página fora das rotas: o código sai do endereço.
  const parametros = useParams();
  const { pathname } = useLocation();
  const codigo = parametros.codigo ?? decodeURIComponent(pathname.slice('/compartilhado/'.length).split('/')[0] ?? '');
  const navegar = useNavigate();
  const sessao = useSessao();
  const [publico, setPublico] = useState<BotPublico | null | undefined>(undefined);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    let vivo = true;
    verBotPublico(codigo).then(p => { if (vivo) setPublico(p); }).catch(e => { if (vivo) { setPublico(null); setErro(mensagemDeErro(e)); } });
    return () => { vivo = false; };
  }, [codigo]);

  const usar = async () => {
    if (sessao.estado !== 'logado') { navegar(`/compartilhado/${encodeURIComponent(codigo)}?entrar=1`); return; }
    setOcupado(true); setErro(null);
    try {
      const copia = await importarBotLink(codigo);
      await trazerBotImportado(copia.agente_id).catch(() => undefined);
      toast({ mensagem: [`${copia.nome} agora é seu.`, ...copia.avisos].join(' '), tom: 'sucesso' });
      navegar(`/bots/${copia.agente_id}`);
    } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); }
  };

  if (publico === undefined) return <main className="bot-publico"><p role="status">Carregando…</p></main>;
  if (!publico) return <main className="bot-publico"><div className="bot-publico-cartao">
    <h1>Link indisponível</h1><p className="bot-publico-erro">{erro ?? 'Este link não existe mais.'}</p>
    <Button onClick={() => navegar('/')}>Ir para a Sora</Button></div></main>;

  const { bot } = publico;
  const ferramentas = [...new Set(bot.ferramentas.map(rotuloFerramenta))];
  return <main className="bot-publico">
    <div className="bot-publico-cartao">
      <header className="bot-publico-topo">
        <SoraOrb size={88} color={bot.cor} movimento={bot.movimento} decorative />
        <div><h1>{bot.nome}</h1><p>{bot.funcao || 'Bot de IA'}</p></div>
      </header>
      {bot.instrucoes && <section><h2>Como ele trabalha</h2><pre>{bot.instrucoes}</pre></section>}
      {ferramentas.length > 0 && <section><h2>Ferramentas</h2><div className="bot-publico-chips">{ferramentas.map(f => <span key={f}>{f}</span>)}</div></section>}
      {bot.rotinas.length > 0 && <section><h2>Rotinas</h2><ul>{bot.rotinas.map(r => <li key={r.titulo}><b>{r.titulo}</b> · {quando(r)}</li>)}</ul></section>}
      {bot.habilidades.length > 0 && <section><h2>Habilidades</h2><ul>{bot.habilidades.map(h => <li key={h.nome}><b>{h.nome}</b> — {h.descricao}</li>)}</ul></section>}
      <div className="bot-publico-acoes">
        <Button variante="primario" carregando={ocupado} onClick={() => void usar()}>{sessao.estado === 'logado' ? 'Usar este bot' : 'Entrar e usar este bot'}</Button>
        <small>Você ganha uma cópia: as rotinas chegam pausadas e nada é publicado sem a sua aprovação.</small>
      </div>
      {erro && <p className="bot-publico-erro" role="alert">{erro}</p>}
    </div>
  </main>;
}
