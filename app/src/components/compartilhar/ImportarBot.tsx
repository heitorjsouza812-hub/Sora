// "Importar bot" (Onda 3): escolhe um .zip exportado da Sora e cria a cópia na conta.
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { mensagemDeErro } from '../../api/cliente';
import { importarBotArquivo } from '../../api/compartilhar';
import { Button, toast } from '../base';
import { trazerBotImportado } from './trazerBot';

export function ImportarBot({ tamanho = 'P' }: { tamanho?: 'P' | 'M' }) {
  const entrada = useRef<HTMLInputElement>(null);
  const navegar = useNavigate();
  const [ocupado, setOcupado] = useState(false);
  const escolher = async (arquivo: File | undefined) => {
    if (!arquivo) return;
    setOcupado(true);
    try {
      const copia = await importarBotArquivo(arquivo);
      await trazerBotImportado(copia.agente_id).catch(() => undefined);
      toast({ mensagem: [`${copia.nome} foi importado.`, ...copia.avisos].join(' '), tom: 'sucesso' });
      navegar(`/bots/${copia.agente_id}`);
    } catch (e) {
      toast({ mensagem: mensagemDeErro(e), tom: 'erro' });
    } finally {
      setOcupado(false);
      if (entrada.current) entrada.current.value = '';
    }
  };
  return <>
    <input ref={entrada} type="file" accept=".zip,application/zip" hidden aria-label="Arquivo do bot (.zip)" onChange={e => void escolher(e.target.files?.[0])} />
    <Button tamanho={tamanho} variante="secundario" carregando={ocupado} onClick={() => entrada.current?.click()}>Importar bot</Button>
  </>;
}
