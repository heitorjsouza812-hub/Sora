// Janela principal do app de desktop: recebe da ilha os pedidos de navegação e mantém a janela da
// ilha visível/escondida conforme a preferência "Mostrar ilha". No navegador não faz nada.
import { AvisosAtencao } from './AvisosAtencao';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useIlhaPrefs } from '../components/ilha/ilhaEstado';
import { navegarAtePedido } from './focarPedido';
import { PontePc } from './PontePc';
import { aoNavegar, definirIlhaVisivel, janelaAtual } from './ponte';

export function PonteNavegacao() {
  const navigate = useNavigate();
  const { visivel } = useIlhaPrefs();

  useEffect(() => (janelaAtual === 'main' ? aoNavegar(caminho => navegarAtePedido(navigate, caminho)) : undefined), [navigate]);

  useEffect(() => {
    if (janelaAtual === 'main') void definirIlhaVisivel(visivel).catch(() => {});
  }, [visivel]);

  return <><AvisosAtencao abrir={caminho => navegarAtePedido(navigate, caminho)} /><PontePc /></>;
}

export default PonteNavegacao;
