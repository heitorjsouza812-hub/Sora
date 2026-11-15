// Janela de teste do QA do desktop real (nunca vai para o produto). Compilar com o csc do .NET Framework:
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /r:System.Windows.Forms.dll /r:System.Drawing.dll /out:janela-qa.exe janela-qa.cs
// Modos:  outra  → janela comum, só para ter "outro programa" em foco (qa/janelas.ps1 foco-outra)
//         senha  → janela com um campo de SENHA (já com o foco) e um campo comum, para o teste do C3.
//         sora   → janela magenta com "Sora" no título: o C3 tem de tarjar só a parte dela que aparece (D1).
using System;
using System.Drawing;
using System.Windows.Forms;

static class Programa {
  [STAThread]
  static void Main(string[] args) {
    Application.EnableVisualStyles();
    string modo = args.Length > 0 ? args[0] : "outra";
    var f = new Form {
      Text = modo == "senha" ? "QA campo de senha" : modo == "sora" ? "Sora - QA da tarja" : "QA outra janela",
      Width = 440, Height = 230, StartPosition = FormStartPosition.Manual, Location = new Point(140, 140),
    };
    // opcional: janela-qa.exe <modo> <x> <y> [<largura> <altura>]
    int x, y, w, h;
    if (args.Length > 2 && int.TryParse(args[1], out x) && int.TryParse(args[2], out y)) f.Location = new Point(x, y);
    if (args.Length > 4 && int.TryParse(args[3], out w) && int.TryParse(args[4], out h)) { f.Width = w; f.Height = h; }
    if (modo == "sora") f.BackColor = Color.Magenta;
    if (modo == "senha") {
      var rotulo1 = new Label { Text = "Senha (campo de teste)", Left = 12, Top = 12, Width = 400 };
      var senha = new TextBox { Left = 12, Top = 34, Width = 400, UseSystemPasswordChar = true, Name = "campoSenha", TabIndex = 0 };
      var rotulo2 = new Label { Text = "Campo comum (teste)", Left = 12, Top = 80, Width = 400 };
      var comum = new TextBox { Left = 12, Top = 102, Width = 400, Name = "campoComum", TabIndex = 1 };
      f.Controls.AddRange(new Control[] { rotulo1, senha, rotulo2, comum });
      f.Shown += (o, e) => { f.Activate(); senha.Focus(); };
    } else {
      f.Controls.Add(new Label { Text = "Janela de teste do QA — pode fechar.", Left = 12, Top = 12, Width = 400 });
    }
    Application.Run(f);
  }
}
