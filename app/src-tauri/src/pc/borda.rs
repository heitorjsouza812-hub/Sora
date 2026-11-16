//! Enquanto um bot controla o PC (C3): **borda acesa** na tela, na cor do bot, e a pílula com
//! **Parar** sempre visível; e a **vigia de entrada física**, que pausa o bot quando o usuário
//! mexe no mouse ou no teclado.
//!
//! Tudo em Win32 nativo, numa thread própria com fila de mensagens (sem WebView: nada do conteúdo
//! web influencia a borda). As quatro faixas da borda deixam os cliques passarem
//! (`WS_EX_TRANSPARENT`, como a ilha fora da pílula); a pílula aceita clique sem roubar o foco
//! (`WS_EX_NOACTIVATE`). Nenhuma delas aparece na captura que vai para o bot
//! (`WDA_EXCLUDEFROMCAPTURE`).
//!
//! A vigia usa ganchos de baixo nível (`WH_MOUSE_LL`/`WH_KEYBOARD_LL`) só enquanto um bot
//! controla. Entrada com a flag "injetada" ou com a marca da Sora é do bot; o resto é o usuário.

#![allow(unsafe_code)]

use std::{
    cell::Cell,
    sync::{
        Mutex, OnceLock,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
};

use windows::{
    Win32::{
        Foundation::{COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, WPARAM},
        Graphics::Gdi::{
            BeginPaint, CLEARTYPE_QUALITY, CLIP_DEFAULT_PRECIS, CreateFontW, CreateRoundRectRgn, CreateSolidBrush,
            DEFAULT_CHARSET, DT_CENTER, DT_END_ELLIPSIS, DT_SINGLELINE, DT_VCENTER, DeleteObject, DrawTextW, Ellipse,
            EndPaint, FF_SWISS, FW_SEMIBOLD, FillRect, GetStockObject, InvalidateRect, NULL_PEN, OUT_DEFAULT_PRECIS,
            PAINTSTRUCT, RoundRect, ScreenToClient, SelectObject, SetBkMode, SetTextColor, SetWindowRgn, TRANSPARENT,
        },
        System::{LibraryLoader::GetModuleHandleW, Threading::GetCurrentThreadId},
        UI::{
            HiDpi::GetDpiForWindow,
            WindowsAndMessaging::{
                CallNextHookEx, CreateWindowExW, DefWindowProcW, DispatchMessageW, GetClientRect, GetCursorPos,
                GetMessageW, GetSystemMetrics, HC_ACTION, HHOOK, HTTRANSPARENT, HWND_TOPMOST, IDC_ARROW, IDC_HAND,
                KBDLLHOOKSTRUCT, LLMHF_INJECTED, LWA_ALPHA, LoadCursorW, MA_NOACTIVATE, MSG, MSLLHOOKSTRUCT,
                PM_NOREMOVE, PeekMessageW, PostThreadMessageW, RegisterClassExW, SM_CXSCREEN, SM_CYSCREEN,
                SPI_GETWORKAREA, SW_HIDE, SWP_NOACTIVATE, SWP_SHOWWINDOW, SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS,
                SetCursor, SetLayeredWindowAttributes, SetWindowDisplayAffinity, SetWindowPos, SetWindowsHookExW,
                ShowWindow, SystemParametersInfoW, TranslateMessage, UnhookWindowsHookEx, WDA_EXCLUDEFROMCAPTURE,
                WH_KEYBOARD_LL, WH_MOUSE_LL, WM_APP, WM_ERASEBKGND, WM_LBUTTONUP, WM_MOUSEACTIVATE, WM_MOUSEMOVE,
                WM_NCHITTEST, WM_PAINT, WM_SETCURSOR, WNDCLASSEXW, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
                WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_POPUP,
            },
        },
    },
    core::{PCWSTR, w},
};

use super::sistema::MARCA_SORA;

const WM_ATUALIZAR: u32 = WM_APP + 1;
const WM_ENTRADA: u32 = WM_APP + 2;
const LLKHF_INJETADA: u32 = 0x10 | 0x02;
const LLMHF_INJETADA: u32 = LLMHF_INJECTED | 0x02;
/// Movimento físico do mouse que conta como "o usuário pegou o mouse" (px).
const LIMIAR_MOVIMENTO: i32 = 0;

static PRONTA: AtomicBool = AtomicBool::new(false);

/// Nunca injeta entrada se a borda, Parar ou os ganchos físicos falharam ao iniciar.
pub fn pronta() -> bool {
    PRONTA.load(Ordering::SeqCst)
}

/// Espera a borda e os ganchos ficarem prontos (Vela-12). Pegar o controle manda acender a borda
/// por mensagem à thread dela; o primeiro comando (agora pode ser `abrir_programa`, não só
/// `observar`) chegava antes e era recusado. Nunca age sem eles: só espera um pouco.
pub fn esperar_pronta(prazo: std::time::Duration) -> bool {
    let inicio = std::time::Instant::now();
    while !pronta() {
        if inicio.elapsed() >= prazo {
            return false;
        }
        thread::sleep(std::time::Duration::from_millis(15));
    }
    true
}

#[derive(Clone)]
pub struct InfoBorda {
    pub visivel: bool,
    pub cor: (u8, u8, u8),
    pub nome: String,
    pub pausado: bool,
}

static INFO: Mutex<InfoBorda> =
    Mutex::new(InfoBorda { visivel: false, cor: (0xE2, 0xEC, 0xFF), nome: String::new(), pausado: false });
static THREAD: OnceLock<u32> = OnceLock::new();
static SINALIZADA: AtomicBool = AtomicBool::new(false);

thread_local! {
    static JANELAS: Cell<[isize; 5]> = const { Cell::new([0; 5]) };
    static GANCHOS: Cell<(isize, isize)> = const { Cell::new((0, 0)) };
    static BASE_MOUSE: Cell<Option<(i32, i32)>> = const { Cell::new(None) };
}

fn rgb((r, g, b): (u8, u8, u8)) -> COLORREF {
    COLORREF(u32::from(r) | (u32::from(g) << 8) | (u32::from(b) << 16))
}

fn info() -> InfoBorda {
    INFO.lock().map(|i| i.clone()).unwrap_or(InfoBorda { visivel: false, cor: (0, 0, 0), nome: String::new(), pausado: false })
}

/// Mostra, atualiza ou esconde a borda (qualquer thread).
pub fn atualizar(novo: InfoBorda) {
    if let Ok(mut atual) = INFO.lock() {
        *atual = novo;
    }
    let id = *THREAD.get_or_init(iniciar_thread);
    if id != 0 {
        // SAFETY: mensagem para a fila da thread da borda.
        unsafe {
            let _ = PostThreadMessageW(id, WM_ATUALIZAR, WPARAM(0), LPARAM(0));
        }
    }
}

fn iniciar_thread() -> u32 {
    let (tx, rx) = mpsc::channel();
    let criada = thread::Builder::new().name("sora-pc-borda".into()).spawn(move || {
        // SAFETY: tudo nesta thread: cria a fila, as janelas e roda o laço de mensagens.
        unsafe {
            let mut msg = MSG::default();
            let _ = PeekMessageW(&mut msg, None, 0, 0, PM_NOREMOVE); // cria a fila antes de avisar
            criar_janelas();
            let _ = tx.send(GetCurrentThreadId());
            while GetMessageW(&mut msg, None, 0, 0).as_bool() {
                if msg.hwnd.is_invalid() {
                    match msg.message {
                        WM_ATUALIZAR => aplicar(),
                        WM_ENTRADA => {
                            SINALIZADA.store(false, Ordering::SeqCst);
                            super::ao_entrada_fisica();
                        }
                        _ => {}
                    }
                    continue;
                }
                let _ = TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
        }
    });
    if criada.is_err() {
        return 0;
    }
    rx.recv().unwrap_or(0)
}

unsafe fn criar_janelas() {
    // SAFETY: chamado só na thread da borda; classes e janelas desta thread.
    unsafe {
        let Ok(modulo) = GetModuleHandleW(None) else { return };
        let instancia = modulo.into();
        let seta = LoadCursorW(None, IDC_ARROW).ok();
        for (nome, proc_) in [
            (w!("SoraPcBorda"), proc_borda as unsafe extern "system" fn(HWND, u32, WPARAM, LPARAM) -> LRESULT),
            (w!("SoraPcParar"), proc_parar),
        ] {
            let classe = WNDCLASSEXW {
                cbSize: size_of::<WNDCLASSEXW>() as u32,
                lpfnWndProc: Some(proc_),
                hInstance: instancia,
                hCursor: seta.unwrap_or_default(),
                lpszClassName: nome,
                ..Default::default()
            };
            RegisterClassExW(&classe);
        }
        let mut janelas = [0isize; 5];
        for (i, slot) in janelas.iter_mut().enumerate() {
            let (classe, extra) = if i < 4 {
                (w!("SoraPcBorda"), WS_EX_TRANSPARENT)
            } else {
                (w!("SoraPcParar"), Default::default())
            };
            let Ok(hwnd) = CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE | extra,
                classe,
                w!("Sora"),
                WS_POPUP,
                0,
                0,
                1,
                1,
                None,
                None,
                Some(instancia),
                None,
            ) else {
                continue;
            };
            let _ = SetLayeredWindowAttributes(hwnd, COLORREF(0), 235, LWA_ALPHA);
            let _ = SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE);
            *slot = hwnd.0 as isize;
        }
        JANELAS.set(janelas);
    }
}

fn hw(v: isize) -> HWND {
    HWND(v as *mut core::ffi::c_void)
}

fn escala(hwnd: HWND) -> f64 {
    // SAFETY: só leitura.
    let dpi = unsafe { GetDpiForWindow(hwnd) };
    if dpi == 0 { 1.0 } else { f64::from(dpi) / 96.0 }
}

unsafe fn aplicar() {
    PRONTA.store(false, Ordering::SeqCst);
    let info = info();
    let janelas = JANELAS.get();
    // SAFETY: janelas desta thread.
    unsafe {
        if !info.visivel {
            for j in janelas.iter().filter(|j| **j != 0) {
                let _ = ShowWindow(hw(*j), SW_HIDE);
            }
            desligar_ganchos();
            return;
        }
        let (largura, altura) = (GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
        let k = escala(hw(janelas[4]));
        let grossura = (5.0 * k).round() as i32;
        let faixas = [
            (0, 0, largura, grossura),
            (0, altura - grossura, largura, grossura),
            (0, 0, grossura, altura),
            (largura - grossura, 0, grossura, altura),
        ];
        let alfa = if info.pausado { 120 } else { 235 };
        for (j, (x, y, w, h)) in janelas.iter().zip(faixas) {
            if *j == 0 {
                continue;
            }
            let _ = SetLayeredWindowAttributes(hw(*j), COLORREF(0), alfa, LWA_ALPHA);
            let _ = SetWindowPos(hw(*j), Some(HWND_TOPMOST), x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW);
            let _ = InvalidateRect(Some(hw(*j)), None, true);
        }
        if janelas[4] != 0 {
            let (pw, ph) = ((470.0 * k).round() as i32, (52.0 * k).round() as i32);
            let mut area = RECT { left: 0, top: 0, right: largura, bottom: altura };
            let _ = SystemParametersInfoW(
                SPI_GETWORKAREA,
                0,
                Some((&mut area as *mut RECT).cast()),
                SYSTEM_PARAMETERS_INFO_UPDATE_FLAGS(0),
            );
            let x = area.left + (area.right - area.left - pw) / 2;
            let y = area.bottom - ph - (20.0 * k).round() as i32;
            let parar = hw(janelas[4]);
            let _ = SetLayeredWindowAttributes(parar, COLORREF(0), 245, LWA_ALPHA);
            let _ = SetWindowPos(parar, Some(HWND_TOPMOST), x, y, pw, ph, SWP_NOACTIVATE | SWP_SHOWWINDOW);
            SetWindowRgn(parar, Some(CreateRoundRectRgn(0, 0, pw + 1, ph + 1, ph, ph)), true);
            let _ = InvalidateRect(Some(parar), None, true);
        }
        BASE_MOUSE.set(None);
        ligar_ganchos();
    }
}

// ---------- pintura ----------

unsafe extern "system" fn proc_borda(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    // SAFETY: janela desta thread; GDI criado e liberado aqui.
    unsafe {
        match msg {
            WM_NCHITTEST => LRESULT(HTTRANSPARENT as isize),
            WM_ERASEBKGND => LRESULT(1),
            WM_PAINT => {
                let mut ps = PAINTSTRUCT::default();
                let dc = BeginPaint(hwnd, &mut ps);
                let pincel = CreateSolidBrush(rgb(info().cor));
                FillRect(dc, &ps.rcPaint, pincel);
                let _ = DeleteObject(pincel.into());
                let _ = EndPaint(hwnd, &ps);
                LRESULT(0)
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }
}

fn retangulo_botao(cliente: &RECT, k: f64) -> RECT {
    let margem = (8.0 * k).round() as i32;
    RECT {
        left: cliente.right - (104.0 * k).round() as i32,
        top: cliente.top + margem,
        right: cliente.right - margem,
        bottom: cliente.bottom - margem,
    }
}

unsafe fn texto(dc: windows::Win32::Graphics::Gdi::HDC, s: &str, r: &mut RECT, alinhar_centro: bool) {
    let mut largo: Vec<u16> = s.encode_utf16().collect();
    let mut formato = DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS;
    if alinhar_centro {
        formato |= DT_CENTER;
    }
    // SAFETY: DC válido do WM_PAINT.
    unsafe {
        DrawTextW(dc, &mut largo, r, formato);
    }
}

unsafe extern "system" fn proc_parar(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    // SAFETY: janela desta thread; GDI criado e liberado aqui.
    unsafe {
        match msg {
            WM_MOUSEACTIVATE => LRESULT(MA_NOACTIVATE as isize),
            WM_ERASEBKGND => LRESULT(1),
            WM_SETCURSOR => {
                let mut p = POINT::default();
                let _ = GetCursorPos(&mut p);
                let _ = ScreenToClient(hwnd, &mut p);
                let mut c = RECT::default();
                let _ = GetClientRect(hwnd, &mut c);
                let b = retangulo_botao(&c, escala(hwnd));
                let cursor = if p.x >= b.left && p.x <= b.right { IDC_HAND } else { IDC_ARROW };
                if let Ok(c) = LoadCursorW(None, cursor) {
                    SetCursor(Some(c));
                }
                LRESULT(1)
            }
            WM_LBUTTONUP => {
                let (x, y) = ((lparam.0 & 0xFFFF) as i16 as i32, ((lparam.0 >> 16) & 0xFFFF) as i16 as i32);
                let mut c = RECT::default();
                let _ = GetClientRect(hwnd, &mut c);
                let b = retangulo_botao(&c, escala(hwnd));
                if x >= b.left && x <= b.right && y >= b.top && y <= b.bottom {
                    super::parar_local();
                }
                LRESULT(0)
            }
            WM_PAINT => {
                let info = info();
                let k = escala(hwnd);
                let mut ps = PAINTSTRUCT::default();
                let dc = BeginPaint(hwnd, &mut ps);
                let mut c = RECT::default();
                let _ = GetClientRect(hwnd, &mut c);
                let fundo = CreateSolidBrush(COLORREF(0x0015_110F)); // #0F1115
                FillRect(dc, &c, fundo);
                let _ = DeleteObject(fundo.into());
                let caneta = SelectObject(dc, GetStockObject(NULL_PEN));
                // bolinha na cor do bot
                let cor = CreateSolidBrush(rgb(info.cor));
                let antigo = SelectObject(dc, cor.into());
                let d = (12.0 * k).round() as i32;
                let cy = (c.bottom - c.top) / 2;
                let x0 = (20.0 * k).round() as i32;
                let _ = Ellipse(dc, x0, cy - d / 2, x0 + d, cy + d / 2);
                // botão Parar (claro, como o botão principal da Sora)
                let b = retangulo_botao(&c, k);
                let claro = CreateSolidBrush(COLORREF(0x00FA_F2EE)); // #EEF2FA
                SelectObject(dc, claro.into());
                let _ = RoundRect(dc, b.left, b.top, b.right, b.bottom, b.bottom - b.top, b.bottom - b.top);
                SelectObject(dc, antigo);
                SelectObject(dc, caneta);
                let _ = DeleteObject(cor.into());
                let _ = DeleteObject(claro.into());
                let fonte = CreateFontW(
                    -(15.0 * k).round() as i32,
                    0,
                    0,
                    0,
                    FW_SEMIBOLD.0 as i32,
                    0,
                    0,
                    0,
                    DEFAULT_CHARSET,
                    OUT_DEFAULT_PRECIS,
                    CLIP_DEFAULT_PRECIS,
                    CLEARTYPE_QUALITY,
                    u32::from(FF_SWISS.0),
                    w!("Segoe UI"),
                );
                let fonte_antiga = SelectObject(dc, fonte.into());
                SetBkMode(dc, TRANSPARENT);
                SetTextColor(dc, COLORREF(0x00FB_F5F2)); // #F2F5FB
                let frase = if info.pausado {
                    format!("{} pausou: você mexeu no computador", info.nome)
                } else {
                    format!("{} está usando o seu computador", info.nome)
                };
                let mut r = RECT { left: x0 + d + (12.0 * k).round() as i32, top: c.top, right: b.left - (10.0 * k).round() as i32, bottom: c.bottom };
                texto(dc, &frase, &mut r, false);
                SetTextColor(dc, COLORREF(0x0012_0D0B)); // #0B0D12
                let mut rb = b;
                texto(dc, "Parar", &mut rb, true);
                SelectObject(dc, fonte_antiga);
                let _ = DeleteObject(fonte.into());
                let _ = EndPaint(hwnd, &ps);
                LRESULT(0)
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }
}

// ---------- vigia de entrada física ----------

fn sinalizar() {
    if SINALIZADA.swap(true, Ordering::SeqCst) {
        return;
    }
    if let Some(id) = THREAD.get() {
        // SAFETY: mensagem para a fila desta mesma thread (o gancho roda nela).
        unsafe {
            let _ = PostThreadMessageW(*id, WM_ENTRADA, WPARAM(0), LPARAM(0));
        }
    }
}

unsafe extern "system" fn gancho_mouse(codigo: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if codigo == HC_ACTION as i32 {
        // SAFETY: o Windows passa um MSLLHOOKSTRUCT válido em `lparam` para WH_MOUSE_LL.
        let dados = unsafe { &*(lparam.0 as *const MSLLHOOKSTRUCT) };
        let do_bot = dados.flags & LLMHF_INJETADA != 0 || dados.dwExtraInfo == MARCA_SORA;
        if !do_bot {
            if wparam.0 as u32 == WM_MOUSEMOVE {
                let (x, y) = (dados.pt.x, dados.pt.y);
                match BASE_MOUSE.get() {
                    None => {
                        BASE_MOUSE.set(Some((x, y)));
                        sinalizar();
                    }
                    Some((bx, by)) if (x - bx).pow(2) + (y - by).pow(2) > LIMIAR_MOVIMENTO.pow(2) => sinalizar(),
                    Some(_) => {}
                }
            } else {
                sinalizar(); // clique ou roda
            }
        }
    }
    // SAFETY: repassa ao próximo gancho, como manda a documentação.
    unsafe { CallNextHookEx(None, codigo, wparam, lparam) }
}

unsafe extern "system" fn gancho_teclado(codigo: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if codigo == HC_ACTION as i32 {
        // SAFETY: o Windows passa um KBDLLHOOKSTRUCT válido em `lparam` para WH_KEYBOARD_LL.
        let dados = unsafe { &*(lparam.0 as *const KBDLLHOOKSTRUCT) };
        if dados.flags.0 & LLKHF_INJETADA == 0 && dados.dwExtraInfo != MARCA_SORA {
            sinalizar();
        }
    }
    // SAFETY: repassa ao próximo gancho.
    unsafe { CallNextHookEx(None, codigo, wparam, lparam) }
}

unsafe fn ligar_ganchos() {
    if GANCHOS.get() != (0, 0) {
        let (mouse, teclado) = GANCHOS.get();
        PRONTA.store(mouse != 0 && teclado != 0 && JANELAS.get().iter().all(|j| *j != 0), Ordering::SeqCst);
        return;
    }
    // SAFETY: ganchos globais de baixo nível desta thread (que tem laço de mensagens).
    unsafe {
        let Ok(modulo) = GetModuleHandleW(PCWSTR::null()) else { return };
        let mouse = SetWindowsHookExW(WH_MOUSE_LL, Some(gancho_mouse), Some(modulo.into()), 0)
            .map(|h| h.0 as isize)
            .unwrap_or(0);
        let teclado = SetWindowsHookExW(WH_KEYBOARD_LL, Some(gancho_teclado), Some(modulo.into()), 0)
            .map(|h| h.0 as isize)
            .unwrap_or(0);
        GANCHOS.set((mouse, teclado));
        PRONTA.store(mouse != 0 && teclado != 0 && JANELAS.get().iter().all(|j| *j != 0), Ordering::SeqCst);
    }
}

unsafe fn desligar_ganchos() {
    let (mouse, teclado) = GANCHOS.get();
    // SAFETY: ganchos instalados por esta thread.
    unsafe {
        for g in [mouse, teclado] {
            if g != 0 {
                let _ = UnhookWindowsHookEx(HHOOK(g as *mut core::ffi::c_void));
            }
        }
    }
    GANCHOS.set((0, 0));
}
