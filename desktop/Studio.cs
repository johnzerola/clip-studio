using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Studio {
    [STAThread] static void Main() {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string launcher = Path.Combine(root, "scripts", "launch.ps1");
        try {
            using (var process = Process.Start(new ProcessStartInfo("powershell.exe",
                "-NoProfile -ExecutionPolicy RemoteSigned -File \"" + launcher + "\"") {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true
            })) {
                process.WaitForExit();
                if (process.ExitCode != 0) throw new InvalidOperationException("Execute Instalar.cmd --verificar para conferir as dependências.");
            }
        } catch (Exception error) {
            MessageBox.Show(error.Message, "Codex · Edição de vídeo", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
