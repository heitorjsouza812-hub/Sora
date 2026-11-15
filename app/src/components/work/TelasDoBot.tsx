// Telas ao vivo do bot no painel Trabalho (Vitral-6): navegador (com "Assumir a aba") e computador próprio.
// Simples de reestilizar: classes `.wk-tela*` (telas.css), sem cor fixa além da do bot (`--agent`).
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { ehErroApi, mensagemDeErro } from '../../api/cliente';
import * as telas from '../../api/telas';
import { assumirAba, carregarAbas, devolverAba, useEquipe } from '../../state/equipe';
import { useTelas } from '../../state/telas';
import { Button } from '../base';
import { Modal } from '../overlay';
import './telas.css';

const OCIOSO_MS = 90_000;

/** "agora", "há 5 s", "há 2 min". */
function tempoDesde(desde: number | null, agora: number): string {
  if (desde === null) return '';
  const s = Math.max(0, Math.round((agora - desde) / 1000));
  return s < 2 ? 'agora' : s < 60 ? `há ${s} s` : `há ${Math.floor(s / 60)} min`;
}
function useRelogio(ativo = true) {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => { if (!ativo) return; const t = setInterval(() => setAgora(Date.now()), 1000); return () => clearInterval(t); }, [ativo]);
  return agora;
}

/** Busca uma imagem autenticada (blob); revoga ao sair. Falha (404) = sem imagem. `buscar` nulo = não busca. */
function useBlob(buscar: ((s: AbortSignal) => Promise<string>) | null, chave: string): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null); if (!buscar) return;
    const ac = new AbortController(); let objeto: string | null = null;
    buscar(ac.signal).then(u => { if (ac.signal.aborted) URL.revokeObjectURL(u); else { objeto = u; setUrl(u); } }).catch(() => undefined);
    return () => { ac.abort(); if (objeto) URL.revokeObjectURL(objeto); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, !!buscar]);
  return url;
}

// ── Superfície da aba (interativa quando assumida) ─────────────────────────────────────

/** A imagem da aba. Com `ativo` (aba assumida) clique, teclado e roda viram comandos na aba. O texto digitado
 *  passa por uma ref só até o envio (200 ms): nunca vai para estado, tela, log nem armazenamento. */
function SuperficieAba({ abaId, src, alt, ativo, largura, altura }: { abaId: string; src: string; alt: string; ativo: boolean; largura: number; altura: number }) {
  const img = useRef<HTMLImageElement>(null);
  const caixa = useRef<HTMLDivElement>(null);
  const fila = useRef<Promise<unknown>>(Promise.resolve());
  const buffer = useRef('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const roda = useRef<{ dy: number; t: ReturnType<typeof setTimeout> | null }>({ dy: 0, t: null });
  const geracao = useRef(0);
  const [erro, setErro] = useState('');
  const enviar = (f: () => Promise<unknown>) => {
    const g = geracao.current;
    fila.current = fila.current.then(() => g === geracao.current ? f() : undefined).then(() => setErro(''), e => setErro(ehErroApi(e) && e.status === 409 ? 'A aba não está mais com você.' : mensagemDeErro(e)));
  };
  const escala = () => {
    const el = img.current; const r = el?.getBoundingClientRect();
    const w = el?.naturalWidth || largura, h = el?.naturalHeight || altura;
    return { r, w, h, fx: r && r.width ? w / r.width : 1, fy: r && r.height ? h / r.height : 1 };
  };
  const soltarTexto = () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    const t = buffer.current; buffer.current = ''; if (t) enviar(() => telas.digitarNaAba(abaId, t));
  };
  useEffect(() => () => { geracao.current++; if (timer.current) clearTimeout(timer.current); timer.current = null; if (roda.current.t) clearTimeout(roda.current.t); roda.current = { dy: 0, t: null }; buffer.current = ''; }, [ativo, abaId]);
  useEffect(() => { // a roda precisa de preventDefault, que o React registra como passivo
    const el = caixa.current; if (!ativo || !el) return;
    const aoRolar = (ev: WheelEvent) => {
      ev.preventDefault();
      roda.current.dy += ev.deltaY * escala().fy;
      if (!roda.current.t) roda.current.t = setTimeout(() => { const dy = roda.current.dy; roda.current = { dy: 0, t: null }; if (dy) enviar(() => telas.rolarAba(abaId, dy)); }, 150);
    };
    el.addEventListener('wheel', aoRolar, { passive: false });
    return () => el.removeEventListener('wheel', aoRolar);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ativo, abaId]);
  const aoClicar = (ev: React.MouseEvent) => {
    if (!ativo) return; caixa.current?.focus();
    const { r, w, h, fx, fy } = escala(); if (!r) return;
    soltarTexto();
    enviar(() => telas.clicarNaAba(abaId, (ev.clientX - r.left) * fx, (ev.clientY - r.top) * fy, w, h));
  };
  const aoTeclar = (ev: React.KeyboardEvent) => {
    if (!ativo || ev.nativeEvent.isComposing || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if ((telas.TECLAS_ABA as readonly string[]).includes(ev.key)) { ev.preventDefault(); ev.stopPropagation(); soltarTexto(); enviar(() => telas.teclaNaAba(abaId, ev.key)); return; }
    if (ev.key.length === 1) {
      ev.preventDefault(); buffer.current += ev.key;
      if (buffer.current.length >= 500) soltarTexto(); else if (!timer.current) timer.current = setTimeout(soltarTexto, 200);
    }
  };
  return (
    <div className="wk-tela-caixa" ref={caixa} tabIndex={ativo ? 0 : -1} onKeyDown={aoTeclar} data-ativo={ativo || undefined}
      aria-label={ativo ? 'Aba do bot. Clique, digite e role aqui para controlar.' : undefined}>
      <img ref={img} className="wk-tela-img" src={src} alt={alt} draggable={false} onClick={aoClicar} style={{ cursor: ativo ? 'crosshair' : undefined }} />
      {ativo && <label className="wk-tela-digitacao">Digitar na aba
        <input type="password" aria-label="Digitar na aba" autoComplete="off" autoCorrect="off" spellCheck={false}
          onKeyDown={e => { e.stopPropagation(); if ((telas.TECLAS_ABA as readonly string[]).includes(e.key) && e.key !== 'Tab') { e.preventDefault(); soltarTexto(); enviar(() => telas.teclaNaAba(abaId, e.key)); } }}
          onChange={e => { const texto = e.currentTarget.value; e.currentTarget.value = ''; if (texto) enviar(() => telas.digitarNaAba(abaId, texto)); }} />
        <small>O texto é enviado diretamente e não fica guardado neste campo.</small>
      </label>}
      {erro && <small className="wk-nav-erro" role="alert">{erro}</small>}
    </div>
  );
}

// ── Navegador ────────────────────────────────────────────────────────────────────────

function TelaNavegador({ agenteId, cor }: { agenteId: string; cor?: string }) {
  const equipe = useEquipe();
  const quadro = useTelas().navegador[agenteId];
  const abas = Object.values(equipe.abas).filter(a => a.agenteId === agenteId);
  const aba = abas.find(a => a.id === quadro?.abaId) ?? abas.find(a => a.assumida) ?? abas[abas.length - 1];
  const abaId = aba?.id ?? quadro?.abaId ?? '';
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');
  const [devolvida, setDevolvida] = useState(false);
  const [ampliada, setAmpliada] = useState(false);
  const agora = useRelogio(!!abaId);
  const assumida = aba?.assumida === true;
  const imagemDoQuadro = quadro && quadro.abaId === abaId ? quadro.imagem : null;
  const inicial = useBlob(abaId && !imagemDoQuadro ? s => telas.capturaDaAba(abaId, s) : null, abaId);
  const cheia = useBlob(ampliada && abaId ? s => telas.capturaDaAba(abaId, s) : null, `${abaId}:${ampliada}:${quadro?.recebidoEm}`);
  const imagem = imagemDoQuadro ?? inicial;

  // "estou olhando": a marca dura 12 s no servidor; repete a cada 8 s, só com a página visível
  const temAba = !!abaId;
  useEffect(() => {
    if (!temAba) return;
    const pingar = () => { if (document.visibilityState === 'visible') void telas.assistirNavegador(agenteId).catch(() => undefined); };
    pingar(); const t = setInterval(pingar, 8000);
    document.addEventListener('visibilitychange', pingar);
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', pingar); };
  }, [agenteId, temAba]);

  if (!abaId) return null;
  const largura = quadro?.largura || 1280, altura = quadro?.altura || 800;
  const url = quadro?.url || aba?.url || '';
  const agir = async () => {
    setOcupado(true); setErro('');
    try { if (assumida) { await devolverAba(abaId); setDevolvida(true); } else { await assumirAba(abaId); setDevolvida(false); } }
    catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const alt = `Tela ao vivo do navegador${aba?.titulo ? `: ${aba.titulo}` : ''}`;
  const grande = cheia ?? imagem;
  return (
    <section className={`wk-tela ${assumida ? 'is-controle' : ''}`} aria-label="Navegador ao vivo" data-aba={abaId}>
      <header className="wk-tela-cab">
        <strong>Navegador</strong>
        <span className="wk-tela-url" title={url}>{aba?.titulo || url || 'Aba aberta'}{url && aba?.titulo ? <small>{url}</small> : null}</span>
        <small className="wk-tela-idade">{quadro ? `atualizado ${tempoDesde(quadro.recebidoEm, agora)}` : 'aguardando imagem'}</small>
      </header>
      {assumida && <p className="wk-tela-aviso" role="status">Você está no controle — o bot espera.</p>}
      {quadro?.aviso && <p className="wk-tela-aviso wk-tela-atencao" role="status">{quadro.aviso}</p>}
      {imagem
        ? <SuperficieAba key={abaId} abaId={abaId} src={imagem} alt={alt} ativo={assumida && !ampliada && !ocupado} largura={largura} altura={altura} />
        : <div className="wk-tela-vazio">Ainda não há imagem desta aba. Ela aparece aqui assim que o navegador mandar o primeiro quadro.</div>}
      <div className="wk-tela-acoes">
        <Button tamanho="M" variante={assumida ? 'primario' : 'secundario'} disabled={ocupado} onClick={() => void agir()}>{assumida ? 'Devolver ao bot' : 'Assumir a aba'}</Button>
        <Button tamanho="M" variante="fantasma" disabled={!imagem} onClick={() => setAmpliada(true)}>Ampliar</Button>
      </div>
      {devolvida && !assumida && <small className="wk-tela-nota" role="status">Devolvido. O bot retoma na próxima ação dele.</small>}
      {erro && <small className="wk-nav-erro" role="alert">{erro}</small>}
      <Modal open={ampliada} onClose={() => setAmpliada(false)} title="Navegador do bot" size="lg" className="wk-tela-modal">
        <div className={`wk-tela-cheia ${assumida ? 'is-controle' : ''}`} style={{ '--agent': cor } as CSSProperties}>
          {assumida && <p className="wk-tela-aviso" role="status">Você está no controle — o bot espera.</p>}
          {grande && <SuperficieAba key={abaId} abaId={abaId} src={grande} alt={`${alt} (ampliada)`} ativo={assumida && !ocupado} largura={largura} altura={altura} />}
        </div>
      </Modal>
    </section>
  );
}

// ── Computador ───────────────────────────────────────────────────────────────────────

function TelaComputador({ agenteId, usa }: { agenteId: string; usa: boolean }) {
  const quadro = useTelas().computador[agenteId];
  const [api, setApi] = useState<telas.EstadoComputadorApi | null>(null);
  const [erro, setErro] = useState('');
  const [confirma, setConfirma] = useState(false);
  const [desligando, setDesligando] = useState(false);
  const [pedidoDesligar, setPedidoDesligar] = useState(false);
  const [ampliada, setAmpliada] = useState(false);
  const agora = useRelogio(true);
  useEffect(() => {
    if (!usa) return; let vivo = true;
    telas.estadoDoComputador(agenteId).then(e => { if (vivo) setApi(e); }).catch(e => { if (vivo) setErro(mensagemDeErro(e)); });
    return () => { vivo = false; };
  }, [agenteId, usa]);
  const ligado = quadro ? quadro.ligado : api?.ligado === true;
  if (!ligado && (pedidoDesligar || ampliada)) { setPedidoDesligar(false); setAmpliada(false); } // ao desligar, zera (ajuste durante a renderização)
  const inicial = useBlob(ligado && !quadro?.imagem ? s => telas.capturaDoComputador(agenteId, s) : null, `${agenteId}:${ligado}`);
  const cheia = useBlob(ampliada && ligado ? s => telas.capturaDoComputador(agenteId, s) : null, `${agenteId}:${ampliada}:${quadro?.recebidoEm}`);
  const imagem = quadro?.imagem ?? inicial;
  if (!usa && !quadro) return null;
  const desde = quadro?.recebidoEm ?? (api?.atualizado_em ? Date.parse(api.atualizado_em) : null);
  const estado = !ligado ? 'Desligado' : !imagem ? 'Ligando' : desde !== null && agora - desde > OCIOSO_MS ? 'Ocioso' : 'Ligado';
  const janela = quadro?.janelaAtiva ?? api?.janela_ativa ?? null;
  const acao = quadro?.acao ?? api?.acao ?? null;
  const grande = cheia ?? imagem;
  const desligar = async () => {
    setDesligando(true); setErro('');
    try {
      await telas.desligarComputador(agenteId);
      setPedidoDesligar(true); setConfirma(false);
    } catch (e) { setErro(mensagemDeErro(e)); } finally { setDesligando(false); }
  };
  return (
    <section className="wk-tela wk-tela-pc" aria-label="Computador do bot" data-estado={estado.toLowerCase()}>
      <header className="wk-tela-cab">
        <strong>Computador</strong>
        <span className="wk-tela-url">{janela ?? (ligado ? 'Sem janela ativa' : '')}</span>
        <small className="wk-tela-idade">{estado}{desde !== null && ligado ? ` · ${tempoDesde(desde, agora)}` : ''}</small>
      </header>
      {api && !api.disponivel && !ligado
        ? <div className="wk-tela-vazio">O computador próprio está desligado neste servidor.</div>
        : imagem
          ? <img className="wk-tela-img" src={imagem} alt={`Tela do computador do bot${janela ? `: ${janela}` : ''}`} />
          : <div className="wk-tela-vazio">{estado === 'Ligando' ? 'Ligando o computador do bot…' : 'O computador do bot está desligado. Ele liga sozinho quando o bot precisar.'}</div>}
      {pedidoDesligar && ligado && <small role="status">Desligamento solicitado. Aguardando o computador confirmar.</small>}
      {acao && ligado && <small className="wk-tela-nota">{acao}</small>}
      {ligado && quadro?.mudou === false && <small className="wk-tela-nota wk-tela-atencao">A tela não mudou depois da última ação.</small>}
      {ligado && (
        <div className="wk-tela-acoes">
          <Button tamanho="M" variante="fantasma" disabled={!imagem} onClick={() => setAmpliada(true)}>Ampliar</Button>
          <Button tamanho="M" variante="perigo" disabled={pedidoDesligar} onClick={() => setConfirma(true)}>Desligar computador</Button>
        </div>
      )}
      {erro && <small className="wk-nav-erro" role="alert">{erro}</small>}
      <Modal open={confirma} onClose={() => { if (!desligando) setConfirma(false); }} title="Desligar o computador do bot?" size="sm"
        footer={<div className="cfg-modal-actions"><Button disabled={desligando} onClick={() => setConfirma(false)}>Cancelar</Button><Button variante="perigo" carregando={desligando} onClick={() => void desligar()}>Desligar</Button></div>}>
        <p className="cfg-modal-copy">Os arquivos que estão no computador do bot serão apagados. Ele liga outro, vazio, na próxima vez que precisar.</p>
      </Modal>
      <Modal open={ampliada} onClose={() => setAmpliada(false)} title="Computador do bot" size="lg" className="wk-tela-modal">
        {grande && <img className="wk-tela-img" src={grande} alt="Tela do computador do bot, ampliada" />}
      </Modal>
    </section>
  );
}

/** Navegador e computador do bot. Some quando o bot não usa nenhum dos dois. */
export function TelasDoBot({ agenteId, usaComputador, cor }: { agenteId: string; usaComputador: boolean; cor?: string }) {
  useEffect(() => { void carregarAbas(agenteId).catch(() => undefined); }, [agenteId]);
  return <div className="wk-telas" key={agenteId}><TelaNavegador agenteId={agenteId} cor={cor} /><TelaComputador agenteId={agenteId} usa={usaComputador} /></div>;
}
