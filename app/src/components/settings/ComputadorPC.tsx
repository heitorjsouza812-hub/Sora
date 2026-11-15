// Configurações → Computador (C3, Vela-3): quais bots podem usar o mouse e o teclado deste PC.
// Desligado por padrão, ligado por bot, só no app de desktop. As regras de segurança moram no
// servidor e na ponte Rust; esta tela só liga/desliga e mostra quem está usando o computador.
import { useEffect, useState } from 'react';
import { Button } from '../base';
import { api, mensagemDeErro } from '../../api/cliente';
import { useBots } from '../../state/bots';
import { alternarBotNoPc, reconectarPontePc, usePontePc } from '../../desktop/computadorPc';
import { pcParar } from '../../desktop/ponte';
import './pecas.css';

interface EstadoServidor { conectado: boolean; dispositivo: string | null; vez: { agente_id: string; nome: string } | null }

const FERRAMENTAS_DO_COMPUTADOR = ['computador_observar', 'computador_agir'];

export function ComputadorPC() {
  const ponte = usePontePc();
  const bots = useBots();
  const [servidor, setServidor] = useState<EstadoServidor | null>(null);
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState<string | null>(null);

  useEffect(() => {
    if (ponte.disponivel) return;
    let vivo = true;
    void api.get<EstadoServidor>('/v1/computador-pc/estado').then(e => { if (vivo) setServidor(e); }).catch(() => {});
    return () => { vivo = false; };
  }, [ponte.disponivel]);

  const alternar = async (agenteId: string, ligado: boolean) => {
    setOcupado(agenteId);
    setErro('');
    try { await alternarBotNoPc(agenteId, ligado); } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(null); }
  };

  const local = ponte.local;
  const ligados = new Set(local?.autorizados ?? []);
  const controlando = local?.controlando;

  return <>
    <header className="cfg-heading">
      <h2>Computador</h2>
      <p>Deixe um bot usar o mouse e o teclado deste computador, pelo app de desktop. Fica desligado até você ligar, bot por bot.</p>
    </header>
    <ul className="pc-lista" aria-label="Como funciona">
      <li><span><strong>Você continua no controle</strong><small>Enquanto um bot usa o computador, a tela ganha uma borda na cor dele e um botão Parar{local?.atalho_parar ? ` (ou ${local.atalho_parar})` : ''}. Se você mexer no mouse ou no teclado, ele pausa na hora e pede para continuar.</small></span></li>
      <li><span><strong>Um bot por vez</strong><small>Os outros esperam a vez. Na primeira ação em cada programa, a Sora pergunta antes: permitir uma vez, sempre nesse programa ou recusar.</small></span></li>
      <li><span><strong>O que fica de fora</strong><small>Senhas e campos de senha, gerenciadores de senha, segurança do Windows, UAC, terminais e a própria Sora. Rotinas sem você por perto nunca usam o computador, e o texto digitado não fica guardado.</small></span></li>
    </ul>

    {!ponte.disponivel ? <section className="cfg-ilha" aria-label="Disponibilidade">
      <p className="pc-vazio">Disponível só no app de desktop da Sora para Windows. Abra o app no computador para ligar os bots.</p>
      {servidor && <p role="status">{servidor.conectado ? `App de desktop conectado agora${servidor.dispositivo ? ` (${servidor.dispositivo})` : ''}.` : 'Nenhum app de desktop conectado nesta conta agora.'}{servidor.vez ? ` ${servidor.vez.nome} está usando o computador.` : ''}</p>}
    </section> : <section className="cfg-ilha" aria-label="Controle deste computador">
      {local && !local.windows && <p className="pc-vazio">O controle do computador só funciona no Windows.</p>}
      <p role="status">
        {ponte.substituida ? 'Outro computador entrou nesta conta e assumiu o controle.' : ponte.conectado ? 'Este computador está conectado à Sora.' : 'Conectando este computador à Sora…'}
        {ponte.erro && !ponte.conectado ? ` ${ponte.erro}` : ''}
      </p>
      {ponte.substituida && <div className="cfg-ilha__acoes"><Button tamanho="M" onClick={reconectarPontePc}>Usar este computador</Button></div>}
      {controlando && <div className="pc-aba" role="status" aria-live="polite">
        <p><strong>{controlando.nome}</strong> {local?.pausado ? 'pausou porque você usou o computador. Responda o cartão "Precisa de você" para continuar.' : 'está usando o seu computador.'}</p>
        <span className="pc-acoes"><Button tamanho="M" variante="perigo" onClick={() => void pcParar().catch(() => {})}>Parar</Button></span>
      </div>}
      {erro && <p className="pc-erro" role="alert">{erro}</p>}
      {!bots.length ? <p className="pc-vazio">Você ainda não tem bots. Peça à Sora para criar um.</p> :
        <ul className="pc-lista" aria-label="Bots que podem usar este computador">
          {bots.map(bot => {
            const ligado = ligados.has(bot.id);
            const temFerramenta = FERRAMENTAS_DO_COMPUTADOR.every(f => bot.ferramentas.includes(f));
            return <li key={bot.id} data-ativa={ligado ? 'true' : 'false'}>
              <span>
                <strong><span aria-hidden="true" style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: bot.cor, marginRight: 8 }} />{bot.nome}</strong>
                <small>{bot.funcao || 'Bot'}{!temFerramenta ? ' · Este bot ainda não tem a ferramenta Computador: peça à Sora para incluí-la.' : ''}</small>
              </span>
              <label className="cfg-switch">
                <input type="checkbox" role="switch" aria-label={`${bot.nome} pode usar este computador`} checked={ligado} disabled={!local || ocupado === bot.id} onChange={e => void alternar(bot.id, e.target.checked)} />
                <span aria-hidden="true" /><em>{ligado ? 'Pode usar' : 'Desligado'}</em>
              </label>
            </li>;
          })}
        </ul>}
    </section>}
  </>;
}

export default ComputadorPC;
