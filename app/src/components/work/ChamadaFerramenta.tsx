import { useState } from 'react';
import type { PassoTrabalho, ResultadoPasso } from '../../types';
import { SoraOrb } from '../mascot';
import { AvisoPluginDesconectado, useErroSimulado } from '../erros';
import { ImagensEntrega } from '../ui/ImagensEntrega';
import { PluginMark } from '../ui/PluginMark';
import type { Movimento } from '../../types';
import { duracao, ehPassoNavegador, pluginInfo } from './util';
import { RastroNavegador } from './RastroNavegador';


/** JSON compacto numa linha (ex.: {consulta: "café", limite: 8}). */
function jsonCompacto(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(jsonCompacto).join(', ')}]`;
  if (v && typeof v === 'object') return `{${Object.entries(v).map(([k, x]) => `${k}: ${jsonCompacto(x)}`).join(', ')}}`;
  return typeof v === 'string' ? `"${v}"` : String(v);
}

/** Miniaturas do resultado: só imagens reais (anexo ou URL de imagem). Sem imagem, nada (sem simulação). */
export function Miniaturas({ resultado }: { resultado: ResultadoPasso; cor?: string }) {
  return <ImagensEntrega entrega={{ titulo: resultado.resumo, imagens: resultado.imagens }} className="wk-thumbs" limite={4} compacta />;
}

export function ResultadoResumo({ resultado }: { resultado: ResultadoPasso; cor?: string }) {
  if (!resultado.resumo && !resultado.links?.length && !resultado.imagens?.length) return null; // ex.: passo do navegador que só traz rastro
  return (
    <div className="wk-result">
      <span className="wk-result-sum">{resultado.resumo}</span>
      {resultado.links && resultado.links.length > 0 && (
        <ul className="wk-links">{resultado.links.map(l => <li key={l.titulo}><span>{l.titulo}</span><small>{l.dominio}</small></li>)}</ul>
      )}
      <Miniaturas resultado={resultado} />
    </div>
  );
}

/** Uma chamada de ferramenta: ícone do plugin, ação, parâmetros (expansíveis), estado e resultado. */
export function ChamadaFerramenta({ passo, cor, movimento, agora }: { passo: PassoTrabalho; cor: string; movimento: Movimento; agora: number }) {
  const [aberto, setAberto] = useState(false);
  const p = pluginInfo(passo.ferramenta);
  const executando = passo.status === 'executando';
  const params = passo.parametros ?? {};
  const pluginCaiu = useErroSimulado() === 'plugin' && executando && !!passo.ferramenta;
  return (
    <div className={`wk-tool wk-${passo.status}`}>
      <button type="button" className="wk-tool-head" onClick={() => setAberto(v => !v)} aria-expanded={aberto}>
        <PluginMark nome={passo.ferramenta ?? '?'} cor={p?.hex ?? cor} path={p?.path ?? null} size={22} />
        <span className="wk-tool-main">
          <code>{passo.acao}</code>
          <small>{passo.texto}</small>
        </span>
        <span className="wk-tool-state">
          {executando && <><SoraOrb size={20} color={cor} movimento={movimento} state="working" glow={false} title="Executando" /><span className="shimmer">{duracao(Math.max(0, agora - passo.inicio))}</span></>}
          {passo.status === 'concluido' && <><b className="wk-ok">✓</b>{passo.fim ? duracao(passo.fim - passo.inicio) : ''}</>}
          {passo.status === 'erro' && <b className="wk-err">Erro</b>}
        </span>
        <span className="wk-chevron" aria-hidden="true">{aberto ? '▾' : '▸'}</span>
      </button>
      <div className="wk-params" title={jsonCompacto(params)}>{jsonCompacto(params)}</div>
      {aberto && <pre className="wk-params-full">{JSON.stringify(params, null, 2)}</pre>}
      {pluginCaiu && <AvisoPluginDesconectado plugin={p?.name ?? passo.ferramenta!} />}
      {passo.resultado && <ResultadoResumo resultado={passo.resultado} cor={cor} />}
      {ehPassoNavegador(passo) && <RastroNavegador passo={passo} />}
    </div>
  );
}
