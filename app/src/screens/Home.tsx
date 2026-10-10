// Novo chat: tela de chat normal (estilo ChatGPT), SEM o mascote. A Sora aparece no primeiro envio:
// pensa (thinking orb), responde e, se o pedido pede trabalho, cria os agentes.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { MessageComposer } from '../components/ui/MessageComposer';
import { criarProjeto, novoChat, useProjetos } from '../state/projetos';

const sugestoes: [string, string][] = [
  ['Criar campanha', 'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.'],
  ['Pesquisar mercado', 'Faça uma pesquisa de mercado sobre cafeterias no meu bairro, com concorrentes e preços.'],
  ['Planejar posts', 'Planeje os posts do mês para o Instagram da minha loja.'],
  ['Resumir e-mails', 'Resuma meus e-mails da semana e sugira respostas.'],
];

export default function Home() {
  const [texto, setTexto] = useState('');
  const navigate = useNavigate();
  const { sora } = useProjetos();

  useEffect(() => { novoChat(); }, []);

  const enviar = (pedido: string) => {
    const p = criarProjeto(pedido, undefined, { tipo: 'chat' });
    navigate(`/projeto/${p.id}`);
  };

  return (
    <AppShell titulo="Novo chat" acoes={<span />}>
      <main className="home-screen home-plain">
        <h1>Em que posso te ajudar hoje?</h1>
        <div className="hero-composer">
          <MessageComposer
            placeholder={`Peça qualquer coisa à ${sora.nome}…`}
            tools
            value={texto}
            onValueChange={setTexto}
            onSend={enviar}
          />
        </div>
        <div className="suggestions" aria-label="Sugestões">
          {sugestoes.map(([rotulo, pedido]) => <button type="button" key={rotulo} onClick={() => setTexto(pedido)}>{rotulo}</button>)}
        </div>
      </main>
    </AppShell>
  );
}
