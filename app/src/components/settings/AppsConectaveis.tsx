// Catálogo de apps com login (Onda 3): Conectar abre o login do próprio app em outra janela; quando
// ele volta, o app vira um conector e os bots passam a usar as ferramentas dele. Toda ação que muda
// algo no app continua pedindo a sua aprovação.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, mensagemDeErro } from '../../api/cliente';
import { Button, toast } from '../base';

interface AppCatalogo { id: string; nome: string; descricao: string; categoria: string; url: string; conectado: boolean; conector_id: string | null }

const listarApps = () => api.get<AppCatalogo[]>('/v1/conectores/apps');
/** Relógio fora do componente (o lint de pureza não aceita Date.now dentro dele). */
const agora = () => Date.now();
const conectarApp = (id: string) => api.post<{ url_autorizacao: string }>(`/v1/conectores/apps/${encodeURIComponent(id)}/conectar`);

export function AppsConectaveis({ aoConectar }: { aoConectar?: () => void }) {
  const [apps, setApps] = useState<AppCatalogo[] | null>(null);
  const [esperando, setEsperando] = useState<string | null>(null);
  const [erro, setErro] = useState('');
  // volta do login: a janela aberta pelo app chega com ?resultado=… (lido uma vez, ao abrir)
  const [params] = useState(() => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search));
  const espera = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const carregar = useCallback(() => listarApps().then(lista => { setApps(lista); return lista; }), []);
  useEffect(() => {
    let vivo = true;
    listarApps().then(l => { if (vivo) setApps(l); }).catch(e => { if (vivo) { setApps([]); setErro(mensagemDeErro(e)); } });
    return () => { vivo = false; clearInterval(espera.current); };
  }, []);

  const resultado = params.get('resultado');
  const mensagemVolta = resultado === 'erro' ? params.get('mensagem') : null;

  const conectar = async (app: AppCatalogo) => {
    setErro(''); setEsperando(app.id);
    try {
      const { url_autorizacao } = await conectarApp(app.id);
      window.open(url_autorizacao, '_blank', 'noopener,noreferrer');
      const inicio = agora();
      clearInterval(espera.current);
      espera.current = setInterval(() => {
        void carregar().then(lista => {
          if (lista.find(a => a.id === app.id)?.conectado) {
            clearInterval(espera.current); setEsperando(null);
            toast({ mensagem: `${app.nome} conectado. Os bots já podem usar.`, tom: 'sucesso' });
            aoConectar?.();
          } else if (agora() - inicio > 3 * 60_000) { clearInterval(espera.current); setEsperando(null); }
        }).catch(() => undefined);
      }, 3000);
    } catch (e) { setErro(mensagemDeErro(e)); setEsperando(null); }
  };

  return <section className="apps-catalogo" aria-label="Apps para conectar">
    <header><h3>Apps</h3><p>Entre com a sua conta de cada app. A Sora não vê sua senha, e toda ação que muda algo no app pede a sua aprovação.</p></header>
    {resultado === 'conectado' && <p className="apps-aviso" role="status">App conectado.</p>}
    {mensagemVolta && <p className="pc-erro" role="alert">{mensagemVolta}</p>}
    {erro && <p className="pc-erro" role="alert">{erro}</p>}
    {apps === null ? <p role="status">Carregando apps…</p> : <ul className="apps-grade">{apps.map(app => <li key={app.id} data-conectado={app.conectado}>
      <span className="apps-inicial" aria-hidden="true">{app.nome.slice(0, 1)}</span>
      <span className="apps-texto"><strong>{app.nome}</strong><small>{app.descricao}</small></span>
      {app.conectado
        ? <span className="apps-conectado">● Conectado</span>
        : <Button tamanho="P" variante="secundario" carregando={esperando === app.id} disabled={!!esperando && esperando !== app.id} onClick={() => void conectar(app)}>{esperando === app.id ? 'Esperando o login…' : 'Conectar'}</Button>}
    </li>)}</ul>}
  </section>;
}
