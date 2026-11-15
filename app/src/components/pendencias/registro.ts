// Guarda a última decisão de cada pedido, para a linha "✓ Permitido uma vez" depois que ele sai da lista.
export const ultimaAcao = new Map<string, string>();
export const registrarDecisao = (id: string, acao: string) => { ultimaAcao.set(id, acao); };
