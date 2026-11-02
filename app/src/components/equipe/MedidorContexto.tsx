// Medidor de contexto de um agente (Âncora): % da janela usada, nível e "Compactar agora".
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { carregarContexto, chaveContexto, compactarAgora, useEquipe } from '../../state/equipe';
import { Button } from '../base';
import { ProgressBar } from '../ui/ProgressBar';
import './equipe.css';

const NIVEL: Record<string, string> = { ok: 'Tudo certo', atencao: 'Atenção', compactar: 'Vai compactar sozinho', cheio: 'Cheio' };
const COR: Record<string, string> = { ok: '#7EF2C4', atencao: '#FFD166', compactar: '#FF9F5A', cheio: '#FF6B6B' };

export function MedidorContexto({ agenteId, fio = 'principal' }: { agenteId: string; fio?: string }) {
  const c = useEquipe().contextos[chaveContexto(agenteId, fio)];
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);
  useEffect(() => { void carregarContexto(agenteId).catch(() => undefined); }, [agenteId]);
  const compactar = async () => { setEnviando(true); setErro(''); try { await compactarAgora(agenteId, fio); } catch (e) { setErro(mensagemDeErro(e)); } finally { setEnviando(false); } };
  if (!c) return <section className="eq-contexto" aria-label="Contexto"><p className="eyebrow tools-label">Contexto</p><p className="eq-nota">Ainda não medido. Aparece depois da primeira resposta.</p></section>;
  const compactando = c.compactacao === 'compactando';
  return (
    <section className="eq-contexto" aria-label="Contexto" data-nivel={c.nivel}>
      <div className="progress-title"><span>Contexto</span><b>{c.estimado ? '~' : ''}{c.porcentagem}%</b></div>
      <ProgressBar value={c.porcentagem} color={COR[c.nivel]} label="Contexto usado" status={NIVEL[c.nivel]} />
      <p className="eq-nota" role="status">{compactando ? 'Compactando o histórico…' : c.compactacao === 'falhou' ? 'A última compactação falhou.' : NIVEL[c.nivel]} · {c.tokens.toLocaleString('pt-BR')} de {c.janela.toLocaleString('pt-BR')} tokens</p>
      <Button tamanho="M" variante="secundario" disabled={enviando || compactando} onClick={() => void compactar()}>Compactar agora</Button>
      {erro && <p className="eq-erro" role="alert">{erro}</p>}
    </section>
  );
}
