// Configurações → Conta → Relatar problema: botão para relatar e os relatos já enviados, com Retirar.
import { useEffect, useState } from 'react';
import { Button, toast } from '../base';
import { mensagemDeErro } from '../../api/cliente';
import { listarRelatos, retirarRelato, type RelatoEnviado } from '../../api/relatos';
import { abrirRelatarProblema, useVersaoRelatos } from './estado';
import './relatos.css';

const data = new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

export function RelatosEnviados() {
  const versao = useVersaoRelatos();
  const [relatos, setRelatos] = useState<RelatoEnviado[]>([]);
  const [retirando, setRetirando] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    listarRelatos().then(lista => { if (vivo) setRelatos(lista); }).catch(() => { /* a lista é um extra */ });
    return () => { vivo = false; };
  }, [versao]);

  const retirar = async (id: string) => {
    setRetirando(id);
    try {
      await retirarRelato(id);
      setRelatos(lista => lista.filter(r => r.id !== id));
      toast({ mensagem: 'Relato retirado.', tom: 'neutro' });
    } catch (falha) {
      toast({ mensagem: mensagemDeErro(falha), tom: 'erro' });
    } finally {
      setRetirando(null);
    }
  };

  return <section className="cfg-account cfg-account--neutra relatos-enviados">
    <div className="relatos-enviados__topo">
      <div><h3>Relatar problema</h3><p>Algo não funcionou? Conte para o time da Sora. Você pode retirar um relato quando quiser.</p></div>
      <Button onClick={abrirRelatarProblema}>Relatar problema</Button>
    </div>
    {relatos.length > 0 && <ul className="relatos-enviados__lista" aria-label="Relatos enviados">
      {relatos.map(r => <li key={r.id}>
        <span><time dateTime={r.criado_em}>{data.format(new Date(r.criado_em))}</time>{r.resumo}</span>
        <Button variante="fantasma" tamanho="P" carregando={retirando === r.id} onClick={() => { void retirar(r.id); }} aria-label={`Retirar relato: ${r.resumo}`}>Retirar</Button>
      </li>)}
    </ul>}
  </section>;
}
