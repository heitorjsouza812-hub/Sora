import { describe, expect, it } from 'vitest';
import { markdownSeguro } from '../markdownSeguro';

describe('markdownSeguro', () => {
  it('não deixa imagens remotas (pixel de rastreio) passarem', () => {
    expect(markdownSeguro('![x](https://attacker.example/p.gif)')).not.toContain('<img');
    expect(markdownSeguro('<img src="https://a.b/p.gif">')).not.toContain('<img');
  });
  it('remove scripts, handlers e javascript:', () => {
    const h = markdownSeguro('<script>alert(1)</script><a href="javascript:alert(1)" onclick="x()">oi</a> <svg onload=alert(1)>');
    expect(h).not.toMatch(/<script|javascript:|onclick|onload|<svg/i);
  });
  it('links externos ganham noopener', () => {
    expect(markdownSeguro('[a](https://x.com)')).toContain('noopener noreferrer');
  });
});
