fn main() {
    // Comandos do app declarados no manifesto: cada um só funciona na janela cuja capability
    // o libera (capabilities/main.json e capabilities/ilha.json). APP-003.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "ilha_emitir",
            "ilha_retangulo",
            "ilha_visivel",
            "notificar_atencao",
            "titulo_atencao",
            "mostrar_app",
            "navegar",
            "cofre_ler",
            "cofre_gravar",
            "cofre_apagar",
            "pc_conta",
            "pc_autorizar",
            "pc_estado",
            "pc_executar",
            "pc_parar",
            "pc_sair",
        ]),
    ))
    .expect("falha ao gerar o manifesto do app Tauri");
}
