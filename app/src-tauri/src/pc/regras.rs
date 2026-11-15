//! Regras do controle do PC (C3) que não dependem do Windows: o que é bloqueado, como cada ação
//! vira passos de mouse e teclado, e as conferências antes de agir. Tudo testável sem tela.
//!
//! O servidor confere de novo do lado dele (`backend/app/computador/pc_usuario.py`), mas a ponte
//! é quem sabe o executável de cada janela e o que está sob o mouse: aqui fica a palavra final.

use serde::Serialize;
use serde_json::Value;

/// Programas em que um bot nunca mexe. Espelho em `PROGRAMAS_BLOQUEADOS` do backend.
pub const PROGRAMAS_BLOQUEADOS: &[&str] = &[
    // UAC, credenciais e tela de bloqueio
    "consent.exe",
    "credentialuibroker.exe",
    "logonui.exe",
    "lockapp.exe",
    // segurança e configurações do Windows
    "sechealthui.exe",
    "securityhealthhost.exe",
    "securityhealthsystray.exe",
    "systemsettings.exe",
    "regedit.exe",
    "mmc.exe",
    "taskmgr.exe",
    // gerenciadores de senha
    "1password.exe",
    "bitwarden.exe",
    "keepass.exe",
    "keepassxc.exe",
    "dashlane.exe",
    "lastpass.exe",
    "nordpass.exe",
    "keeper.exe",
    "keeperpasswordmanager.exe",
    "roboform.exe",
    "enpass.exe",
    "protonpass.exe",
    // terminais (seria um "executar comando" no PC do usuário)
    "cmd.exe",
    "powershell.exe",
    "powershell_ise.exe",
    "pwsh.exe",
    "windowsterminal.exe",
    "wt.exe",
    "openconsole.exe",
    "conhost.exe",
    // lançadores e executores de script (Cerca A1): Explorer (barra de endereço, caixa Executar),
    // busca do Iniciar e companhia rodam qualquer comando sem nunca focar um terminal
    "explorer.exe",
    "searchhost.exe",
    "searchapp.exe",
    "searchui.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "wscript.exe",
    "cscript.exe",
    "mshta.exe",
    "rundll32.exe",
    "regsvr32.exe",
    "msiexec.exe",
    "bash.exe",
    "wsl.exe",
    "wslhost.exe",
    "certutil.exe",
    "bitsadmin.exe",
    "schtasks.exe",
    "msbuild.exe",
    "installutil.exe",
    "control.exe",
    // a própria Sora
    "sora.exe",
];

/// Pedaços de título que denunciam senhas ou segurança mesmo dentro de um programa liberado
/// (ex.: a página de senhas do navegador).
const TITULOS_BLOQUEADOS: &[&str] = &[
    "gerenciador de senhas",
    "password manager",
    "senhas salvas",
    "saved passwords",
    "segurança do windows",
    "windows security",
    "controle de conta de usuário",
    "user account control",
    "credential manager",
    "gerenciador de credenciais",
];

/// Programa (executável) de uma janela, como o servidor vê: só o nome, em minúsculas.
pub fn normalizar_programa(caminho: &str) -> String {
    caminho
        .trim()
        .rsplit(['\\', '/'])
        .next()
        .unwrap_or("")
        .to_lowercase()
        .chars()
        .take(80)
        .collect()
}

pub fn programa_bloqueado(programa: &str) -> bool {
    PROGRAMAS_BLOQUEADOS.contains(&programa)
}

/// Títulos exatos de janelas que executam comandos (a caixa Executar do Windows).
const TITULOS_EXATOS_BLOQUEADOS: &[&str] = &["executar", "run"];

pub fn titulo_bloqueado(titulo: &str) -> bool {
    let titulo = titulo.trim().to_lowercase();
    TITULOS_BLOQUEADOS.iter().any(|t| titulo.contains(t))
        || TITULOS_EXATOS_BLOQUEADOS.contains(&titulo.as_str())
        || mostra_a_sora(&titulo)
}

/// Janela que mostra a Sora (Cerca A2): a Sora web num navegador liberado tem "Sora" no título da
/// aba. Palavra inteira, para não pegar "professora" ou "assessora". Conta como bloqueada para
/// agir, para a árvore e para a captura: o bot não aprova os próprios cartões.
pub fn mostra_a_sora(titulo: &str) -> bool {
    titulo.to_lowercase().split(|c: char| !c.is_alphanumeric()).any(|p| p == "sora")
}

/// Uma janela de topo que vai receber a ação.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AlvoJanela {
    pub hwnd: isize,
    pub pid: u32,
    pub programa: String,
    pub titulo: String,
}

/// Erro que volta ao servidor (`erro.codigo`); o servidor traduz para o bot.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ErroPc {
    pub codigo: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mensagem: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub programa: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub titulo: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub por: Option<String>,
}

impl ErroPc {
    pub fn novo(codigo: &'static str) -> Self {
        Self { codigo, mensagem: None, programa: None, titulo: None, por: None }
    }

    pub fn com_mensagem(codigo: &'static str, mensagem: impl Into<String>) -> Self {
        Self { mensagem: Some(mensagem.into()), ..Self::novo(codigo) }
    }
}

/// Confere se o bot pode agir nesta janela: nunca na própria Sora, nunca em programa ou título
/// bloqueado, e só em programa que o usuário liberou (cartão "Precisa de você").
pub fn conferir_alvo(alvo: &AlvoJanela, permitidos: &[String], pid_proprio: u32) -> Result<(), ErroPc> {
    if alvo.pid == pid_proprio {
        return Err(ErroPc { programa: Some("sora.exe".into()), ..ErroPc::novo("programa_bloqueado") });
    }
    if programa_bloqueado(&alvo.programa) || titulo_bloqueado(&alvo.titulo) {
        return Err(ErroPc {
            programa: Some(alvo.programa.clone()),
            ..ErroPc::novo("programa_bloqueado")
        });
    }
    if alvo.programa.is_empty() || !permitidos.iter().any(|p| p == &alvo.programa) {
        return Err(ErroPc {
            programa: Some(alvo.programa.clone()),
            titulo: Some(alvo.titulo.chars().take(120).collect()),
            ..ErroPc::novo("programa_nao_permitido")
        });
    }
    Ok(())
}

// ---------- teclas ----------

pub const VK_SHIFT: u16 = 0x10;
pub const VK_CONTROL: u16 = 0x11;
pub const VK_MENU: u16 = 0x12;
pub const VK_RETURN: u16 = 0x0D;
pub const VK_TAB: u16 = 0x09;

/// Uma tecla virtual do Windows e se ela é "estendida" (setas, Home, End…).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Tecla {
    pub vk: u16,
    pub estendida: bool,
}

const fn t(vk: u16) -> Tecla {
    Tecla { vk, estendida: false }
}

const fn e(vk: u16) -> Tecla {
    Tecla { vk, estendida: true }
}

/// Nomes que o servidor manda (`normalizar_tecla` do backend, padrão xdotool) → tecla do Windows.
/// Nada de tecla Windows (super) nem ctrl+alt+Delete.
fn tecla_base(nome: &str) -> Option<Tecla> {
    Some(match nome {
        "Return" => t(VK_RETURN),
        "Tab" => t(VK_TAB),
        "Escape" => t(0x1B),
        "BackSpace" => t(0x08),
        "Delete" => e(0x2E),
        "space" => t(0x20),
        "Up" => e(0x26),
        "Down" => e(0x28),
        "Left" => e(0x25),
        "Right" => e(0x27),
        "Page_Up" => e(0x21),
        "Page_Down" => e(0x22),
        "Home" => e(0x24),
        "End" => e(0x23),
        _ => {
            if let Some(n) = nome.strip_prefix('F').and_then(|n| n.parse::<u16>().ok())
                && (1..=12).contains(&n)
            {
                return Some(t(0x70 + n - 1));
            }
            let mut letras = nome.chars();
            let (Some(c), None) = (letras.next(), letras.next()) else {
                return None;
            };
            if c.is_ascii_alphanumeric() {
                return Some(t(c.to_ascii_uppercase() as u16));
            }
            return None;
        }
    })
}

/// `ctrl+shift+l` → (modificadores, tecla). Letra solta só com modificador (texto vai por
/// `digitar`).
pub fn interpretar_tecla(texto: &str) -> Result<(Vec<Tecla>, Tecla), ErroPc> {
    let partes: Vec<&str> = texto.split('+').map(str::trim).filter(|p| !p.is_empty()).collect();
    let invalida = || ErroPc::com_mensagem("invalido", "tecla não permitida");
    let (base, mods) = partes.split_last().ok_or_else(invalida)?;
    if partes.len() > 4 {
        return Err(invalida());
    }
    let mut modificadores = Vec::new();
    for m in mods {
        let vk = match m.to_lowercase().as_str() {
            "ctrl" | "control" => VK_CONTROL,
            "alt" => VK_MENU,
            "shift" => VK_SHIFT,
            _ => return Err(invalida()),
        };
        if !modificadores.iter().any(|x: &Tecla| x.vk == vk) {
            modificadores.push(t(vk));
        }
    }
    let base_tecla = tecla_base(base).ok_or_else(invalida)?;
    let letra = base.len() == 1;
    if letra && modificadores.is_empty() {
        return Err(invalida());
    }
    let tem = |vk| modificadores.iter().any(|m: &Tecla| m.vk == vk);
    if tem(VK_CONTROL) && tem(VK_MENU) && matches!(base_tecla.vk, 0x2E | 0x08) {
        return Err(invalida());
    }
    if (base_tecla.vk == 0x1B && (tem(VK_CONTROL) || tem(VK_MENU)))
        || (base_tecla.vk == VK_TAB && tem(VK_MENU))
        || base_tecla.vk == 0x7B
        || (tem(VK_CONTROL) && tem(VK_SHIFT) && matches!(base_tecla.vk, 0x49 | 0x4A | 0x43))
    {
        return Err(invalida());
    }
    Ok((modificadores, base_tecla))
}

// ---------- ações → passos ----------

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Botao {
    Esquerdo,
    Direito,
}

/// Um passo de entrada: o executor manda um por vez e confere interrupção entre eles.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Passo {
    /// Pixels físicos da tela principal.
    Mover(i32, i32),
    Botao(Botao, bool),
    /// `vertical`, múltiplos de 120 (positivo = para cima / para a direita).
    Roda(bool, i32),
    Tecla(Tecla, bool),
    /// Uma unidade UTF-16 (tecla "unicode"), descendo e subindo.
    Caractere(u16),
}

/// O que a ação precisa conferir antes de começar.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Conferencia {
    /// Janela e campo sob este ponto (físico).
    Ponto(i32, i32),
    /// Janela e campo com o foco do teclado.
    Foco,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Plano {
    pub conferencias: Vec<Conferencia>,
    /// Janela a trazer para a frente antes de digitar (ref de janela do bot).
    pub trazer: Option<isize>,
    pub passos: Vec<Passo>,
}

/// Converte coordenadas da captura em pixels físicos e confere que estão na tela.
pub fn ponto_fisico(dados: &Value, cx: &str, cy: &str, escala: f64, tela: (i32, i32)) -> Result<Option<(i32, i32)>, ErroPc> {
    let (Some(x), Some(y)) = (dados.get(cx).and_then(Value::as_f64), dados.get(cy).and_then(Value::as_f64)) else {
        return Ok(None);
    };
    if !(x.is_finite() && y.is_finite()) || x < 0.0 || y < 0.0 {
        return Err(ErroPc::novo("fora_da_tela"));
    }
    let (px, py) = ((x * escala).round() as i32, (y * escala).round() as i32);
    if px >= tela.0 || py >= tela.1 {
        return Err(ErroPc::novo("fora_da_tela"));
    }
    Ok(Some((px, py)))
}

const MAX_TEXTO: usize = 2_000;

/// Monta o plano de uma ação vinda do servidor. `escala` = pixels físicos por pixel da captura.
pub fn planejar(acao: &Value, escala: f64, tela: (i32, i32)) -> Result<Plano, ErroPc> {
    let tipo = acao.get("tipo").and_then(Value::as_str).unwrap_or("");
    let invalido = |m: &str| ErroPc::com_mensagem("invalido", m);
    let ponto = ponto_fisico(acao, "x", "y", escala, tela)?;
    let mut plano = Plano { conferencias: Vec::new(), trazer: None, passos: Vec::new() };
    let clique = |botao: Botao, vezes: usize, plano: &mut Plano| -> Result<(), ErroPc> {
        let (x, y) = ponto.ok_or_else(|| invalido("clique precisa de x/y"))?;
        plano.conferencias.push(Conferencia::Ponto(x, y));
        plano.passos.push(Passo::Mover(x, y));
        for _ in 0..vezes {
            plano.passos.push(Passo::Botao(botao, true));
            plano.passos.push(Passo::Botao(botao, false));
        }
        Ok(())
    };
    match tipo {
        "clicar" => clique(Botao::Esquerdo, 1, &mut plano)?,
        "clique_duplo" => clique(Botao::Esquerdo, 2, &mut plano)?,
        "clicar_direito" => clique(Botao::Direito, 1, &mut plano)?,
        "rolar" => {
            if let Some((x, y)) = ponto {
                plano.conferencias.push(Conferencia::Ponto(x, y));
                plano.passos.push(Passo::Mover(x, y));
            } else {
                plano.conferencias.push(Conferencia::Foco);
            }
            let quantidade = acao.get("quantidade").and_then(Value::as_i64).unwrap_or(3).clamp(1, 15) as i32;
            let (vertical, sinal) = match acao.get("direcao").and_then(Value::as_str).unwrap_or("baixo") {
                "cima" => (true, 1),
                "baixo" => (true, -1),
                "direita" => (false, 1),
                "esquerda" => (false, -1),
                _ => return Err(invalido("direção inválida")),
            };
            for _ in 0..quantidade {
                plano.passos.push(Passo::Roda(vertical, 120 * sinal));
            }
        }
        "arrastar" => {
            let (x, y) = ponto.ok_or_else(|| invalido("arrastar precisa de x/y"))?;
            let (ax, ay) = ponto_fisico(acao, "ate_x", "ate_y", escala, tela)?
                .ok_or_else(|| invalido("arrastar precisa de ate_x/ate_y"))?;
            plano.conferencias.push(Conferencia::Ponto(x, y));
            plano.conferencias.push(Conferencia::Ponto(ax, ay));
            plano.passos.push(Passo::Mover(x, y));
            plano.passos.push(Passo::Botao(Botao::Esquerdo, true));
            for i in 1..=10 {
                plano.passos.push(Passo::Mover(x + (ax - x) * i / 10, y + (ay - y) * i / 10));
            }
            plano.passos.push(Passo::Botao(Botao::Esquerdo, false));
        }
        "digitar" => {
            let texto = acao.get("texto").and_then(Value::as_str).unwrap_or("");
            if texto.is_empty() || texto.chars().count() > MAX_TEXTO {
                return Err(invalido("texto vazio ou longo demais"));
            }
            plano.trazer = acao.get("janela").and_then(Value::as_str).and_then(|j| j.parse().ok());
            plano.conferencias.push(Conferencia::Foco);
            for c in texto.chars() {
                match c {
                    '\r' => {}
                    '\n' => {
                        plano.passos.push(Passo::Tecla(t(VK_RETURN), true));
                        plano.passos.push(Passo::Tecla(t(VK_RETURN), false));
                    }
                    '\t' => {
                        plano.passos.push(Passo::Tecla(t(VK_TAB), true));
                        plano.passos.push(Passo::Tecla(t(VK_TAB), false));
                    }
                    c if c.is_control() => {}
                    c => {
                        let mut unidades = [0u16; 2];
                        for u in c.encode_utf16(&mut unidades) {
                            plano.passos.push(Passo::Caractere(*u));
                        }
                    }
                }
            }
        }
        "tecla" => {
            let texto = acao.get("tecla").and_then(Value::as_str).unwrap_or("");
            let (mods, base) = interpretar_tecla(texto)?;
            plano.conferencias.push(Conferencia::Foco);
            for m in &mods {
                plano.passos.push(Passo::Tecla(*m, true));
            }
            plano.passos.push(Passo::Tecla(base, true));
            plano.passos.push(Passo::Tecla(base, false));
            for m in mods.iter().rev() {
                plano.passos.push(Passo::Tecla(*m, false));
            }
        }
        "abrir" => return Err(invalido("abrir programas não é permitido no PC do usuário")),
        _ => return Err(invalido("ação desconhecida")),
    }
    Ok(plano)
}

/// Teclas e botões ainda apertados depois de `feitos` passos (para soltar se a ação parar no
/// meio: nunca deixar ctrl ou o botão do mouse preso).
pub fn ainda_apertados(passos: &[Passo]) -> Vec<Passo> {
    let mut apertados: Vec<Passo> = Vec::new();
    for passo in passos {
        match *passo {
            Passo::Tecla(tecla, true) => apertados.push(Passo::Tecla(tecla, false)),
            Passo::Tecla(tecla, false) => apertados.retain(|p| *p != Passo::Tecla(tecla, false)),
            Passo::Botao(b, true) => apertados.push(Passo::Botao(b, false)),
            Passo::Botao(b, false) => apertados.retain(|p| *p != Passo::Botao(b, false)),
            _ => {}
        }
    }
    apertados.reverse();
    apertados
}

/// Id de bot vindo do app ou do servidor: só UUID (sem caminho, sem texto livre).
pub fn uuid_valido(texto: &str) -> bool {
    texto.len() == 36
        && texto.chars().enumerate().all(|(i, c)| {
            if [8, 13, 18, 23].contains(&i) { c == '-' } else { c.is_ascii_hexdigit() }
        })
}

/// Cor `#RRGGBB` → (r, g, b). Cor inválida vira a da Sora.
pub fn cor_rgb(cor: &str) -> (u8, u8, u8) {
    let hex = cor.trim().trim_start_matches('#');
    if hex.len() == 6
        && hex.is_ascii()
        && let (Ok(r), Ok(g), Ok(b)) = (
            u8::from_str_radix(&hex[0..2], 16),
            u8::from_str_radix(&hex[2..4], 16),
            u8::from_str_radix(&hex[4..6], 16),
        )
    {
        return (r, g, b);
    }
    (0xE2, 0xEC, 0xFF)
}

/// Programas que abrem outros (Cerca A1): um processo bloqueado que nasce filho de um deles
/// durante a ação do bot foi o bot que abriu.
const LANCADORES: &[&str] = &[
    "explorer.exe",
    "searchhost.exe",
    "searchapp.exe",
    "searchui.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "sihost.exe",
];

/// Hospedeiros de console: nascem junto de qualquer programa de linha de comando (inclusive o
/// `git` que um editor liberado roda sozinho). O terminal de verdade (`cmd`, `powershell`…) é que
/// denuncia a ação.
const SO_HOSPEDEIROS: &[&str] = &["conhost.exe", "openconsole.exe", "explorer.exe"];

/// Processos bloqueados que nasceram durante a ação, filhos de um programa liberado, de um
/// lançador ou de outro processo novo (cadeia `explorer → cmd → powershell`). Devolve (pid,
/// programa). Processos de serviços do sistema ficam de fora: não foram abertos pela ação.
pub fn processos_suspeitos(
    antes: &[(u32, u32, String)],
    depois: &[(u32, u32, String)],
    permitidos: &[String],
) -> Vec<(u32, String)> {
    let existiam: std::collections::HashSet<u32> = antes.iter().map(|p| p.0).collect();
    let novos: Vec<&(u32, u32, String)> = depois.iter().filter(|p| !existiam.contains(&p.0)).collect();
    let mut vigiados: std::collections::HashSet<u32> = antes
        .iter()
        .filter(|p| LANCADORES.contains(&p.2.as_str()) || permitidos.iter().any(|q| q == &p.2))
        .map(|p| p.0)
        .collect();
    vigiados.extend(novos.iter().map(|p| p.0));
    novos
        .into_iter()
        .filter(|p| {
            programa_bloqueado(&p.2) && !SO_HOSPEDEIROS.contains(&p.2.as_str()) && p.2 != "sora.exe" && vigiados.contains(&p.1)
        })
        .map(|p| (p.0, p.2.clone()))
        .collect()
}

/// Tarja em pixels da captura; retângulos fora da tela são recortados.
pub fn tarjar_rgb(rgb: &mut [u8], largura: usize, altura: usize, r: [i32; 4]) {
    let [x1, y1, x2, y2] = r;
    for y in y1.max(0) as usize..(y2.max(0) as usize).min(altura) {
        for x in x1.max(0) as usize..(x2.max(0) as usize).min(largura) {
            rgb[(y * largura + x) * 3..(y * largura + x + 1) * 3].fill(0);
        }
    }
}

#[cfg(test)]
mod testes {
    use super::*;
    use serde_json::json;

    #[test]
    fn sora_no_titulo_e_caixa_executar_sao_bloqueadas() {
        for titulo in ["Sora - Google Chrome", "Sora — agentes de IA - Microsoft Edge", "Precisa de você · SORA", "Executar", "Run"] {
            assert!(titulo_bloqueado(titulo), "{titulo}");
            assert!(conferir_alvo(&alvo("chrome.exe", titulo, 10), &["chrome.exe".into()], 99).is_err());
        }
        for titulo in ["Professora Ana - Gmail", "Assessoria - Word", "Executar testes.txt - Bloco de Notas"] {
            assert!(!titulo_bloqueado(titulo), "{titulo}");
        }
    }

    #[test]
    fn processo_bloqueado_filho_da_acao_e_pego() {
        let p = |pid: u32, pai: u32, nome: &str| (pid, pai, nome.to_string());
        let antes = vec![p(4, 0, "system"), p(100, 4, "explorer.exe"), p(200, 100, "chrome.exe"), p(300, 4, "services.exe"), p(400, 100, "code.exe")];
        let permitidos = vec!["chrome.exe".to_string(), "code.exe".to_string()];
        // caixa Executar / barra do Explorer → powershell; e a cadeia cmd → powershell
        let depois = [antes.clone(), vec![p(500, 100, "powershell.exe"), p(501, 500, "conhost.exe")]].concat();
        assert_eq!(processos_suspeitos(&antes, &depois, &permitidos), vec![(500, "powershell.exe".into())]);
        let cadeia = [antes.clone(), vec![p(600, 200, "cmd.exe"), p(601, 600, "powershell.exe")]].concat();
        assert_eq!(processos_suspeitos(&antes, &cadeia, &permitidos).len(), 2);
        let script = [antes.clone(), vec![p(700, 200, "mshta.exe")]].concat();
        assert_eq!(processos_suspeitos(&antes, &script, &permitidos), vec![(700, "mshta.exe".into())]);
        // o que não é da ação fica: serviço do sistema, git do editor com o conhost dele, processo que já existia
        let ruido = [antes.clone(), vec![p(800, 300, "cmd.exe"), p(801, 400, "git.exe"), p(802, 801, "conhost.exe"), p(803, 100, "notepad.exe")]].concat();
        assert!(processos_suspeitos(&antes, &ruido, &permitidos).is_empty());
        assert!(processos_suspeitos(&cadeia, &cadeia, &permitidos).is_empty());
    }

    #[test]
    fn ataques_vela9_recusados() {
        for tecla in ["ctrl+Escape", "ctrl+shift+Escape", "alt+Tab", "F12", "ctrl+shift+i"] {
            assert!(interpretar_tecla(tecla).is_err(), "{tecla}");
        }
        for programa in ["explorer.exe", "searchhost.exe", "taskmgr.exe", "wscript.exe"] {
            assert!(conferir_alvo(&alvo(programa, "Executar", 10), &[programa.into()], 99).is_err());
        }
        assert!(conferir_alvo(&alvo("chrome.exe", "Sora - Chrome", 10), &["chrome.exe".into()], 99).is_err());
        let mut pixels = vec![255; 4 * 4 * 3];
        tarjar_rgb(&mut pixels, 4, 4, [-1, 1, 2, 8]);
        assert_eq!(&pixels[12..18], &[0; 6]);
        assert_eq!(&pixels[..12], &[255; 12]);
        assert_eq!(&pixels[18..24], &[255; 6]);
    }

    fn alvo(programa: &str, titulo: &str, pid: u32) -> AlvoJanela {
        AlvoJanela { hwnd: 1, pid, programa: programa.into(), titulo: titulo.into() }
    }

    #[test]
    fn programa_normalizado_e_bloqueios() {
        assert_eq!(normalizar_programa(r"C:\Windows\System32\Notepad.EXE"), "notepad.exe");
        assert!(programa_bloqueado("consent.exe"));
        assert!(programa_bloqueado("keepassxc.exe"));
        assert!(programa_bloqueado("powershell.exe"));
        assert!(!programa_bloqueado("notepad.exe"));
        assert!(titulo_bloqueado("Gerenciador de senhas - Google Chrome"));
        assert!(!titulo_bloqueado("Sem título - Bloco de Notas"));
    }

    #[test]
    fn so_age_em_programa_liberado_e_nunca_na_sora() {
        let liberados = vec!["notepad.exe".to_string()];
        assert!(conferir_alvo(&alvo("notepad.exe", "Notas", 10), &liberados, 99).is_ok());
        let e = conferir_alvo(&alvo("excel.exe", "Pasta1", 10), &liberados, 99).unwrap_err();
        assert_eq!(e.codigo, "programa_nao_permitido");
        assert_eq!(e.programa.as_deref(), Some("excel.exe"));
        // liberado pelo usuário não vale para programa bloqueado nem para a própria Sora
        let todos = vec!["consent.exe".to_string(), "notepad.exe".to_string()];
        assert_eq!(conferir_alvo(&alvo("consent.exe", "", 10), &todos, 99).unwrap_err().codigo, "programa_bloqueado");
        assert_eq!(conferir_alvo(&alvo("notepad.exe", "x", 99), &todos, 99).unwrap_err().codigo, "programa_bloqueado");
        let senhas = alvo("chrome.exe", "Gerenciador de senhas", 10);
        assert_eq!(conferir_alvo(&senhas, &["chrome.exe".into()], 99).unwrap_err().codigo, "programa_bloqueado");
    }

    #[test]
    fn teclas_da_lista_e_proibidas() {
        let (mods, base) = interpretar_tecla("ctrl+l").unwrap();
        assert_eq!(mods, vec![t(VK_CONTROL)]);
        assert_eq!(base, t(b'L' as u16));
        assert_eq!(interpretar_tecla("Return").unwrap().1, t(VK_RETURN));
        assert_eq!(interpretar_tecla("F5").unwrap().1, t(0x74));
        assert!(interpretar_tecla("Page_Down").unwrap().1.estendida);
        assert!(interpretar_tecla("l").is_err(), "letra solta é texto, não tecla");
        assert!(interpretar_tecla("super+r").is_err());
        assert!(interpretar_tecla("ctrl+alt+Delete").is_err());
        assert!(interpretar_tecla("F13").is_err());
        assert!(interpretar_tecla("").is_err());
    }

    #[test]
    fn clique_converte_a_escala_e_confere_o_ponto() {
        let plano = planejar(&json!({"tipo": "clicar", "x": 100, "y": 50}), 1.5, (1920, 1080)).unwrap();
        assert_eq!(plano.conferencias, vec![Conferencia::Ponto(150, 75)]);
        assert_eq!(
            plano.passos,
            vec![Passo::Mover(150, 75), Passo::Botao(Botao::Esquerdo, true), Passo::Botao(Botao::Esquerdo, false)]
        );
        let fora = planejar(&json!({"tipo": "clicar", "x": 1300, "y": 10}), 1.5, (1920, 1080));
        assert_eq!(fora.unwrap_err().codigo, "fora_da_tela");
        assert_eq!(planejar(&json!({"tipo": "clicar"}), 1.0, (10, 10)).unwrap_err().codigo, "invalido");
    }

    #[test]
    fn digitar_vai_por_caractere_e_confere_o_foco() {
        let plano = planejar(&json!({"tipo": "digitar", "texto": "Oi\nç😀", "janela": "123"}), 1.0, (10, 10)).unwrap();
        assert_eq!(plano.trazer, Some(123));
        assert_eq!(plano.conferencias, vec![Conferencia::Foco]);
        assert_eq!(plano.passos[0], Passo::Caractere(b'O' as u16));
        assert_eq!(plano.passos[2], Passo::Tecla(t(VK_RETURN), true));
        assert_eq!(plano.passos.len(), 2 + 2 + 1 + 2); // O, i, Enter, ç, emoji em 2 unidades
        assert!(planejar(&json!({"tipo": "digitar", "texto": ""}), 1.0, (10, 10)).is_err());
        let longo = "a".repeat(2_001);
        assert!(planejar(&json!({"tipo": "digitar", "texto": longo}), 1.0, (10, 10)).is_err());
        assert!(planejar(&json!({"tipo": "abrir", "programa": "terminal"}), 1.0, (10, 10)).is_err());
    }

    #[test]
    fn arrastar_confere_os_dois_pontos_e_rolar_usa_a_roda() {
        let plano = planejar(&json!({"tipo": "arrastar", "x": 0, "y": 0, "ate_x": 10, "ate_y": 20}), 1.0, (100, 100)).unwrap();
        assert_eq!(plano.conferencias, vec![Conferencia::Ponto(0, 0), Conferencia::Ponto(10, 20)]);
        assert_eq!(plano.passos.last(), Some(&Passo::Botao(Botao::Esquerdo, false)));
        let rolar = planejar(&json!({"tipo": "rolar", "direcao": "cima", "quantidade": 2}), 1.0, (10, 10)).unwrap();
        assert_eq!(rolar.conferencias, vec![Conferencia::Foco]);
        assert_eq!(rolar.passos, vec![Passo::Roda(true, 120), Passo::Roda(true, 120)]);
    }

    #[test]
    fn interrompido_no_meio_solta_o_que_ficou_apertado() {
        let plano = planejar(&json!({"tipo": "tecla", "tecla": "ctrl+shift+s"}), 1.0, (10, 10)).unwrap();
        // parou depois de apertar ctrl, shift e s: solta s, shift, ctrl
        let soltar = ainda_apertados(&plano.passos[..3]);
        assert_eq!(soltar.len(), 3);
        assert_eq!(soltar[0], Passo::Tecla(t(b'S' as u16), false));
        assert_eq!(soltar[2], Passo::Tecla(t(VK_CONTROL), false));
        assert!(ainda_apertados(&plano.passos).is_empty());
    }

    #[test]
    fn ids_e_cores() {
        assert!(uuid_valido("0b8f5c1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e"));
        assert!(!uuid_valido("../../etc/passwd"));
        assert!(!uuid_valido("0b8f5c1e-2d3a-4b5c-8d9e-0f1a2b3c4d5"));
        assert_eq!(cor_rgb("#56A8FF"), (0x56, 0xA8, 0xFF));
        assert_eq!(cor_rgb("vermelho"), (0xE2, 0xEC, 0xFF));
        assert_eq!(cor_rgb("a😀b"), (0xE2, 0xEC, 0xFF));
    }
}
