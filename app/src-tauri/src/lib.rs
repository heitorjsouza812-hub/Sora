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
fn ilha_retangulo(x: f64, y: f64, w: f64, h: f64, estado: State<'_, IlhaEstado>) {
    *estado
        .retangulo
        .lock()
        .expect("retângulo da ilha envenenado") = RetanguloIlha { x, y, w, h };
}

#[tauri::command]
fn ilha_visivel(visivel: bool, app: AppHandle, estado: State<'_, IlhaEstado>) {
    definir_visibilidade(&app, &estado, visivel);
}

#[tauri::command]
fn mostrar_app(app: AppHandle) {
    mostrar_principal(&app);
}

#[tauri::command]
fn navegar(caminho: String, app: AppHandle) {
    mostrar_principal(&app);
    let _ = app.emit_to("main", "sora-navegar", caminho);
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
            navegar
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
