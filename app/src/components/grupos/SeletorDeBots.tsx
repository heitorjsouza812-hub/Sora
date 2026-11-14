import { useNavigate } from 'react-router-dom';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import type { BotResumo } from '../../state/bots';
import './grupos.css';

export const MIN_BOTS = 2;
export const MAX_BOTS = 5;

const rotuloEstado = (estado: BotResumo['estado']) => estado === 'trabalhando' ? 'Trabalhando' : estado === 'precisa_de_voce' ? 'Precisa de você' : 'Livre';

/** Escolha de 2 a 5 bots com contador. Sem bots suficientes, o único caminho é criar um (conversa com a Sora). */
export function SeletorDeBots({ bots, marcados, onAlternar, aoCriarBot }: { bots: BotResumo[]; marcados: string[]; onAlternar: (id: string) => void; aoCriarBot?: () => void }) {
  const navegar = useNavigate();
  const criar = () => { aoCriarBot?.(); navegar('/'); };
  return <>
    <fieldset className="grp-escolha"><legend>Escolha de {MIN_BOTS} a {MAX_BOTS} bots <span>{marcados.length}/{MAX_BOTS}</span></legend>
      {bots.map(bot => <label key={bot.id} data-marcado={marcados.includes(bot.id)}>
        <input type="checkbox" checked={marcados.includes(bot.id)} disabled={!marcados.includes(bot.id) && marcados.length >= MAX_BOTS} onChange={() => onAlternar(bot.id)} />
        <SoraOrb size={26} color={bot.cor} movimento={bot.movimento} glow={false} decorative seed={bot.nome.length} />
        <span><b>{bot.nome}</b><small>{bot.funcao}</small></span>
        <em>{rotuloEstado(bot.estado)}</em>
      </label>)}
    </fieldset>
    {bots.length < MIN_BOTS && <div className="grp-sem-bots">
      <p className="grp-nota">{bots.length === 0 ? 'Você ainda não tem bots.' : 'Você tem só 1 bot.'} Um grupo reúne de {MIN_BOTS} a {MAX_BOTS} bots; peça à Sora para criar {bots.length === 0 ? 'os primeiros' : 'mais um'}.</p>
      <Button type="button" tamanho="M" variante="primario" onClick={criar}>Criar um bot</Button>
    </div>}
    {marcados.length > 0 && marcados.length < MIN_BOTS && bots.length >= MIN_BOTS && <p className="grp-erro" role="alert">Escolha mais {MIN_BOTS - marcados.length} bot.</p>}
  </>;
}
