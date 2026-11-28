# Conferência FORA do bot das tarefas de tela G01–G10 e das reproduções R1/R3 (tarefa 0.5).
# Não é código do produto. Tudo aqui só LÊ a tela (UI Automation, COM do Excel, user32), exceto
# "intruso", que abre a janela intrusa da G10 de propósito.
#
# Uso (Windows PowerShell 5.1, no PC do Heitor):
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 frente
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 vigiar-frente -Saida C:\bancada-g\G04-r1-frente.csv -Segundos 600
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 notepad-texto [-Titulo G02_lista]
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 calc-valor
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 excel-tabela
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 janelas
#   powershell -ExecutionPolicy Bypass -File conferir_g.ps1 intruso -Atraso 8 [-Pasta C:\bancada-g]
# Saída: uma linha JSON (o roteiro manda colar no baseline.md o essencial).
param(
  [Parameter(Position = 0)][string]$Acao = 'frente',
  [string]$Titulo = '',
  [string]$Saida = '',
  [int]$Segundos = 600,
  [int]$Atraso = 8,
  [string]$Pasta = 'C:\bancada-g'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class Jan {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  public static string Texto(IntPtr h) { var s = new StringBuilder(512); GetWindowText(h, s, 512); return s.ToString(); }
  public static string Classe(IntPtr h) { var s = new StringBuilder(256); GetClassName(h, s, 256); return s.ToString(); }
  public static List<IntPtr> Visiveis() {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { if (IsWindowVisible(h) && Texto(h).Length > 0) r.Add(h); return true; }, IntPtr.Zero);
    return r;
  }
}
"@

function Descrever([IntPtr]$h) {
  $pid0 = [uint32]0
  [void][Jan]::GetWindowThreadProcessId($h, [ref]$pid0)
  $proc = (Get-Process -Id $pid0 -ErrorAction SilentlyContinue)
  [ordered]@{ hwnd = ('0x{0:X}' -f $h.ToInt64()); pid = $pid0; processo = if ($proc) { $proc.ProcessName + '.exe' } else { '?' };
              titulo = [Jan]::Texto($h); classe = [Jan]::Classe($h) }
}

function Json($obj) { $obj | ConvertTo-Json -Depth 6 -Compress }

function UiaDe([IntPtr]$h) {
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  [System.Windows.Automation.AutomationElement]::FromHandle($h)
}

function JanelasDe([string]$processo, [string]$titulo) {
  foreach ($h in [Jan]::Visiveis()) {
    $d = Descrever $h
    if ($d.processo -ieq $processo -and ($titulo -eq '' -or $d.titulo -like "*$titulo*")) { $h }
  }
}

switch ($Acao) {
  'frente' {
    $d = Descrever ([Jan]::GetForegroundWindow())
    $d['hora'] = (Get-Date).ToString('HH:mm:ss.fff')
    Json $d
  }
  'janelas' {
    $lista = foreach ($h in [Jan]::Visiveis()) { Descrever $h }
    Json @($lista)
  }
  'vigiar-frente' {
    # Registra cada troca da janela em primeiro plano (a cada 200 ms) até Ctrl+C ou -Segundos.
    if (-not $Saida) { throw 'Informe -Saida (arquivo .csv).' }
    'hora;hwnd;pid;processo;titulo' | Out-File -FilePath $Saida -Encoding utf8
    $ultimo = ''
    $fim = (Get-Date).AddSeconds($Segundos)
    while ((Get-Date) -lt $fim) {
      $d = Descrever ([Jan]::GetForegroundWindow())
      $chave = "$($d.hwnd)|$($d.titulo)"
      if ($chave -ne $ultimo) {
        $ultimo = $chave
        $linha = "{0};{1};{2};{3};{4}" -f (Get-Date).ToString('HH:mm:ss.fff'), $d.hwnd, $d.pid, $d.processo, ($d.titulo -replace ';', ',')
        $linha | Out-File -FilePath $Saida -Append -Encoding utf8
        Write-Host $linha
      }
      Start-Sleep -Milliseconds 200
    }
  }
  'notepad-texto' {
    # Texto do documento ATIVO de cada janela do Bloco de Notas (TextPattern). -Titulo filtra pelo título.
    $res = @()
    foreach ($h in (JanelasDe 'notepad.exe' $Titulo)) {
      $raiz = UiaDe $h
      $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
      $doc = $raiz.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
      if (-not $doc) {
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
        $doc = $raiz.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
      }
      $texto = $null
      if ($doc) {
        $tp = $null
        if ($doc.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$tp)) { $texto = $tp.DocumentRange.GetText(-1) }
        else { $vp = $null; if ($doc.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) { $texto = $vp.Current.Value } }
      }
      $norm = if ($null -ne $texto) { ($texto -replace "`r`n", "`n") -replace "`r", "`n" } else { $null }
      $sha = if ($null -ne $norm) { -join ([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($norm.TrimEnd("`n"))) | ForEach-Object { $_.ToString('x2') }) } else { $null }
      $d = Descrever $h
      $d['texto'] = $norm
      $d['sha256_sem_quebra_final'] = $sha
      $res += $d
    }
    Json @($res)
  }
  'calc-valor' {
    $res = @()
    foreach ($h in [Jan]::Visiveis()) {
      $d = Descrever $h
      if ($d.titulo -notmatch '^(Calculadora|Calculator)') { continue }
      $raiz = UiaDe $h
      $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'CalculatorResults')
      $el = $raiz.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
      $d['visor'] = if ($el) { $el.Current.Name } else { $null }
      $d['numero'] = if ($el) { ($el.Current.Name -replace '[^\d,\.\-]', '') } else { $null }
      $res += $d
    }
    Json @($res)
  }
  'excel-tabela' {
    # Só leitura, pelo COM do Excel aberto: planilha ativa, até 12 linhas × 8 colunas da área usada.
    $xl = [Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application')
    $wb = $xl.ActiveWorkbook; $ws = $xl.ActiveSheet; $usado = $ws.UsedRange
    $celulas = @()
    $nl = [Math]::Min($usado.Rows.Count, 12); $nc = [Math]::Min($usado.Columns.Count, 8)
    for ($i = 1; $i -le $nl; $i++) {
      for ($j = 1; $j -le $nc; $j++) {
        $c = $usado.Cells.Item($i, $j)
        if ($null -eq $c.Value2 -or "$($c.Value2)" -eq '') { continue }
        $celulas += [ordered]@{ endereco = $c.Address($false, $false); valor = "$($c.Value2)";
          sublinhado = ($c.Font.Underline -ne -4142 -and $c.Font.Underline -ne $false -and $null -ne $c.Font.Underline);
          negrito = [bool]$c.Font.Bold; cor_fundo = ($c.Interior.ColorIndex -ne -4142); cor_fonte = $c.Font.Color }
      }
    }
    Json ([ordered]@{ pasta = $wb.Name; salvo = [bool]$wb.Saved; caminho = $wb.FullName; planilha = $ws.Name;
      area_usada = $usado.Address($false, $false); linhas = $usado.Rows.Count; colunas = $usado.Columns.Count;
      celulas_com_valor = $celulas.Count; com_sublinhado = @($celulas | Where-Object { $_.sublinhado }).Count;
      com_cor_de_fundo = @($celulas | Where-Object { $_.cor_fundo }).Count; celulas = $celulas })
  }
  'intruso' {
    # G10: abre a janela intrusa (Bloco de Notas com G10_intruso.txt) depois de -Atraso segundos.
    $arq = Join-Path $Pasta 'G10_intruso.txt'
    if (-not (Test-Path $arq)) { throw "Falta $arq (rode fixtures_gui.py preparar)." }
    Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-Command', "Start-Sleep -Seconds $Atraso; Start-Process notepad.exe -ArgumentList '`"$arq`"'")
    Json ([ordered]@{ intruso = $arq; abre_em_s = $Atraso; hora = (Get-Date).ToString('HH:mm:ss.fff') })
  }
  default { throw "Ação desconhecida: $Acao" }
}
