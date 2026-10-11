// Estados de erro projetados (item 47): sem conexão, modelo falhou, plugin desconectado, créditos.
import { Link } from 'react-router-dom';
import { Button } from '../base';
import { SoraOrb } from '../mascot';
import { useConexao } from './estado';
import { definirErroSimulado, TIPOS_ERRO, useErroSimulado } from './simulacao';
import './erros.css';

function IconeAlerta() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 2.8 19.5h18.4z" /><path d="M12 10v4.2M12 17h.01" /></svg>;
}

/** faixa no topo enquanto não há internet (nada quando online) */
export function FaixaSemConexao() {
  const { online, tentarDeNovo } = useConexao();
  if (online) return null;
  return (
    <div className="err-faixa" role="alert">
      <span className="err-faixa__ponto" aria-hidden="true" />
      <p><strong>Sem conexão.</strong> Seus agentes pausaram; nada se perde. Assim que a internet voltar, a Sora continua.</p>
      <Button tamanho="P" variante="secundario" onClick={tentarDeNovo}>Tentar de novo</Button>
    </div>
  );
}

export interface CardErroModeloProps {
  onTentarDeNovo: () => void;
  /** ex.: "OpenAI · gpt-5.6" */
  modelo?: string;
  /** quem falhou (padrão: a Sora) */
  autor?: string;
  cor?: string;
}

/** card na conversa quando a chamada ao modelo falha */
export function CardErroModelo({ onTentarDeNovo, modelo, autor = 'A Sora', cor = '#E2ECFF' }: CardErroModeloProps) {
  return (
    <div className="err-card" role="alert">
      <SoraOrb size={34} color={cor} state="idle" glow={false} decorative seed={41} />
      <div className="err-card__texto">
        <strong>{autor} não conseguiu responder</strong>
        <p>{modelo ? <>O modelo <b>{modelo}</b> não respondeu.</> : 'O modelo de IA não respondeu.'} Pode ser instabilidade do provedor ou uma chave inválida.</p>
        <div className="err-acoes">
          <Button tamanho="P" variante="primario" onClick={onTentarDeNovo}>Tentar de novo</Button>
          <Button tamanho="P" asChild><Link to="/configuracoes">Trocar modelo</Link></Button>
        </div>
      </div>
    </div>
  );
}

/** aviso dentro do passo do painel Trabalho quando o plugin caiu */
export function AvisoPluginDesconectado({ plugin }: { plugin: string }) {
  return (
    <div className="err-aviso" role="alert">
      <IconeAlerta />
      <p><strong>{plugin} desconectado.</strong> O agente parou neste passo até você reconectar.</p>
      <Button tamanho="P" asChild><Link to="/plugins">Reconectar</Link></Button>
    </div>
  );
}

/** bloqueio suave: dá para escrever, mas não enviar */
export function AvisoCreditos({ compacto = false }: { compacto?: boolean }) {
  return (
    <div className={`err-aviso err-aviso--creditos ${compacto ? 'is-compacto' : ''}`} role="status">
      <IconeAlerta />
      <p><strong>Seus créditos acabaram.</strong> Você ainda pode escrever; para enviar, escolha um plano ou espere o próximo ciclo.</p>
      <Button tamanho="P" variante="primario" asChild><Link to="/configuracoes?secao=conta">Ver planos</Link></Button>
    </div>
  );
}

/** painel DEV para ligar/desligar os erros simulados (para o /lab/ui) */
export function PainelErrosDev() {
  const atual = useErroSimulado();
  if (!import.meta.env.DEV) return null;
  return (
    <fieldset className="err-dev">
      <legend>Simular erro (DEV)</legend>
      <div className="err-acoes">
        <Button tamanho="P" variante={atual === null ? 'primario' : 'secundario'} aria-pressed={atual === null} onClick={() => definirErroSimulado(null)}>Nenhum</Button>
        {TIPOS_ERRO.map(t => (
          <Button key={t.id} tamanho="P" variante={atual === t.id ? 'primario' : 'secundario'} aria-pressed={atual === t.id} onClick={() => definirErroSimulado(t.id)}>{t.rotulo}</Button>
        ))}
      </div>
      <small>Também por URL: <code>?simularErro=conexao|modelo|plugin|creditos</code></small>
    </fieldset>
  );
}
