use std::{
    sync::{Arc, Condvar, Mutex, OnceLock},
    thread,
    time::{Duration, Instant},
};

use serde::Serialize;
use tauri::{
    AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, Runtime, State, WebviewWindow,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

/// C3: controle do PC do usuário por um bot (ponte local; ver `pc/mod.rs`).
mod pc;

const ILHA_LARGURA: f64 = 800.0;
const ILHA_ALTURA: f64 = 460.0;
const MARGEM: f64 = 8.0;
const COFRE_SERVICO: &str = "com.sora.desktop";
const COFRE_USUARIO: &str = "token-renovacao";

#[derive(Clone, Copy, Default)]
struct RetanguloIlha {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}

/// A etapa 5 só mostra a ilha fora do app: a janela nativa fica visível quando o usuário permite
/// (preferência "mostrar ilha", via o comando `ilha_visivel`) **e** a janela "main" não está em
/// foco (perdeu o foco, foi minimizada — o que sempre tira o foco no Windows antes — ou escondida
/// na bandeja). Dentro do app e no navegador a ilha nunca chega a existir como janela separada.
///
/// Uma única thread (`iniciar_vigia_foco`) decide mostrar/esconder; eventos de janela e o comando
/// `ilha_visivel` só a "cutucam". Assim não há corrida entre quem lê o foco e quem mostra a ilha.
#[derive(Clone)]
struct IlhaEstado {
    retangulo: Arc<Mutex<RetanguloIlha>>,
    atividade: Arc<(Mutex<bool>, Condvar)>,
    permitida: Arc<Mutex<bool>>,
    foco_principal: Arc<Mutex<bool>>,
    principal_minimizada: Arc<Mutex<bool>>,
    cutucada: Arc<(Mutex<bool>, Condvar)>,
    /// HWND da janela "main" (Windows), guardado no setup: a vigia lê o estado real do Windows
    /// sem depender da thread da interface.
    hwnd_principal: Arc<OnceLock<isize>>,
    /// HWND da janela da ilha (Windows): ver `ilha_nativa`.
    hwnd_ilha: Arc<OnceLock<isize>>,
}

impl IlhaEstado {
    fn novo(permitida: bool) -> Self {
        Self {
            retangulo: Arc::new(Mutex::new(RetanguloIlha::default())),
            // a janela "main" começa em foco (é ela que abre primeiro): a ilha começa escondida.
            atividade: Arc::new((Mutex::new(false), Condvar::new())),
            permitida: Arc::new(Mutex::new(permitida)),
            foco_principal: Arc::new(Mutex::new(true)),
            principal_minimizada: Arc::new(Mutex::new(false)),
            cutucada: Arc::new((Mutex::new(false), Condvar::new())),
            hwnd_principal: Arc::new(OnceLock::new()),
            hwnd_ilha: Arc::new(OnceLock::new()),
        }
    }

    /// Pede à vigia que reconcilie a ilha agora (sem esperar o próximo tique).
    fn cutucar(&self) {
        let (pedido, aviso) = &*self.cutucada;
        *pedido.lock().expect("cutucada da ilha envenenada") = true;
        aviso.notify_all();
    }

    /// Espera uma cutucada ou o tempo máximo; consome a cutucada.
    fn esperar_cutucada(&self, maximo: Duration) {
        let (pedido, aviso) = &*self.cutucada;
        let guarda = pedido.lock().expect("cutucada da ilha envenenada");
        let (mut guarda, _) = aviso
            .wait_timeout_while(guarda, maximo, |p| !*p)
            .expect("cutucada da ilha envenenada");
        *guarda = false;
    }

    fn definir_ativa(&self, ativa: bool) {
        let (estado, aviso) = &*self.atividade;
        *estado.lock().expect("estado da ilha envenenado") = ativa;
        aviso.notify_all();
    }

    fn ativa(&self) -> bool {
        *self.atividade.0.lock().expect("estado da ilha envenenado")
    }

    fn definir_permitida(&self, permitida: bool) {
        *self.permitida.lock().expect("permissão da ilha envenenada") = permitida;
    }

    fn definir_foco_principal(&self, foco: bool) {
        *self.foco_principal.lock().expect("foco da ilha envenenado") = foco;
    }

    fn definir_principal_minimizada(&self, minimizada: bool) {
        *self
            .principal_minimizada
            .lock()
            .expect("estado minimizado da janela principal envenenado") = minimizada;
    }

    /// Visível só fora do app: permitida pelo usuário e a janela principal sem foco ou minimizada.
    fn deveria_estar_visivel(&self) -> bool {
        deveria_estar_visivel(
            *self.permitida.lock().expect("permissão da ilha envenenada"),
            *self.foco_principal.lock().expect("foco da ilha envenenado"),
            *self
                .principal_minimizada
                .lock()
                .expect("estado minimizado da janela principal envenenado"),
        )
    }
}

/// Função pura (testável sem Tauri): a ilha só aparece fora do app.
fn deveria_estar_visivel(
    permitida: bool,
    foco_principal: bool,
    principal_minimizada: bool,
) -> bool {
    permitida && (!foco_principal || principal_minimizada)
}

#[derive(Clone, Copy, Serialize)]
struct MouseIlha {
    dentro: bool,
    x: f64,
    y: f64,
}

fn janela<R: Runtime>(app: &AppHandle<R>, nome: &str) -> Option<WebviewWindow<R>> {
    app.get_webview_window(nome)
}

fn mostrar_principal<R: Runtime>(app: &AppHandle<R>) {
    if let Some(main) = janela(app, "main") {
        let _ = main.unminimize();
        let _ = main.show();
        let _ = main.set_focus();
    }
}

/// Janela da ilha no Windows, mexida direto pelo Win32 depois de criada.
///
/// Motivo: no tao 0.37 todo `show()`, `set_position()`, `set_ignore_cursor_events()` e
/// `set_focusable()` passa por `set_window_flags`, que chama `ShowWindow(SW_SHOW)` (janela
/// visível) ou `ShowWindow(SW_HIDE)` (escondida) a CADA chamada. `SW_SHOW` ATIVA a janela quando
/// o processo da Sora tem direito ao primeiro plano — e tem logo depois de o usuário clicar em
/// minimizar: a ilha virava a janela ativa e roubava o teclado do programa seguinte
/// (`WS_EX_NOACTIVATE` não impede ativação por código). Aqui a ilha aparece com
/// `SW_SHOWNOACTIVATE` e o resto não toca na visibilidade.
#[cfg(windows)]
mod ilha_nativa {
    use windows::Win32::{
        Foundation::HWND,
        UI::WindowsAndMessaging::{
            GWL_EXSTYLE, GetWindowLongPtrW, HWND_TOPMOST, SW_HIDE, SW_SHOWNOACTIVATE,
            SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER,
            SetWindowLongPtrW, SetWindowPos, ShowWindow, WS_EX_LAYERED, WS_EX_NOACTIVATE,
            WS_EX_TRANSPARENT,
        },
    };

    fn h(hwnd: isize) -> HWND {
        HWND(hwnd as *mut core::ffi::c_void)
    }

    // SAFETY (todas): HWND da própria janela da ilha; com HWND inválido as chamadas só falham.
    pub fn mostrar(hwnd: isize) {
        unsafe {
            let _ = ShowWindow(h(hwnd), SW_SHOWNOACTIVATE);
        }
    }

    pub fn esconder(hwnd: isize) {
        unsafe {
            let _ = ShowWindow(h(hwnd), SW_HIDE);
        }
    }

    /// Posição e tamanho em pixels físicos, sempre por cima e sem ativar.
    pub fn posicionar(hwnd: isize, x: i32, y: i32, largura: i32, altura: i32) {
        unsafe {
            let _ = SetWindowPos(
                h(hwnd),
                Some(HWND_TOPMOST),
                x,
                y,
                largura,
                altura,
                SWP_NOACTIVATE,
            );
        }
    }

    /// Fora da pílula: cliques atravessam e a janela não aceita foco (os mesmos estilos que o tao
    /// usa em `set_ignore_cursor_events(true)` + `set_focusable(false)`). Dentro: recebe cliques e
    /// aceita foco, para dar para digitar uma resposta.
    pub fn atravessar_cliques(hwnd: isize, atravessar: bool) {
        let bits = (WS_EX_TRANSPARENT.0 | WS_EX_LAYERED.0 | WS_EX_NOACTIVATE.0) as isize;
        unsafe {
            let atual = GetWindowLongPtrW(h(hwnd), GWL_EXSTYLE);
            let novo = if atravessar {
                atual | bits
            } else {
                atual & !bits
            };
            if novo != atual {
                SetWindowLongPtrW(h(hwnd), GWL_EXSTYLE, novo);
                let _ = SetWindowPos(
                    h(hwnd),
                    None,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                );
            }
        }
    }
}

fn posicionar_ilha<R: Runtime>(app: &AppHandle<R>, estado: &IlhaEstado) {
    let Some(ilha) = janela(app, "ilha") else {
        return;
    };
    let Ok(Some(monitor)) = app.primary_monitor() else {
        return;
    };
    let escala = monitor.scale_factor();
    let origem = monitor.position();
    let tamanho = monitor.size();
    let largura_fisica = (ILHA_LARGURA * escala).round() as i32;
    let x = origem.x + (tamanho.width as i32 - largura_fisica) / 2;
    #[cfg(windows)]
    if let Some(&hwnd) = estado.hwnd_ilha.get() {
        let altura_fisica = (ILHA_ALTURA * escala).round() as i32;
        ilha_nativa::posicionar(hwnd, x, origem.y, largura_fisica, altura_fisica);
        return;
    }
    let _ = estado;
    let _ = ilha.set_size(LogicalSize::new(ILHA_LARGURA, ILHA_ALTURA));
    let _ = ilha.set_position(PhysicalPosition::new(x, origem.y));
}

fn definir_visibilidade<R: Runtime>(app: &AppHandle<R>, estado: &IlhaEstado, visivel: bool) {
    let Some(ilha) = janela(app, "ilha") else {
        return;
    };
    #[cfg(windows)]
    if let Some(&hwnd) = estado.hwnd_ilha.get() {
        if visivel {
            posicionar_ilha(app, estado);
            ilha_nativa::mostrar(hwnd);
            estado.definir_ativa(true);
        } else {
            estado.definir_ativa(false);
            ilha_nativa::esconder(hwnd);
            let _ = app.emit_to("ilha", "ilha-escondida", ());
        }
        return;
    }
    if visivel {
        posicionar_ilha(app, estado);
        let _ = ilha.show();
        estado.definir_ativa(true);
    } else {
        estado.definir_ativa(false);
        let _ = ilha.hide();
        let _ = app.emit_to("ilha", "ilha-escondida", ());
    }
}

/// Fora da pílula os cliques atravessam e a ilha não aceita foco; dentro, ela recebe cliques e
/// aceita foco (para digitar uma resposta).
fn definir_atravessar_cliques<R: Runtime>(
    ilha: &WebviewWindow<R>,
    estado: &IlhaEstado,
    atravessar: bool,
) {
    #[cfg(windows)]
    if let Some(&hwnd) = estado.hwnd_ilha.get() {
        ilha_nativa::atravessar_cliques(hwnd, atravessar);
        return;
    }
    let _ = estado;
    let _ = ilha.set_ignore_cursor_events(atravessar);
    let _ = ilha.set_focusable(!atravessar);
}

/// Quanto tempo a ilha espera, com a Sora fora de foco, antes de aparecer: evita piscar em
/// trocas rápidas de janela (ex.: Alt+Tab passando pela Sora).
const ATRASO_PARA_APARECER: Duration = Duration::from_millis(150);

/// Decide o que fazer neste tique: esconder na hora, mostrar só depois de `ATRASO_PARA_APARECER`
/// seguidos querendo aparecer. `querendo_desde` é o instante em que passou a querer aparecer.
fn reconciliar<R: Runtime>(
    app: &AppHandle<R>,
    estado: &IlhaEstado,
    querendo_desde: &mut Option<Instant>,
) {
    let deveria = estado.deveria_estar_visivel();
    if deveria && !estado.ativa() {
        let desde = *querendo_desde.get_or_insert_with(Instant::now);
        if desde.elapsed() >= ATRASO_PARA_APARECER {
            *querendo_desde = None;
            definir_visibilidade(app, estado, true);
        }
    } else {
        *querendo_desde = None;
        if !deveria && estado.ativa() {
            definir_visibilidade(app, estado, false);
        }
    }
}

#[tauri::command]
fn ilha_emitir(janela: tauri::WebviewWindow, evento: String, dados: serde_json::Value) -> Result<(), String> {
    if janela.label() != "ilha" || !evento_ilha_permitido(&evento) {
        return Err("Evento não permitido nesta janela.".into());
    }
    janela.app_handle().emit_to("main", &evento, dados).map_err(|e| e.to_string())
}

fn evento_ilha_permitido(evento: &str) -> bool {
    matches!(evento, "sora-armazenamento" | "sora-sessao-pedir")
}

#[tauri::command]
fn ilha_retangulo(
    x: f64,
    y: f64,
    w: f64,
    h: f64,
    janela: WebviewWindow,
    estado: State<'_, IlhaEstado>,
) -> Result<(), String> {
    if !janela_pode("ilha_retangulo", janela.label()) {
        return Err("só a janela da ilha pode informar o retângulo".into());
    }
    let r = validar_retangulo(x, y, w, h).ok_or("retângulo inválido")?;
    *estado
        .retangulo
        .lock()
        .expect("retângulo da ilha envenenado") = r;
    pc::regras::ilha_definir_pilula(r.x, r.y, r.w, r.h);
    Ok(())
}

/// Rejeita não finitos/negativos e limita o retângulo à janela da ilha (800×460).
fn validar_retangulo(x: f64, y: f64, w: f64, h: f64) -> Option<RetanguloIlha> {
    if ![x, y, w, h].iter().all(|v| v.is_finite() && *v >= 0.0) {
        return None;
    }
    let x = x.min(ILHA_LARGURA);
    let y = y.min(ILHA_ALTURA);
    Some(RetanguloIlha {
        x,
        y,
        w: w.min(ILHA_LARGURA - x),
        h: h.min(ILHA_ALTURA - y),
    })
}

/// Rota interna do app: "/" + caracteres simples; sem esquema, "//" ou "..".
fn caminho_interno_valido(caminho: &str) -> bool {
    caminho.len() <= 200
        && caminho.starts_with('/')
        && !caminho.starts_with("//")
        && !caminho.contains("..")
        && caminho
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "-_./?=&%#".contains(c))
}

/// Qual janela pode chamar cada comando (segunda trava; a primeira são as capabilities
/// `capabilities/main.json` e `capabilities/ilha.json`, que liberam os mesmos comandos). APP-003.
const COMANDOS_POR_JANELA: &[(&str, &str)] = &[
    ("ilha_retangulo", "ilha"),
    ("navegar", "ilha"),
    ("ilha_visivel", "main"),
    ("notificar_atencao", "main"),
    ("titulo_atencao", "main"),
    ("cofre_ler", "main"),
    ("cofre_gravar", "main"),
    ("cofre_apagar", "main"),
    ("pc_conta", "main"),
    ("pc_autorizar", "main"),
    ("pc_estado", "main"),
    ("pc_executar", "main"),
    ("pc_parar", "main"),
    ("pc_sair", "main"),
];

fn janela_pode(comando: &str, label: &str) -> bool {
    COMANDOS_POR_JANELA
        .iter()
        .any(|(c, janela)| *c == comando && *janela == label)
}

#[tauri::command]
fn ilha_visivel(
    visivel: bool,
    janela: WebviewWindow,
    estado: State<'_, IlhaEstado>,
) -> Result<(), String> {
    if !janela_pode("ilha_visivel", janela.label()) {
        return Err("só a janela principal liga/desliga a ilha".into());
    }
    // "visivel" aqui é a preferência do usuário ("mostrar ilha"); a janela só aparece de
    // verdade quando, além disso, a "main" estiver fora de foco (etapa 5: ilha só fora do app).
    estado.definir_permitida(visivel);
    estado.cutucar();
    Ok(())
}

#[tauri::command]
fn titulo_atencao(total: usize, janela: WebviewWindow) -> Result<(), String> {
    if !janela_pode("titulo_atencao", janela.label()) { return Err("janela inválida".into()); }
    janela.set_title(&if total == 0 { "Sora".into() } else { format!("({total}) Sora") }).map_err(|e| e.to_string())
}

#[tauri::command]
fn notificar_atencao(id: i32, origem: String, caminho: String, janela: WebviewWindow, app: AppHandle, estado: State<'_, IlhaEstado>, rotas: State<'_, RotasNotificacao>) -> Result<(), String> {
    if !janela_pode("notificar_atencao", janela.label()) || !caminho_interno_valido(&caminho) { return Err("pedido inválido".into()); }
    if estado_da_principal(&app, &estado).is_none_or(|(foco, minimizada)| foco && !minimizada) { return Ok(()); }
    rotas.0.lock().map_err(|e| e.to_string())?.insert(id, caminho);
    app.notification().builder().id(id).title("Precisa de você").body(origem).show().map_err(|e| e.to_string())
}

#[derive(Default)]
struct RotasNotificacao(Mutex<std::collections::HashMap<i32, String>>);

#[tauri::command]
fn mostrar_app(app: AppHandle) {
    mostrar_principal(&app);
}

fn entrada_cofre() -> Result<keyring::Entry, String> {
    keyring::Entry::new(COFRE_SERVICO, COFRE_USUARIO)
        .map_err(|erro| format!("não foi possível acessar o cofre do sistema: {erro}"))
}

#[tauri::command]
fn cofre_ler(janela: WebviewWindow) -> Result<Option<String>, String> {
    if !janela_pode("cofre_ler", janela.label()) {
        return Err("só a janela principal pode ler o cofre".into());
    }
    match entrada_cofre()?.get_password() {
        Ok(token) => Ok(Some(token)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(erro) => Err(format!("não foi possível ler o cofre do sistema: {erro}")),
    }
}

#[tauri::command]
fn cofre_gravar(token: String, janela: WebviewWindow) -> Result<(), String> {
    if !janela_pode("cofre_gravar", janela.label()) {
        return Err("só a janela principal pode gravar no cofre".into());
    }
    if token.is_empty() {
        return Err("o token de renovação não pode ser vazio".into());
    }
    entrada_cofre()?
        .set_password(&token)
        .map_err(|erro| format!("não foi possível gravar no cofre do sistema: {erro}"))
}

#[tauri::command]
fn cofre_apagar(janela: WebviewWindow) -> Result<(), String> {
    if !janela_pode("cofre_apagar", janela.label()) {
        return Err("só a janela principal pode apagar o cofre".into());
    }
    match entrada_cofre()?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(erro) => Err(format!(
            "não foi possível apagar o cofre do sistema: {erro}"
        )),
    }
}

#[tauri::command]
fn navegar(caminho: String, janela: WebviewWindow, app: AppHandle) -> Result<(), String> {
    if !janela_pode("navegar", janela.label()) {
        return Err("só a ilha pede navegação".into());
    }
    if !caminho_interno_valido(&caminho) {
        return Err("caminho inválido".into());
    }
    mostrar_principal(&app);
    let _ = app.emit_to("main", "sora-navegar", caminho);
    Ok(())
}

fn geometria_monitor<R: Runtime>(app: &AppHandle<R>) -> Option<(i32, i32, u32, u32, u64)> {
    let monitor = app.primary_monitor().ok().flatten()?;
    let p = monitor.position();
    let s = monitor.size();
    Some((
        p.x,
        p.y,
        s.width,
        s.height,
        monitor.scale_factor().to_bits(),
    ))
}

fn iniciar_poll_cursor(app: AppHandle, estado: IlhaEstado) {
    thread::spawn(move || {
        let mut dentro_anterior = false;
        let mut mouse_anterior = (f64::MIN, f64::MIN);
        let mut geometria_anterior = geometria_monitor(&app);
        let mut ticks = 0_u32;
        loop {
            {
                let (atividade, aviso) = &*estado.atividade;
                let mut ativa = atividade.lock().expect("estado da ilha envenenado");
                while !*ativa {
                    ativa = aviso.wait(ativa).expect("estado da ilha envenenado");
                }
            }

            while estado.ativa() {
                thread::sleep(Duration::from_millis(33));
                ticks = ticks.wrapping_add(1);
                if ticks.is_multiple_of(15) {
                    let geometria = geometria_monitor(&app);
                    if geometria.is_some() && geometria != geometria_anterior {
                        geometria_anterior = geometria;
                        posicionar_ilha(&app, &estado);
                    }
                }

                let Some(ilha) = janela(&app, "ilha") else {
                    continue;
                };
                let Ok(cursor) = app.cursor_position() else {
                    continue;
                };
                let Ok(origem) = ilha.outer_position() else {
                    continue;
                };
                let escala = ilha.scale_factor().unwrap_or(1.0);
                let x = (cursor.x - f64::from(origem.x)) / escala;
                let y = (cursor.y - f64::from(origem.y)) / escala;
                let r = *estado
                    .retangulo
                    .lock()
                    .expect("retângulo da ilha envenenado");
                let dentro = r.w > 0.0
                    && x >= r.x - MARGEM
                    && x <= r.x + r.w + MARGEM
                    && y >= r.y - MARGEM
                    && y <= r.y + r.h + MARGEM;

                let mudou_area = dentro != dentro_anterior;
                if mudou_area {
                    dentro_anterior = dentro;
                    definir_atravessar_cliques(&ilha, &estado, !dentro);
                }
                if (x - mouse_anterior.0).abs() >= 1.0
                    || (y - mouse_anterior.1).abs() >= 1.0
                    || mudou_area
                {
                    mouse_anterior = (x, y);
                    let _ = ilha.emit("ilha-mouse", MouseIlha { dentro, x, y });
                }
            }
        }
    });
}

/// Estado real `(em foco, minimizada)` da janela "main". "Em foco" = visível, não minimizada e
/// em primeiro plano. No Windows vem direto do sistema
/// (`GetForegroundWindow`/`IsIconic`): o foco do tao segue o WM_SETFOCUS da janela de topo, mas no
/// WebView2 o foco do teclado mora na janela filha, então ele pode dizer "sem foco" com a Sora na
/// frente (e a ilha aparecia dentro do app depois de restaurar).
#[cfg(windows)]
fn estado_da_principal<R: Runtime>(
    _app: &AppHandle<R>,
    estado: &IlhaEstado,
) -> Option<(bool, bool)> {
    use windows::Win32::{
        Foundation::HWND,
        UI::WindowsAndMessaging::{
            GA_ROOTOWNER, GetAncestor, GetForegroundWindow, IsIconic, IsWindowVisible,
        },
    };
    let principal = HWND(*estado.hwnd_principal.get()? as *mut core::ffi::c_void);
    // SAFETY: só leitura de estado de janelas; HWND inválido devolve falso/nulo, sem efeito.
    unsafe {
        let minimizada = IsIconic(principal).as_bool();
        let visivel = IsWindowVisible(principal).as_bool();
        let frente = GetForegroundWindow();
        let na_frente = !frente.is_invalid()
            && (frente == principal || GetAncestor(frente, GA_ROOTOWNER) == principal);
        Some((visivel && !minimizada && na_frente, minimizada))
    }
}

#[cfg(not(windows))]
fn estado_da_principal<R: Runtime>(
    app: &AppHandle<R>,
    _estado: &IlhaEstado,
) -> Option<(bool, bool)> {
    let main = janela(app, "main")?;
    let minimizada = main.is_minimized().unwrap_or(false);
    let foco = main.is_focused().unwrap_or(true) && main.is_visible().unwrap_or(true);
    Some((foco && !minimizada, minimizada))
}

/// A única thread que mostra/esconde a ilha. Reconcilia a cada 250 ms ou logo que for cutucada
/// (eventos de foco/tamanho/fechar da "main" e o comando `ilha_visivel`). Também cobre o app
/// aberto em segundo plano, quando nenhum evento de foco chega.
fn iniciar_vigia_foco(app: AppHandle, estado: IlhaEstado) {
    thread::spawn(move || {
        // dá tempo à janela de nascer e ganhar o foco inicial (evita piscar a ilha na abertura)
        thread::sleep(Duration::from_millis(800));
        let mut querendo_desde = None;
        loop {
            if let Some((foco, minimizada)) = estado_da_principal(&app, &estado) {
                estado.definir_foco_principal(foco);
                estado.definir_principal_minimizada(minimizada);
            }
            reconciliar(&app, &estado, &mut querendo_desde);
            // esperando para aparecer: confere de novo logo, para não atrasar além do necessário
            let espera = if querendo_desde.is_some() { 50 } else { 250 };
            estado.esperar_cutucada(Duration::from_millis(espera));
        }
    });
}

fn montar_bandeja(app: &tauri::App) -> tauri::Result<()> {
    let abrir = MenuItem::with_id(app, "abrir", "Abrir a Sora", true, None::<&str>)?;
    let alternar = MenuItem::with_id(
        app,
        "alternar-ilha",
        "Mostrar/ocultar a ilha",
        true,
        None::<&str>,
    )?;
    let sair = MenuItem::with_id(app, "sair", "Sair", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&abrir, &alternar, &sair])?;
    let mut bandeja = TrayIconBuilder::with_id("sora")
        .tooltip("Sora")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, evento| match evento.id.as_ref() {
            "abrir" => mostrar_principal(app),
            "alternar-ilha" => {
                // O WebView da ilha atualiza a preferência; a janela principal a repassa pelo
                // comando `ilha_visivel`. Nunca mostramos a janela diretamente aqui, porque isso
                // quebraria a regra da etapa 5 quando a janela principal estiver em foco.
                let _ = app.emit_to("ilha", "ilha-alternar", ());
            }
            "sair" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|bandeja, evento| {
            if matches!(
                evento,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                mostrar_principal(bandeja.app_handle());
            }
        });
    if let Some(icone) = app.default_window_icon() {
        bandeja = bandeja.icon(icone.clone());
    }
    bandeja.build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let estado = IlhaEstado::novo(true);
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            mostrar_principal(app)
        }))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, atalho, evento| {
                    if evento.state() != ShortcutState::Pressed {
                        return;
                    }
                    if pc::e_atalho_parar(atalho) {
                        pc::parar_local();
                    } else {
                        let _ = app.emit_to("ilha", "ilha-alternar", ());
                    }
                })
                .build(),
        )
        .manage(estado.clone())
        .manage(RotasNotificacao::default())
        .invoke_handler(tauri::generate_handler![
            ilha_emitir,
            ilha_retangulo,
            ilha_visivel,
            notificar_atencao,
            titulo_atencao,
            mostrar_app,
            navegar,
            cofre_ler,
            cofre_gravar,
            cofre_apagar,
            pc::pc_conta,
            pc::pc_autorizar,
            pc::pc_estado,
            pc::pc_executar,
            pc::pc_parar,
            pc::pc_sair
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            app.notification().on_action(move |acao| {
                if acao.action_id() != "tap" { return; }
                if let Some(id) = acao.notification().map(|n| n.id()) {
                    let caminho = handle.state::<RotasNotificacao>().0.lock().ok().and_then(|mut rotas| rotas.remove(&id));
                    if let Some(caminho) = caminho { mostrar_principal(&handle); let _ = handle.emit_to("main", "sora-navegar", caminho); }
                }
            })?;
            if let Some(ilha) = janela(app.handle(), "ilha") {
                #[cfg(windows)]
                if let Ok(hwnd) = ilha.hwnd() {
                    let _ = estado.hwnd_ilha.set(hwnd.0 as isize);
                    pc::regras::ilha_definir_janela(hwnd.0 as isize);
                }
                // cliques atravessam e a ilha não aceita foco até o mouse entrar na pílula
                // (ver iniciar_poll_cursor): aparecer não rouba o foco de quem estava digitando.
                definir_atravessar_cliques(&ilha, &estado, true);
            }
            posicionar_ilha(app.handle(), &estado);
            if let Some(main) = janela(app.handle(), "main")
                && let Ok(hwnd) = main.hwnd()
            {
                let _ = estado.hwnd_principal.set(hwnd.0 as isize);
            }
            app.global_shortcut().register("Ctrl+Shift+S")?;
            pc::iniciar(app.handle());
            montar_bandeja(app)?;
            iniciar_poll_cursor(app.handle().clone(), estado.clone());
            iniciar_vigia_foco(app.handle().clone(), estado.clone());
            Ok(())
        })
        .on_window_event(|janela, evento| {
            if janela.label() != "main" {
                return;
            }
            match evento {
                // foco, minimizar/restaurar: a vigia lê o estado real e decide na hora.
                tauri::WindowEvent::Focused(_) | tauri::WindowEvent::Resized(_) => {
                    janela.app_handle().state::<IlhaEstado>().cutucar();
                }
                // fechar esconde na bandeja (não fecha de verdade): também é "fora do app".
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    api.prevent_close();
                    let _ = janela.hide();
                    janela.app_handle().state::<IlhaEstado>().cutucar();
                }
                _ => {}
            }
        })
        .run(tauri::generate_context!())
        .expect("erro ao executar a Sora");
}

#[cfg(test)]
mod testes {
    use super::*;

    /// Textos que o usuário lê (aviso do sistema, erros) já saíram com o acento trocado por interrogação
    /// ("Precisa de voc?", "inv?lida"). Letra + interrogação + letra, ou letra + interrogação + aspas de
    /// fechamento, só existe assim em texto: no código Rust a interrogação (operador) vem depois de uma
    /// expressão e antes de ponto, ponto e vírgula, parêntese ou espaço.
    #[test]
    fn textos_do_rust_nao_perdem_acento() {
        let fontes = [
            ("lib.rs", include_str!("lib.rs")),
            ("pc/mod.rs", include_str!("pc/mod.rs")),
            ("pc/regras.rs", include_str!("pc/regras.rs")),
            ("pc/sistema.rs", include_str!("pc/sistema.rs")),
            ("pc/borda.rs", include_str!("pc/borda.rs")),
        ];
        for (arquivo, fonte) in fontes {
            for (n, linha) in fonte.lines().enumerate() {
                if linha.trim_start().starts_with("//") {
                    continue;
                }
                let c: Vec<char> = linha.chars().collect();
                for i in 1..c.len().saturating_sub(1) {
                    let perdeu = c[i] == '?' && c[i - 1].is_alphabetic() && (c[i + 1].is_alphabetic() || c[i + 1] == '"');
                    assert!(!perdeu, "{arquivo}:{}: acento perdido (interrogação no fim ou no meio de uma palavra): {}", n + 1, linha.trim());
                }
            }
        }
    }

    #[test]
    fn retangulo_rejeita_valores_ruins() {
        assert!(validar_retangulo(100.0, 0.0, 600.0, 400.0).is_some());
        assert!(validar_retangulo(f64::NAN, 0.0, 10.0, 10.0).is_none());
        assert!(validar_retangulo(-1.0, 0.0, 10.0, 10.0).is_none());
        let r = validar_retangulo(0.0, 0.0, 5000.0, 10.0).unwrap();
        assert!(r.w <= ILHA_LARGURA);
        assert!(validar_retangulo(0.0, 0.0, f64::INFINITY, 10.0).is_none());
    }

    #[test]
    fn caminho_aceita_so_rotas_internas() {
        assert!(caminho_interno_valido("/revisao/abc-1"));
        assert!(!caminho_interno_valido("//evil.com"));
        assert!(!caminho_interno_valido("https://evil.com"));
        assert!(!caminho_interno_valido("javascript:alert(1)"));
        assert!(!caminho_interno_valido("/a/../b"));
        assert!(!caminho_interno_valido("/a\\b"));
    }

    #[test]
    fn cada_comando_so_na_sua_janela() {
        assert!(janela_pode("ilha_retangulo", "ilha"));
        assert!(janela_pode("navegar", "ilha"));
        assert!(janela_pode("ilha_visivel", "main"));
        assert!(!janela_pode("ilha_retangulo", "main"));
        assert!(!janela_pode("navegar", "main"));
        assert!(!janela_pode("ilha_visivel", "ilha"));
        assert!(!janela_pode("mostrar_app", "main"));
        assert!(!janela_pode("mostrar_app", "ilha"));
        assert!(!janela_pode("navegar", "outra"));
    }

    /// A ilha só aparece fora do app: permitida pelo usuário e a janela principal sem foco.
    #[test]
    fn ilha_so_aparece_fora_do_app() {
        assert!(
            !deveria_estar_visivel(true, true, false),
            "main em foco: ilha some, mesmo permitida"
        );
        assert!(
            deveria_estar_visivel(true, false, false),
            "main fora de foco e permitida: ilha aparece"
        );
        assert!(
            deveria_estar_visivel(true, false, true),
            "main minimizada: ilha aparece"
        );
        assert!(
            deveria_estar_visivel(true, true, true),
            "minimizada vale mesmo que o foco ainda não tenha sido atualizado"
        );
        assert!(
            !deveria_estar_visivel(false, false, true),
            "desligada pelo usuário: nunca aparece"
        );
        assert!(
            !deveria_estar_visivel(false, true, false),
            "desligada e em foco: nunca aparece"
        );
    }

    /// Minimizar ou escolher outro programa tira o foco da "main" antes de qualquer outra coisa
    /// no Windows; o estado inicial (`IlhaEstado::novo`) assume a main em foco, então a ilha nasce
    /// escondida (não pisca visível no instante entre abrir o app e ele ganhar foco).
    #[test]
    fn estado_inicial_comeca_com_a_main_em_foco() {
        let estado = IlhaEstado::novo(true);
        assert!(!estado.deveria_estar_visivel());
        estado.definir_foco_principal(false);
        assert!(estado.deveria_estar_visivel());
        estado.definir_foco_principal(true);
        estado.definir_principal_minimizada(true);
        assert!(estado.deveria_estar_visivel());
    }

    /// As capabilities liberam exatamente os comandos da tabela, uma por janela (APP-003).
    #[test]
    fn capabilities_batem_com_a_tabela() {
        let main = include_str!("../capabilities/main.json");
        let ilha = include_str!("../capabilities/ilha.json");
        assert!(main.contains(r#""windows": ["main"]"#));
        assert!(ilha.contains(r#""windows": ["ilha"]"#));
        for (comando, janela) in COMANDOS_POR_JANELA {
            let permissao = format!("\"allow-{}\"", comando.replace('_', "-"));
            let (dono, outra) = if *janela == "main" {
                (main, ilha)
            } else {
                (ilha, main)
            };
            assert!(dono.contains(&permissao), "{permissao} falta em {janela}");
            assert!(
                !outra.contains(&permissao),
                "{permissao} sobrando na outra janela"
            );
        }
        for cap in [main, ilha] {
            assert!(!cap.contains("allow-mostrar-app"));
            assert!(!cap.contains("core:default"));
        }
        assert!(
            !std::path::Path::new(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/capabilities/default.json"
            ))
            .exists()
        );
    }
}

#[cfg(test)]
mod testes_eventos_pc {
    #[test]
    fn ilha_nao_forja_eventos_pc() {
        assert!(!super::evento_ilha_permitido("pc-estado"));
        assert!(!super::evento_ilha_permitido("pc-parar"));
        assert!(super::evento_ilha_permitido("sora-armazenamento"));
        let cap: serde_json::Value = serde_json::from_str(include_str!("../capabilities/ilha.json")).unwrap();
        assert!(!cap["permissions"].as_array().unwrap().iter().any(|p| p == "core:event:allow-emit"));
    }
}
