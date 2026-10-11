// Estados de erro (item 47).
export { AvisoCreditos, AvisoPluginDesconectado, CardErroModelo, FaixaSemConexao, PainelErrosDev, type CardErroModeloProps } from './Erros';
export { useConexao, useCreditosEsgotados } from './estado';
export { definirErroSimulado, lerErroSimulado, TIPOS_ERRO, useErroSimulado, type TipoErro } from './simulacao';
