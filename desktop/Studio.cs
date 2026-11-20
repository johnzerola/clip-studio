using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal sealed class Studio : Form {
    const string Origin = "http://127.0.0.1:45839";
    readonly string root = AppDomain.CurrentDomain.BaseDirectory;
    readonly string token = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
    readonly Label splash = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter, Text = "Abrindo o Cortex Studio…" };
    readonly Button classic = new Button { Dock = DockStyle.Bottom, Height = 42, Text = "Abrir painel clássico", Visible = false };
    readonly Timer timer = new Timer { Interval = 20 * 60 * 1000 };
    WebView2 view;
    Process server;
    bool checking;
    static readonly string stateDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Cortex Clip Studio");

    Studio() {
        Text = "Cortex · Clip Studio";
        Width = 1280; Height = 850; MinimumSize = new Size(820, 560);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(23, 23, 27);
        ForeColor = Color.WhiteSmoke;
        Controls.Add(splash);
        Controls.Add(classic);
        classic.Click += delegate { OpenClassic(); };
        Shown += async delegate {
            try {
                await Task.Yield();
                await StartStudio();
            } catch (Exception e) {
                if (!IsDisposed) ShowStartupError(e.Message);
            }
        };
        FormClosed += delegate { timer.Stop(); StopServer(); };
    }
    string Local(string name) { return Path.Combine(root, name); }
    ProcessStartInfo Command(string exe, string args) {
        return new ProcessStartInfo(exe, args) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true };
    }
    static void Log(string stage) {
        try {
            Directory.CreateDirectory(stateDir);
            File.AppendAllText(Path.Combine(stateDir, "startup.log"), DateTime.Now.ToString("s") + " " + stage + Environment.NewLine);
        } catch (IOException) {} catch (UnauthorizedAccessException) {}
    }
    void StopServer() {
        if (server == null) return;
        try { server.StandardInput.Close(); } catch (IOException) {}
        server.Dispose();
        server = null;
    }
    void ShowStartupError(string message) {
        Log("Falha: " + message);
        if (view != null) { view.Dispose(); view = null; }
        StopServer();
        splash.Text = message + Environment.NewLine + "Você pode abrir o painel clássico de edição.";
        classic.Visible = File.Exists(Local(".venv/Scripts/pythonw.exe"));
    }
    async void OpenClassic() {
        classic.Enabled = false;
        try {
            await Task.Run(() => Process.Start(Command(Local(".venv/Scripts/pythonw.exe"), "-X utf8 painel.py")));
            Close();
        } catch (Exception e) {
            classic.Enabled = true;
            MessageBox.Show(this, e.Message, Text);
        }
    }
    bool WaitForServer(Process child) {
        var elapsed = Stopwatch.StartNew();
        while (elapsed.Elapsed < TimeSpan.FromSeconds(15)) {
            if (child.HasExited) throw new Exception("O serviço local não abriu. Verifique a porta 45839.");
            var request = (HttpWebRequest)WebRequest.Create(Origin + "/_desktop/ready");
            request.Proxy = null;
            request.Timeout = 1000;
            request.ReadWriteTimeout = 1000;
            request.AllowAutoRedirect = false;
            request.Headers["X-Cortex-Session"] = token;
            try {
                using (var response = (HttpWebResponse)request.GetResponse())
                using (var reader = new StreamReader(response.GetResponseStream())) {
                    if (response.StatusCode == HttpStatusCode.OK && reader.ReadToEnd() == "ready") return true;
                }
            } catch (WebException error) {
                if (error.Response != null) error.Response.Dispose();
            }
            System.Threading.Thread.Sleep(250);
        }
        return false;
    }
    static async Task<T> Limit<T>(Task<T> operation, string message) {
        if (await Task.WhenAny(operation, Task.Delay(20000)) != operation) {
            throw new TimeoutException(message);
        }
        return await operation;
    }
    static async void CloseLateServer(Task<Process> launch) {
        try {
            using (var child = await launch.ConfigureAwait(false)) { child.StandardInput.Close(); }
        } catch (Exception e) { Log("Falha no encerramento do serviço: " + e.Message); }
    }
    async Task StartStudio() {
        Log("Iniciando Cortex");
        if (!File.Exists(Local(".venv/Scripts/python.exe")) || !File.Exists(Local("desktop/runtime/node.exe"))) {
            splash.Text = "Preparando o painel e os motores de vídeo…";
            var setup = Command("powershell.exe", "-NoProfile -ExecutionPolicy RemoteSigned -File \"" + Local("scripts/install.ps1") + "\" -InstallPrerequisites");
            int exit = await Task.Run(() => {
                using (var p = Process.Start(setup)) { p.WaitForExit(); return p.ExitCode; }
            });
            if (IsDisposed) return;
            if (exit != 0) throw new Exception("A preparação falhou. Abra Instalar.cmd --automatico para ver o diagnóstico.");
        }
        splash.Text = "Iniciando o serviço local…";
        var start = Command(Local("desktop/runtime/node.exe"), "\"" + Local("desktop/server.mjs") + "\"");
        start.RedirectStandardInput = true;
        start.EnvironmentVariables["CORTEX_SESSION"] = token;
        var launch = Task.Run(() => Process.Start(start));
        if (await Task.WhenAny(launch, Task.Delay(15000)) != launch) {
            CloseLateServer(launch);
            throw new TimeoutException("O Windows demorou para iniciar o serviço local.");
        }
        server = await launch;
        if (IsDisposed) { StopServer(); return; }
        Log("Serviço iniciado");
        var process = server;
        bool ready = await Task.Run(() => WaitForServer(process));
        if (IsDisposed) return;
        if (!ready) throw new TimeoutException("O serviço local demorou para responder.");
        Log("Serviço respondeu");
        splash.Text = "Abrindo o painel…";
        var env = await Limit(CoreWebView2Environment.CreateAsync(null, Path.Combine(stateDir, "WebView"), null),
            "O Microsoft Edge WebView2 demorou para iniciar.");
        if (IsDisposed) return;
        view = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
        Controls.Add(view);
        var initialize = view.EnsureCoreWebView2Async(env);
        if (await Task.WhenAny(initialize, Task.Delay(20000)) != initialize) {
            throw new TimeoutException("A janela do WebView2 demorou para iniciar.");
        }
        await initialize;
        if (IsDisposed) return;
        Log("WebView2 iniciado");
        var web = view.CoreWebView2;
        web.AddWebResourceRequestedFilter(Origin + "/*", CoreWebView2WebResourceContext.All, CoreWebView2WebResourceRequestSourceKinds.All);
        web.WebResourceRequested += (sender, args) => {
            Uri uri;
            if (Uri.TryCreate(args.Request.Uri, UriKind.Absolute, out uri) && uri.GetLeftPart(UriPartial.Authority) == Origin) {
                args.Request.Headers.SetHeader("X-Cortex-Session", token);
            }
        };
        web.NavigationStarting += (sender, args) => {
            if (!args.Uri.StartsWith(Origin + "/", StringComparison.Ordinal)) {
                args.Cancel = true;
                OpenExternal(args.Uri);
            }
        };
        web.NewWindowRequested += (sender, args) => { args.Handled = true; OpenExternal(args.Uri); };
        var loaded = new TaskCompletionSource<CoreWebView2NavigationCompletedEventArgs>();
        EventHandler<CoreWebView2NavigationCompletedEventArgs> firstLoad = (sender, args) => loaded.TrySetResult(args);
        web.NavigationCompleted += firstLoad;
        web.Navigate(Origin + "/");
        var result = await Limit(loaded.Task, "O painel demorou para carregar.");
        if (IsDisposed) return;
        web.NavigationCompleted -= firstLoad;
        if (!result.IsSuccess || result.HttpStatusCode >= 400) {
            throw new Exception("O painel não abriu no WebView2 (" + result.WebErrorStatus + ", HTTP " + result.HttpStatusCode + ").");
        }
        view.BringToFront();
        Log("Painel aberto");
        timer.Tick += async delegate { await CheckUpdate(); };
        timer.Start(); await CheckUpdate();
    }
    static void OpenExternal(string value) {
        Uri url;
        if (Uri.TryCreate(value, UriKind.Absolute, out url) && url.Scheme == "https")
            Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true });
    }
    async Task CheckUpdate() {
        if (checking) return;
        checking = true;
        try {
            var info = Command(Local(".venv/Scripts/python.exe"), "-X utf8 desktop_actions.py update");
            info.RedirectStandardInput = true; info.RedirectStandardOutput = true;
            using (var proc = Process.Start(info)) {
                proc.StandardInput.Write("{}"); proc.StandardInput.Close();
                var result = await proc.StandardOutput.ReadToEndAsync();
                if (result.Contains("\"installing\": true") && !IsDisposed) Close();
            }
        } catch (Exception e) { Log("Falha ao verificar atualização: " + e.Message); }
        finally { checking = false; }
    }
    [STAThread] static void Main() {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        using (var mutex = new System.Threading.Mutex(false, "Local\\CortexHookSparkWindow")) {
            if (!mutex.WaitOne(0)) { MessageBox.Show("O Clip Studio já está aberto."); return; }
            try { Application.Run(new Studio()); } finally { mutex.ReleaseMutex(); }
        }
    }
}
