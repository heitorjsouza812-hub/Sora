// Menu "…" de um agente (ou da Sora): "Editar agente"/"Personalizar" + itens extras.
// Usa o menu acessível da gestão (teclado WAI-ARIA); Renomear/Apagar entram só via `itens`.
import { MenuItemAcoes, type ItemAcao } from '../gestao';
import { abrirEditorAgente } from './editorAberto';

export type ItemMenu = ItemAcao;

export interface MenuAgenteProps {
  /** id do agente, 'sora', ou o id de outro alvo quando `semEditar` */
  agenteId: string;
  nome: string;
  itens?: ItemMenu[];
  className?: string;
  /** sem o item "Editar agente" (ex.: menu de um chat) */
  semEditar?: boolean;
}

export function MenuAgente({ agenteId, nome, itens = [], className = '', semEditar = false }: MenuAgenteProps) {
  const editar: ItemMenu[] = semEditar ? [] : [{ rotulo: agenteId === 'sora' ? 'Personalizar' : 'Editar agente', onClick: () => abrirEditorAgente(agenteId) }];
  return <MenuItemAcoes alvo={{ tipo: 'agente', id: agenteId }} nome={nome} itens={[...editar, ...itens]} renomear={false} apagar={false} className={className} />;
}
