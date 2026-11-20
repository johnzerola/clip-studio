using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;

internal static class Setup {
    [STAThread] static void Main() {
        Application.EnableVisualStyles();
        try {
            string parent;
            using (var choose = new FolderBrowserDialog()) {
                choose.Description = "Onde deseja instalar o Cortex Clip Studio?";
                choose.SelectedPath = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (choose.ShowDialog() != DialogResult.OK) return;
                parent = choose.SelectedPath;
            }
            var target = Path.Combine(parent, "Cortex Clip Studio " + typeof(Setup).Assembly.GetName().Version.ToString(3));
            if (Directory.Exists(target)) { MessageBox.Show("Esta pasta já existe. Abra o aplicativo instalado ou escolha outra pasta."); return; }
            using (var form = new Form { Text = "Instalar Clip Studio", Width = 500, Height = 150, StartPosition = FormStartPosition.CenterScreen, ControlBox = false }) {
                var label = new Label { Dock = DockStyle.Fill, TextAlign = System.Drawing.ContentAlignment.MiddleCenter, Text = "Extraindo o painel e as ferramentas de edição…" };
                form.Controls.Add(label);
                form.Shown += async delegate {
                    try {
                        await Task.Run(() => Extract(target));
                        label.Text = "Instalando e verificando as dependências. Pode levar alguns minutos…";
                        var info = new ProcessStartInfo("powershell.exe", "-NoProfile -ExecutionPolicy RemoteSigned -File \"" + Path.Combine(target,"scripts/install.ps1") + "\" -InstallPrerequisites") { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = target };
                        int exit = await Task.Run(() => {
                            using (var p = Process.Start(info)) { p.WaitForExit(); return p.ExitCode; }
                        });
                        if (exit != 0) throw new Exception("Execute Instalar.cmd --automatico em " + target + " para ver o diagnóstico.");
                        await Task.Run(() => Process.Start(new ProcessStartInfo(Path.Combine(target, "Iniciar.cmd")) {
                            WorkingDirectory = target,
                            UseShellExecute = true
                        }));
                    } catch (Exception e) { MessageBox.Show(e.Message, "Instalação"); }
                    finally { form.Close(); }
                };
                Application.Run(form);
            }
        } catch (Exception e) { MessageBox.Show(e.Message, "Clip Studio"); }
    }
    static void Extract(string target) {
        Directory.CreateDirectory(target);
        using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
        using (var zip = new ZipArchive(stream, ZipArchiveMode.Read)) {
            foreach (var item in zip.Entries) {
                if (!item.FullName.StartsWith("Clip-Studio/", StringComparison.Ordinal)) throw new InvalidDataException();
                var path = Path.GetFullPath(Path.Combine(target, item.FullName.Substring(12)));
                if (!path.StartsWith(target + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                using (var source = item.Open()) using (var output = new FileStream(path, FileMode.CreateNew)) source.CopyTo(output);
            }
        }
    }
}
