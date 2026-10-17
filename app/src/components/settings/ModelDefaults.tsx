import { useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import {
  definirPadraoNovosAgentes, definirPadraoSora, definirPrioridade, modelosAtivos,
  nomeAmigavelDoModelo, type EscolhaModelo, type EstadoModelos, type PrioridadeModelo, type ProvedorModeloId,
} from '../../state/modelos';

const encode = (x: EscolhaModelo | null) => x ? `${x.provedor}::${x.modelo}` : '';
const decode = (x: string): EscolhaModelo | null => {
  const [provedor, ...partes] = x.split('::');
  return provedor && partes.length ? { provedor: provedor as ProvedorModeloId, modelo: partes.join('::') } : null;
};

export function ModelDefaults({ estado }: { estado: EstadoModelos }) {
  const [retorno, setRetorno] = useState('');
  const opcoes = modelosAtivos(estado).map(({ provedor, modelo, definicao }) => ({
    escolha: { provedor, modelo: modelo.modelo }, label: `${definicao.nome} · ${nomeAmigavelDoModelo(modelo)}`,
  }));
  const mudarPrioridade = async (prioridade: PrioridadeModelo) => {
    setRetorno('');
    try { await definirPrioridade(prioridade); setRetorno('Prioridade atualizada.'); }
    catch (erro) { setRetorno(mensagemDeErro(erro)); }
  };
  return <section className="cfg-defaults">
    <div><span className="cfg-eyebrow">Modelo padrão</span><h2>Quem pensa por padrão</h2><p>Cada agente ainda pode usar um modelo próprio.</p></div>
    <label><span>Sora</span><select value={encode(estado.padraoSora)} onChange={e => definirPadraoSora(decode(e.target.value))}><option value="">Escolher automaticamente</option>{opcoes.map(x => <option key={`s-${encode(x.escolha)}`} value={encode(x.escolha)}>{x.label}</option>)}</select></label>
    <label><span>Novos agentes</span><select value={encode(estado.padraoNovosAgentes)} onChange={e => definirPadraoNovosAgentes(decode(e.target.value))}><option value="">Escolher automaticamente</option>{opcoes.map(x => <option key={`a-${encode(x.escolha)}`} value={encode(x.escolha)}>{x.label}</option>)}</select></label>
    <label><span>Priorizar</span><select value={estado.prioridade} onChange={e => void mudarPrioridade(e.target.value as PrioridadeModelo)}><option value="custo">Menor custo</option><option value="velocidade">Mais velocidade</option><option value="qualidade">Mais qualidade</option></select></label>
    {!opcoes.length && <small>Conecte e ative pelo menos um modelo para definir os padrões.</small>}
    {retorno && <small role="status">{retorno}</small>}
  </section>;
}
