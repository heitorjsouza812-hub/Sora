fn main() {
    // Comandos do app declarados no manifesto: cada um só funciona na janela cuja capability
    // o libera (capabilities/main.json e capabilities/ilha.json). APP-003.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "ilha_retangulo",
            "ilha_visivel",
            "mostrar_app",
            "navegar",
            "cofre_ler",
            "cofre_gravar",
            "cofre_apagar",
        ]),
    ))
    .expect("falha ao gerar o manifesto do app Tauri");
}
