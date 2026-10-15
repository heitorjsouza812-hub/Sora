// Catálogo dos componentes base (/lab/ui, só em DEV): todos os componentes e estados lado a lado.
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  Badge, Button, Card, IconButton, Input, Select, Textarea, ToastProvider, Tooltip, useToast, type Tamanho, type Variante,
} from '../components/base';
import { PainelErrosDev } from '../components/erros';
import '../components/base/catalogo.css';

const VARIANTES: Variante[] = ['primario', 'secundario', 'fantasma', 'perigo'];
const TAMANHOS: Tamanho[] = ['P', 'M', 'G'];
const NOMES: Record<Variante, string> = { primario: 'Primário', secundario: 'Secundário', fantasma: 'Fantasma', perigo: 'Perigo' };

const Mais = () => <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>;
const Seta = () => <svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
const Lixo = () => <svg viewBox="0 0 24 24"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12h10l1-12M9 7V4h6v3" /></svg>;
const Copiar = () => <svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a1 1 0 0 1 1-1h10" /></svg>;
const Engrenagem = () => <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" /></svg>;

function Secao({ titulo, descricao, children }: { titulo: string; descricao?: string; children: ReactNode }) {
  return (
    <section className="cat-secao" aria-labelledby={`cat-${titulo}`}>
      <header><h2 id={`cat-${titulo}`}>{titulo}</h2>{descricao && <p>{descricao}</p>}</header>
      {children}
    </section>
  );
}

function Toasts() {
  const { mostrar } = useToast();
  return (
    <div className="cat-linha">
      <Button onClick={() => mostrar({ mensagem: 'Link copiado' })}>Neutro</Button>
      <Button onClick={() => mostrar({ mensagem: 'Projeto apagado', descricao: '“Campanha · Cafeteria” e 3 agentes.', tom: 'sucesso',
        acao: { rotulo: 'Desfazer', onClick: () => mostrar({ mensagem: 'Projeto restaurado', tom: 'sucesso' }) } })}>Sucesso com Desfazer</Button>
      <Button onClick={() => mostrar({ mensagem: 'Plugin desconectado', descricao: 'Luna não vai conseguir usar o Canva.', tom: 'aviso' })}>Aviso</Button>
      <Button variante="perigo" onClick={() => mostrar({ mensagem: 'Não foi possível salvar', descricao: 'Verifique a conexão e tente de novo.', tom: 'erro', duracao: 0 })}>Erro (fica até fechar)</Button>
    </div>
  );
}

export default function Catalogo() {
  const [carregando, setCarregando] = useState(false);
  const [nome, setNome] = useState('');
  const simular = () => { setCarregando(true); window.setTimeout(() => setCarregando(false), 2500); };

  return (
    <ToastProvider>
      <main className="cat">
        <header className="cat-topo">
          <h1>Componentes base</h1>
          <p>Catálogo de <code>components/base</code>: todas as variantes e estados, só com os tokens de <code>styles/tokens.css</code>.</p>
        </header>

        <Secao titulo="Button" descricao="Primário, secundário, fantasma e perigo × P, M, G. “Carregando” mostra a Sora pensando (sem spinner).">
          <div className="cat-tabela">
            {VARIANTES.map((v) => (
              <div className="cat-linha" key={v}>
                <span className="cat-rotulo">{NOMES[v]}</span>
                {TAMANHOS.map((t) => <span key={t}><Button variante={v} tamanho={t}>{NOMES[v]} {t}</Button></span>)}
                <span><Button variante={v} disabled>Desativado</Button></span>
                <span><Button variante={v} carregando>Gerando…</Button></span>
              </div>
            ))}
          </div>
          <div className="cat-linha">
            <Button variante="primario" iconeEsquerda={<Mais />}>Novo projeto</Button>
            <Button iconeDireita={<Seta />}>Revisar</Button>
            <Button variante="perigo" iconeEsquerda={<Lixo />}>Apagar</Button>
            <Button variante="primario" carregando={carregando} onClick={simular}>{carregando ? 'Sora está criando…' : 'Clique para carregar'}</Button>
            <Button asChild variante="fantasma" iconeDireita={<Seta />}><Link to="/projetos">Link com asChild</Link></Button>
          </div>
          <div className="cat-bloco"><Button variante="secundario" bloco tamanho="G">Bloco (largura toda)</Button></div>
        </Secao>

        <Secao titulo="IconButton" descricao="aria-label obrigatório; com Tooltip mostra o rótulo também para quem vê.">
          <div className="cat-linha">
            {TAMANHOS.map((t) => <Tooltip key={t} conteudo={`Copiar (${t})`}><IconButton aria-label={`Copiar (${t})`} tamanho={t} icone={<Copiar />} /></Tooltip>)}
            <Tooltip conteudo="Configurações"><IconButton aria-label="Configurações" variante="secundario" icone={<Engrenagem />} /></Tooltip>
            <Tooltip conteudo="Novo chat"><IconButton aria-label="Novo chat" variante="primario" icone={<Mais />} /></Tooltip>
            <Tooltip conteudo="Apagar"><IconButton aria-label="Apagar" variante="perigo" icone={<Lixo />} /></Tooltip>
            <IconButton aria-label="Gerando" carregando icone={<Copiar />} />
            <IconButton aria-label="Desativado" disabled icone={<Copiar />} />
          </div>
        </Secao>

        <Secao titulo="Campos" descricao="Input, Textarea e Select nativo — rótulo, ajuda e erro ligados por aria-describedby.">
          <div className="cat-grade">
            <Input rotulo="Nome do agente" placeholder="Ex.: Atlas" value={nome} onChange={(e) => setNome(e.target.value)}
              ajuda="Até 24 caracteres." maxLength={24} />
            <Input rotulo="E-mail" type="email" defaultValue="cafeteria@" erro="Digite um e-mail válido." />
            <Input rotulo="Chave da API" placeholder="sk-…" disabled ajuda="Disponível quando houver back-end." />
            <Select rotulo="Movimento" vazio="Escolha…" defaultValue="" ajuda="Como os pontos se mexem quando o agente trabalha."
              opcoes={[{ valor: 'gira', rotulo: 'Gira' }, { valor: 'vibracao', rotulo: 'Vibração fina' }, { valor: 'espiral', rotulo: 'Espiral' }, { valor: 'ondas', rotulo: 'Ondas' }]} />
            <Select rotulo="Modelo" defaultValue="x" erro="Conecte uma API em Configurações."
              opcoes={[{ valor: 'x', rotulo: 'Nenhum modelo conectado' }]} />
            <Textarea rotulo="Instruções" placeholder="Fale como uma barista simpática…" ajuda="O agente segue isso em todas as tarefas." />
          </div>
        </Secao>

        <Secao titulo="Badge" descricao="Neutro, sucesso, aviso, erro e cor do agente (--agent-color).">
          <div className="cat-linha">
            <Badge>Rascunho</Badge>
            <Badge tom="sucesso" ponto>Concluído</Badge>
            <Badge tom="aviso" ponto>Aguardando aprovação</Badge>
            <Badge tom="erro" ponto>Erro</Badge>
            <Badge tom="agente" cor="#56A8FF" ponto="pulso">Atlas · Pesquisando</Badge>
            <Badge tom="agente" cor="#AC80FF" ponto="pulso">Luna · Criando</Badge>
            <Badge tom="agente" cor="#46E8A8" ponto>Nina · Concluído</Badge>
          </div>
        </Secao>

        <Secao titulo="Card" descricao="Superfícies 1, 2 e 3 (e espaçamentos P/M/G).">
          <div className="cat-grade">
            {([1, 2, 3] as const).map((s) => (
              <Card key={s} superficie={s} como="article">
                <Badge tom={s === 3 ? 'sucesso' : 'neutro'}>Superfície {s}</Badge>
                <h3>Campanha · Cafeteria</h3>
                <p>{s === 1 ? 'Painel padrão, para listas e grades.' : s === 2 ? 'Painel elevado, para cartões dentro de painéis.' : 'Destaque: menus, toasts e o que flutua.'}</p>
              </Card>
            ))}
            {(['P', 'G'] as const).map((e) => <Card key={e} espaco={e} interativo><p>Espaço {e} · interativo</p></Card>)}
          </div>
        </Secao>

        <Secao titulo="Tooltip" descricao="Abre no hover (350 ms) e no foco pelo teclado; Esc fecha; o mouse pode ir até o balão.">
          <div className="cat-linha">
            <Tooltip conteudo="Nada é publicado sem a sua aprovação."><Button>Passe o mouse ou foque</Button></Tooltip>
            <Tooltip conteudo="Aparece embaixo quando não cabe em cima." lado="baixo"><Button variante="fantasma">Lado de baixo</Button></Tooltip>
          </div>
        </Secao>

        <Secao titulo="Toast" descricao="Fila (até 3 visíveis), aria-live, fecha sozinho e pausa no hover/foco; ação opcional “Desfazer”.">
          <Toasts />
        </Secao>

        <Secao titulo="Erros simulados" descricao="Painel DEV do Forja: liga e desliga falhas de conexão, modelo, plugin e créditos para ver os estados de erro.">
          <PainelErrosDev />
        </Secao>
      </main>
    </ToastProvider>
  );
}
