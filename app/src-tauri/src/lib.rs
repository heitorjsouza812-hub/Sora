use std::{
    sync::{Arc, Condvar, Mutex},
    thread,
    time::Duration,
};

use serde::Serialize;
use tauri::{
    AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, Runtime, State, WebviewWindow,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

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

#[derive(Clone)]
struct IlhaEstado {
    retangulo: Arc<Mutex<RetanguloIlha>>,
    atividade: Arc<(Mutex<bool>, Condvar)>,
}

impl IlhaEstado {
    fn novo(visivel: bool) -> Self {
        Self {
            retangulo: Arc::new(Mutex::new(RetanguloIlha::default())),
            atividade: Arc::new((Mutex::new(visivel), Condvar::new())),
        }
    }

    fn definir_ativa(&self, ativa: bool) {
        let (estado, aviso) = &*self.atividade;
        *estado.lock().expect("estado da ilha envenenado") = ativa;
        aviso.notify_all();
    }

    fn ativa(&self) -> bool {
        *self.atividade.0.lock().expect("estado da ilha envenenado")
    }
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

fn posicionar_ilha<R: Runtime>(app: &AppHandle<R>) {
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
    let _ = ilha.set_size(LogicalSize::new(ILHA_LARGURA, ILHA_ALTURA));
    let _ = ilha.set_position(PhysicalPosition::new(x, origem.y));
}

fn definir_visibilidade<R: Runtime>(app: &AppHandle<R>, estado: &IlhaEstado, visivel: bool) {
    let Some(ilha) = janela(app, "ilha") else {
        return;
    };
    if visivel {
        posicionar_ilha(app);
        let _ = ilha.show();
        estado.definir_ativa(true);
    } else {
        estado.definir_ativa(false);
        let _ = ilha.hide();
    }
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
    ("cofre_ler", "main"),
    ("cofre_gravar", "main"),
    ("cofre_apagar", "main"),
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
    app: AppHandle,
    estado: State<'_, IlhaEstado>,
) -> Result<(), String> {
    if !janela_pode("ilha_visivel", janela.label()) {
        return Err("só a janela principal liga/desliga a ilha".into());
    }
    definir_visibilidade(&app, &estado, visivel);
    Ok(())
}

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

#[cfg(test)]
mod testes {
    use super::*;

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
                        posicionar_ilha(&app);
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
                    let _ = ilha.set_ignore_cursor_events(!dentro);
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
                let estado = app.state::<IlhaEstado>();
                definir_visibilidade(app, &estado, !estado.ativa());
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
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            mostrar_principal(app)
        }))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _atalho, evento| {
                    if evento.state() == ShortcutState::Pressed {
                        let _ = app.emit_to("ilha", "ilha-alternar", ());
                    }
                })
                .build(),
        )
        .manage(estado.clone())
        .invoke_handler(tauri::generate_handler![
            ilha_retangulo,
            ilha_visivel,
            mostrar_app,
            navegar,
            cofre_ler,
            cofre_gravar,
            cofre_apagar
        ])
        .setup(move |app| {
            posicionar_ilha(app.handle());
            if let Some(ilha) = janela(app.handle(), "ilha") {
                let _ = ilha.set_ignore_cursor_events(true);
            }
            app.global_shortcut().register("Ctrl+Shift+S")?;
            montar_bandeja(app)?;
            iniciar_poll_cursor(app.handle().clone(), estado.clone());
            Ok(())
        })
        .on_window_event(|janela, evento| {
            if janela.label() == "main"
                && let tauri::WindowEvent::CloseRequested { api, .. } = evento
            {
                api.prevent_close();
                let _ = janela.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("erro ao executar a Sora");
}
