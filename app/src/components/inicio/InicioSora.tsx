// Início da tela vazia da Sora: aviso de chave (só quem ainda não conectou) e começos de pedido
// que apenas preenchem o campo; o usuário completa e envia.
import { AvisoSemProvedor } from '../sessao/AvisoSemProvedor';
import { INICIOS_DE_PEDIDO } from './pedidoInicial';
import './inicio.css';


export interface InicioSoraProps {
  /** Recebe o começo do pedido para colocar no campo de mensagem (sem enviar). */
  onPreencher: (texto: string) => void;
}

export function InicioSora({ onPreencher }: InicioSoraProps) {
  return (
    <div className="inicio-sora">
      <AvisoSemProvedor />
      <ul className="inicio-sugestoes" aria-label="Começos de pedido">
        {INICIOS_DE_PEDIDO.map(texto => (
          <li key={texto}><button type="button" onClick={() => onPreencher(texto)}>{texto.trim()}…</button></li>
        ))}
      </ul>
    </div>
  );
}
