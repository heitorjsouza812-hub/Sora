import { useState, type FormEvent } from 'react';
import { criarGrupo } from '../../api/grupos';
import { mensagemDeErro } from '../../api/cliente';
import { useBots } from '../../state/bots';
import { receberGrupo } from '../../state/grupos';
import { Button, Input } from '../base';
import { SoraOrb } from '../mascot';
import { Modal } from '../overlay';
import { SeletorDeBots } from './SeletorDeBots';
import { MAX_BOTS, MIN_BOTS, faltaParaOGrupo } from './regras';
import './grupos.css';

const FORM = 'novo-grupo-form';

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
  const falta = faltaParaOGrupo(membros.length) || (!nome.trim() ? 'Dê um nome ao grupo' : '');
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

  return <Modal open onClose={fechar} title="Novo grupo" className="grp-modal-novo" description={`Reúna de ${MIN_BOTS} a ${MAX_BOTS} bots. A Sora sempre participa como chefe de equipe.`}
    footer={<>
      {!valido && !enviando && <span className="grp-dica" role="status">{falta}</span>}
      <Button type="button" tamanho="M" variante="fantasma" onClick={fechar}>Cancelar</Button>
      <Button type="submit" form={FORM} tamanho="M" variante="primario" disabled={enviando || !valido}>{enviando ? 'Criando…' : 'Criar grupo'}</Button>
    </>}>
    <form id={FORM} className="grp-form-novo" onSubmit={evento => void enviar(evento)}>
      <Input rotulo="Nome do grupo" value={nome} onChange={evento => setNome(evento.target.value)} placeholder="Ex.: Lançamento do produto" maxLength={80} autoFocus />
      <p className="grp-chefe"><SoraOrb size={24} color="#E2ECFF" glow={false} decorative seed={3} /><b>Sora</b><span>Chefe de equipe · sempre participa</span></p>
      <SeletorDeBots bots={bots} marcados={membros} onAlternar={alternar} aoCriarBot={fechar} />
      {erro && <p className="grp-erro" role="alert">{erro}</p>}
    </form>
  </Modal>;
}
