import { describe, expect, it } from 'vitest';
import { aplicarEventoTelas, telasIniciais } from '../telas';

const img = (c: string) => `data:image/jpeg;base64,${c}`;
const quadro = (extra: Record<string, unknown> = {}) => ({ aba_id: 'x', agente_id: 'a1', url: 'https://loja.com', titulo: 'Loja', largura: 1280, altura: 800, miniatura: img('AAA'), mudou: true, assumida_pelo_usuario: false, aviso: null, ...extra });

describe('estado das telas ao vivo', () => {
  it('navegador: guarda o quadro e mantém a imagem quando a miniatura vem nula (quadro igual)', () => {
    const a = aplicarEventoTelas(telasIniciais(), 'navegador.tela', quadro(), 1000);
    expect(a.navegador.a1).toMatchObject({ abaId: 'x', url: 'https://loja.com', largura: 1280, imagem: img('AAA'), recebidoEm: 1000 });
    const b = aplicarEventoTelas(a, 'navegador.tela', quadro({ miniatura: null, mudou: false }), 2000);
    expect(b.navegador.a1.imagem).toBe(img('AAA'));
    expect(b.navegador.a1.recebidoEm).toBe(2000);
  });
  it('navegador: outra aba não herda a imagem da anterior e miniatura que não é imagem é ignorada', () => {
    const a = aplicarEventoTelas(telasIniciais(), 'navegador.tela', quadro());
    const b = aplicarEventoTelas(a, 'navegador.tela', quadro({ aba_id: 'y', miniatura: null }));
    expect(b.navegador.a1.imagem).toBeNull();
    expect(aplicarEventoTelas(telasIniciais(), 'navegador.tela', quadro({ miniatura: 'javascript:alert(1)' })).navegador.a1.imagem).toBeNull();
  });
  it('computador: geração antiga não desfaz a nova; desligar limpa a imagem', () => {
    const c = (extra: Record<string, unknown>) => ({ agente_id: 'a1', alvo: 'virtual', ligado: true, geracao: 5, largura: 1280, altura: 800, miniatura: img('PPP'), janela_ativa: 'Terminal', acao: 'Clicou', mudou: true, ...extra });
    const a = aplicarEventoTelas(telasIniciais(), 'computador.tela', c({}));
    expect(aplicarEventoTelas(a, 'computador.tela', c({ geracao: 4, ligado: false })).computador.a1.ligado).toBe(true);
    const b = aplicarEventoTelas(a, 'computador.tela', c({ geracao: 6, ligado: false, miniatura: null }));
    expect(b.computador.a1).toMatchObject({ ligado: false, imagem: null });
    expect(aplicarEventoTelas(a, 'computador.tela', c({ miniatura: null, geracao: 6 })).computador.a1.imagem).toBe(img('PPP'));
  });
  it('evento sem agente ou de outro tipo devolve o mesmo estado', () => {
    const e = telasIniciais();
    expect(aplicarEventoTelas(e, 'navegador.tela', {})).toBe(e);
    expect(aplicarEventoTelas(e, 'outro', { agente_id: 'a1' })).toBe(e);
  });
});
