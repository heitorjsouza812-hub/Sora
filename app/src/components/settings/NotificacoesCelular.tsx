// Configurações → Notificações: avisar este aparelho (celular ou navegador) quando um bot precisar de
// você. A notificação diz só quem precisa; o pedido em si continua no app.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { desligar, ligar, situacao, testar, type SituacaoPush } from '../../push';
import { Button } from '../base';

const TEXTO: Record<SituacaoPush, string> = {
  sem_suporte: 'Este navegador não recebe notificações da Sora. No app de desktop, os avisos aparecem pelo sistema (veja a seção Ilha).',
  precisa_instalar: 'No iPhone e no iPad: toque em Compartilhar → Adicionar à Tela de Início, abra a Sora por lá e ligue aqui.',
  servidor_desligado: 'A notificação no celular ainda não está ligada neste servidor.',
  bloqueado: 'As notificações da Sora estão bloqueadas neste navegador. Libere nas configurações do site e volte aqui.',
  desligado: 'Desligado neste aparelho.',
  ligado: 'Ligado neste aparelho.',
};

export function NotificacoesCelular() {
  const [estado, setEstado] = useState<SituacaoPush | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    situacao().then(s => { if (vivo) setEstado(s); }).catch(() => { if (vivo) setEstado('servidor_desligado'); });
    return () => { vivo = false; };
  }, []);

  const agir = async (f: () => Promise<void>) => {
    setOcupado(true); setAviso(null);
    try { await f(); } catch (e) { setAviso(mensagemDeErro(e)); } finally { setOcupado(false); }
  };

  return <>
    <header className="cfg-heading"><h2>Notificações</h2><p>Receba um aviso neste aparelho quando um bot precisar de você. O aviso diz só quem precisa; o pedido você vê no app.</p></header>
    <section className="cfg-account cfg-account--neutra">
      <div><h3>Avisar neste aparelho</h3><p role="status">{estado ? TEXTO[estado] : 'Conferindo…'}</p></div>
      {estado === 'desligado' && <Button variante="primario" carregando={ocupado} onClick={() => void agir(async () => setEstado(await ligar()))}>Ligar</Button>}
      {estado === 'ligado' && <span className="cfg-notif-acoes">
        <Button carregando={ocupado} onClick={() => void agir(async () => { const r = await testar(); setAviso(r.enviadas ? 'Aviso de teste enviado.' : 'Nenhum aparelho recebeu: ligue de novo.'); })}>Enviar teste</Button>
        <Button variante="fantasma" disabled={ocupado} onClick={() => void agir(async () => setEstado(await desligar()))}>Desligar</Button>
      </span>}
    </section>
    {aviso && <p className="cfg-senha__erro" role="status">{aviso}</p>}
  </>;
}
