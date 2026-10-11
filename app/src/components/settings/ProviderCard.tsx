import { useState } from 'react';
import {
  definirModelosDoProvedor, desconectarProvedor, mascararChave, salvarConfiguracao, testarConexao,
  type ConfiguracaoProvedor, type DefinicaoProvedor,
} from '../../state/modelos';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import { ProviderIcon } from './ProviderIcon';

export function ProviderCard({ provedor, configuracao }: { provedor: DefinicaoProvedor; configuracao: ConfiguracaoProvedor }) {
  const [aberto, setAberto] = useState(false);
  const [mostrar, setMostrar] = useState(false);
  const [chave, setChave] = useState('');
  const [urlBase, setUrlBase] = useState(configuracao.urlBase ?? '');
  const [nome, setNome] = useState(configuracao.nome ?? '');
  const [modelos, setModelos] = useState(configuracao.modelos);
  const [testando, setTestando] = useState(false);
  const [retorno, setRetorno] = useState('');
  const [statusLocal, setStatusLocal] = useState(configuracao.status);

  const testar = async () => {
    setTestando(true); setRetorno('');
    const resultado = await testarConexao(provedor.id, { chave: chave || configuracao.chave, urlBase, nome });
    setTestando(false); setStatusLocal(resultado.ok ? 'conectado' : 'erro'); setRetorno(resultado.mensagem);
  };
  const salvar = () => {
    salvarConfiguracao(provedor.id, {
      chave: chave || configuracao.chave, urlBase: urlBase.trim(), nome: nome.trim(), modelos,
      status: statusLocal === 'conectado' ? 'conectado' : configuracao.status,
    });
    setChave(''); setRetorno('Configuração salva neste navegador.');
  };
  const statusTexto = statusLocal === 'conectado' ? 'Conectado' : statusLocal === 'erro' ? 'Erro' : 'Não conectado';

  return <article className="cfg-provider-card" data-open={aberto || undefined}>
    <button type="button" className="cfg-provider-summary" onClick={() => setAberto(x => !x)} aria-expanded={aberto}>
      <ProviderIcon provedor={provedor} />
      <span><strong>{provedor.nome}</strong><small>{provedor.descricao}</small></span>
      <span className="cfg-status" data-status={statusLocal}><i />{statusTexto}</span>
      <span className="cfg-chevron" aria-hidden="true">›</span>
    </button>
    {aberto && <div className="cfg-provider-body">
      <div className="cfg-fields">
        {provedor.pedeNome && <label><span>Nome da conexão</span><input value={nome} onChange={e => setNome(e.target.value)} placeholder="Ex.: Servidor da empresa" /></label>}
        {provedor.pedeUrl && <label><span>URL base</span><input value={urlBase} onChange={e => setUrlBase(e.target.value)} placeholder="https://api.exemplo.com/v1" inputMode="url" /></label>}
        {provedor.pedeChave && <label><span>Chave da API</span><span className="cfg-secret"><input type={mostrar ? 'text' : 'password'} value={chave} onChange={e => setChave(e.target.value)} placeholder={configuracao.chave ? mascararChave(configuracao.chave) : `${provedor.prefixo ?? ''}…`} autoComplete="off" /><button type="button" aria-pressed={mostrar} onClick={() => setMostrar(x => !x)}>{mostrar ? 'Ocultar' : 'Mostrar'}</button></span>{configuracao.chave && <small>Chave salva: {mascararChave(configuracao.chave)}</small>}</label>}
      </div>
      <div className="cfg-model-list"><span className="cfg-eyebrow">Modelos disponíveis</span>{modelos.map((modelo, index) => <div className="cfg-model-row" key={`${modelo.id}-${index}`}>
        <input aria-label={`ID do modelo ${index + 1}`} value={modelo.id} onChange={e => setModelos(xs => xs.map((x, i) => i === index ? { ...x, id: e.target.value } : x))} />
        <label className="cfg-switch"><input type="checkbox" checked={modelo.habilitado} onChange={e => setModelos(xs => xs.map((x, i) => i === index ? { ...x, habilitado: e.target.checked } : x))} /><span /><em>{modelo.habilitado ? 'Habilitado' : 'Desabilitado'}</em></label>
      </div>)}<button type="button" className="cfg-inline" onClick={() => setModelos(x => [...x, { id: '', habilitado: true }])}>+ Adicionar modelo</button></div>
      <div className="cfg-card-feedback" role="status">{testando ? <><SoraOrb size={28} state="thinking" seed={33} decorative />Testando conexão…</> : retorno}</div>
      <footer className="cfg-card-actions">
        {configuracao.status === 'conectado' && <Button className="cfg-btn-perigo" onClick={() => { desconectarProvedor(provedor.id); setStatusLocal('nao-conectado'); setRetorno('Conexão removida.'); }}>Desconectar</Button>}
        <span />
        <Button onClick={testar} disabled={testando}>Testar conexão</Button>
        <Button variante="primario" onClick={() => { definirModelosDoProvedor(provedor.id, modelos); salvar(); }}>Salvar</Button>
      </footer>
    </div>}
  </article>;
}

