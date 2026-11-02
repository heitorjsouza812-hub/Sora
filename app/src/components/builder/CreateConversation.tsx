import { SoraOrb } from '../mascot';

export interface CreateConversationProps { onIrConfigurar: () => void }

/** Não há rota no backend para criar agente por conversa (POST /v1/agentes cria de uma vez, sem rascunho
 * nem prévia). Sem resposta simulada: avisa e leva o usuário ao formulário, que salva no backend. */
export function CreateConversation({ onIrConfigurar }: CreateConversationProps) {
  return <section className="bld-create bld-indisponivel" aria-label="Criar agente por conversa">
    <div className="bld-indisponivel-corpo" role="status">
      <SoraOrb size={72} state="idle" seed={11} decorative />
      <h2>Criar por conversa ainda não está disponível</h2>
      <p>Por enquanto, monte o agente na aba Configurar: nome, função, cor, movimento, ferramentas e instruções.</p>
      <button type="button" className="bld-save" onClick={onIrConfigurar}>Ir para Configurar</button>
    </div>
  </section>;
}
