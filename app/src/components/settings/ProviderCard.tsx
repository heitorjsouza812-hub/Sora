import { Fragment, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import {
  atualizarModelo, atualizarProvedor, CAPACIDADES_DO_MODELO, conectarProvedor, desconectarProvedor, useModelos,
  nomeAmigavelDoModelo, type DefinicaoProvedor, type NivelModelo,
} from '../../state/modelos';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import { ProviderIcon } from './ProviderIcon';

export interface ProviderCardProps {
  provedor: DefinicaoProvedor;
  inicialmenteAberto?: boolean;
  onConectado?: () => void;
}

const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

export function ProviderCard({ provedor, inicialmenteAberto = false, onConectado }: ProviderCardProps) {
  const estado = useModelos();
  const configuracao = estado.provedores[provedor.id];
  const conexao = configuracao.conexao;
  const [aberto, setAberto] = useState(inicialmenteAberto);
  const [mostrar, setMostrar] = useState(false);
  const [chave, setChave] = useState('');
  const [urlBase, setUrlBase] = useState(provedor.baseUrl ?? '');
  const [tetoEditado, setTetoEditado] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [retorno, setRetorno] = useState('');

  const teto = tetoEditado ?? (conexao?.teto_mensal_usd == null ? '' : String(conexao.teto_mensal_usd));
  const urlExibida = conexao?.base_url ?? urlBase;

  const executar = async (acao: () => Promise<void>, sucesso: string) => {
    setOcupado(true); setRetorno('');
    try { await acao(); setChave(''); setRetorno(sucesso); }
    catch (erro) { setRetorno(mensagemDeErro(erro)); }
    finally { setOcupado(false); }
  };

  const conectar = () => executar(async () => {
    await conectarProvedor(provedor.id, { chave, baseUrl: urlBase });
    onConectado?.();
  }, 'API conectada e modelos carregados.');

  const salvar = () => executar(
    () => atualizarProvedor(provedor.id, { chave: chave.trim() || undefined, tetoMensalUsd: teto.trim() ? Number(teto) : null }),
    chave.trim() ? 'Chave testada e configuração atualizada.' : 'Limite mensal atualizado.',
  );

  const [marcando, setMarcando] = useState<Set<string>>(new Set());
  const editarModelo = (id: string, patch: { nivel?: NivelModelo; ativo?: boolean; capacidades?: string[] }) => {
    if (patch.capacidades) setMarcando(s => new Set(s).add(id));
    return executar(() => atualizarModelo(id, patch), 'Modelo atualizado.');
  };

  // Modelo que chegou sem capacidades é de fora do catálogo: o bloco continua na tela enquanto o usuário marca.
  const editavel = (id: string, capacidades: string[]) => !capacidades.length || marcando.has(id);
  const statusTexto = conexao ? 'Conectado' : 'Não conectado';
  return <article className="cfg-provider-card" data-open={aberto || undefined}>
    <button type="button" className="cfg-provider-summary" onClick={() => setAberto(x => !x)} aria-expanded={aberto}>
      <ProviderIcon provedor={provedor} />
      <span><strong>{provedor.nome}</strong><small>{provedor.descricao}</small></span>
      <span className="cfg-status" data-status={configuracao.status}><i />{statusTexto}</span>
      <span className="cfg-chevron" aria-hidden="true">›</span>
    </button>
    {aberto && <div className="cfg-provider-body">
      <div className="cfg-fields">
        {provedor.pedeUrl && <label><span>URL base</span><input value={urlExibida} onChange={e => setUrlBase(e.target.value)} placeholder="https://api.exemplo.com/v1" inputMode="url" disabled={!!conexao} /></label>}
        {provedor.pedeChave && <label><span>{conexao ? 'Trocar chave da API' : 'Chave da API'}</span><span className="cfg-secret"><input type={mostrar ? 'text' : 'password'} value={chave} onChange={e => setChave(e.target.value)} placeholder={conexao?.chave_final ? `••••••••${conexao.chave_final}` : `${provedor.prefixo ?? ''}…`} autoComplete="off" /><button type="button" aria-pressed={mostrar} onClick={() => setMostrar(x => !x)}>{mostrar ? 'Ocultar' : 'Mostrar'}</button></span>{conexao?.chave_final && <small>Chave guardada no servidor: …{conexao.chave_final}</small>}</label>}
        {conexao && <label><span>Teto mensal (USD)</span><input type="number" min="0" step="0.01" value={teto} onChange={e => setTetoEditado(e.target.value)} placeholder="Sem teto" /><small>Vazio remove o teto.</small></label>}
        {conexao && <div className="cfg-provider-spend"><span>Gasto neste mês</span><strong>{moeda.format(Number(conexao.gasto_mes_usd))}</strong>{conexao.teto_mensal_usd != null && <small>de {moeda.format(Number(conexao.teto_mensal_usd))}</small>}</div>}
      </div>
      {conexao && <div className="cfg-model-list"><span className="cfg-eyebrow">Modelos disponíveis</span>
        {configuracao.modelos.length ? configuracao.modelos.map(modelo => <Fragment key={modelo.id}><div className="cfg-model-row">
          <span className="cfg-model-name"><strong>{nomeAmigavelDoModelo(modelo)}</strong><small>{modelo.contexto.toLocaleString('pt-BR')} tokens{modelo.capacidades.length ? ` · ${modelo.capacidades.join(', ')}` : ''}</small></span>
          <label><span className="sr-only">Nível de {nomeAmigavelDoModelo(modelo)}</span><select value={modelo.nivel} disabled={ocupado} onChange={e => editarModelo(modelo.id, { nivel: e.target.value as NivelModelo })}><option value="N1">N1</option><option value="N2">N2</option><option value="N3">N3</option><option value="especial">Especial</option></select></label>
          <label className="cfg-switch"><input type="checkbox" checked={modelo.ativo} disabled={ocupado} onChange={e => editarModelo(modelo.id, { ativo: e.target.checked })} /><span /><em>{modelo.ativo ? 'Ativo' : 'Inativo'}</em></label>
        </div>
          {editavel(modelo.id, modelo.capacidades) && <fieldset className="cfg-capacidades" disabled={ocupado}>
            <legend>Modelo fora do catálogo: marque o que ele faz</legend>
            <small>Sem isso a Sora não usa este modelo, porque não sabe se ele aguenta ferramentas e respostas estruturadas.</small>
            <div>{CAPACIDADES_DO_MODELO.map(c => <label key={c.id} className="cfg-capacidade" title={c.ajuda}>
              <input type="checkbox" checked={modelo.capacidades.includes(c.id)} onChange={e => editarModelo(modelo.id, { capacidades: e.target.checked ? [...modelo.capacidades, c.id] : modelo.capacidades.filter(x => x !== c.id) })} />
              <span>{c.rotulo}</span>
            </label>)}</div>
          </fieldset>}
        </Fragment>) : <small className="cfg-empty">Nenhum modelo foi informado por esta API.</small>}
      </div>}
      <div className="cfg-card-feedback" role="status" aria-live="polite">{ocupado ? <><SoraOrb size={28} state="thinking" seed={33} decorative />Falando com o servidor…</> : retorno}</div>
      <footer className="cfg-card-actions">
        {conexao && <Button className="cfg-btn-perigo" disabled={ocupado} onClick={() => executar(() => desconectarProvedor(provedor.id), 'Conexão removida do servidor.')}>Desconectar</Button>}
        <span />
        {conexao ? <Button variante="primario" disabled={ocupado || (!!chave.trim() && chave.trim().length < 4)} onClick={salvar}>Salvar alterações</Button>
          : <Button variante="primario" disabled={ocupado || (provedor.pedeChave && !chave.trim()) || (provedor.pedeUrl && !urlBase.trim())} onClick={conectar}>Testar e conectar</Button>}
      </footer>
    </div>}
  </article>;
}
