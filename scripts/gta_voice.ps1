param([Parameter(Mandatory)][string] $BriefPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $portuguese = $voice.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'pt-BR'
    } | Select-Object -First 1
    if (-not $portuguese) { throw 'Voz pt-BR indisponível.' }
    $voice.SelectVoice($portuguese.VoiceInfo.Name)
    $lines = Get-Content -LiteralPath $BriefPath -Raw -Encoding UTF8 | ConvertFrom-Json
    for ($index = 0; $index -lt $lines.Count; $index++) {
        $voice.SetOutputToWaveFile((Join-Path (Split-Path -Parent $BriefPath) "voice-$index.wav"))
        $voice.Speak([string] $lines[$index])
        $voice.SetOutputToNull()
    }
} finally {
    $voice.Dispose()
}
