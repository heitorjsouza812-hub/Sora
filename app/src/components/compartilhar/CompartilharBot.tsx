// Janela "Compartilhar bot" (Onda 3): link público, .zip e parar de compartilhar. O link leva o
// retrato do bot no momento em que foi criado; mudar o bot depois não muda o link.
import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../api/cliente';
import { compartilharBot, exportarBot, pararDeCompartilhar, verCompartilhamento, type Compartilhamento } from '../../api/compartilhar';
import { listarHabilidades, type Habilidade } from '../../state/pecas';
import { Button, toast } from '../base';
import { Modal } from '../overlay';
import './compartilhar.css';

interface Props { botId: string; nome: string; aberto: boolean; aoFechar: () => void }

export function CompartilharBot({ botId, nome, aberto, aoFechar }: Props) {
  const [link, setLink] = useState<Compartilhamento | null | undefined>(undefined);
  const [habilidades, setHabilidades] = useState<Habilidade[]>([]);
  const [escolhidas, setEscolhidas] = useState<string[]>([]);
  const [comRotinas, setComRotinas] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!aberto) return;
    let vivo = true;
    Promise.all([verCompartilhamento(botId), listarHabilidades().catch(() => [] as Habilidade[])])
      .then(([atual, lista]) => {
        if (!vivo) return;
        setLink(atual); setHabilidades(lista);
        if (atual) {
          setComRotinas(atual.bot.rotinas.length > 0);
          setEscolhidas(lista.filter(h => atual.bot.habilidades.some(c => c.nome === h.nome)).map(h => h.id));
        }
      })
      .catch(e => { if (vivo) { setLink(null); setErro(mensagemDeErro(e)); } });
    return () => { vivo = false; };
  }, [aberto, botId]);

  const opcoes = () => ({ habilidades: escolhidas, com_rotinas: comRotinas });
  const agir = async (f: () => Promise<void>) => {
    setOcupado(true); setErro(null);
    try { await f(); } catch (e) { setErro(mensagemDeErro(e)); } finally { setOcupado(false); }
  };
  const copiar = async (texto: string) => {
    try { await navigator.clipboard.writeText(texto); toast({ mensagem: 'Link copiado.', tom: 'sucesso' }); }
    catch { setErro('Não consegui copiar. Selecione o link e copie à mão.'); }
  };
  const alternar = (id: string) => setEscolhidas(l => l.includes(id) ? l.filter(x => x !== id) : l.length >= 10 ? l : [...l, id]);

  return <Modal open={aberto} onClose={aoFechar} title={`Compartilhar ${nome}`} size="md"
    description="Quem abrir o link vê o bot e pode criar uma cópia na própria conta. Nunca vão junto conversas, memória, arquivos ou chaves."
    footer={<div className="cfg-modal-actions">
      <Button disabled={ocupado} onClick={() => void agir(() => exportarBot(botId, nome, opcoes()))}>Baixar .zip</Button>
      <Button variante="primario" carregando={ocupado} onClick={() => void agir(async () => { setLink(await compartilharBot(botId, opcoes())); })}>{link ? 'Trocar link' : 'Criar link'}</Button>
    </div>}>
    <div className="compartilhar">
      {link === undefined ? <p role="status">Carregando…</p> : link ? <section className="compartilhar-link" aria-label="Link ativo">
        <div className="compartilhar-linha"><code>{link.url}</code><Button tamanho="P" onClick={() => void copiar(link.url)}>Copiar</Button></div>
        <small>Criado em {new Date(link.criado_em).toLocaleDateString('pt-BR')} · {link.usos === 1 ? '1 pessoa usou' : `${link.usos} pessoas usaram`}. Trocar o link cria outro endereço com o bot como está agora; o antigo para de funcionar.</small>
        <Button tamanho="P" variante="perigo" disabled={ocupado} onClick={() => void agir(async () => { await pararDeCompartilhar(botId); setLink(null); })}>Parar de compartilhar</Button>
      </section> : <p className="compartilhar-vazio">Este bot ainda não tem link.</p>}
      <fieldset className="compartilhar-opcoes">
        <legend>O que vai junto</legend>
        <label><input type="checkbox" checked={comRotinas} onChange={e => setComRotinas(e.target.checked)} /> Rotinas do bot (chegam pausadas para quem usar)</label>
        {habilidades.length > 0 && <>
          <p>Habilidades (até 10):</p>
          <ul>{habilidades.map(h => <li key={h.id}><label><input type="checkbox" checked={escolhidas.includes(h.id)} onChange={() => alternar(h.id)} /> {h.nome}</label></li>)}</ul>
        </>}
        <small>Também vão nome, função, cor, instruções e as ferramentas comuns. Controle do computador e dados de clientes nunca vão.</small>
      </fieldset>
      {erro && <p className="compartilhar-erro" role="alert">{erro}</p>}
    </div>
  </Modal>;
}
