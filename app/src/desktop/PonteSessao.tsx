// Janela principal do app de desktop: responde ao pedido de sessão da janela da ilha. A ilha não vê o
// cofre do sistema e nunca renova sozinha (gastaria o mesmo token de renovação duas vezes); ela pede o
// token de acesso por aqui. Fica FORA do GateSessao de propósito: a ilha pode pedir enquanto a
// principal ainda está renovando a própria sessão (a renovação em voo é compartilhada). No navegador
// não faz nada.
import { useEffect } from 'react';
import { lerTokenAcesso, renovarSessao } from '../api/cliente';
import { aoPedirSessao, emitirSessao, janelaAtual } from './ponte';

export function PonteSessao() {
  useEffect(() => (janelaAtual === 'main' ? aoPedirSessao(async ({ id, tokenAtual }) => {
    let token = lerTokenAcesso();
    // sem token (ainda carregando) ou o mesmo que a ilha já tentou e não serviu: renova uma vez
    if (!token || token === tokenAtual) {
      await renovarSessao().catch(() => false);
      token = lerTokenAcesso();
    }
    await emitirSessao(token, id).catch(() => {});
  }) : undefined), []);
  return null;
}

export default PonteSessao;
