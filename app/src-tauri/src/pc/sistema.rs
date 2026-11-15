//! O PC de verdade (Windows): captura da tela principal, janelas de topo, árvore de UI Automation
//! da janela em foco, campo de senha (`IsPassword`) e entrada por `SendInput`.
//!
//! Ideia do agent-desktop (Apache-2.0, `docs/referencias/agent-desktop.md`): observar a janela como
//! árvore de elementos com refs. Nada copiado; reescrito para UI Automation.
//!
//! Toda entrada injetada leva `MARCA_SORA` em `dwExtraInfo` e a flag "injetada" do Windows: é assim
//! que a vigia de entrada física (`borda.rs`) separa o bot do usuário.

#![allow(unsafe_code)]

use base64::Engine;
use serde_json::{Value, json};
use windows::{
    Win32::{
        Foundation::{CloseHandle, HWND, LPARAM, POINT, RECT},
        Graphics::{
            Dwm::{DWMWA_CLOAKED, DwmGetWindowAttribute},
            Gdi::{
                BI_RGB, BITMAPINFO, BITMAPINFOHEADER, CAPTUREBLT, CreateCompatibleBitmap, CreateCompatibleDC,
                DIB_RGB_COLORS, DeleteDC, DeleteObject, GetDC, GetDIBits, HALFTONE, ROP_CODE, ReleaseDC, SRCCOPY,
                SelectObject, SetBrushOrgEx, SetStretchBltMode, StretchBlt,
            },
        },
        System::{
            Com::{CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED, CoCreateInstance, CoInitializeEx},
            Diagnostics::ToolHelp::{
                CreateToolhelp32Snapshot, PROCESSENTRY32W, Process32FirstW, Process32NextW, TH32CS_SNAPPROCESS,
            },
            Threading::{
                OpenProcess, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_TERMINATE,
                QueryFullProcessImageNameW, TerminateProcess,
            },
        },
        UI::{
            Accessibility::{
                CUIAutomation, IUIAutomation, IUIAutomation2, IUIAutomationElement, TreeScope_Descendants,
                UIA_BoundingRectanglePropertyId, UIA_CONTROLTYPE_ID, UIA_ControlTypePropertyId,
                UIA_HasKeyboardFocusPropertyId, UIA_IsEnabledPropertyId, UIA_IsOffscreenPropertyId,
                UIA_IsPasswordPropertyId, UIA_NamePropertyId, UIA_ValueValuePropertyId,
            },
            Input::KeyboardAndMouse::{
                GetKeyState, GetKeyboardLayout, INPUT, INPUT_0, INPUT_KEYBOARD, INPUT_MOUSE, KEYBD_EVENT_FLAGS,
                KEYBDINPUT, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, MAPVK_VK_TO_CHAR,
                MOUSE_EVENT_FLAGS, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_HWHEEL, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
                MOUSEEVENTF_MOVE, MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, MOUSEEVENTF_WHEEL, MOUSEINPUT,
                MapVirtualKeyExW, SendInput, VIRTUAL_KEY, VK_CAPITAL, VkKeyScanExW,
            },
            WindowsAndMessaging::{
                EnumChildWindows, EnumWindows, GA_ROOT, GWL_EXSTYLE, GetAncestor, GetForegroundWindow, GetSystemMetrics,
                GetClassNameW, GetWindowLongPtrW, GetWindowRect, GetWindowTextW, GetWindowThreadProcessId, IsIconic, IsWindowVisible,
                SM_CXSCREEN, SM_CYSCREEN, SetForegroundWindow, WS_EX_TOOLWINDOW, WindowFromPoint,
            },
        },
    },
    core::{BOOL, BSTR, Interface, PWSTR},
};

use super::regras::{AlvoJanela, Botao, ErroPc, Passo, normalizar_programa, programa_bloqueado, titulo_bloqueado};

/// Marca das entradas da Sora (`dwExtraInfo`): "SORA".
pub const MARCA_SORA: usize = 0x534F_5241;
/// Largura máxima da captura enviada ao bot (o resto da tela é reduzido na mesma proporção).
const LARGURA_MAXIMA: i32 = 1280;
const MAX_ELEMENTOS: usize = 250;
const MAX_JANELAS: usize = 25;

/// Tela principal: tamanho físico, tamanho da captura e a escala entre os dois.
#[derive(Clone, Copy, Debug)]
pub struct Tela {
    pub largura_fisica: i32,
    pub altura_fisica: i32,
    pub largura: i32,
    pub altura: i32,
    /// Pixels físicos por pixel da captura.
    pub escala: f64,
}

pub fn tela() -> Tela {
    // SAFETY: só leitura de métricas do sistema.
    let (w, h) = unsafe { (GetSystemMetrics(SM_CXSCREEN).max(1), GetSystemMetrics(SM_CYSCREEN).max(1)) };
    let escala = if w > LARGURA_MAXIMA { f64::from(w) / f64::from(LARGURA_MAXIMA) } else { 1.0 };
    Tela {
        largura_fisica: w,
        altura_fisica: h,
        largura: (f64::from(w) / escala).round() as i32,
        altura: (f64::from(h) / escala).round() as i32,
        escala,
    }
}

fn h(hwnd: isize) -> HWND {
    HWND(hwnd as *mut core::ffi::c_void)
}

// ---------- captura ----------

/// Captura PNG da tela principal (GDI). As janelas da borda ficam fora (`WDA_EXCLUDEFROMCAPTURE`).
///
/// Cerca A3: antes de codificar, pinta de preto toda janela bloqueada (senhas, segurança,
/// terminais, a própria Sora e a Sora web; ver `retangulos_bloqueados`), conferindo antes e
/// depois da cópia. Com um programa bloqueado na frente, devolve `None`: nenhum pixel sai do PC.
pub fn capturar(t: &Tela) -> Result<Option<Vec<u8>>, String> {
    let (w, hh) = (t.largura, t.altura);
    let antes = retangulos_bloqueados(t);
    if antes.1 {
        return Ok(None);
    }
    let mut bgra = vec![0u8; (w * hh * 4) as usize];
    // SAFETY: DCs e bitmap criados e liberados aqui mesmo; o buffer tem o tamanho exato do DIB.
    unsafe {
        let tela_dc = GetDC(None);
        if tela_dc.is_invalid() {
            return Err("sem acesso à tela".into());
        }
        let mem = CreateCompatibleDC(Some(tela_dc));
        let bmp = CreateCompatibleBitmap(tela_dc, w, hh);
        let antigo = SelectObject(mem, bmp.into());
        SetStretchBltMode(mem, HALFTONE);
        let _ = SetBrushOrgEx(mem, 0, 0, None);
        let copiou = StretchBlt(
            mem,
            0,
            0,
            w,
            hh,
            Some(tela_dc),
            0,
            0,
            t.largura_fisica,
            t.altura_fisica,
            ROP_CODE(SRCCOPY.0 | CAPTUREBLT.0),
        )
        .as_bool();
        let mut info = BITMAPINFO {
            bmiHeader: BITMAPINFOHEADER {
                biSize: size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: w,
                biHeight: -hh,
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB.0,
                ..Default::default()
            },
            ..Default::default()
        };
        let linhas = GetDIBits(mem, bmp, 0, hh as u32, Some(bgra.as_mut_ptr().cast()), &mut info, DIB_RGB_COLORS);
        SelectObject(mem, antigo);
        let _ = DeleteObject(bmp.into());
        let _ = DeleteDC(mem);
        ReleaseDC(None, tela_dc);
        if !copiou || linhas == 0 {
            return Err("a captura da tela falhou".into());
        }
    }
    let mut rgb = Vec::with_capacity((w * hh * 3) as usize);
    for px in bgra.as_chunks::<4>().0 {
        rgb.extend_from_slice(&[px[2], px[1], px[0]]);
    }
    drop(bgra);
    let depois = retangulos_bloqueados(t);
    if depois.1 {
        return Ok(None);
    }
    for r in antes.0.iter().chain(depois.0.iter()) {
        super::regras::tarjar_rgb(&mut rgb, w as usize, hh as usize, *r);
    }
    let mut saida = Vec::new();
    {
        let mut codificador = png::Encoder::new(&mut saida, w as u32, hh as u32);
        codificador.set_color(png::ColorType::Rgb);
        codificador.set_depth(png::BitDepth::Eight);
        codificador.set_compression(png::Compression::Fast);
        let mut escritor = codificador.write_header().map_err(|e| e.to_string())?;
        escritor.write_image_data(&rgb).map_err(|e| e.to_string())?;
    }
    Ok(Some(saida))
}

fn classe(hwnd: HWND) -> String {
    let mut buffer = [0u16; 128];
    // SAFETY: buffer local com tamanho informado.
    let n = unsafe { GetClassNameW(hwnd, &mut buffer) };
    String::from_utf16_lossy(&buffer[..n.max(0) as usize])
}

/// Área de trabalho (papel de parede e ícones) e barra de tarefas: são do `explorer.exe`, mas não
/// mostram segredo nem cobrem outras janelas. Ficam fora da tarja e da regra "bloqueado na frente".
fn e_area_de_trabalho(hwnd: HWND) -> bool {
    matches!(classe(hwnd).as_str(), "Progman" | "WorkerW" | "Shell_TrayWnd" | "Shell_SecondaryTrayWnd")
}

/// Visível de verdade: não escondida, não minimizada, não camuflada (outra área de trabalho
/// virtual, app suspenso).
fn na_tela(hwnd: HWND) -> bool {
    // SAFETY: só leitura.
    unsafe {
        if !IsWindowVisible(hwnd).as_bool() || IsIconic(hwnd).as_bool() {
            return false;
        }
        let mut camuflada = 0u32;
        let _ = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, (&mut camuflada as *mut u32).cast(), 4);
        camuflada == 0
    }
}

/// Janela que nada do bot pode ver: a própria Sora, programa desconhecido (com mais privilégios),
/// programa bloqueado ou título bloqueado (inclui a Sora web, `regras::mostra_a_sora`).
fn janela_bloqueada(alvo: &AlvoJanela) -> bool {
    alvo.pid == std::process::id()
        || alvo.programa.is_empty()
        || programa_bloqueado(&alvo.programa)
        || titulo_bloqueado(&alvo.titulo)
}

/// Raio dos cantos arredondados do Windows 11 a 100 % (8 px, com folga; cresce com o DPI): os cantos de uma
/// janela não maximizada deixam ver o que está atrás, então não contam como cobertos.
const MARGEM_CANTOS: i32 = 10;
/// `DWMSBT_TRANSIENTWINDOW`: fundo acrílico, que deixa ver (borrado) o que está atrás.
const FUNDO_ACRILICO: i32 = 3;

/// Retângulos que a janela cobre de verdade, ou vazio se ela não cobre ou se há dúvida (D1):
/// pintar a mais é o lado seguro. Não cobrem: janelas da própria Sora (ilha, borda, Parar),
/// camadas (`WS_EX_LAYERED`, podem ser transparentes), `WS_EX_TRANSPARENT`, janelas de ferramenta
/// (sombras, menus, avisos), janelas com região própria (formato não retangular), fundo acrílico,
/// `CoreWindow` (Iniciar, busca, teclado virtual) e janela sem a moldura do DWM.
fn cobertura(hwnd: HWND, pid: u32) -> Vec<RECT> {
    use windows::Win32::{
        Graphics::{
            Dwm::{DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_SYSTEMBACKDROP_TYPE},
            Gdi::GetWindowRgnBox,
        },
        UI::{
            HiDpi::GetDpiForWindow,
            WindowsAndMessaging::{IsZoomed, WS_EX_LAYERED, WS_EX_TRANSPARENT},
        },
    };
    if pid == std::process::id() || classe(hwnd) == "Windows.UI.Core.CoreWindow" {
        return Vec::new();
    }
    // SAFETY: só leitura de atributos da janela; os buffers têm o tamanho informado.
    unsafe {
        let estilo = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        let sem_cobrir = (WS_EX_LAYERED.0 | WS_EX_TRANSPARENT.0 | WS_EX_TOOLWINDOW.0) as isize;
        if estilo & sem_cobrir != 0 {
            return Vec::new();
        }
        let mut caixa = RECT::default();
        // sem região própria o Windows responde ERROR (0); com região, não cobre.
        let regiao = GetWindowRgnBox(hwnd, &mut caixa);
        if regiao.0 != 0 {
            return Vec::new();
        }
        let mut fundo = 0i32;
        if DwmGetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, (&mut fundo as *mut i32).cast(), 4).is_ok()
            && fundo == FUNDO_ACRILICO
        {
            return Vec::new();
        }
        let mut r = RECT::default();
        if DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, (&mut r as *mut RECT).cast(), size_of::<RECT>() as u32)
            .is_err()
        {
            return Vec::new();
        }
        if IsZoomed(hwnd).as_bool() {
            return vec![r];
        }
        // em cruz: a janela toda menos os quatro cantos.
        let m = (MARGEM_CANTOS * GetDpiForWindow(hwnd).max(96) as i32 + 95) / 96;
        vec![
            RECT { left: r.left + m, top: r.top, right: r.right - m, bottom: r.bottom },
            RECT { left: r.left, top: r.top + m, right: r.right, bottom: r.bottom - m },
        ]
    }
}

fn retangulo(r: &RECT) -> super::regras::Retangulo {
    [r.left, r.top, r.right, r.bottom]
}

// Enumeração exclusiva da captura: sem teto de janelas, sem filtrar janelas de ferramenta. O
// `EnumWindows` entrega as janelas de topo na ordem z, da frente para trás: é essa ordem que
// `areas_a_tarjar` usa para tarjar só o que está à mostra.
unsafe extern "system" fn coletar_bloqueios(hwnd: HWND, dados: LPARAM) -> BOOL {
    // SAFETY: `dados` aponta para o Vec do chamador, vivo durante a enumeração.
    let pilha = unsafe { &mut *(dados.0 as *mut Vec<super::regras::JanelaNaPilha>) };
    // escondida, minimizada ou camuflada não aparece na tela: não tarja nem cobre. A borda e o
    // Parar ficam fora da captura (`WDA_EXCLUDEFROMCAPTURE`): também não tarjam nem cobrem.
    if !na_tela(hwnd) || e_area_de_trabalho(hwnd) || matches!(classe(hwnd).as_str(), "SoraPcBorda" | "SoraPcParar") {
        return BOOL(1);
    }
    let alvo = alvo_da_janela(hwnd);
    let tarja = janela_bloqueada(&alvo).then(|| {
        let mut r = RECT::default();
        // SAFETY: só leitura. O `GetWindowRect` inclui a moldura invisível: tarja a mais.
        if unsafe { GetWindowRect(hwnd, &mut r) }.is_err() {
            r = RECT { left: 0, top: 0, right: i32::MAX / 2, bottom: i32::MAX / 2 };
        }
        let janela = retangulo(&r);
        let ilha = super::regras::ilha_conhecida();
        if ilha.hwnd != 0 && ilha.hwnd == hwnd.0 as isize {
            // a janela da ilha é quase toda transparente: só a pílula vai à tarja.
            // SAFETY: só leitura.
            let dpi = unsafe { windows::Win32::UI::HiDpi::GetDpiForWindow(hwnd) };
            return super::regras::tarja_da_ilha(janela, dpi, ilha.pilula);
        }
        janela
    });
    let cobre = cobertura(hwnd, alvo.pid).iter().map(retangulo).collect();
    pilha.push(super::regras::JanelaNaPilha { tarja, cobre });
    BOOL(1)
}

/// Retângulos (em pixels da captura) a tarjar e se a captura deve ser omitida: programa
/// bloqueado, a Sora ou nada em primeiro plano (a área de trabalho não conta), ou falha ao listar.
/// Só a parte à mostra de cada janela bloqueada é tarjada (D1): uma janela bloqueada coberta por
/// outras não apaga a tela inteira.
fn retangulos_bloqueados(t: &Tela) -> (Vec<[i32; 4]>, bool) {
    let mut pilha: Vec<super::regras::JanelaNaPilha> = Vec::new();
    // SAFETY: callback acima; a pilha vive até o fim da chamada.
    let ok = unsafe { EnumWindows(Some(coletar_bloqueios), LPARAM(&mut pilha as *mut _ as isize)) }.is_ok();
    let omitida = !ok || bloqueada_na_frente();
    let retangulos = super::regras::areas_a_tarjar(&pilha)
        .iter()
        .map(|r| {
            [
                (f64::from(r[0]) / t.escala).floor() as i32 - 2,
                (f64::from(r[1]) / t.escala).floor() as i32 - 2,
                (f64::from(r[2]) / t.escala).ceil() as i32 + 2,
                (f64::from(r[3]) / t.escala).ceil() as i32 + 2,
            ]
        })
        .collect();
    (retangulos, omitida)
}

/// Em primeiro plano está algo que o bot não pode ver (a área de trabalho não conta).
pub fn bloqueada_na_frente() -> bool {
    // SAFETY: só leitura.
    let frente = unsafe { GetForegroundWindow() };
    if frente.is_invalid() {
        return true;
    }
    !e_area_de_trabalho(frente) && janela_bloqueada(&alvo_da_janela(frente))
}

unsafe extern "system" fn coletar_alvos_bloqueados(hwnd: HWND, dados: LPARAM) -> BOOL {
    // SAFETY: `dados` aponta para o Vec do chamador, vivo durante a enumeração.
    let lista = unsafe { &mut *(dados.0 as *mut Vec<AlvoJanela>) };
    // Só janelas de verdade: as escondidas (IME, mensagens) nascem o tempo todo em qualquer
    // programa, e avisos do sistema são janelas de ferramenta.
    // SAFETY: só leitura.
    let ferramenta = unsafe { GetWindowLongPtrW(hwnd, GWL_EXSTYLE) } & WS_EX_TOOLWINDOW.0 as isize != 0;
    if ferramenta || !na_tela(hwnd) || e_area_de_trabalho(hwnd) {
        return BOOL(1);
    }
    let alvo = alvo_da_janela(hwnd);
    if alvo.pid != std::process::id() && janela_bloqueada(&alvo) {
        lista.push(alvo);
    }
    BOOL(1)
}

/// Janelas bloqueadas visíveis agora (sem as da própria Sora).
pub fn alvos_bloqueados() -> Result<Vec<AlvoJanela>, ErroPc> {
    let mut lista: Vec<AlvoJanela> = Vec::new();
    // SAFETY: callback acima; a lista vive até o fim da chamada.
    unsafe { EnumWindows(Some(coletar_alvos_bloqueados), LPARAM(&mut lista as *mut _ as isize)) }
        .map_err(|_| ErroPc::novo("falha"))?;
    Ok(lista)
}

/// Processos em execução: (pid, pid do pai, programa).
pub fn processos() -> Vec<(u32, u32, String)> {
    let mut saida = Vec::new();
    // SAFETY: snapshot aberto e fechado aqui; a estrutura tem `dwSize` preenchido.
    unsafe {
        let Ok(foto) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else {
            return saida;
        };
        let mut item = PROCESSENTRY32W { dwSize: size_of::<PROCESSENTRY32W>() as u32, ..Default::default() };
        let mut tem = Process32FirstW(foto, &mut item).is_ok();
        while tem {
            let n = item.szExeFile.iter().position(|&c| c == 0).unwrap_or(item.szExeFile.len());
            let nome = normalizar_programa(&String::from_utf16_lossy(&item.szExeFile[..n]));
            saida.push((item.th32ProcessID, item.th32ParentProcessID, nome));
            tem = Process32NextW(foto, &mut item).is_ok();
        }
        let _ = CloseHandle(foto);
    }
    saida
}

/// Fecha um processo que o bot fez nascer (terminal, script). Melhor esforço.
pub fn encerrar_processo(pid: u32) -> bool {
    // SAFETY: handle aberto só para encerrar e fechado em seguida.
    unsafe {
        let Ok(processo) = OpenProcess(PROCESS_TERMINATE, false, pid) else {
            return false;
        };
        let ok = TerminateProcess(processo, 1).is_ok();
        let _ = CloseHandle(processo);
        ok
    }
}

// ---------- janelas e programas ----------

fn pid_da_janela(hwnd: HWND) -> u32 {
    let mut pid = 0u32;
    // SAFETY: só leitura.
    unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid)) };
    pid
}

fn programa_do_pid(pid: u32) -> String {
    // SAFETY: handle aberto só para consulta e fechado em seguida; buffer com tamanho informado.
    unsafe {
        let Ok(processo) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) else {
            return String::new();
        };
        let mut buffer = [0u16; 1024];
        let mut tamanho = buffer.len() as u32;
        let ok = QueryFullProcessImageNameW(processo, PROCESS_NAME_WIN32, PWSTR(buffer.as_mut_ptr()), &mut tamanho);
        let _ = CloseHandle(processo);
        if ok.is_err() {
            return String::new();
        }
        normalizar_programa(&String::from_utf16_lossy(&buffer[..tamanho as usize]))
    }
}

fn titulo(hwnd: HWND) -> String {
    let mut buffer = [0u16; 512];
    // SAFETY: buffer local com tamanho informado.
    let n = unsafe { GetWindowTextW(hwnd, &mut buffer) };
    String::from_utf16_lossy(&buffer[..n.max(0) as usize])
}

unsafe extern "system" fn achar_filho_de_outro_processo(filho: HWND, dados: LPARAM) -> BOOL {
    // SAFETY: `dados` aponta para o par (pid da moldura, resultado) do chamador, vivo durante a enumeração.
    let par = unsafe { &mut *(dados.0 as *mut (u32, u32)) };
    let pid = pid_da_janela(filho);
    if pid != 0 && pid != par.0 {
        par.1 = pid;
        return BOOL(0);
    }
    BOOL(1)
}

/// Programa de uma janela de topo. Apps da Loja ficam dentro do `ApplicationFrameHost`: o programa
/// de verdade é o da janela filha (senão "sempre permitir" num app liberaria todos).
fn alvo_da_janela(raiz: HWND) -> AlvoJanela {
    let mut pid = pid_da_janela(raiz);
    let mut programa = programa_do_pid(pid);
    if programa == "applicationframehost.exe" {
        let mut par = (pid, 0u32);
        // SAFETY: callback acima; o par vive até o fim da chamada.
        unsafe {
            let _ = EnumChildWindows(Some(raiz), Some(achar_filho_de_outro_processo), LPARAM(&mut par as *mut _ as isize));
        }
        if par.1 != 0 {
            pid = par.1;
            programa = programa_do_pid(pid);
        }
    }
    AlvoJanela { hwnd: raiz.0 as isize, pid, programa, titulo: titulo(raiz) }
}

/// Janela de topo sob um ponto físico.
pub fn alvo_no_ponto(x: i32, y: i32) -> Option<AlvoJanela> {
    // SAFETY: só leitura de janelas.
    unsafe {
        let janela = WindowFromPoint(POINT { x, y });
        if janela.is_invalid() {
            return None;
        }
        let raiz = GetAncestor(janela, GA_ROOT);
        Some(alvo_da_janela(if raiz.is_invalid() { janela } else { raiz }))
    }
}

/// Janela em primeiro plano (quem recebe o teclado).
pub fn alvo_em_foco() -> Option<AlvoJanela> {
    // SAFETY: só leitura.
    let frente = unsafe { GetForegroundWindow() };
    (!frente.is_invalid()).then(|| alvo_da_janela(frente))
}

pub fn alvo_da_ref(hwnd: isize) -> Option<AlvoJanela> {
    // SAFETY: HWND vindo do servidor; com HWND inválido as chamadas só falham.
    let visivel = unsafe { IsWindowVisible(h(hwnd)).as_bool() };
    visivel.then(|| alvo_da_janela(h(hwnd)))
}

/// Traz uma janela para a frente (para digitar nela). Falso se o Windows não deixou.
pub fn trazer_para_frente(hwnd: isize) -> bool {
    // SAFETY: HWND do servidor; inválido só falha.
    unsafe {
        let _ = SetForegroundWindow(h(hwnd));
        GetForegroundWindow() == h(hwnd)
    }
}

struct Coleta {
    janelas: Vec<(HWND, RECT)>,
}

unsafe extern "system" fn coletar_janela(hwnd: HWND, dados: LPARAM) -> BOOL {
    // SAFETY: `dados` aponta para a `Coleta` do chamador, viva durante a enumeração.
    let coleta = unsafe { &mut *(dados.0 as *mut Coleta) };
    unsafe {
        if !IsWindowVisible(hwnd).as_bool() || IsIconic(hwnd).as_bool() {
            return BOOL(1);
        }
        if GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW.0 as isize != 0 {
            return BOOL(1);
        }
        let mut camuflada = 0u32;
        let _ = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, (&mut camuflada as *mut u32).cast(), 4);
        if camuflada != 0 {
            return BOOL(1);
        }
        let mut r = RECT::default();
        if GetWindowRect(hwnd, &mut r).is_err() || r.right - r.left < 40 || r.bottom - r.top < 30 {
            return BOOL(1);
        }
        coleta.janelas.push((hwnd, r));
        BOOL(if coleta.janelas.len() >= 60 { 0 } else { 1 })
    }
}

fn capturado(t: &Tela, valor: i32) -> i32 {
    (f64::from(valor) / t.escala).round() as i32
}

/// Janelas visíveis na tela principal (da frente para trás), com o programa de cada uma.
pub fn janelas(t: &Tela, pid_proprio: u32) -> Vec<Value> {
    let mut coleta = Coleta { janelas: Vec::new() };
    // SAFETY: callback acima; a coleta vive até o fim da chamada.
    unsafe {
        let _ = EnumWindows(Some(coletar_janela), LPARAM(&mut coleta as *mut _ as isize));
    }
    let frente = unsafe { GetForegroundWindow() };
    let mut saida = Vec::new();
    for (hwnd, r) in coleta.janelas {
        if r.right <= 0 || r.bottom <= 0 || r.left >= t.largura_fisica || r.top >= t.altura_fisica {
            continue; // em outro monitor
        }
        let texto = titulo(hwnd);
        if texto.trim().is_empty() {
            continue;
        }
        let alvo = alvo_da_janela(hwnd);
        let propria = alvo.pid == pid_proprio;
        let programa = if propria { "sora.exe".to_string() } else { alvo.programa.clone() };
        let bloqueada = propria || programa_bloqueado(&programa) || titulo_bloqueado(&texto);
        let (x, y) = (r.left.max(0), r.top.max(0));
        saida.push(json!({
            "id": (hwnd.0 as isize).to_string(),
            "titulo": if bloqueada { String::new() } else { texto.chars().take(200).collect() },
            "x": capturado(t, x),
            "y": capturado(t, y),
            "largura": capturado(t, r.right.min(t.largura_fisica) - x),
            "altura": capturado(t, r.bottom.min(t.altura_fisica) - y),
            "ativa": hwnd == frente,
            "programa": programa,
            "bloqueado": bloqueada,
        }));
        if saida.len() >= MAX_JANELAS {
            break;
        }
    }
    saida
}

// ---------- UI Automation ----------

fn automacao() -> Option<IUIAutomation> {
    // SAFETY: COM no modo multithread desta thread (repetir é inofensivo: devolve S_FALSE).
    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        let uia: IUIAutomation = CoCreateInstance(&CUIAutomation, None, CLSCTX_INPROC_SERVER).ok()?;
        if let Ok(uia2) = uia.cast::<IUIAutomation2>() {
            let _ = uia2.SetConnectionTimeout(2_000);
            let _ = uia2.SetTransactionTimeout(3_000);
        }
        Some(uia)
    }
}

fn papel(tipo: UIA_CONTROLTYPE_ID) -> Option<(&'static str, bool)> {
    // (nome em PT-BR, interativo?)
    Some(match tipo.0 {
        50000 => ("botão", true),
        50002 => ("caixa de seleção", true),
        50003 => ("caixa de combinação", true),
        50004 => ("campo de texto", true),
        50005 => ("link", true),
        50006 => ("imagem", false),
        50007 => ("item de lista", true),
        50008 => ("lista", false),
        50009 => ("menu", false),
        50010 => ("barra de menu", false),
        50011 => ("item de menu", true),
        50013 => ("opção", true),
        50015 => ("controle deslizante", true),
        50016 => ("seletor numérico", true),
        50018 => ("abas", false),
        50019 => ("aba", true),
        50020 => ("texto", false),
        50021 => ("barra de ferramentas", false),
        50023 => ("árvore", false),
        50024 => ("item de árvore", true),
        50028 | 50036 => ("tabela", false),
        50029 => ("item de tabela", true),
        50030 => ("documento", true),
        50031 => ("botão dividido", true),
        50034 | 50035 => ("cabeçalho", false),
        50040 => ("barra de aplicativo", false),
        _ => return None, // painel, grupo, separador, barra de rolagem… só poluem
    })
}

/// Árvore de UI Automation da janela em primeiro plano: refs `eN`, papel, nome, valor (nunca de
/// campo de senha), centro em pixels da captura e estados. Janela da Sora ou bloqueada: vazia.
pub fn arvore(t: &Tela, pid_proprio: u32) -> Vec<Value> {
    let Some(frente) = alvo_em_foco() else {
        return Vec::new();
    };
    if frente.pid == pid_proprio || programa_bloqueado(&frente.programa) || titulo_bloqueado(&frente.titulo) {
        return Vec::new();
    }
    let Some(uia) = automacao() else {
        return Vec::new();
    };
    let mut saida = Vec::new();
    // SAFETY: chamadas COM com interfaces válidas; erros viram lista vazia.
    unsafe {
        let Ok(raiz) = uia.ElementFromHandle(h(frente.hwnd)) else {
            return saida;
        };
        let Ok(cache) = uia.CreateCacheRequest() else {
            return saida;
        };
        for p in [
            UIA_NamePropertyId,
            UIA_ControlTypePropertyId,
            UIA_BoundingRectanglePropertyId,
            UIA_IsPasswordPropertyId,
            UIA_IsEnabledPropertyId,
            UIA_IsOffscreenPropertyId,
            UIA_HasKeyboardFocusPropertyId,
            UIA_ValueValuePropertyId,
        ] {
            let _ = cache.AddProperty(p);
        }
        let Ok(condicao) = uia.ControlViewCondition() else {
            return saida;
        };
        let Ok(todos) = raiz.FindAllBuildCache(TreeScope_Descendants, &condicao, &cache) else {
            return saida;
        };
        let total = todos.Length().unwrap_or(0);
        for i in 0..total {
            if saida.len() >= MAX_ELEMENTOS {
                break;
            }
            let Ok(el) = todos.GetElement(i) else { continue };
            if el.CachedIsOffscreen().map(|b| b.as_bool()).unwrap_or(true) {
                continue;
            }
            let Some((nome_papel, interativo)) = el.CachedControlType().ok().and_then(papel) else {
                continue;
            };
            let nome = el.CachedName().map(|b| b.to_string()).unwrap_or_default();
            if nome.trim().is_empty() && !interativo {
                continue;
            }
            let Ok(r) = el.CachedBoundingRectangle() else { continue };
            let (cx, cy) = ((r.left + r.right) / 2, (r.top + r.bottom) / 2);
            if r.right <= r.left || r.bottom <= r.top || cx < 0 || cy < 0 || cx >= t.largura_fisica || cy >= t.altura_fisica {
                continue;
            }
            let senha = el.CachedIsPassword().map(|b| b.as_bool()).unwrap_or(true);
            let mut estados = Vec::new();
            if senha {
                estados.push("senha");
            }
            if el.CachedHasKeyboardFocus().map(|b| b.as_bool()).unwrap_or(false) {
                estados.push("foco");
            }
            if !el.CachedIsEnabled().map(|b| b.as_bool()).unwrap_or(true) {
                estados.push("desativado");
            }
            let mut item = json!({
                "ref": format!("e{}", saida.len() + 1),
                "papel": nome_papel,
                "nome": nome.chars().take(120).collect::<String>(),
                "centro": [capturado(t, cx), capturado(t, cy)],
            });
            if !senha
                && let Ok(valor) = el.GetCachedPropertyValue(UIA_ValueValuePropertyId)
                && let Ok(texto) = BSTR::try_from(&valor)
                && !texto.is_empty()
            {
                item["valor"] = Value::String(texto.to_string().chars().take(200).collect());
            }
            if !estados.is_empty() {
                item["estados"] = json!(estados);
            }
            saida.push(item);
        }
    }
    saida
}

fn e_senha(el: &IUIAutomationElement) -> bool {
    // SAFETY: interface válida.
    unsafe { el.CurrentIsPassword().map(|b| b.as_bool()).unwrap_or(true) }
}

/// Campo sob o ponto: falha de UI Automation recusa a entrada.
pub fn senha_no_ponto(x: i32, y: i32) -> bool {
    let Some(uia) = automacao() else { return true };
    // SAFETY: chamada COM com interface válida.
    unsafe { uia.ElementFromPoint(POINT { x, y }).map(|el| e_senha(&el)).unwrap_or(true) }
}

/// O campo com o foco do teclado é de senha?
pub fn senha_em_foco() -> bool {
    let Some(uia) = automacao() else { return true };
    // SAFETY: chamada COM com interface válida.
    unsafe { uia.GetFocusedElement().map(|el| e_senha(&el)).unwrap_or(true) }
}

// ---------- entrada ----------

fn mouse(dx: i32, dy: i32, dados: i32, flags: MOUSE_EVENT_FLAGS) -> INPUT {
    INPUT {
        r#type: INPUT_MOUSE,
        Anonymous: INPUT_0 {
            mi: MOUSEINPUT { dx, dy, mouseData: dados as u32, dwFlags: flags, time: 0, dwExtraInfo: MARCA_SORA },
        },
    }
}

fn teclado(vk: u16, scan: u16, flags: KEYBD_EVENT_FLAGS) -> INPUT {
    INPUT {
        r#type: INPUT_KEYBOARD,
        Anonymous: INPUT_0 {
            ki: KEYBDINPUT { wVk: VIRTUAL_KEY(vk), wScan: scan, dwFlags: flags, time: 0, dwExtraInfo: MARCA_SORA },
        },
    }
}

/// Caractere que existe no teclado do usuário (só com Shift; sem AltGr nem tecla morta) vira tecla
/// de verdade, no layout da janela em foco. Pacotes unicode (`VK_PACKET`) em sequência se juntam em
/// apps WinUI, como o Bloco de Notas novo ("012345" chegava como "555555": teste ao vivo da Vela-6).
/// Com Caps Lock ligado, ou fora do teclado (acentos no ABNT2, emoji), segue o pacote unicode.
fn tecla_do_caractere(unidade: u16) -> Option<(u16, bool)> {
    // SAFETY: só consultas ao Windows, sem ponteiros guardados.
    unsafe {
        if GetKeyState(i32::from(VK_CAPITAL.0)) & 1 != 0 {
            return None;
        }
        let thread = GetWindowThreadProcessId(GetForegroundWindow(), None);
        let layout = GetKeyboardLayout(thread);
        let r = VkKeyScanExW(unidade, layout);
        if r == -1 {
            return None;
        }
        let vk = (r as u16) & 0xFF;
        let estado = ((r as u16) >> 8) & 0xFF;
        if estado & !1 != 0 {
            return None; // precisa de Ctrl/Alt (AltGr) ou outra tecla especial
        }
        if MapVirtualKeyExW(u32::from(vk), MAPVK_VK_TO_CHAR, Some(layout)) & 0x8000_0000 != 0 {
            return None; // tecla morta: começaria um acento
        }
        Some((vk, estado & 1 != 0))
    }
}

/// Manda um passo de entrada. `t` dá o tamanho físico da tela (coordenada absoluta 0..65535).
pub fn enviar(passo: Passo, t: &Tela) -> Result<(), String> {
    let entradas: Vec<INPUT> = match passo {
        Passo::Mover(x, y) => {
            let nx = (i64::from(x) * 65_535 / i64::from((t.largura_fisica - 1).max(1))) as i32;
            let ny = (i64::from(y) * 65_535 / i64::from((t.altura_fisica - 1).max(1))) as i32;
            vec![mouse(nx, ny, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)]
        }
        Passo::Botao(botao, desce) => {
            let flags = match (botao, desce) {
                (Botao::Esquerdo, true) => MOUSEEVENTF_LEFTDOWN,
                (Botao::Esquerdo, false) => MOUSEEVENTF_LEFTUP,
                (Botao::Direito, true) => MOUSEEVENTF_RIGHTDOWN,
                (Botao::Direito, false) => MOUSEEVENTF_RIGHTUP,
            };
            vec![mouse(0, 0, 0, flags)]
        }
        Passo::Roda(vertical, delta) => {
            vec![mouse(0, 0, delta, if vertical { MOUSEEVENTF_WHEEL } else { MOUSEEVENTF_HWHEEL })]
        }
        Passo::Tecla(tecla, desce) => {
            let mut flags = if desce { KEYBD_EVENT_FLAGS(0) } else { KEYEVENTF_KEYUP };
            if tecla.estendida {
                flags |= KEYEVENTF_EXTENDEDKEY;
            }
            vec![teclado(tecla.vk, 0, flags)]
        }
        Passo::Caractere(unidade) => match tecla_do_caractere(unidade) {
            Some((vk, shift)) => {
                let mut v = Vec::with_capacity(4);
                if shift {
                    v.push(teclado(super::regras::VK_SHIFT, 0, KEYBD_EVENT_FLAGS(0)));
                }
                v.push(teclado(vk, 0, KEYBD_EVENT_FLAGS(0)));
                v.push(teclado(vk, 0, KEYEVENTF_KEYUP));
                if shift {
                    v.push(teclado(super::regras::VK_SHIFT, 0, KEYEVENTF_KEYUP));
                }
                v
            }
            None => vec![
                teclado(0, unidade, KEYEVENTF_UNICODE),
                teclado(0, unidade, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
            ],
        },
    };
    // SAFETY: entradas montadas acima, com o tamanho de INPUT.
    let enviadas = unsafe { SendInput(&entradas, size_of::<INPUT>() as i32) };
    if enviadas as usize == entradas.len() {
        Ok(())
    } else {
        Err("o Windows recusou a entrada (programa com mais privilégios?)".into())
    }
}

/// Observação completa para o servidor.
pub fn observar(pid_proprio: u32) -> Result<(Value, Tela), String> {
    let t = tela();
    let png = capturar(&t)?;
    // omitida: nem pixel nem árvore saem do PC; a lista de janelas (títulos bloqueados apagados)
    // continua, para o bot trazer um programa liberado para a frente
    let omitida = png.is_none();
    Ok((
        json!({
            "captura_omitida": omitida,
            "png": png.map(|p| base64::engine::general_purpose::STANDARD.encode(p)).unwrap_or_default(),
            "largura": t.largura,
            "altura": t.altura,
            "janelas": janelas(&t, pid_proprio),
            "arvore": if omitida { Vec::new() } else { arvore(&t, pid_proprio) },
        }),
        t,
    ))
}
