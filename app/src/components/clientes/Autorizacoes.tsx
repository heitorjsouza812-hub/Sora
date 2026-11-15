import { canaisEmpresa, type AutorizacaoEmpresa } from '../../api/canaisEmpresa';
import { useBots } from '../../state/bots';
import { useGrupos } from '../../state/grupos';
import { EstadoConsulta, useAcao, useConsulta } from './comum';

export function Autorizacoes() {
  const bots = useBots(), grupos = useGrupos();
  const consulta = useConsulta('autorizacoes', canaisEmpresa.autorizacoes);
  const { ocupado, erro, executar } = useAcao();
  const alvos = [...bots.map(b => ({ tipo: 'agente' as const, id: b.id, nome: b.nome })), ...grupos.lista.map(g => ({ tipo: 'grupo' as const, id: g.id, nome: g.nome }))];
  const mudar = (alvo_tipo: AutorizacaoEmpresa['alvo_tipo'], alvo_id: string, escopo: AutorizacaoEmpresa['escopos'][number], ligado: boolean) => executar(async () => {
    const anterior = consulta.dados?.find(a => a.alvo_tipo === alvo_tipo && a.alvo_id === alvo_id)?.escopos ?? [];
    await canaisEmpresa.autorizar({ alvo_tipo, alvo_id, escopos: ligado ? [...anterior, escopo] : anterior.filter(e => e !== escopo) });
    consulta.recarregar();
  });
  return <section aria-label="Autorizações"><h2>Quem pode consultar</h2><p className="ce-ajuda">Estas permissões valem para todas as fichas de clientes e para o conhecimento da empresa. Em um grupo autorizado, o acesso do bot vale apenas dentro daquele grupo.</p>
    <EstadoConsulta {...consulta} />{erro && <p role="alert">{erro}</p>}
    {consulta.dados && <fieldset disabled={ocupado || consulta.carregando}>{alvos.map(a => {
      const escopos = consulta.dados?.find(x => x.alvo_tipo === a.tipo && x.alvo_id === a.id)?.escopos ?? [];
      return <section className="ce-faixa" key={`${a.tipo}:${a.id}`} aria-label={`${a.nome} · ${a.tipo === 'grupo' ? 'Grupo' : 'Bot'}`}><h3>{a.nome} · {a.tipo === 'grupo' ? 'Grupo' : 'Bot'}</h3>
        {(['clientes', 'conhecimento'] as const).map(escopo => <label className="ce-check" key={escopo}><input type="checkbox" checked={escopos.includes(escopo)} onChange={e => void mudar(a.tipo, a.id, escopo, e.target.checked)} />{escopo === 'clientes' ? 'Fichas de clientes' : 'Conhecimento da empresa'}</label>)}
      </section>;
    })}{!alvos.length && <p>Seus bots e grupos aparecerão aqui para você autorizar o acesso.</p>}</fieldset>}
  </section>;
}
