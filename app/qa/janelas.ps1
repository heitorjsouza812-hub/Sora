# Ajuda do teste da Ilha no Tauri real (Windows): lista/controla as janelas do sora.exe via user32.
# Uso: powershell -File qa/janelas.ps1 estado|minimizar|restaurar|foco-outra|foco-sora
#   estado      -> imprime JSON {principal:{visivel,minimizada,foco}, ilha:{visivel}}
#   minimizar   -> minimiza a janela principal (como o botão da barra de título)
#   restaurar   -> restaura e traz a principal para frente
#   foco-outra  -> dá o foco a outro programa (uma janela temporária do PowerShell)
#   foco-sora   -> dá o foco à janela principal da Sora
param([string]$acao = 'estado', [string]$a1 = '', [string]$a2 = '', [string]$a3 = '', [string]$a4 = '', [string]$a5 = '')

Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class U32 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int pid);
  [DllImport("user32.dll")] public static extern void SwitchToThisWindow(IntPtr h, bool alt);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool repintar);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  public static List<IntPtr> DoProcesso(uint pidAlvo) {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { uint pid; GetWindowThreadProcessId(h, out pid); if (pid == pidAlvo) r.Add(h); return true; }, IntPtr.Zero);
    return r;
  }
}
"@

$sora = Get-Process sora -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $sora) { Write-Error 'sora.exe não está rodando'; exit 2 }

function Achar([string]$titulo) {
  foreach ($h in [U32]::DoProcesso([uint32]$sora.Id)) {
    $s = New-Object System.Text.StringBuilder 256; [void][U32]::GetWindowText($h, $s, 256)
    $c = New-Object System.Text.StringBuilder 256; [void][U32]::GetClassName($h, $c, 256)
    if ($c.ToString() -like 'Tauri Window*' -or $c.ToString() -like 'Window Class*') {
      if ($titulo -eq 'ilha' -and $s.ToString() -eq 'Ilha da Sora') { return $h }
      if ($titulo -eq 'principal' -and $s.ToString() -ne 'Ilha da Sora' -and $s.ToString() -ne '') { return $h }
    }
  }
  return [IntPtr]::Zero
}

$principal = Achar 'principal'
$ilha = Achar 'ilha'

# O Windows nega SetForegroundWindow a quem não recebeu a última entrada; uma tecla sintética (F24, que
# ninguém usa; Alt deixava a janela em "modo menu" e ela ignorava o minimizar) + SwitchToThisWindow liberam.
function Focar([IntPtr]$h) {
  for ($i = 0; $i -lt 4; $i++) {
    [U32]::keybd_event(0x87, 0, 0, [UIntPtr]::Zero)
    [void][U32]::BringWindowToTop($h); [void][U32]::SetForegroundWindow($h); [U32]::SwitchToThisWindow($h, $true)
    [U32]::keybd_event(0x87, 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 200
    if ([U32]::GetForegroundWindow().ToInt64() -eq $h.ToInt64()) { return }
  }
}

switch ($acao) {
  'estado' {
    $fg = [U32]::GetForegroundWindow()
    [pscustomobject]@{
      principal = [pscustomobject]@{ encontrada = ($principal -ne [IntPtr]::Zero); visivel = [U32]::IsWindowVisible($principal); minimizada = [U32]::IsIconic($principal); foco = ($fg.ToInt64() -eq $principal.ToInt64()) }
      ilha = [pscustomobject]@{ encontrada = ($ilha -ne [IntPtr]::Zero); visivel = [U32]::IsWindowVisible($ilha); foco = ($fg.ToInt64() -eq $ilha.ToInt64()) }
    } | ConvertTo-Json -Compress
  }
  # como o botão "_" da barra de título: WM_SYSCOMMAND/SC_MINIMIZE (o Windows ativa a próxima janela)
  'minimizar' {
    for ($i = 0; $i -lt 4 -and -not [U32]::IsIconic($principal); $i++) {
      [void][U32]::PostMessage($principal, 0x0112, [IntPtr]0xF020, [IntPtr]::Zero)
      for ($j = 0; $j -lt 10 -and -not [U32]::IsIconic($principal); $j++) { Start-Sleep -Milliseconds 100 }
    }
  }
  # ---- ajudas do teste "cliques atravessam" e do atalho global (coordenadas em pixels físicos) ----
  'rect-ilha' {
    [void][U32]::SetProcessDPIAware()
    $r = New-Object U32+RECT; [void][U32]::GetWindowRect($ilha, [ref]$r)
    [pscustomobject]@{ x = $r.L; y = $r.T; w = $r.R - $r.L; h = $r.B - $r.T } | ConvertTo-Json -Compress
  }
  'cursor' { [void][U32]::SetProcessDPIAware(); [void][U32]::SetCursorPos([int]$a1, [int]$a2) }
  # quem está sob o ponto (x y): a ilha (id da janela) ou outro programa — se a ilha deixa o clique passar, é "outro"
  'janela-em' {
    [void][U32]::SetProcessDPIAware()
    $p = New-Object U32+POINT; $p.X = [int]$a1; $p.Y = [int]$a2
    $h = [U32]::GetAncestor([U32]::WindowFromPoint($p), 2)
    $pid2 = [uint32]0; [void][U32]::GetWindowThreadProcessId($h, [ref]$pid2)
    $s = New-Object System.Text.StringBuilder 256; [void][U32]::GetWindowText($h, $s, 256)
    [pscustomobject]@{ ilha = ($h.ToInt64() -eq $ilha.ToInt64()); processo = (Get-Process -Id $pid2 -ErrorAction SilentlyContinue).ProcessName; titulo = $s.ToString() } | ConvertTo-Json -Compress
  }
  # Ctrl+Shift+S: o atalho global da Ilha (RegisterHotKey reage a entrada sintética)
  'atalho-ilha' {
    [U32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero); [U32]::keybd_event(0x10, 0, 0, [UIntPtr]::Zero); [U32]::keybd_event(0x53, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [U32]::keybd_event(0x53, 0, 2, [UIntPtr]::Zero); [U32]::keybd_event(0x10, 0, 2, [UIntPtr]::Zero); [U32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
  }
  # todas as janelas de nível superior do sora.exe (título, visível, posição) — para ver a borda e o botão Parar
  'listar-sora' {
    [void][U32]::SetProcessDPIAware()
    $lista = foreach ($h in [U32]::DoProcesso([uint32]$sora.Id)) {
      $s = New-Object System.Text.StringBuilder 256; [void][U32]::GetWindowText($h, $s, 256)
      $c = New-Object System.Text.StringBuilder 256; [void][U32]::GetClassName($h, $c, 256)
      if ($c.ToString() -like 'Tauri Window*' -or $c.ToString() -like 'Window Class*' -or $c.ToString() -like 'Sora*') {
        $r = New-Object U32+RECT; [void][U32]::GetWindowRect($h, [ref]$r)
        [pscustomobject]@{ classe = $c.ToString(); titulo = $s.ToString(); visivel = [U32]::IsWindowVisible($h); x = $r.L; y = $r.T; w = $r.R - $r.L; h = $r.B - $r.T }
      }
    }
    $lista | ConvertTo-Json -Compress
  }
  # dá o foco à janela de um programa que o QA abriu (nome do processo, ex.: notepad)
  'foco-processo' {
    $alvo = Get-Process $a1 -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $alvo) { Write-Error "janela de $a1 não encontrada"; exit 4 }
    Focar $alvo.MainWindowHandle
    Write-Output "foco em: $($alvo.ProcessName)"
  }
  # Ctrl+Shift+F12: o atalho global do Parar do controle do PC
  'atalho-parar' {
    [U32]::keybd_event(0x11, 0, 0, [UIntPtr]::Zero); [U32]::keybd_event(0x10, 0, 0, [UIntPtr]::Zero); [U32]::keybd_event(0x7B, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [U32]::keybd_event(0x7B, 0, 2, [UIntPtr]::Zero); [U32]::keybd_event(0x10, 0, 2, [UIntPtr]::Zero); [U32]::keybd_event(0x11, 0, 2, [UIntPtr]::Zero)
  }
  # janela que o QA abriu, achada pelo TÍTULO (terminais do Windows 11 moram dentro do WindowsTerminal.exe)
  'foco-titulo' {
    $alvo = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$a1*" } | Select-Object -First 1
    if (-not $alvo) { Write-Error "janela com título '$a1' não encontrada"; exit 4 }
    Focar $alvo.MainWindowHandle
    Write-Output "foco em: $($alvo.ProcessName)"
  }
  # fecha SÓ o que o QA abriu: processo com esse título E iniciado nos últimos 10 min (nunca um terminal do usuário)
  'fechar-titulo' {
    Get-Process | Where-Object { $_.MainWindowTitle -like "*$a1*" -and $_.StartTime -gt (Get-Date).AddMinutes(-10) } | Stop-Process -Force
  }
  # posiciona SÓ uma janela que o QA abriu (título e iniciada nos últimos 10 min): titulo x y largura altura
  'posicionar-titulo' {
    [void][U32]::SetProcessDPIAware()
    $alvo = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$a1*" -and $_.StartTime -gt (Get-Date).AddMinutes(-10) } | Select-Object -First 1
    if (-not $alvo) { Write-Error "janela com título '$a1' não encontrada"; exit 4 }
    [void][U32]::ShowWindow($alvo.MainWindowHandle, 9)
    [void][U32]::MoveWindow($alvo.MainWindowHandle, [int]$a2, [int]$a3, [int]$a4, [int]$a5, $true)
    Write-Output "posicionada: $($alvo.ProcessName)"
  }
  # fecha com WM_CLOSE (sem matar) SÓ uma janela que o QA abriu nos últimos 10 min
  'fechar-suave' {
    Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$a1*" -and $_.StartTime -gt (Get-Date).AddMinutes(-10) } | ForEach-Object { [void][U32]::PostMessage($_.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) }
  }
  # clique esquerdo (entrada SINTÉTICA, que a vigia do mouse físico ignora de propósito) num ponto da tela
  'clique' {
    [void][U32]::SetProcessDPIAware(); [void][U32]::SetCursorPos([int]$a1, [int]$a2); Start-Sleep -Milliseconds 150
    [U32]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60; [U32]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
  }
  'frente' {
    $fg = [U32]::GetForegroundWindow(); $s = New-Object System.Text.StringBuilder 256; [void][U32]::GetWindowText($fg, $s, 256)
    Write-Output $s.ToString()
  }
  'restaurar' { [void][U32]::ShowWindow($principal, 9); Focar $principal }
  'foco-sora' { Focar $principal }
  # Com SORA_QA_JANELA_EXE (qa/janela-qa.cs compilado) o "outro programa" é uma janela de teste NOSSA: o QA não
  # mexe no foco de janelas do usuário. Sem a variável, cai no comportamento antigo (primeira janela alheia).
  'limpar' { Get-Process janela-qa -ErrorAction SilentlyContinue | Stop-Process -Force }
  'foco-outra' {
    if ($env:SORA_QA_JANELA_EXE -and (Test-Path $env:SORA_QA_JANELA_EXE)) {
      $minha = Get-Process janela-qa -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
      if (-not $minha) {
        Start-Process $env:SORA_QA_JANELA_EXE -ArgumentList 'outra'
        for ($i = 0; $i -lt 30 -and -not $minha; $i++) { Start-Sleep -Milliseconds 200; $minha = Get-Process janela-qa -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1 }
      }
      Focar $minha.MainWindowHandle
      Write-Output 'foco em: janela-qa'
      return
    }
    $outra = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.Id -ne $sora.Id -and $_.ProcessName -notin @('powershell','pwsh') } | Select-Object -First 1
    if (-not $outra) { Write-Error 'nenhuma outra janela para focar'; exit 3 }
    Focar $outra.MainWindowHandle
    Write-Output "foco em: $($outra.ProcessName)"
  }
}
