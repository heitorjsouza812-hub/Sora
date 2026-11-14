import { SoraOrb } from '../mascot';

export interface CreateConversationProps { onIrConfigurar: () => void }

/** A criação acontece na conversa principal; este aviso só existe para usos legados do editor. */
export function CreateConversation({ onIrConfigurar }: CreateConversationProps) {
  return <section className="bld-create bld-indisponivel" aria-label="Editar bot">
    <div className="bld-indisponivel-corpo" role="status">
      <SoraOrb size={72} state="idle" seed={11} decorative />
      <h2>Os bots nascem na conversa com a Sora</h2>
      <p>Este editor serve para ajustar um bot que já existe: identidade, ferramentas e instruções.</p>
      <button type="button" className="bld-save" onClick={onIrConfigurar}>Continuar editando</button>
    </div>
  </section>;
}
