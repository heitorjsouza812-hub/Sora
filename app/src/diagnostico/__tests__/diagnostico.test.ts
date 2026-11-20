import { afterEach, describe, expect, it } from 'vitest';
import { _limparDiagnosticoParaTestes, errosRecentes, limparTexto, montarDiagnostico, registrarErroRecente } from '..';

afterEach(() => { _limparDiagnosticoParaTestes(); window.history.replaceState(null, '', '/'); });

describe('diagnóstico do Relatar problema', () => {
  it('tira e-mail, tokens, números longos e o que vem depois de "senha"', () => {
    const limpo = limparTexto('falhou para ana@empresa.com.br, Bearer abc.def, eyJa.b.c, sk-proj-12345678abcd, senha: Abc@123, CPF 529.982.247-25, cartão 4111 1111 1111 1111');
    expect(limpo).not.toMatch(/ana@empresa|abc\.def|eyJa|sk-proj|Abc@123|529\.982|4111/);
    expect(limpo).toContain('[e-mail]');
    expect(limpo).toContain('[número]');
  });

  it('guarda só os 20 erros mais novos e corta mensagens longas', () => {
    for (let i = 0; i < 25; i++) registrarErroRecente('app', `erro ${i}`);
    const erros = errosRecentes();
    expect(erros).toHaveLength(20);
    expect(erros[0].mensagem).toBe('erro 5');
    registrarErroRecente('app', 'x'.repeat(900));
    expect(errosRecentes().at(-1)!.mensagem.length).toBe(500);
  });

  it('a rota vai sem consulta nem fragmento (o link de senha nova leva o token no #)', () => {
    window.history.replaceState(null, '', '/redefinir-senha?x=1#token=segredo');
    const d = montarDiagnostico();
    expect(d.rota).toBe('/redefinir-senha');
    expect(JSON.stringify(d)).not.toContain('segredo');
    expect(['web', 'celular', 'desktop']).toContain(d.plataforma);
  });
});
