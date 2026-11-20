// Configurações → Conta → Versão do app (só no app de desktop): versão, "Procurar atualização" e
// "Instalar e reiniciar" quando há versão nova assinada.
import { Button } from '../base';
import { atualizacaoPossivel, instalarAgora, procurarAtualizacao, useAtualizacao } from '../../desktop/atualizacao';

export function VersaoApp() {
  const estado = useAtualizacao();
  if (!atualizacaoPossivel()) return null;
  const ultima = estado.ultima;
  const versao = ultima?.versao_atual ?? String(import.meta.env.VITE_SORA_VERSAO ?? '');
  const situacao = estado.fase === 'verificando' ? 'Procurando versão nova…'
    : estado.fase === 'instalando' ? 'Baixando e instalando… o app vai reiniciar.'
    : 'erro' in estado && estado.erro ? estado.erro
    : ultima?.estado === 'disponivel' ? `A versão ${ultima.versao_nova} está pronta para instalar.`
    : ultima?.estado === 'em_dia' ? 'Você está na versão mais nova.'
    : ultima?.estado === 'desligada' ? 'Esta versão ainda não se atualiza sozinha. Baixe a nova no site da Sora.'
    : '';
  return <section className="cfg-account cfg-account--neutra">
    <div><h3>Versão do app{versao ? ` · ${versao}` : ''}</h3><p role="status">{situacao || 'O app procura versão nova sozinho ao abrir e a cada 6 horas.'}</p></div>
    {ultima?.estado === 'disponivel'
      ? <Button variante="primario" carregando={estado.fase === 'instalando'} disabled={estado.fase !== 'parada'} onClick={() => { void instalarAgora(); }}>Instalar e reiniciar</Button>
      : <Button carregando={estado.fase === 'verificando'} disabled={estado.fase !== 'parada'} onClick={() => { void procurarAtualizacao(); }}>Procurar atualização</Button>}
  </section>;
}
