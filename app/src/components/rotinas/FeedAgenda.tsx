// "Assinar no calendário": endereço .ics secreto para o Google Agenda, o Outlook ou o celular
// mostrarem as próximas execuções das rotinas (só título e bot). O endereço só aparece ao gerar.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { desligarFeed, ligarFeed, obterFeed, type Feed } from '../../api/agenda';
import { Button } from '../base';
import './rotinas.css';

export function FeedAgenda() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    obterFeed().then(f => { if (vivo) setFeed(f); }).catch(() => { if (vivo) setFeed({ ligado: false, criado_em: null, url: null }); });
    return () => { vivo = false; };
  }, []);

  const agir = async (f: () => Promise<void>) => {
    setOcupado(true); setAviso(null);
    try { await f(); } catch (e) { setAviso(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const gerar = () => agir(async () => { const f = await ligarFeed(); setFeed(f); setUrl(f.url); });
  const copiar = async () => {
    if (!url) return;
    try { await navigator.clipboard.writeText(url); setAviso('Endereço copiado.'); } catch { setAviso('Selecione o endereço e copie.'); }
  };

  return <section className="feed-agenda" aria-label="Assinar no calendário">
    <div><strong>Assinar no calendário</strong>
      <small>Veja as próximas execuções no Google Agenda, no Outlook ou no celular. O calendário recebe só o título da rotina e o nome do bot.</small></div>
    {url && <div className="gancho-segredo" role="status">
      <small>Guarde este endereço agora: ele não aparece de novo. No Google Agenda: Outras agendas → Do URL.</small>
      <div className="gancho-linha"><code>{url}</code><button type="button" onClick={() => void copiar()}>Copiar</button></div>
    </div>}
    <div className="mem-acoes">
      {!feed?.ligado ? <Button tamanho="P" disabled={ocupado || feed === null} onClick={() => void gerar()}>Gerar endereço</Button> : <>
        <Button tamanho="P" variante="secundario" disabled={ocupado} onClick={() => void gerar()}>Trocar endereço</Button>
        <Button tamanho="P" variante="fantasma" disabled={ocupado} onClick={() => void agir(async () => { await desligarFeed(); setFeed({ ligado: false, criado_em: null, url: null }); setUrl(null); })}>Desligar</Button>
      </>}
    </div>
    {feed?.ligado && !url && <small>Ligado. Para ver o endereço de novo, troque por um novo (o antigo para de funcionar).</small>}
    {aviso && <small role="status">{aviso}</small>}
  </section>;
}
