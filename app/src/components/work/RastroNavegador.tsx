// Rastro do navegador no painel Trabalho (Leme): o que o agente fez na aba (comando, resultado), a captura
// e o botão "Assumir aba" para o usuário fazer login/captcha. Vem no passo padrão, em `resultado.rastro`.
import { useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { ImagemAnexo } from '../ui/ImagemAnexo';
import type { PassoTrabalho } from '../../types';
import { assumirAba, devolverAba, useEquipe, type AbaNavegador } from '../../state/equipe';
import { Button } from '../base';


/** Captura (PNG anexo): blob autenticado, o mesmo das entregas (ImagemAnexo). */
function Captura({ anexoId, nome }: { anexoId: string; nome: string }) {
  return <ImagemAnexo anexoId={anexoId} alt={`Captura da página: ${nome}`} className="wk-nav-captura" carregando="Carregando captura…" erro="Não foi possível carregar a captura." />;
}

function ControleAba({ aba }: { aba: AbaNavegador }) {
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');
  const agir = async () => { setOcupado(true); setErro(''); try { await (aba.assumida ? devolverAba(aba.id) : assumirAba(aba.id)); } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); } };
  return (
    <div className="wk-nav-aba" data-aba={aba.id}>
      {aba.pedidoDeAjuda && <p className="wk-nav-ajuda" role="status">O agente pediu ajuda: {aba.pedidoDeAjuda}</p>}
      <span className="wk-nav-aba-url" title={aba.url}>{aba.titulo || aba.url}</span>
      <Button tamanho="M" variante={aba.assumida ? 'primario' : 'secundario'} disabled={ocupado} onClick={() => void agir()}>{aba.assumida ? 'Devolver a aba' : 'Assumir aba'}</Button>
      {aba.assumida && <small>Os agentes não mexem nesta aba até você devolver.</small>}
      {erro && <small className="wk-nav-erro" role="alert">{erro}</small>}
    </div>
  );
}

export function RastroNavegador({ passo }: { passo: PassoTrabalho }) {
  const equipe = useEquipe();
  const r = passo.resultado;
  const rastro = r?.rastro;
  const abas = Object.values(equipe.abas).filter(a => a.agenteId === passo.agenteId);
  const argumentos = rastro?.args?.length ? rastro.args.join(' ') : '';
  const mostraAbas = passo.status === 'executando' && abas.length > 0 || abas.some(a => a.assumida || a.pedidoDeAjuda);
  if (!rastro && !r?.titulo && !r?.url && !r?.anexo_id && !mostraAbas) return null; // nada a mostrar ainda
  return (
    <div className="wk-nav">
      {!r?.anexo_id && (r?.titulo || r?.url) && <div className="wk-nav-pagina"><b>{r.titulo || r.url}</b>{r.titulo && r.url && <small title={r.url}>{r.url}</small>}</div>}
      {rastro && (
        <div className={`wk-nav-rastro ${rastro.ok ? '' : 'wk-nav-falha'}`}>
          <code>{rastro.comando}{argumentos ? ` ${argumentos}` : ''}</code>
          <small>{rastro.ok ? 'ok' : 'falhou'}{typeof rastro.duracao_ms === 'number' ? ` · ${rastro.duracao_ms} ms` : ''}{rastro.entrega ? ` · ${rastro.entrega}` : ''}</small>
        </div>
      )}
      {r?.anexo_id && <Captura anexoId={r.anexo_id} nome={r.nome ?? 'captura'} />}
      {mostraAbas ? abas.map(a => <ControleAba key={a.id} aba={a} />) : null}
    </div>
  );
}
