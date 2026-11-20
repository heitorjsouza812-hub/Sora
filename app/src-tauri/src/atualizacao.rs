//! Atualização automática do app de desktop (Onda 1, 2026-11-20).
//!
//! O app procura `latest.json` no endereço de `plugins.updater.endpoints` (tauri.conf.json), baixa
//! o instalador novo e só instala se a assinatura (minisign) bater com a chave pública de
//! `plugins.updater.pubkey`. Enquanto a chave pública estiver vazia, a atualização fica desligada
//! e o app diz isso, sem erro. Como ligar: `app/docs/atualizacao-desktop.md`.
//!
//! Só a janela principal pode verificar e instalar (mesma regra dos outros comandos, APP-003).

use serde::Serialize;
use tauri::{AppHandle, Runtime, WebviewWindow};
use tauri_plugin_updater::UpdaterExt;

/// O que a janela principal recebe de `atualizacao_verificar`.
#[derive(Debug, Serialize, PartialEq, Eq)]
#[serde(tag = "estado", rename_all = "snake_case")]
pub enum Verificacao {
    /// Sem chave pública no tauri.conf.json: esta versão não se atualiza sozinha.
    Desligada { versao_atual: String },
    EmDia { versao_atual: String },
    Disponivel { versao_atual: String, versao_nova: String, notas: Option<String> },
}

/// Chave pública configurada (vazia = atualização desligada).
pub fn chave_publica(plugins: &serde_json::Value) -> String {
    plugins
        .get("updater")
        .and_then(|u| u.get("pubkey"))
        .and_then(|p| p.as_str())
        .unwrap_or("")
        .trim()
        .to_string()
}

fn ligada<R: Runtime>(app: &AppHandle<R>) -> bool {
    let plugins = serde_json::to_value(&app.config().plugins).unwrap_or_default();
    !chave_publica(&plugins).is_empty()
}

/// Erro do plugin em PT-BR, sem endereço nem detalhe técnico (vai para a tela).
fn texto_do_erro(erro: tauri_plugin_updater::Error) -> String {
    use tauri_plugin_updater::Error as E;
    match erro {
        E::ReleaseNotFound | E::TargetNotFound(_) | E::TargetsNotFound(_) => {
            "Não achei a versão nova no servidor de atualizações. Tente mais tarde.".into()
        }
        E::Minisign(_)
        | E::Base64(_)
        | E::SignatureUtf8(_)
        | E::SignedVersionMismatch { .. }
        | E::MissingSignedVersion => {
            "O instalador baixado não tem a assinatura da Sora. Nada foi instalado.".into()
        }
        E::Reqwest(_) | E::Network(_) => {
            "Sem conexão com o servidor de atualizações. Tente de novo.".into()
        }
        _ => "Não consegui verificar a atualização agora. Tente de novo.".into(),
    }
}

fn so_principal(comando: &str, janela: &WebviewWindow) -> Result<(), String> {
    if crate::janela_pode(comando, janela.label()) {
        Ok(())
    } else {
        Err("só a janela principal cuida da atualização".into())
    }
}

#[tauri::command]
pub async fn atualizacao_verificar(janela: WebviewWindow, app: AppHandle) -> Result<Verificacao, String> {
    so_principal("atualizacao_verificar", &janela)?;
    let versao_atual = app.package_info().version.to_string();
    if !ligada(&app) {
        return Ok(Verificacao::Desligada { versao_atual });
    }
    let atualizador = app.updater().map_err(texto_do_erro)?;
    Ok(match atualizador.check().await.map_err(texto_do_erro)? {
        None => Verificacao::EmDia { versao_atual },
        Some(nova) => Verificacao::Disponivel {
            versao_atual: nova.current_version.clone(),
            versao_nova: nova.version.clone(),
            notas: nova.body.clone(),
        },
    })
}

/// Baixa, confere a assinatura e instala. No Windows o instalador fecha o app sozinho; nos
/// outros sistemas o app reinicia aqui.
#[tauri::command]
pub async fn atualizacao_instalar(janela: WebviewWindow, app: AppHandle) -> Result<(), String> {
    so_principal("atualizacao_instalar", &janela)?;
    if !ligada(&app) {
        return Err("A atualização automática não está ligada nesta versão.".into());
    }
    let atualizador = app.updater().map_err(texto_do_erro)?;
    let Some(nova) = atualizador.check().await.map_err(texto_do_erro)? else {
        return Err("Você já está na versão mais nova.".into());
    };
    nova.download_and_install(|_, _| {}, || {}).await.map_err(texto_do_erro)?;
    app.restart();
}

#[cfg(test)]
mod testes {
    use super::*;

    #[test]
    fn chave_vazia_desliga() {
        let sem = serde_json::json!({ "updater": { "pubkey": "  ", "endpoints": [] } });
        assert_eq!(chave_publica(&sem), "");
        assert_eq!(chave_publica(&serde_json::json!({})), "");
        let com = serde_json::json!({ "updater": { "pubkey": "dW50cnVzdGVk" } });
        assert_eq!(chave_publica(&com), "dW50cnVzdGVk");
    }

    #[test]
    fn verificacao_vai_para_o_app_com_estado_em_portugues() {
        let v = Verificacao::Disponivel { versao_atual: "0.1.0".into(), versao_nova: "0.2.0".into(), notas: None };
        let json = serde_json::to_value(&v).unwrap();
        assert_eq!(json["estado"], "disponivel");
        assert_eq!(json["versao_nova"], "0.2.0");
        let desligada = serde_json::to_value(Verificacao::Desligada { versao_atual: "0.1.0".into() }).unwrap();
        assert_eq!(desligada["estado"], "desligada");
    }
}
