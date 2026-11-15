import { useRef, useState, type CSSProperties } from 'react';
import { Button } from '../base';
import { Popover } from '../overlay';
import { OrbDoAutor } from './MensagemGrupo';
import { useMembrosDoGrupo, type SituacaoMembro } from './useMembrosDoGrupo';
import './grupos.css';
import './pagina.css';

const ROTULO_MEMBRO: Record<SituacaoMembro, string> = { trabalhando: 'Trabalhando', parado: 'Parado', livre: 'Livre', precisa_de_voce: 'Precisa de você' };

type Estado = ReturnType<typeof useMembrosDoGrupo>;

/** Cabeçalho do grupo: pilha de orbs (Sora primeiro; quem trabalha anima) que abre o painel de membros. */
export function MembrosGrupo({ membros, grupoId, liderId, estado, onAdicionarBots }: { membros: string[]; grupoId: string; liderId?: string | null; estado?: Estado; onAdicionarBots?: () => void }) {
  const proprio = useMembrosDoGrupo(membros, grupoId, liderId);
  const { noGrupo, situacaoDe, ultimoPassoDe, parar, retomar, parando, erro } = estado ?? proprio;
  const ancora = useRef<HTMLButtonElement>(null);
  const [aberto, setAberto] = useState(false);
  const total = noGrupo.length;
  return <>
    <button ref={ancora} type="button" className="grp-pilha" aria-haspopup="dialog" aria-expanded={aberto} aria-label={`Membros do grupo: Sora e ${total} ${total === 1 ? 'bot' : 'bots'}`} onClick={() => setAberto(valor => !valor)}>
      <OrbDoAutor tamanho={28} semente={3} />
      {noGrupo.slice(0, 5).map(bot => <OrbDoAutor key={bot.id} cor={bot.cor} movimento={bot.movimento} tamanho={28} trabalhando={situacaoDe(bot.id) === 'trabalhando'} semente={bot.nome.length} />)}
    </button>
    <Popover open={aberto} onClose={() => setAberto(false)} anchorRef={ancora} ariaLabel="Membros do grupo" width={320} className="grp-painel-membros">
      <ul className="grp-membros" aria-label="Membros do grupo">
        <li className="grp-membro"><OrbDoAutor tamanho={28} semente={3} /><span><b>Sora</b><small>Chefe de equipe</small></span></li>
        {noGrupo.map(bot => {
          const situacao = situacaoDe(bot.id);
          const ultimo = ultimoPassoDe(bot.id);
          return <li className="grp-membro" key={bot.id} data-estado={situacao}>
            <OrbDoAutor cor={bot.cor} movimento={bot.movimento} tamanho={28} trabalhando={situacao === 'trabalhando'} semente={bot.nome.length} />
            <span><b style={{ color: bot.cor }}>{bot.nome}</b><small>{ROTULO_MEMBRO[situacao]}</small>{ultimo && situacao === 'trabalhando' && <small className="grp-ultimo" title={ultimo}>{ultimo}</small>}</span>
            {situacao === 'parado' && <Button tamanho="P" variante="secundario" aria-label={`Retomar ${bot.nome}`} disabled={parando === bot.id} onClick={() => void retomar(bot.id)}>{parando === bot.id ? 'Retomando…' : 'Retomar'}</Button>}
            {situacao === 'trabalhando' && <Button tamanho="P" variante="secundario" aria-label={`Parar ${bot.nome}`} disabled={parando === bot.id} onClick={() => void parar(bot.id)}>{parando === bot.id ? 'Parando…' : '■ Parar'}</Button>}
          </li>;
        })}
      </ul>
      {onAdicionarBots && <div className="grp-painel-rodape"><Button tamanho="P" variante="fantasma" onClick={() => { setAberto(false); onAdicionarBots(); }}>Adicionar bots</Button></div>}
      {erro && <p className="grp-erro grp-erro-faixa" role="alert">{erro}</p>}
    </Popover>
  </>;
}

/** Faixa de trabalho: uma pílula por bot que está trabalhando, com Parar à mão. Some quando ninguém trabalha. */
export function FaixaDeTrabalho({ estado }: { estado: Estado }) {
  const { noGrupo, situacaoDe, ultimoPassoDe, parar, parando, erro } = estado;
  const ativos = noGrupo.filter(bot => situacaoDe(bot.id) === 'trabalhando');
  if (!ativos.length && !erro) return null;
  return <div className="grp-faixas">
    {ativos.map(bot => {
      const ultimo = ultimoPassoDe(bot.id);
      return <div className="grp-faixa" key={bot.id} style={{ '--cor': bot.cor } as CSSProperties} role="status">
        <i aria-hidden="true" /><b>{bot.nome}</b><span title={ultimo}>trabalhando{ultimo ? ` · ${ultimo}` : ''}</span>
        <Button tamanho="P" variante="secundario" aria-label={`Parar ${bot.nome}`} disabled={parando === bot.id} onClick={() => void parar(bot.id)}>{parando === bot.id ? 'Parando…' : '■ Parar'}</Button>
      </div>;
    })}
    {erro && <p className="grp-erro" role="alert">{erro}</p>}
  </div>;
}
