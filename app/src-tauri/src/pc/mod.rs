//! Ponte local do controle do PC do usuário (C3, `docs/computador-por-bot.md`).
//!
//! O servidor nunca age no PC: a janela principal busca os comandos do bot
//! (`GET /v1/computador-pc/comandos`, em `src/desktop/computadorPc.ts`) e chama `pc_executar`; a
//! resposta volta ao servidor por POST. Aqui ficam as regras que valem **mesmo que o servidor
//! erre**:
//!
//! - **desligado por padrão**: só bots que o usuário ligou neste PC, para a conta logada nele
//!   (`computador-pc.json` na pasta de dados do app, por conta);
//! - **um bot por vez**: quem está com a vez; os outros recebem `em_uso`;
//! - **borda acesa + Parar** enquanto controla (`borda.rs`), atalho global Ctrl+Shift+F12;
//! - **mexer no mouse ou no teclado pausa** na hora (a ação em andamento para entre um passo e
//!   outro e solta teclas apertadas); só o servidor, depois do cartão, manda `retomar`;
//! - antes de cada ação: programa liberado (cartão "Precisa de você"), nunca bloqueado, nunca a
//!   própria Sora, nunca campo de senha (`IsPassword`); a cada passo de entrada confere de
//!   novo quem tem o foco;
//! - nada fica gravado: nem captura, nem texto digitado.

#[cfg(windows)]
mod borda;
pub mod regras;
#[cfg(windows)]
mod sistema;

use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{
        Mutex, MutexGuard, OnceLock,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};
use tauri_plugin_global_shortcut::GlobalShortcutExt;

use regras::ErroPc;

/// Atalho global de Parar, registrado só enquanto um bot controla.
pub const ATALHO_PARAR: &str = "Ctrl+Shift+F12";
/// Sem comando por este tempo, a borda apaga e o bot perde a vez (o servidor usa o mesmo prazo).
const OCIOSO: Duration = Duration::from_secs(90);

/// Depois do Parar, o mesmo bot não pega o PC de novo por este tempo.
const PARADO_POR: Duration = Duration::from_secs(120);
const MAX_PERMITIDOS: usize = 200;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Agente {
    id: String,
    nome: String,
    cor: String,
}

#[derive(Default, Serialize, Deserialize)]
struct Config {
    #[serde(default)]
    contas: HashMap<String, ContaConfig>,
}

#[derive(Default, Serialize, Deserialize)]
struct ContaConfig {
    #[serde(default)]
    bots: Vec<String>,
}

#[derive(Default)]
struct Estado {
    conta: Option<String>,
    config: Config,
    controlador: Option<Agente>,
    pausado: bool,
    desde: Option<Instant>,
    ultimo: Option<Instant>,
    executando: bool,
    parados: HashMap<String, Instant>,
    usados: HashMap<String, Instant>,
}

impl Estado {
    fn autorizados(&self) -> Vec<String> {
        self.conta
            .as_ref()
            .and_then(|c| self.config.contas.get(c))
            .map(|c| c.bots.clone())
            .unwrap_or_default()
    }
}

struct ControlePc {
    estado: Mutex<Estado>,
    execucao: Mutex<()>,
    interrompido: AtomicBool,
    /// Eventos para a janela principal e o atalho de Parar. Instalado em `iniciar` (só no app):
    /// assim o executor não referencia o runtime do Tauri e os testes rodam sem tela.
    avisos: OnceLock<Box<dyn Fn(Aviso) + Send + Sync>>,
    arquivo: OnceLock<PathBuf>,
}

enum Aviso {
    Evento(&'static str, Value),
    AtalhoParar(bool),
}

static CONTROLE: OnceLock<ControlePc> = OnceLock::new();

fn controle() -> &'static ControlePc {
    CONTROLE.get_or_init(|| ControlePc {
        estado: Mutex::new(Estado::default()),
        execucao: Mutex::new(()),
        interrompido: AtomicBool::new(false),
        avisos: OnceLock::new(),
        arquivo: OnceLock::new(),
    })
}

fn travar<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|e| e.into_inner())
}

fn erro(e: ErroPc) -> Value {
    json!({ "ok": false, "erro": e })
}

fn ok(resultado: Value) -> Value {
    json!({ "ok": true, "resultado": resultado })
}

/// No `setup` do app: guarda o app, lê a configuração e liga a vigia de ociosidade.
pub fn iniciar(app: &AppHandle) {
    let c = controle();
    let dono = app.clone();
    let _ = c.avisos.set(Box::new(move |aviso| match aviso {
        Aviso::Evento(nome, dados) => {
            let _ = dono.emit_to("main", nome, dados);
        }
        Aviso::AtalhoParar(ligar) => {
            let atalhos = dono.global_shortcut();
            let registrado = atalhos.is_registered(ATALHO_PARAR);
            if ligar && !registrado {
                let _ = atalhos.register(ATALHO_PARAR);
            } else if !ligar && registrado {
                let _ = atalhos.unregister(ATALHO_PARAR);
            }
        }
    }));
    if let Ok(pasta) = app.path().app_data_dir() {
        let arquivo = pasta.join("computador-pc.json");
        if let Ok(texto) = std::fs::read_to_string(&arquivo)
            && let Ok(config) = serde_json::from_str::<Config>(&texto)
        {
            travar(&c.estado).config = config;
        }
        let _ = c.arquivo.set(arquivo);
    }
    thread::Builder::new()
        .name("sora-pc-ocioso".into())
        .spawn(|| {
            loop {
                thread::sleep(Duration::from_secs(2));
                let c = controle();
                let mut e = travar(&c.estado);
                let ocioso = e.controlador.is_some()
                    && !e.executando
                    && e.ultimo.is_some_and(|u| u.elapsed() > OCIOSO);
                if ocioso {
                    encerrar_controle(c, &mut e);
                }
            }
        })
        .ok();
}

fn salvar(c: &ControlePc, e: &Estado) {
    if let Some(arquivo) = c.arquivo.get() {
        if let Some(pasta) = arquivo.parent() {
            let _ = std::fs::create_dir_all(pasta);
        }
        if let Ok(texto) = serde_json::to_string_pretty(&e.config) {
            let _ = std::fs::write(arquivo, texto);
        }
    }
}

fn emitir(c: &ControlePc, evento: &'static str, dados: Value) {
    if let Some(avisar) = c.avisos.get() {
        avisar(Aviso::Evento(evento, dados));
    }
}

fn estado_publico(e: &Estado) -> Value {
    json!({
        "conta": e.conta,
        "autorizados": e.autorizados(),
        "controlando": e.controlador,
        "pausado": e.pausado,
        "windows": cfg!(windows),
        "atalho_parar": ATALHO_PARAR,
    })
}

/// Liga/desliga a borda e o atalho de Parar conforme o estado; avisa a tela de Configurações.
fn atualizar_borda(c: &ControlePc, e: &Estado) {
    let Some(avisar) = c.avisos.get() else { return }; // nos testes não há tela nem app
    #[cfg(windows)]
    {
        let (visivel, cor, nome) = match &e.controlador {
            Some(a) => (true, regras::cor_rgb(&a.cor), a.nome.clone()),
            None => (false, (0, 0, 0), String::new()),
        };
        borda::atualizar(borda::InfoBorda { visivel, cor, nome, pausado: e.pausado });
    }
    avisar(Aviso::AtalhoParar(e.controlador.is_some()));
    avisar(Aviso::Evento("pc-estado", estado_publico(e)));
}

fn encerrar_controle(c: &ControlePc, e: &mut Estado) {
    e.controlador = None;
    e.pausado = false;
    e.desde = None;
    atualizar_borda(c, e);
}

/// Entrada física (mouse ou teclado do usuário) enquanto um bot controla: pausa na hora.
pub fn ao_entrada_fisica() {
    let c = controle();
    let mut e = travar(&c.estado);
    let Some(agente) = e.controlador.clone() else { return };
    if e.pausado {
        return;
    }
    e.pausado = true;
    c.interrompido.store(true, Ordering::SeqCst);
    atualizar_borda(c, &e);
    emitir(c, "pc-pausado", json!({ "agente_id": agente.id }));
}

/// Parar (pílula da borda, atalho global ou Configurações): tira a vez do bot na hora.
pub fn parar_local() {
    let c = controle();
    let mut e = travar(&c.estado);
    c.interrompido.store(true, Ordering::SeqCst);
    if let Some(agente) = e.controlador.clone() {
        e.parados.insert(agente.id.clone(), Instant::now());
        emitir(c, "pc-parar", json!({ "agente_id": agente.id }));
    }
    encerrar_controle(c, &mut e);
}

pub fn e_atalho_parar(atalho: &tauri_plugin_global_shortcut::Shortcut) -> bool {
    ATALHO_PARAR.parse::<tauri_plugin_global_shortcut::Shortcut>().is_ok_and(|a| a.id() == atalho.id())
}

fn conferir_janela(janela: &WebviewWindow, comando: &str) -> Result<(), String> {
    if crate::janela_pode(comando, janela.label()) {
        Ok(())
    } else {
        Err("só a janela principal controla o computador".into())
    }
}

// ---------- comandos do app ----------

/// A janela principal diz qual conta está logada; devolve os bots ligados nela neste PC.
#[tauri::command]
pub fn pc_conta(usuario_id: String, janela: WebviewWindow) -> Result<Value, String> {
    conferir_janela(&janela, "pc_conta")?;
    if !regras::uuid_valido(&usuario_id) {
        return Err("conta inválida".into());
    }
    let c = controle();
    let mut e = travar(&c.estado);
    if e.conta.as_deref() != Some(usuario_id.as_str()) {
        encerrar_controle(c, &mut e);
        e.conta = Some(usuario_id);
    }
    Ok(estado_publico(&e))
}

#[tauri::command]
pub fn pc_autorizar(agente_id: String, ligado: bool, janela: WebviewWindow) -> Result<Value, String> {
    conferir_janela(&janela, "pc_autorizar")?;
    if !regras::uuid_valido(&agente_id) {
        return Err("bot inválido".into());
    }
    let c = controle();
    let mut e = travar(&c.estado);
    let Some(conta) = e.conta.clone() else {
        return Err("entre na sua conta no app de desktop".into());
    };
    let bots = &mut e.config.contas.entry(conta).or_default().bots;
    bots.retain(|b| b != &agente_id);
    if ligado {
        bots.push(agente_id.clone());
    }
    if !ligado && e.controlador.as_ref().is_some_and(|a| a.id == agente_id) {
        c.interrompido.store(true, Ordering::SeqCst);
        encerrar_controle(c, &mut e);
    }
    salvar(c, &e);
    emitir(c, "pc-estado", estado_publico(&e));
    Ok(estado_publico(&e))
}

#[tauri::command]
pub fn pc_estado(janela: WebviewWindow) -> Result<Value, String> {
    conferir_janela(&janela, "pc_estado")?;
    Ok(estado_publico(&travar(&controle().estado)))
}

#[tauri::command]
pub fn pc_parar(janela: WebviewWindow) -> Result<(), String> {
    conferir_janela(&janela, "pc_parar")?;
    parar_local();
    Ok(())
}

/// Saiu da conta (ou a sessão caiu): nenhum bot controla mais nada.
#[tauri::command]
pub fn pc_sair(janela: WebviewWindow) -> Result<(), String> {
    conferir_janela(&janela, "pc_sair")?;
    let c = controle();
    let mut e = travar(&c.estado);
    c.interrompido.store(true, Ordering::SeqCst);
    encerrar_controle(c, &mut e);
    e.conta = None;
    Ok(())
}

/// Executa um comando do servidor e devolve `{ok, resultado}` ou `{ok: false, erro}`.
#[tauri::command]
pub async fn pc_executar(comando: Value, janela: WebviewWindow) -> Result<Value, String> {
    conferir_janela(&janela, "pc_executar")?;
    tauri::async_runtime::spawn_blocking(move || executar(controle(), &comando))
        .await
        .map_err(|e| e.to_string())
}

fn agente_do_comando(comando: &Value) -> Option<Agente> {
    let a = comando.get("agente")?;
    let id = a.get("id")?.as_str()?.to_string();
    regras::uuid_valido(&id).then(|| Agente {
        id,
        nome: a.get("nome").and_then(Value::as_str).unwrap_or("Bot").chars().take(40).collect(),
        cor: a.get("cor").and_then(Value::as_str).unwrap_or("#E2ECFF").chars().take(9).collect(),
    })
}

fn agora_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64
}

fn executar(c: &ControlePc, comando: &Value) -> Value {
    let Some(agente) = agente_do_comando(comando) else {
        return erro(ErroPc::com_mensagem("invalido", "comando sem bot"));
    };
    let operacao = comando.get("operacao").and_then(Value::as_str).unwrap_or("");
    let dados = comando.get("dados").cloned().unwrap_or(Value::Null);
    let _vez = travar(&c.execucao); // um comando por vez
    {
        let mut e = travar(&c.estado);
        let id = comando.get("id").and_then(Value::as_str).unwrap_or("");
        let prazo = comando.get("prazo_em_ms").and_then(Value::as_u64).unwrap_or(0);
        if id.is_empty() || id.len() > 64 || agora_ms() >= prazo {
            return erro(ErroPc::novo("vencido"));
        }
        e.usados.retain(|_, em| em.elapsed() < Duration::from_secs(600));
        if e.usados.insert(id.to_string(), Instant::now()).is_some() {
            return erro(ErroPc::novo("usado"));
        }
        if e.conta.is_none() || !e.autorizados().contains(&agente.id) {
            return erro(ErroPc::novo("nao_autorizado"));
        }
        if operacao != "encerrar" && e.parados.get(&agente.id).is_some_and(|t| t.elapsed() < PARADO_POR) {
            return erro(ErroPc::novo("parado"));
        }
        let outro = e.controlador.as_ref().filter(|a| a.id != agente.id).cloned();
        match operacao {
            "encerrar" => {
                if e.controlador.as_ref().is_some_and(|a| a.id == agente.id) {
                    encerrar_controle(c, &mut e);
                }
                return ok(Value::Null);
            }
            "retomar" => {
                if let Some(outro) = outro {
                    return erro(ErroPc { por: Some(outro.nome), ..ErroPc::novo("em_uso") });
                }
                e.pausado = false;
                e.controlador = Some(agente);
                e.desde = Some(Instant::now());
                e.ultimo = Some(Instant::now());
                c.interrompido.store(false, Ordering::SeqCst);
                atualizar_borda(c, &e);
                return ok(Value::Null);
            }
            "observar" | "agir" => {}
            _ => return erro(ErroPc::com_mensagem("invalido", "operação desconhecida")),
        }
        if e.parados.get(&agente.id).is_some_and(|t| t.elapsed() < PARADO_POR) {
            return erro(ErroPc::novo("parado"));
        }
        if let Some(outro) = outro {
            return erro(ErroPc { por: Some(outro.nome), ..ErroPc::novo("em_uso") });
        }
        if e.pausado {
            return erro(ErroPc::novo("pausado"));
        }
        if e.controlador.is_none() {
            e.controlador = Some(agente);
            e.desde = Some(Instant::now());
            c.interrompido.store(false, Ordering::SeqCst);
            atualizar_borda(c, &e);
        }
        e.ultimo = Some(Instant::now());
        e.executando = true;
    }
    let resultado = match operacao {
        "observar" => observar(),
        _ => agir(c, &dados, comando["prazo_em_ms"].as_u64().unwrap_or(0)),
    };
    let mut e = travar(&c.estado);
    e.executando = false;
    e.ultimo = Some(Instant::now());
    match resultado {
        Ok(v) => ok(v),
        Err(falha) => erro(falha),
    }
}

#[cfg(not(windows))]
fn observar() -> Result<Value, ErroPc> {
    Err(ErroPc::novo("so_windows"))
}

#[cfg(windows)]
fn observar() -> Result<Value, ErroPc> {
    sistema::observar(std::process::id()).map(|(v, _)| v).map_err(|m| ErroPc::com_mensagem("falha", m))
}

#[cfg(not(windows))]
fn agir(_c: &ControlePc, _dados: &Value, _prazo: u64) -> Result<Value, ErroPc> {
    Err(ErroPc::novo("so_windows"))
}

fn interrupcao(c: &ControlePc) -> ErroPc {
    if travar(&c.estado).pausado { ErroPc::novo("pausado") } else { ErroPc::novo("parado") }
}

#[cfg(windows)]
fn agir(c: &ControlePc, dados: &Value, prazo: u64) -> Result<Value, ErroPc> {
    use regras::{Conferencia, Passo, conferir_alvo, normalizar_programa, planejar};

    if !borda::pronta() {
        return Err(ErroPc::com_mensagem("falha", "a borda ou a pausa física não estão disponíveis; não executei a ação"));
    }
    let pid = std::process::id();
    let permitidos: Vec<String> = dados
        .get("programas_permitidos")
        .and_then(Value::as_array)
        .map(|l| l.iter().filter_map(Value::as_str).map(normalizar_programa).take(MAX_PERMITIDOS).collect())
        .unwrap_or_default();
    let acao = dados.get("acao").cloned().unwrap_or(Value::Null);
    let t = sistema::tela();
    let plano = planejar(&acao, t.escala, (t.largura_fisica, t.altura_fisica))?;
    let falha = || ErroPc::com_mensagem("falha", "não achei a janela que receberia a ação");

    if let Some(hwnd) = plano.trazer {
        let alvo = sistema::alvo_da_ref(hwnd).ok_or_else(|| ErroPc::novo("janela_sumiu"))?;
        conferir_alvo(&alvo, &permitidos, pid)?;
        if !sistema::trazer_para_frente(hwnd) {
            return Err(ErroPc::novo("sem_foco"));
        }
    }
    for conferencia in &plano.conferencias {
        let (alvo, senha) = match *conferencia {
            Conferencia::Ponto(x, y) => (sistema::alvo_no_ponto(x, y), sistema::senha_no_ponto(x, y)),
            Conferencia::Foco => (sistema::alvo_em_foco(), sistema::senha_em_foco()),
        };
        conferir_alvo(&alvo.ok_or_else(falha)?, &permitidos, pid)?;
        if senha {
            return Err(ErroPc::novo("senha"));
        }
    }
    let digitando = plano.conferencias == [Conferencia::Foco];
    for (i, passo) in plano.passos.iter().enumerate() {
        // soltar uma tecla não digita nada; conferir antes de soltar fazia `ctrl+Escape` (que muda
        // o foco no meio da combinação) parecer falha (Vela-6, teste ao vivo)
        let conferir_foco = digitando && !matches!(passo, Passo::Tecla(_, false));
        let parou = c.interrompido.load(Ordering::SeqCst) || agora_ms() >= prazo;
        let mudou = conferir_foco
            && (sistema::senha_em_foco()
                || sistema::alvo_em_foco().is_none_or(|a| conferir_alvo(&a, &permitidos, pid).is_err()));
        if parou || mudou {
            for soltar in regras::ainda_apertados(&plano.passos[..i]) {
                let _ = sistema::enviar(soltar, &t);
            }
            return Err(if parou {
                interrupcao(c)
            } else {
                ErroPc::com_mensagem("falha", "o foco saiu do programa liberado no meio da digitação; parei")
            });
        }
        if let Err(m) = sistema::enviar(*passo, &t) {
            for soltar in regras::ainda_apertados(&plano.passos[..i]) {
                let _ = sistema::enviar(soltar, &t);
            }
            return Err(ErroPc::com_mensagem("falha", m));
        }
        thread::sleep(Duration::from_millis(match passo {
            Passo::Caractere(_) => 4,
            Passo::Mover(..) => 12,
            Passo::Botao(..) => 35,
            Passo::Tecla(..) => 15,
            Passo::Roda(..) => 40,
        }));
    }
    Ok(Value::Null)
}

#[cfg(test)]
mod testes {
    use super::*;

    fn controle_de_teste() -> ControlePc {
        ControlePc {
            estado: Mutex::new(Estado::default()),
            execucao: Mutex::new(()),
            interrompido: AtomicBool::new(false),
            avisos: OnceLock::new(),
            arquivo: OnceLock::new(),
        }
    }

    const ATLAS: &str = "11111111-2222-4333-8444-555555555555";
    const LUNA: &str = "66666666-7777-4888-9999-aaaaaaaaaaaa";

    fn comando(agente: &str, operacao: &str) -> Value {
        static SEQUENCIA: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);
        json!({"id": SEQUENCIA.fetch_add(1, Ordering::SeqCst).to_string(), "prazo_em_ms": agora_ms() + 60_000, "agente": {"id": agente, "nome": "Atlas", "cor": "#56A8FF"}, "operacao": operacao, "dados": {}})
    }

    fn codigo(v: &Value) -> &str {
        v["erro"]["codigo"].as_str().unwrap_or("")
    }

    #[test]
    fn desligado_por_padrao_e_so_na_conta_logada() {
        let c = controle_de_teste();
        assert_eq!(codigo(&executar(&c, &comando(ATLAS, "observar"))), "nao_autorizado");
        {
            let mut e = travar(&c.estado);
            e.config.contas.entry("conta-a".into()).or_default().bots.push(ATLAS.into());
            e.conta = Some("conta-b".into());
        }
        assert_eq!(codigo(&executar(&c, &comando(ATLAS, "observar"))), "nao_autorizado");
        travar(&c.estado).conta = Some("conta-a".into());
        assert_eq!(codigo(&executar(&c, &comando(LUNA, "observar"))), "nao_autorizado");
        assert_eq!(codigo(&executar(&c, &json!({"operacao": "observar"}))), "invalido");
    }

    #[test]
    fn um_bot_por_vez_pausa_e_parar() {
        let c = controle_de_teste();
        {
            let mut e = travar(&c.estado);
            e.conta = Some("conta".into());
            e.config.contas.entry("conta".into()).or_default().bots.extend([ATLAS.into(), LUNA.into()]);
            e.controlador = Some(Agente { id: ATLAS.into(), nome: "Atlas".into(), cor: "#56A8FF".into() });
        }
        let outro = executar(&c, &comando(LUNA, "observar"));
        assert_eq!(codigo(&outro), "em_uso");
        assert_eq!(outro["erro"]["por"], "Atlas");
        assert_eq!(codigo(&executar(&c, &comando(LUNA, "retomar"))), "em_uso");

        travar(&c.estado).pausado = true;
        assert_eq!(codigo(&executar(&c, &comando(ATLAS, "agir"))), "pausado");
        assert_eq!(executar(&c, &comando(ATLAS, "retomar"))["ok"], true);
        assert!(!travar(&c.estado).pausado);

        // Parar: tira a vez e o mesmo bot não volta logo
        {
            let mut e = travar(&c.estado);
            e.parados.insert(ATLAS.into(), Instant::now());
            e.controlador = None;
        }
        assert_eq!(codigo(&executar(&c, &comando(ATLAS, "observar"))), "parado");
        assert_eq!(executar(&c, &comando(ATLAS, "encerrar"))["ok"], true);
        assert_eq!(codigo(&executar(&c, &comando(ATLAS, "apagar_tudo"))), "parado");
    }

    #[test]
    fn comando_vencido_repetido_e_retomada_depois_de_parar_sao_recusados() {
        let c = controle_de_teste();
        let cmd = comando(ATLAS, "observar");
        assert_eq!(codigo(&executar(&c, &cmd)), "nao_autorizado");
        assert_eq!(codigo(&executar(&c, &cmd)), "usado");
        let mut vencido = comando(ATLAS, "observar");
        vencido["prazo_em_ms"] = json!(1);
        assert_eq!(codigo(&executar(&c, &vencido)), "vencido");
        {
            let mut e = travar(&c.estado);
            e.conta = Some("conta".into());
            e.config.contas.entry("conta".into()).or_default().bots.push(ATLAS.into());
            e.parados.insert(ATLAS.into(), Instant::now());
        }
        assert_eq!(codigo(&executar(&c, &comando(ATLAS, "retomar"))), "parado");
    }

    #[test]
    fn configuracao_por_conta_le_e_grava() {
        let mut config = Config::default();
        config.contas.entry("a".into()).or_default().bots.push(ATLAS.into());
        let texto = serde_json::to_string(&config).unwrap();
        let lida: Config = serde_json::from_str(&texto).unwrap();
        assert_eq!(lida.contas["a"].bots, vec![ATLAS.to_string()]);
        let vazia: Config = serde_json::from_str("{}").unwrap();
        assert!(vazia.contas.is_empty());
    }
}
