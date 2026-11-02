// Cartões do que a equipe espera do usuário: pergunta (opções e/ou resposta livre; o orçamento estourado
// chega como pergunta com Continuar/Parar) e aprovação (Aprovar, Sempre permitir, Recusar).
// Mesmo cartão no chat e na ilha; só a densidade muda.
import { useState, type FormEvent } from 'react';
import { Button, Input } from '../base';
import { SoraOrb } from '../mascot';
import { decidirAprovacao, responderPergunta, type Pendencia } from '../../state/projetos';
import './pendencias.css';

type PerguntaP = Extract<Pendencia, { tipo: 'pergunta' }>;
type AprovacaoP = Extract<Pendencia, { tipo: 'aprovacao' }>;

function Cabeca({ rotulo, cor }: { rotulo: string; cor: string }) {
  return (
    <header className="pend-cabeca">
      <SoraOrb size={28} color={cor} state="listening" glow={false} decorative seed={11} />
      <span>{rotulo}</span>
    </header>
  );
}

function CartaoPergunta({ p, cor }: { p: PerguntaP; cor: string }) {
  const [texto, setTexto] = useState('');
  const enviarLivre = (ev: FormEvent) => { ev.preventDefault(); const v = texto.trim(); if (v && !p.enviando) void responderPergunta(p.id, v); };
  return (
    <section className="pend-card" aria-label="Pergunta da equipe" data-pendencia="pergunta">
      <Cabeca rotulo="A equipe precisa de você" cor={cor} />
      <p className="pend-texto">{p.texto}</p>
      {p.opcoes.length > 0 && (
        <div className="pend-acoes" role="group" aria-label="Opções">
          {p.opcoes.map((o, i) => (
            <Button key={o.valor} tamanho="M" variante={i === 0 ? 'primario' : 'secundario'} disabled={p.enviando} onClick={() => void responderPergunta(p.id, o.valor)}>{o.rotulo}</Button>
          ))}
        </div>
      )}
      {p.respostaLivre && (
        <form className="pend-livre" onSubmit={enviarLivre}>
          <Input rotulo="Sua resposta" rotuloOculto value={texto} onChange={ev => setTexto(ev.target.value)} placeholder="Escreva sua resposta…" disabled={p.enviando} />
          <Button type="submit" tamanho="M" variante="primario" disabled={!texto.trim() || p.enviando}>Responder</Button>
        </form>
      )}
      {p.erro && <p className="pend-erro" role="alert">{p.erro}</p>}
    </section>
  );
}

function CartaoAprovacao({ p, cor }: { p: AprovacaoP; cor: string }) {
  return (
    <section className="pend-card" aria-label="Pedido de aprovação" data-pendencia="aprovacao">
      <Cabeca rotulo="Preciso da sua aprovação" cor={cor} />
      <p className="pend-texto">{p.resumo}</p>
      {p.dano && <p className="pend-dano"><b>O que pode acontecer:</b> {p.dano}</p>}
      {p.quemRecebe && <p className="pend-dano"><b>Quem recebe:</b> {p.quemRecebe}</p>}
      <div className="pend-acoes" role="group" aria-label="Decisão">
        <Button tamanho="M" variante="primario" disabled={p.enviando} onClick={() => void decidirAprovacao(p.id, 'permitir_uma_vez')}>Aprovar</Button>
        <Button tamanho="M" variante="secundario" disabled={p.enviando} onClick={() => void decidirAprovacao(p.id, 'sempre_permitir')}>Sempre permitir</Button>
        <Button tamanho="M" variante="perigo" disabled={p.enviando} onClick={() => void decidirAprovacao(p.id, 'negar')}>Recusar</Button>
      </div>
      {p.expiraEm > 0 && <p className="pend-nota">Sem resposta até {new Date(p.expiraEm).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}, o pedido é recusado.</p>}
      {p.erro && <p className="pend-erro" role="alert">{p.erro}</p>}
    </section>
  );
}

export function CartaoPendencia({ p, cor }: { p: Pendencia; cor: string }) {
  return p.tipo === 'pergunta' ? <CartaoPergunta p={p} cor={cor} /> : <CartaoAprovacao p={p} cor={cor} />;
}

export function ListaPendencias({ pendencias, cor, className = '' }: { pendencias: Pendencia[]; cor: string; className?: string }) {
  if (!pendencias.length) return null;
  return <div className={`pend-lista ${className}`}>{pendencias.map(p => <CartaoPendencia key={p.id} p={p} cor={cor} />)}</div>;
}
