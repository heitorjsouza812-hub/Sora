// Ferramentas que um agente individual pode receber: os nomes exatos que o backend aceita
// (`FERRAMENTAS_POR_PAPEL` em backend/app/ferramentas/permissoes.py; nome fora dela dá 422).
// Não há rota que liste o catálogo: se o backend ganhar ferramenta nova, ela entra aqui.

/** Sempre vão junto (sem elas o agente não responde nem pergunta); não aparecem para escolher. */
export const FERRAMENTAS_BASE = ['falar', 'perguntar'] as const;

export const FERRAMENTAS_AGENTE: { id: string; rotulo: string }[] = [
  { id: 'buscar_web', rotulo: 'Buscar na web' },
  { id: 'ler_pagina', rotulo: 'Ler páginas' },
  { id: 'ler_anexo', rotulo: 'Ler anexos' },
  { id: 'escrever_arquivo', rotulo: 'Escrever arquivos' },
  { id: 'gerar_imagem', rotulo: 'Gerar imagens' },
];

/** Computador próprio do bot: vêm desligadas e o formulário liga todas juntas, num só interruptor (não entram na grade acima). */
export const FERRAMENTAS_COMPUTADOR: { id: string; rotulo: string }[] = [
  { id: 'computador_observar', rotulo: 'Ver a tela do computador' },
  { id: 'computador_agir', rotulo: 'Usar o computador' },
  { id: 'computador_arquivos', rotulo: 'Ver arquivos do computador' },
  { id: 'computador_escrever_arquivo', rotulo: 'Escrever arquivos no computador' },
  { id: 'computador_entregar_arquivo', rotulo: 'Entregar arquivos do computador' },
  { id: 'computador_desligar', rotulo: 'Desligar o computador' },
];
export const usaComputador = (ferramentas: readonly string[]) => ferramentas.some(f => f.startsWith('computador_'));

const ROTULOS: Record<string, string> = Object.fromEntries([...FERRAMENTAS_AGENTE, ...FERRAMENTAS_COMPUTADOR].map(f => [f.id, f.rotulo]));

/** Nome amigável; o que não é do catálogo (plugin, conector) aparece como veio. */
export const rotuloFerramenta = (id: string) => ROTULOS[id] ?? id;

/** O que vai para o backend: as escolhidas do catálogo + as de base. Vazio = padrão do backend. */
export function ferramentasParaSalvar(escolhidas: string[]): string[] {
  const validas = escolhidas.filter(f => f in ROTULOS);
  return validas.length ? [...FERRAMENTAS_BASE, ...new Set(validas)] : [];
}
