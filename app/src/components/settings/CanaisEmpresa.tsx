import { useState } from 'react';
import { API_BASE } from '../../api/cliente';
import { canaisEmpresa, type ConexaoEmpresa, type CanalSlack, type PreferenciasEmpresa } from '../../api/canaisEmpresa';
import { Button } from '../base';
import { EstadoConsulta, nomeCanal, useAcao, useConsulta } from '../clientes/comum';
import '../clientes/clientes.css';

const CAMPOS = { slack: { bot_token: 'Token do bot', signing_secret: 'Signing secret' }, whatsapp: { access_token: 'Token de acesso', app_secret: 'App secret', verify_token: 'Verify token' } };

function Conexao({ inicial }: { inicial: ConexaoEmpresa }) {
  const [conexao, setConexao] = useState(inicial);
  const [segredos, setSegredos] = useState<Record<string, string>>({});
  const [numero, setNumero] = useState(String(inicial.config.phone_number_id ?? ''));
  const [dominio, setDominio] = useState(String(inicial.config.dominio ?? ''));
  const [funcionarios, setFuncionarios] = useState((inicial.config.ids_funcionarios as string[] | undefined)?.join(', ') ?? '');
  const [canais, setCanais] = useState(inicial.canais_escolhidos);
  const [disponiveis, setDisponiveis] = useState<CanalSlack[]>([]);
  const [retorno, setRetorno] = useState('');
  const [basePublica, setBasePublica] = useState(API_BASE || window.location.origin);
  const { ocupado, erro, executar } = useAcao();
  const whatsapp = conexao.canal === 'whatsapp';
  const webhook = conexao.webhook_caminho ? `${basePublica.replace(/\/+$/, '')}${conexao.webhook_caminho}` : '';
  const salvar = () => executar(async () => {
    const nova = await canaisEmpresa.salvarConexao(conexao.canal, {
      segredos: Object.fromEntries(Object.entries(segredos).filter(([, valor]) => valor.trim()).map(([nome, valor]) => [nome, valor.trim()])),
      config: whatsapp ? { phone_number_id: numero.trim() } : { dominio: dominio.trim(), ids_funcionarios: funcionarios.split(/[,\s]+/).filter(Boolean) },
    });
    setSegredos({}); setConexao(nova); setRetorno('Conexão salva. Escolha abaixo o que a Sora pode ler.');
  });
  return <section className="ce-faixa" aria-label={nomeCanal(conexao.canal)}>
    <h3>{nomeCanal(conexao.canal)}</h3>
    <p className="ce-ajuda">{conexao.configurada ? 'Configuração salva' : 'Ainda não conectado'}{conexao.configurada && !conexao.ativa ? ' · Leitura desativada' : ''}</p>
    <form onSubmit={e => { e.preventDefault(); void salvar(); }}>
      <fieldset disabled={ocupado} className="ce-campos">
        {whatsapp ? <label>Número da empresa (phone_number_id)<input required value={numero} onChange={e => setNumero(e.target.value)} autoComplete="off" /></label> : <>
          <label>Domínio do workspace (opcional)<input value={dominio} onChange={e => setDominio(e.target.value)} placeholder="sua-empresa" /></label>
          <label>IDs dos funcionários (opcional)<input value={funcionarios} onChange={e => setFuncionarios(e.target.value)} placeholder="U012345, U067890" /><small className="ce-ajuda">Separe por vírgula para que as respostas da equipe ajudem no aprendizado.</small></label>
        </>}
        {Object.entries(CAMPOS[conexao.canal]).map(([campo, rotulo]) => <label key={campo}>{rotulo}
          <input aria-label={rotulo} type="password" autoComplete="new-password" required={!conexao.segredos_definidos[campo]} value={segredos[campo] ?? ''} onChange={e => setSegredos(s => ({ ...s, [campo]: e.target.value }))} placeholder={conexao.segredos_definidos[campo] ? '•••••••• · salvo' : ''} />
          {conexao.segredos_definidos[campo] && <small className="ce-ajuda">Segredo salvo. Deixe vazio para manter. O servidor não devolve o valor nem seus caracteres finais.</small>}
        </label>)}
        <div className="ce-acoes"><Button type="submit" variante="primario" carregando={ocupado}>Salvar conexão</Button><Button disabled={!conexao.configurada} onClick={() => void executar(async () => {
          const teste = await canaisEmpresa.testar(conexao.canal);
          setRetorno(`${teste.ok ? 'Conexão verificada.' : 'Conexão não validada.'} ${teste.detalhe} ${teste.avisos.join(' ')}`);
        })}>Testar conexão</Button></div>
      </fieldset>
    </form>
    {!whatsapp && <p className="ce-ajuda">Permissões de leitura: {conexao.escopos_slack.join(', ')}. Não conceda chat:write.</p>}
    {whatsapp && <p className="ce-ajuda">Use a Cloud API oficial do WhatsApp Business. Confira na Meta a coexistência com o app do celular.</p>}
    {conexao.configurada && <fieldset disabled={ocupado} className="ce-campos">
      <label>URL pública da API<input type="url" value={basePublica} onChange={e => setBasePublica(e.target.value)} /><small className="ce-ajuda">Slack e Meta precisam de uma URL HTTPS acessível. Em desenvolvimento, informe a URL do túnel.</small></label>
      <label>URL do webhook<input readOnly value={webhook} /></label>
      <Button disabled={!/^https?:\/\//i.test(webhook)} onClick={() => void executar(async () => { await navigator.clipboard.writeText(webhook); setRetorno('URL copiada.'); })}>Copiar URL do webhook</Button>
      <h3>O que a Sora pode ler</h3>
      {whatsapp ? <label className="ce-check"><input type="checkbox" checked={canais.includes(String(conexao.config.phone_number_id))} onChange={e => setCanais(e.target.checked ? [String(conexao.config.phone_number_id)] : [])} />Ler o número {String(conexao.config.numero_exibicao || conexao.config.phone_number_id)}</label> : <>
        <Button onClick={() => void executar(async () => { setDisponiveis(await canaisEmpresa.canaisSlack()); setRetorno('Canais disponíveis atualizados.'); })}>Buscar canais do Slack</Button>
        {[...disponiveis, ...canais.filter(id => !disponiveis.some(c => c.id === id)).map(id => ({ id, nome: id, privado: false }))].map(c => <label className="ce-check" key={c.id}><input type="checkbox" checked={canais.includes(c.id)} onChange={e => setCanais(lista => e.target.checked ? [...lista, c.id] : lista.filter(id => id !== c.id))} />{c.nome}{c.privado ? ' · privado' : ''}</label>)}
      </>}
      {!canais.length && <p className="ce-ajuda">Nenhum canal selecionado. A Sora ainda não lê mensagens.</p>}
      <Button onClick={() => void executar(async () => { const nova = await canaisEmpresa.escolher(conexao.canal, canais); setConexao(nova); setCanais(nova.canais_escolhidos); setRetorno('Seleção de leitura salva.'); })}>Salvar seleção</Button>
    </fieldset>}
    {(retorno || conexao.ultimo_teste_detalhe) && <p role="status">{retorno || conexao.ultimo_teste_detalhe}</p>}
    {erro && <p role="alert">{erro}</p>}
  </section>;
}

function Retencao({ inicial }: { inicial: PreferenciasEmpresa }) {
  const [dias, setDias] = useState(inicial.retencao_dias), [salvo, setSalvo] = useState(false);
  const { ocupado, erro, executar } = useAcao();
  return <form className="ce-faixa" onSubmit={e => { e.preventDefault(); void executar(async () => { await canaisEmpresa.salvarPreferencias({ retencao_dias: dias }); setSalvo(true); }); }}>
    <label>Retenção das mensagens (dias)<input type="number" required min={1} max={3650} value={dias || ''} onChange={e => { setDias(Number(e.target.value)); setSalvo(false); }} /></label>
    <p className="ce-ajuda">Após esse prazo, o texto das mensagens é apagado. Fichas e conhecimento permanecem até você apagá-los.</p>
    <Button type="submit" carregando={ocupado}>Salvar retenção</Button>{salvo && <p role="status">Retenção salva.</p>}{erro && <p role="alert">{erro}</p>}
  </form>;
}
export function CanaisEmpresa() {
  const consulta = useConsulta('conexoes', async signal => { const [conexoes, preferencias] = await Promise.all([canaisEmpresa.conexoes(signal), canaisEmpresa.preferencias(signal)]); return { conexoes, preferencias }; });
  return <div className="ce-area"><header className="cfg-heading"><h2>Canais da empresa</h2><p>A Sora só lê os canais escolhidos e aprende com o atendimento. Nunca envia mensagens por eles.</p></header>
    <p className="ce-ajuda">Privacidade e LGPD: avise os clientes de que o atendimento é registrado e analisado. Inclua esse aviso na política de privacidade e no canal da empresa.</p>
    <EstadoConsulta {...consulta} />
    {consulta.dados && <><Retencao inicial={consulta.dados.preferencias} />{consulta.dados.conexoes.map(c => <Conexao key={c.canal} inicial={c} />)}</>}
  </div>;
}
