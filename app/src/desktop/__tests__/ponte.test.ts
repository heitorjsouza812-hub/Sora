import { describe, expect, it } from 'vitest';
import { caminhoInternoValido, chaveDaSora, cofreApagar, cofreGravar, cofreLer } from '../ponte';

describe('ponte: validação', () => {
  it('aceita só rotas internas', () => {
    expect(caminhoInternoValido('/revisao/abc-1')).toBe(true);
    for (const ruim of ['//evil.com', 'https://evil.com', 'javascript:alert(1)', '/a/../b', '/a\b', '', 42, null]) expect(caminhoInternoValido(ruim)).toBe(false);
  });
  it('só chaves sora.* atravessam a ponte de storage', () => {
    expect(chaveDaSora('sora.projetos.v1')).toBe(true);
    for (const ruim of ['outra', '__proto__', 'sora.', undefined, 3]) expect(chaveDaSora(ruim)).toBe(false);
  });

  it('não acessa o cofre do sistema no navegador', async () => {
    await expect(cofreLer()).resolves.toBeNull();
    await expect(cofreGravar('token-opaco')).resolves.toBeUndefined();
    await expect(cofreApagar()).resolves.toBeUndefined();
  });
});
