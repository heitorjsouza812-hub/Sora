import { useNavigate } from 'react-router-dom';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import type { BotResumo } from '../../state/bots';
import { MAX_BOTS, MIN_BOTS } from './regras';
import './grupos.css';



// "Livre" não informa nada: só aparece estado quando o bot está ocupado ou espera o usuário.
const rotuloEstado = (estado: BotResumo['estado']) => estado === 'trabalhando' ? 'Trabalhando' : estado === 'precisa_de_voce' ? 'Precisa de você' : '';

/** Escolha de 2 a 5 bots com contador. Sem bots suficientes, o único caminho é criar um (conversa com a Sora). */
export function SeletorDeBots({ bots, marcados, onAlternar, aoCriarBot }: { bots: BotResumo[]; marcados: string[]; onAlternar: (id: string) => void; aoCriarBot?: () => void }) {
  const navegar = useNavigate();
  const criar = () => { aoCriarBot?.(); navegar('/'); };
  return <>
    <fieldset className="grp-escolha"><legend><span>Escolha de {MIN_BOTS} a {MAX_BOTS} bots</span> <span className="grp-contador" aria-label={`${marcados.length} de ${MAX_BOTS} escolhidos`}>{marcados.length}/{MAX_BOTS}</span></legend>
      {bots.map(bot => {
        const marcado = marcados.includes(bot.id);
        const estado = rotuloEstado(bot.estado);
        return <label key={bot.id} data-marcado={marcado} data-desativado={!marcado && marcados.length >= MAX_BOTS}>
          <input type="checkbox" checked={marcado} disabled={!marcado && marcados.length >= MAX_BOTS} onChange={() => onAlternar(bot.id)} />
          <SoraOrb size={28} color={bot.cor} movimento={bot.movimento} glow={false} decorative seed={bot.nome.length} />
          <span className="grp-bot-texto"><b>{bot.nome}</b><small>{bot.funcao}</small></span>
          {estado && <em>{estado}</em>}
          <i className="grp-marca" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg></i>
        </label>;
      })}
    </fieldset>
    {bots.length < MIN_BOTS && <div className="grp-sem-bots">
      <p className="grp-nota">{bots.length === 0 ? 'Você ainda não tem bots.' : 'Você tem só 1 bot.'} Um grupo reúne de {MIN_BOTS} a {MAX_BOTS} bots; peça à Sora para criar {bots.length === 0 ? 'os primeiros' : 'mais um'}.</p>
      <Button type="button" tamanho="M" variante="primario" onClick={criar}>Criar um bot</Button>
    </div>}
  </>;
}
