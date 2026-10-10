import { definirPadraoNovosAgentes, definirPadraoSora, type EscolhaModelo, type EstadoModelos, type ProvedorModeloId, PROVEDORES_MODELO } from '../../state/modelos';

const encode = (x: EscolhaModelo | null) => x ? `${x.provedor}::${x.modelo}` : '';
const decode = (x: string): EscolhaModelo | null => { const [provedor, modelo] = x.split('::'); return provedor && modelo ? { provedor: provedor as ProvedorModeloId, modelo } : null; };

export function ModelDefaults({ estado }: { estado: EstadoModelos }) {
  const opcoes = PROVEDORES_MODELO.flatMap(p => estado.provedores[p.id].status === 'conectado'
    ? estado.provedores[p.id].modelos.filter(m => m.habilitado && m.id.trim()).map(m => ({ escolha: { provedor: p.id, modelo: m.id }, label: `${p.nome} · ${m.id}` })) : []);
  return <section className="cfg-defaults">
    <div><span className="cfg-eyebrow">Modelo padrão</span><h2>Quem pensa por padrão</h2><p>Cada agente ainda pode usar um modelo próprio.</p></div>
    <label><span>Sora</span><select value={encode(estado.padraoSora)} onChange={e => definirPadraoSora(decode(e.target.value))}><option value="">Escolher automaticamente</option>{opcoes.map(x => <option key={`s-${encode(x.escolha)}`} value={encode(x.escolha)}>{x.label}</option>)}</select></label>
    <label><span>Novos agentes</span><select value={encode(estado.padraoNovosAgentes)} onChange={e => definirPadraoNovosAgentes(decode(e.target.value))}><option value="">Escolher automaticamente</option>{opcoes.map(x => <option key={`a-${encode(x.escolha)}`} value={encode(x.escolha)}>{x.label}</option>)}</select></label>
    {!opcoes.length && <small>Conecte e habilite pelo menos um modelo para definir os padrões.</small>}
  </section>;
}

