import { useState, type FormEvent } from 'react';
import { criarGrupo } from '../../api/grupos';
import { mensagemDeErro } from '../../api/cliente';
import { useBots } from '../../state/bots';
import { receberGrupo } from '../../state/grupos';
import { Button, Input } from '../base';
import { SoraOrb } from '../mascot';
import { MAX_BOTS, MIN_BOTS, SeletorDeBots } from './SeletorDeBots';
import './grupos.css';

export function NovoGrupo({ aberto, onFechar, onCriado }: { aberto: boolean; onFechar: () => void; onCriado: (grupoId: string) => void }) {
  const bots = useBots();
  const [nome, setNome] = useState('');
  const [membros, setMembros] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState('');
  if (!aberto) return null;

  const fechar = () => { setNome(''); setMembros([]); setErro(''); onFechar(); };
  const alternar = (id: string) => setMembros(atuais => atuais.includes(id) ? atuais.filter(item => item !== id) : atuais.length < MAX_BOTS ? [...atuais, id] : atuais);
  const valido = !!nome.trim() && membros.length >= MIN_BOTS && membros.length <= MAX_BOTS;
  const enviar = async (evento: FormEvent) => {
    evento.preventDefault();
    if (!valido) return;
    setEnviando(true); setErro('');
    try {
      const grupo = await criarGrupo({ nome: nome.trim(), membros });
      receberGrupo(grupo);
      onCriado(grupo.id);
      fechar();
    } catch (falha) {
      setErro(mensagemDeErro(falha) || 'Não foi possível criar o grupo.');
    } finally { setEnviando(false); }
  };

  return <div className="grp-modal" role="presentation" onMouseDown={evento => { if (evento.target === evento.currentTarget) fechar(); }}>
    <section className="grp-novo" role="dialog" aria-modal="true" aria-labelledby="novo-grupo-titulo">
      <header><div><span className="grp-sobretitulo">Novo grupo</span><h2 id="novo-grupo-titulo">Reúna seus bots</h2></div><button type="button" className="grp-fechar" aria-label="Fechar" onClick={fechar}>×</button></header>
      <form onSubmit={evento => void enviar(evento)}>
        <Input rotulo="Nome do grupo" value={nome} onChange={evento => setNome(evento.target.value)} placeholder="Ex.: Lançamento do produto" maxLength={80} autoFocus />
        <div className="grp-chefe"><SoraOrb size={30} color="#E2ECFF" glow={false} decorative seed={3} /><span><b>Sora</b><small>Chefe de equipe · sempre participa</small></span></div>
        <SeletorDeBots bots={bots} marcados={membros} onAlternar={alternar} aoCriarBot={fechar} />
        {erro && <p className="grp-erro" role="alert">{erro}</p>}
        <footer><Button type="button" tamanho="M" variante="secundario" onClick={fechar}>Cancelar</Button><Button type="submit" tamanho="M" variante="primario" disabled={enviando || !valido}>{enviando ? 'Criando…' : 'Criar grupo'}</Button></footer>
      </form>
    </section>
  </div>;
}
