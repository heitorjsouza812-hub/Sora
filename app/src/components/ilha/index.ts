// Ilha da Sora: pílula no topo com a Sora e os bots trabalhando (adaptação do Coucou).
// Etapa 5: só existe na janela dedicada do app de desktop (fora do app e no navegador, não renderiza).
export { Ilha, type ModoIlha } from './Ilha';
export { VisaoGeral, type VisaoGeralProps } from './VisaoGeral';
export {
  useIlha, useIlhaPrefs, definirIlhaPrefs, lerIlhaPrefs, visaoIlha, filtrarBonecos, alternarAgenteOculto,
  type IlhaPrefs, type FiltroBots, type VisaoIlha, type BonecoIlha,
} from './ilhaEstado';
export { abrirIlha, fecharIlha, alternarIlha, useIlhaUi, useIlhaAberta, type VistaIlha } from './ilhaUi';
