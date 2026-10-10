// "Editar agente" — o mesmo editor do estúdio, aberto de qualquer lugar (barra lateral, painel
// Equipe, cabeçalho do chat). Modal no desktop, BottomSheet no celular. Salvar reflete na hora.
import { atualizarAgente, atualizarSora, useProjetos } from '../../state/projetos';
import { BottomSheet, Modal } from '../overlay';
import { useCelular } from '../ui/useMedia';
import { EditorAgente } from './EditorAgente';
import './studio.css';

export interface PainelEditarAgenteProps {
  /** id do agente, ou 'sora' para a Sora */
  agenteId: string;
  onFechar: () => void;
}

export function PainelEditarAgente({ agenteId, onFechar }: PainelEditarAgenteProps) {
  const e = useProjetos();
  const celular = useCelular();
  const sora = agenteId === 'sora';
  const ag = sora ? null : e.agentes[agenteId];
  if (!sora && !ag) return null;
  const inicial = sora
    ? { nome: e.sora.nome, cor: e.sora.cor, funcao: 'Agente principal', tipoMovimento: 'gira' as const, ferramentas: [], instrucoes: '' }
    : { id: ag!.id, nome: ag!.nome, funcao: ag!.funcao, cor: ag!.cor, tipoMovimento: ag!.tipoMovimento, ferramentas: ag!.ferramentas, instrucoes: ag!.instrucoes };
  const titulo = sora ? `Personalizar ${e.sora.nome}` : `Editar ${ag!.nome}`;
  const editor = (
    <EditorAgente
      key={agenteId}
      variante={celular ? 'painel' : 'pagina'}
      modo={sora ? 'sora' : 'agente'}
      inicial={inicial}
      coresEmUso={Object.values(e.agentes).filter(a => a.id !== agenteId).map(a => a.cor)}
      onDescartar={onFechar}
      onSalvar={r => {
        if (sora) atualizarSora({ nome: r.nome, cor: r.cor });
        else atualizarAgente(agenteId, { nome: r.nome, funcao: r.funcao, cor: r.cor, tipoMovimento: r.tipoMovimento, ferramentas: r.ferramentas, instrucoes: r.instrucoes });
        onFechar();
      }}
    />
  );
  const descricao = sora ? 'Nome de exibição e cor da Sora.' : 'As mudanças aparecem na hora em todo o app.';
  return celular
    ? <BottomSheet open onClose={onFechar} title={titulo} description={descricao} className="st-sheet-mobile">{editor}</BottomSheet>
    : <Modal open onClose={onFechar} title={titulo} description={descricao} size="lg" className="st-modal">{editor}</Modal>;
}
