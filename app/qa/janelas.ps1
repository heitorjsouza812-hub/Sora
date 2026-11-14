# Ajuda do teste da Ilha no Tauri real (Windows): lista/controla as janelas do sora.exe via user32.
# Uso: powershell -File qa/janelas.ps1 estado|minimizar|restaurar|foco-outra|foco-sora
#   estado      -> imprime JSON {principal:{visivel,minimizada,foco}, ilha:{visivel}}
#   minimizar   -> minimiza a janela principal (como o botão da barra de título)
#   restaurar   -> restaura e traz a principal para frente
#   foco-outra  -> dá o foco a outro programa (uma janela temporária do PowerShell)
#   foco-sora   -> dá o foco à janela principal da Sora
param([string]$acao = 'estado')

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
  'frente' {
    $fg = [U32]::GetForegroundWindow(); $s = New-Object System.Text.StringBuilder 256; [void][U32]::GetWindowText($fg, $s, 256)
    Write-Output $s.ToString()
  }
  'restaurar' { [void][U32]::ShowWindow($principal, 9); Focar $principal }
  'foco-sora' { Focar $principal }
  'foco-outra' {
    $outra = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.Id -ne $sora.Id -and $_.ProcessName -notin @('powershell','pwsh') } | Select-Object -First 1
    if (-not $outra) { Write-Error 'nenhuma outra janela para focar'; exit 3 }
    Focar $outra.MainWindowHandle
    Write-Output "foco em: $($outra.ProcessName)"
  }
}
