import { useState, type FormEvent } from 'react';
import { criarGrupo } from '../../api/grupos';
import { useBots } from '../../state/bots';
import { receberGrupo } from '../../state/grupos';
import { Button, Input } from '../base';
import './grupos.css';

export function NovoGrupo({ aberto, onFechar, onCriado }: { aberto: boolean; onFechar: () => void; onCriado: (grupoId: string) => void }) {
  const bots = useBots();
  const [nome, setNome] = useState('');
  const [membros, setMembros] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  if (!aberto) return null;

  const fechar = () => { setNome(''); setMembros([]); setErro(''); onFechar(); };
  const alternar = (id: string) => setMembros(atuais => atuais.includes(id) ? atuais.filter(item => item !== id) : atuais.length < 5 ? [...atuais, id] : atuais);
  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    if (!nome.trim() || membros.length < 2 || membros.length > 5) return;
    setEnviando(true); setErro('');
    try {
      const grupo = await criarGrupo({ nome: nome.trim(), membros });
      receberGrupo(grupo);
      onCriado(grupo.id);
      fechar();
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : 'Não foi possível criar o grupo.');
    } finally { setEnviando(false); }
  };

  return <div className="grp-modal" role="presentation" onMouseDown={evento => { if (evento.target === evento.currentTarget) fechar(); }}>
    <section className="grp-novo" role="dialog" aria-modal="true" aria-labelledby="novo-grupo-titulo">
      <header><div><span className="grp-sobretitulo">Novo grupo</span><h2 id="novo-grupo-titulo">Reúna seus bots</h2></div><button type="button" className="grp-fechar" aria-label="Fechar" onClick={fechar}>×</button></header>
      <form onSubmit={evento => void enviar(evento)}>
        <Input rotulo="Nome do grupo" value={nome} onChange={evento => setNome(evento.target.value)} placeholder="Ex.: Lançamento do produto" maxLength={80} autoFocus />
        <div className="grp-chefe"><span className="grp-orb grp-orb-sora" aria-hidden="true" /><span><b>Sora</b><small>Chefe de equipe · sempre participa</small></span></div>
        <fieldset className="grp-escolha"><legend>Escolha de 2 a 5 bots <span>{membros.length}/5</span></legend>
          {bots.length === 0 && <p className="grp-nota">Crie pelo menos dois bots conversando com a Sora antes de montar um grupo.</p>}
          {bots.map(bot => <label key={bot.id} data-marcado={membros.includes(bot.id)}>
            <input type="checkbox" checked={membros.includes(bot.id)} disabled={!membros.includes(bot.id) && membros.length >= 5} onChange={() => alternar(bot.id)} />
            <i style={{ background: bot.cor }} aria-hidden="true" />
            <span><b>{bot.nome}</b><small>{bot.funcao}</small></span>
            <em>{bot.estado === 'trabalhando' ? 'Trabalhando' : bot.estado === 'precisa_de_voce' ? 'Precisa de você' : 'Livre'}</em>
          </label>)}
        </fieldset>
        {membros.length > 0 && membros.length < 2 && <p className="grp-erro" role="alert">Escolha mais {2 - membros.length} bot.</p>}
        {erro && <p className="grp-erro" role="alert">{erro}</p>}
        <footer><Button type="button" tamanho="M" variante="secundario" onClick={fechar}>Cancelar</Button><Button type="submit" tamanho="M" variante="primario" disabled={enviando || !nome.trim() || membros.length < 2 || membros.length > 5}>{enviando ? 'Criando…' : 'Criar grupo'}</Button></footer>
      </form>
    </section>
  </div>;
}
