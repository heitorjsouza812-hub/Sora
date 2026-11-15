import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { arquivarGrupo, definirMembrosDoGrupo } from '../../api/grupos';
import { mensagemDeErro } from '../../api/cliente';
import { useBots } from '../../state/bots';
import { receberGrupo, removerGrupo, type GrupoResumo } from '../../state/grupos';
import { Button } from '../base';
import { Modal, Popover } from '../overlay';
import { SeletorDeBots } from './SeletorDeBots';
import { MAX_BOTS, MIN_BOTS, faltaParaOGrupo } from './regras';
import './grupos.css';

/** Adicionar ou tirar bots: o grupo fica sempre com 2 a 5 (a Sora entra sozinha, como chefe). */
export function EditarBotsDoGrupo({ grupo, aberto, onFechar }: { grupo: GrupoResumo; aberto: boolean; onFechar: () => void }) {
  // Aberta de novo, parte sempre do que o grupo tem agora (o conteúdo nasce a cada abertura).
  return aberto ? <ConteudoEditarBots grupo={grupo} onFechar={onFechar} /> : null;
}

function ConteudoEditarBots({ grupo, onFechar }: { grupo: GrupoResumo; onFechar: () => void }) {
  const bots = useBots();
  const lider = grupo.liderId ?? grupo.membros[0];
  const [marcados, setMarcados] = useState<string[]>(() => grupo.membros.filter(id => id !== lider));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState('');
  const alternar = (id: string) => setMarcados(lista => lista.includes(id) ? lista.filter(item => item !== id) : lista.length < MAX_BOTS ? [...lista, id] : lista);
  const valido = marcados.length >= MIN_BOTS && marcados.length <= MAX_BOTS;
  const salvar = async () => {
    if (!valido) return;
    setSalvando(true); setErro('');
    try { receberGrupo(await definirMembrosDoGrupo(grupo.id, marcados)); onFechar(); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setSalvando(false); }
  };
  return <Modal open onClose={onFechar} title="Bots do grupo" description={`Escolha de ${MIN_BOTS} a ${MAX_BOTS} bots. A Sora continua como chefe de equipe.`}
    footer={<>{!valido && <span className="grp-dica" role="status">{faltaParaOGrupo(marcados.length) || 'Escolha no máximo 5 bots'}</span>}<Button tamanho="M" variante="fantasma" onClick={onFechar}>Cancelar</Button><Button tamanho="M" variante="primario" disabled={!valido || salvando} onClick={() => void salvar()}>{salvando ? 'Salvando…' : 'Salvar bots'}</Button></>}>
    <SeletorDeBots bots={bots} marcados={marcados} onAlternar={alternar} aoCriarBot={onFechar} />
    {erro && <p className="grp-erro" role="alert">{erro}</p>}
  </Modal>;
}

function ArquivarGrupo({ grupo, aberto, onFechar }: { grupo: GrupoResumo; aberto: boolean; onFechar: () => void }) {
  const navegar = useNavigate();
  const [arquivando, setArquivando] = useState(false);
  const [erro, setErro] = useState('');
  const arquivar = async () => {
    setArquivando(true); setErro('');
    try { await arquivarGrupo(grupo.id); removerGrupo(grupo.id); onFechar(); navegar('/grupos'); }
    catch (falha) { setErro(mensagemDeErro(falha)); }
    finally { setArquivando(false); }
  };
  return <Modal open={aberto} onClose={onFechar} title="Arquivar este grupo?" description="O grupo sai da barra lateral e os bots param de trabalhar nele. Os bots continuam existindo."
    footer={<><Button tamanho="M" variante="secundario" onClick={onFechar}>Cancelar</Button><Button tamanho="M" variante="perigo" disabled={arquivando} onClick={() => void arquivar()}>{arquivando ? 'Arquivando…' : 'Arquivar grupo'}</Button></>}>
    <p className="grp-nota">{grupo.nome}</p>
    {erro && <p className="grp-erro" role="alert">{erro}</p>}
  </Modal>;
}

/** Menu do grupo: renomear, gerir os bots e arquivar. */
export function MenuDoGrupo({ grupo, onRenomear, onGerirBots }: { grupo: GrupoResumo; onRenomear: () => void; onGerirBots: () => void }) {
  const ancora = useRef<HTMLButtonElement>(null);
  const [menu, setMenu] = useState(false);
  const [arquivar, setArquivar] = useState(false);
  const item = (rotulo: string, acao: () => void, perigo = false) => <button type="button" role="menuitem" className={`grp-menu-item${perigo ? ' is-perigo' : ''}`} onClick={() => { setMenu(false); acao(); }}>{rotulo}</button>;
  return <>
    <button ref={ancora} type="button" className="grp-menu-botao" aria-haspopup="menu" aria-expanded={menu} aria-label="Menu do grupo" onClick={() => setMenu(aberto => !aberto)}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></svg></button>
    <Popover open={menu} onClose={() => setMenu(false)} anchorRef={ancora} role="menu" ariaLabel="Menu do grupo" width={220}>
      {item('Renomear grupo', onRenomear)}
      {item('Gerir bots', onGerirBots)}
      {item('Arquivar grupo', () => setArquivar(true), true)}
    </Popover>
    <ArquivarGrupo grupo={grupo} aberto={arquivar} onFechar={() => setArquivar(false)} />
  </>;
}
