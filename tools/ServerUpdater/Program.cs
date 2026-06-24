using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;


namespace ServerUpdater;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class MainForm : Form
{
    private readonly Button startButton = new();
    private readonly Button restartButton = new();
    private readonly Button updateRestartButton = new();
    private readonly Button createUserButton = new();
    private readonly TextBox logBox = new();
    private readonly Label statusLabel = new();
    private readonly string projectDir;
    private readonly string stateDir;
    private readonly string pidFile;
    private readonly string serviceOutLog;
    private readonly string serviceErrLog;
    private readonly UpdaterConfig config;
    private const string FirewallRulePrefix = "DingDanGuanLi TCP";
    private bool busy;

    public MainForm()
    {
        projectDir = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
        stateDir = Path.Combine(projectDir, ".server-updater");
        pidFile = Path.Combine(stateDir, "service.pid");
        serviceOutLog = Path.Combine(stateDir, "service.out.log");
        serviceErrLog = Path.Combine(stateDir, "service.err.log");
        Directory.CreateDirectory(stateDir);
        config = UpdaterConfig.Load(projectDir);

        Text = "项目服务管理器";
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 10F);
        MinimumSize = new Size(780, 520);
        Size = new Size(860, 560);

        var title = new Label
        {
            Text = "订单管理项目服务管理器",
            Dock = DockStyle.Top,
            Height = 44,
            TextAlign = ContentAlignment.MiddleLeft,
            Font = new Font(Font.FontFamily, 14F, FontStyle.Bold),
            Padding = new Padding(16, 0, 16, 0)
        };

        var pathLabel = new Label
        {
            Text = $"项目目录：{projectDir}",
            Dock = DockStyle.Top,
            Height = 30,
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(16, 0, 16, 0)
        };

        var buttonPanel = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 72,
            ColumnCount = 4,
            Padding = new Padding(16, 12, 16, 12)
        };
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25F));

        ConfigureButton(startButton, "启动服务");
        ConfigureButton(restartButton, "重启服务");
        ConfigureButton(updateRestartButton, "拉取最新并重启");
        ConfigureButton(createUserButton, "创建账号");
        buttonPanel.Controls.Add(startButton, 0, 0);
        buttonPanel.Controls.Add(restartButton, 1, 0);
        buttonPanel.Controls.Add(updateRestartButton, 2, 0);
        buttonPanel.Controls.Add(createUserButton, 3, 0);

        statusLabel.Dock = DockStyle.Top;
        statusLabel.Height = 32;
        statusLabel.TextAlign = ContentAlignment.MiddleLeft;
        statusLabel.Padding = new Padding(16, 0, 16, 0);

        logBox.Dock = DockStyle.Fill;
        logBox.Multiline = true;
        logBox.ReadOnly = true;
        logBox.ScrollBars = ScrollBars.Vertical;
        logBox.Font = new Font("Consolas", 10F);
        logBox.BackColor = Color.White;
        logBox.Margin = new Padding(16);

        Controls.Add(logBox);
        Controls.Add(statusLabel);
        Controls.Add(buttonPanel);
        Controls.Add(pathLabel);
        Controls.Add(title);

        startButton.Click += async (_, _) => await RunExclusiveAsync("启动服务", StartServiceAsync);
        restartButton.Click += async (_, _) => await RunExclusiveAsync("重启服务", RestartServiceAsync);
        updateRestartButton.Click += async (_, _) => await RunExclusiveAsync("拉取最新并重启服务", UpdateAndRestartAsync);
        createUserButton.Click += (_, _) => ShowCreateUserDialog();

        Shown += (_, _) =>
        {
            UpdateStatus();
            Log("程序已打开。");
            Log($"启动命令：{config.StartCommand}");
            if (!Directory.Exists(Path.Combine(projectDir, ".git")) && string.IsNullOrWhiteSpace(config.RepositoryUrl))
            {
                Log("提示：当前目录没有 .git，也没有 server-updater.json 里的 repositoryUrl。首次部署前需要配置远程仓库地址。");
            }
        };
    }

    private static void ConfigureButton(Button button, string text)
    {
        button.Text = text;
        button.Dock = DockStyle.Fill;
        button.Height = 42;
        button.Margin = new Padding(6, 0, 6, 0);
        button.FlatStyle = FlatStyle.System;
    }

    private async Task RunExclusiveAsync(string actionName, Func<Task> action)
    {
        if (busy)
        {
            return;
        }

        busy = true;
        SetButtons(false);
        try
        {
            Log("");
            Log($"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {actionName}开始。");
            await action();
            Log($"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {actionName}完成。");
        }
        catch (Exception ex)
        {
            Log($"错误：{ex.Message}");
            MessageBox.Show(this, ex.Message, "操作失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            busy = false;
            SetButtons(true);
            UpdateStatus();
        }
    }

    private void SetButtons(bool enabled)
    {
        startButton.Enabled = enabled;
        restartButton.Enabled = enabled;
        updateRestartButton.Enabled = enabled;
    }

    private async Task StartServiceAsync()
    {
        if (TryGetRunningService(out var runningProcess))
        {
            Log($"服务已经在运行，PID：{runningProcess.Id}");
            return;
        }

        await EnsureFirewallRuleAsync(config.Port);

        var command = config.StartCommand;
        if (string.IsNullOrWhiteSpace(command))
        {
            command = "python start.py";
        }

        var outLog = QuoteForCmd(serviceOutLog);
        var errLog = QuoteForCmd(serviceErrLog);
        var fullCommand = $"{command} >> {outLog} 2>> {errLog}";
        var psi = new ProcessStartInfo
        {
            FileName = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe",
            Arguments = "/c " + fullCommand,
            WorkingDirectory = projectDir,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        var process = Process.Start(psi) ?? throw new InvalidOperationException("无法启动服务进程。");
        await File.WriteAllTextAsync(pidFile, process.Id.ToString(), Encoding.UTF8);
        Log($"服务已启动，PID：{process.Id}");
        Log($"Local access: http://127.0.0.1:{config.Port}");
        Log($"External access: http://SERVER_PUBLIC_IP:{config.Port}");
        Log($"服务输出日志：{serviceOutLog}");
        Log($"服务错误日志：{serviceErrLog}");
        await Task.Delay(1000);

        if (!TryGetRunningService(out _))
        {
            var tail = ReadTail(serviceErrLog);
            throw new InvalidOperationException("服务启动后很快退出了。" + (tail.Length > 0 ? Environment.NewLine + tail : ""));
        }
    }

    private async Task RestartServiceAsync()
    {
        await StopServiceAsync();
        await StartServiceAsync();
    }

    private async Task UpdateAndRestartAsync()
    {
        await StopServiceAsync();
        await UpdateCodeAsync();
        await StartServiceAsync();
    }

    private void ShowCreateUserDialog()
    {
        var dbPath = Path.Combine(projectDir, "data.db");
        if (!File.Exists(dbPath))
        {
            MessageBox.Show(this, $"数据库文件不存在：{dbPath}\n请先启动一次服务以创建数据库。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var roles = LoadRolesFromDb(dbPath);
        if (roles.Count == 0)
        {
            MessageBox.Show(this, "数据库中没有角色数据，请先启动一次服务以初始化。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var dialog = new Form
        {
            Text = "创建账号",
            Size = new Size(440, 360),
            StartPosition = FormStartPosition.CenterParent,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false,
            MinimizeBox = false,
            Font = new Font("Microsoft YaHei UI", 10F)
        };

        var y = 20;
        var lblW = 90;
        var inputX = 100;
        var inputW = 290;

        var lblUser = new Label { Text = "用户名：", Location = new Point(20, y + 5), Size = new Size(lblW, 24) };
        var txtUser = new TextBox { Location = new Point(inputX, y), Size = new Size(inputW, 30) };
        y += 45;

        var lblNick = new Label { Text = "昵称：", Location = new Point(20, y + 5), Size = new Size(lblW, 24) };
        var txtNick = new TextBox { Location = new Point(inputX, y), Size = new Size(inputW, 30) };
        y += 45;

        var lblPwd = new Label { Text = "密码：", Location = new Point(20, y + 5), Size = new Size(lblW, 24) };
        var txtPwd = new TextBox { Location = new Point(inputX, y), Size = new Size(inputW, 30), UseSystemPasswordChar = true };
        y += 45;

        var lblRole = new Label { Text = "角色：", Location = new Point(20, y + 5), Size = new Size(lblW, 24) };
        var cmbRole = new ComboBox { Location = new Point(inputX, y), Size = new Size(inputW, 30), DropDownStyle = ComboBoxStyle.DropDownList };
        foreach (var r in roles) cmbRole.Items.Add(r);
        if (cmbRole.Items.Count > 0) cmbRole.SelectedIndex = 0;
        y += 45;

        var chkAgent = new CheckBox { Text = "代理账号（可发展下级）", Location = new Point(inputX, y), Size = new Size(inputW, 24) };
        y += 50;

        var btnOk = new Button { Text = "创建", DialogResult = DialogResult.OK, Size = new Size(100, 36), Location = new Point(120, y) };
        var btnCancel = new Button { Text = "取消", DialogResult = DialogResult.Cancel, Size = new Size(100, 36), Location = new Point(240, y) };

        dialog.Controls.AddRange(new Control[] { lblUser, txtUser, lblNick, txtNick, lblPwd, txtPwd, lblRole, cmbRole, chkAgent, btnOk, btnCancel });
        dialog.AcceptButton = btnOk;
        dialog.CancelButton = btnCancel;

        if (dialog.ShowDialog(this) != DialogResult.OK) return;

        var username = txtUser.Text.Trim();
        var nickname = txtNick.Text.Trim();
        var password = txtPwd.Text.Trim();
        var selectedRole = cmbRole.SelectedItem as RoleItem;

        if (string.IsNullOrEmpty(username))
        {
            MessageBox.Show(this, "用户名不能为空。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        if (string.IsNullOrEmpty(password))
        {
            password = "123456";
        }
        if (selectedRole == null)
        {
            MessageBox.Show(this, "请选择角色。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        try
        {
            var script = Path.Combine(projectDir, "create_user.py");
            if (!File.Exists(script))
            {
                MessageBox.Show(this, $"脚本不存在：{script}", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            var args = $"\"{script}\" {QuoteForArgument(username)} {QuoteForArgument(password)} {QuoteForArgument(selectedRole.Name)} {(chkAgent.Checked ? "1" : "0")} {QuoteForArgument(string.IsNullOrEmpty(nickname) ? username : nickname)}";
            var result = RunProcessSync("python", args, projectDir, 15);

            if (result.ExitCode != 0)
            {
                var errMsg = result.CombinedOutput.Trim();
                Log($"创建账号失败：{errMsg}");
                MessageBox.Show(this, $"创建失败：{errMsg}", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            Log($"账号创建成功：{username}（角色：{selectedRole.Name}，代理：{(chkAgent.Checked ? "是" : "否")}）");
            MessageBox.Show(this, $"账号创建成功！\n\n用户名：{username}\n密码：{password}\n角色：{selectedRole.Name}\n代理：{(chkAgent.Checked ? "是" : "否")}", "创建成功", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception ex)
        {
            Log($"创建账号失败：{ex.Message}");
            MessageBox.Show(this, $"创建账号失败：{ex.Message}", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static List<RoleItem> LoadRolesFromDb(string dbPath)
    {
        var list = new List<RoleItem>();
        if (!File.Exists(dbPath)) return list;

        var projectDirectory = Path.GetDirectoryName(dbPath)!;
        var script = Path.Combine(projectDirectory, "create_user.py");
        if (!File.Exists(script)) return list;

        var psi = new ProcessStartInfo
        {
            FileName = "python",
            Arguments = $"\"{script}\" --list-roles",
            WorkingDirectory = projectDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            CreateNoWindow = true
        };

        try
        {
            using var process = Process.Start(psi);
            if (process == null) return list;
            var output = process.StandardOutput.ReadToEnd();
            process.WaitForExit(10000);
            foreach (var line in output.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries))
            {
                var parts = line.Split('|');
                if (parts.Length == 2 && int.TryParse(parts[0], out var id))
                {
                    list.Add(new RoleItem(id, parts[1]));
                }
            }
        }
        catch { }

        return list;
    }

    private static ProcessResult RunProcessSync(string fileName, string arguments, string workingDirectory, int timeoutSeconds)
    {
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            Arguments = arguments,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = psi };
        process.Start();
        var output = process.StandardOutput.ReadToEnd();
        var error = process.StandardError.ReadToEnd();
        process.WaitForExit(timeoutSeconds * 1000);

        return new ProcessResult(process.ExitCode, output + "\n" + error);
    }

    private sealed record RoleItem(int Id, string Name)
    {
        public override string ToString() => Name;
    }

    private async Task StopServiceAsync()
    {
        if (!TryReadPid(out var pid))
        {
            Log("没有找到已记录的服务 PID，跳过停止。");
            return;
        }

        if (!IsProcessRunning(pid))
        {
            Log($"PID {pid} 已不存在，清理本地记录。");
            TryDelete(pidFile);
            return;
        }

        Log($"正在停止服务 PID：{pid}");
        var result = await RunProcessAsync("taskkill", $"/PID {pid} /T /F", projectDir);
        if (result.ExitCode != 0)
        {
            throw new InvalidOperationException("停止服务失败：" + result.CombinedOutput);
        }

        TryDelete(pidFile);
        Log("服务已停止。");
    }

    private async Task UpdateCodeAsync()
    {
        var gitVersion = await RunProcessAsync("git", "--version", projectDir, allowFailure: true);
        if (gitVersion.ExitCode != 0)
        {
            throw new InvalidOperationException("服务器上没有找到 Git，请先安装 Git 并确保 git 命令可用。");
        }

        var gitDir = Path.Combine(projectDir, ".git");
        var isGitRepo = Directory.Exists(gitDir);
        if (!isGitRepo && string.IsNullOrWhiteSpace(config.RepositoryUrl))
        {
            throw new InvalidOperationException("当前目录还不是 Git 仓库。请在 server-updater.json 里填写 repositoryUrl 后再拉取。");
        }

        if (!isGitRepo)
        {
            Log("当前目录还没有 Git 仓库，开始初始化。");
            await GitAsync("init");
        }

        var realRepoUrl = config.RepositoryUrl?.Trim() ?? "";
        if (!string.IsNullOrEmpty(realRepoUrl))
        {
            Log($"远程仓库地址：{MaskToken(realRepoUrl)}");
            var remote = await RunProcessAsync("git", "remote get-url origin", projectDir, allowFailure: true);
            if (remote.ExitCode == 0)
            {
                await GitAsync("remote set-url origin " + QuoteForArgument(realRepoUrl));
            }
            else
            {
                await GitAsync("remote add origin " + QuoteForArgument(realRepoUrl));
            }
        }

        var mirror = config.MirrorUrl?.Trim();
        var usingMirror = !string.IsNullOrEmpty(mirror);
        string? authToken = null;
        if (usingMirror)
        {
            Log($"使用 GitHub 镜像：{mirror}");
            var currentUrl = (await RunProcessAsync("git", "remote get-url origin", projectDir, allowFailure: true)).Output.Trim();
            authToken = ExtractToken(currentUrl);
            var mirroredUrl = ApplyMirror(currentUrl, mirror);
            if (mirroredUrl != currentUrl)
            {
                Log($"镜像地址：{MaskToken(mirroredUrl)}");
                await GitAsync("remote set-url origin " + QuoteForArgument(mirroredUrl));
                if (!string.IsNullOrEmpty(authToken))
                {
                    await GitAsyncInRepo($"config http.extraHeader \"Authorization: Basic {ConvertToBase64(authToken)}\"");
                    Log("已配置认证头（通过镜像转发到 GitHub）。");
                }
            }
        }

        Log("正在检测网络连通性...");
        var canConnect = await CheckGitHubConnectivityAsync();
        if (!canConnect)
        {
            if (usingMirror)
            {
                await RestoreRealUrlAsync(realRepoUrl);
                if (!string.IsNullOrEmpty(authToken)) await GitAsyncInRepo("config --unset http.extraHeader");
            }
            throw new InvalidOperationException(usingMirror
                ? $"无法连接到 GitHub（已使用镜像 {mirror}），请检查：\n1. 镜像地址是否正确可用\n2. 尝试换一个镜像地址\n3. 或改用 Gitee 做中转"
                : "无法连接到 GitHub，请选择以下方案之一：\n\n方案1：在 server-updater.json 中添加镜像地址：\n  \"mirrorUrl\": \"https://gh-proxy.com/\"\n\n方案2：配置 HTTP 代理：\n  git config --global http.proxy http://代理地址:端口\n\n方案3：使用 Gitee 做中转（最稳定）");
        }
        Log("网络连通性正常。");

        Log("正在拉取远程代码...");
        var fetchTimeout = config.FetchTimeoutSeconds > 0 ? config.FetchTimeoutSeconds : 120;
        var fetchResult = await RunProcessAsyncWithTimeout("git", "fetch --prune origin", projectDir, fetchTimeout);
        if (fetchResult.ExitCode != 0)
        {
            if (usingMirror)
            {
                await RestoreRealUrlAsync(realRepoUrl);
                if (!string.IsNullOrEmpty(authToken)) await GitAsyncInRepo("config --unset http.extraHeader");
            }
            throw new InvalidOperationException(fetchResult.CombinedOutput);
        }

        if (usingMirror)
        {
            await RestoreRealUrlAsync(realRepoUrl);
            if (!string.IsNullOrEmpty(authToken))
            {
                try { await GitAsyncInRepo("config --unset http.extraHeader"); } catch { }
            }
        }

        var branch = await ResolveBranchAsync();
        Log($"使用远程分支：origin/{branch}");

        if (!isGitRepo)
        {
            await BackupConflictingFilesAsync(branch);
        }

        await GitAsync("clean -fd");
        await GitAsync("fetch origin " + QuoteForArgument(branch), allowFailure: true);
        await GitAsync("checkout -B " + QuoteForArgument(branch) + " " + QuoteForArgument("origin/" + branch));
        await GitAsync("branch --set-upstream-to=" + QuoteForArgument("origin/" + branch) + " " + QuoteForArgument(branch));
        Log("代码已更新到远程最新版本。");
    }

    private async Task<bool> CheckGitHubConnectivityAsync()
    {
        try
        {
            var remoteUrl = await RunProcessAsync("git", "remote get-url origin", projectDir, allowFailure: true);
            var testUrl = remoteUrl.ExitCode == 0 ? remoteUrl.Output.Trim() : "https://github.com";
            var result = await RunProcessAsyncWithTimeout("git", $"ls-remote --heads {QuoteForArgument(testUrl)}", projectDir, 20);
            return result.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }

    private static string ApplyMirror(string url, string? mirror)
    {
        if (string.IsNullOrEmpty(url) || string.IsNullOrEmpty(mirror)) return url;
        var ghIndex = url.IndexOf("github.com", StringComparison.OrdinalIgnoreCase);
        if (ghIndex < 0) return url;
        var pathPart = url[ghIndex..];
        return mirror.TrimEnd('/') + "/" + pathPart;
    }

    private static string? ExtractToken(string url)
    {
        if (string.IsNullOrEmpty(url)) return null;
        var scheme = "https://";
        if (!url.StartsWith(scheme, StringComparison.OrdinalIgnoreCase)) return null;
        var afterScheme = url[scheme.Length..];
        var atIndex = afterScheme.IndexOf('@');
        if (atIndex <= 0) return null;
        return afterScheme[..atIndex];
    }

    private static string ConvertToBase64(string token)
    {
        return Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(token));
    }

    private async Task GitAsyncInRepo(string arguments)
    {
        var result = await RunProcessAsync("git", arguments, projectDir);
        if (result.ExitCode != 0)
        {
            throw new InvalidOperationException(result.CombinedOutput);
        }
    }

    private async Task RestoreRealUrlAsync(string realUrl)
    {
        if (!string.IsNullOrEmpty(realUrl))
        {
            try
            {
                await GitAsync("remote set-url origin " + QuoteForArgument(realUrl));
                Log("已恢复原始仓库地址。");
            }
            catch (Exception ex)
            {
                Log($"恢复原始地址失败：{ex.Message}");
            }
        }
    }

    private static string MaskToken(string url)
    {
        if (string.IsNullOrEmpty(url)) return url;
        var tokenPattern = "https://";
        var atIndex = url.IndexOf("@github.com", StringComparison.OrdinalIgnoreCase);
        if (atIndex > 0 && url.StartsWith(tokenPattern, StringComparison.OrdinalIgnoreCase))
        {
            var prefixLen = tokenPattern.Length;
            var tokenPart = url[prefixLen..atIndex];
            if (tokenPart.Length > 4)
            {
                return url[..(prefixLen + 4)] + "****" + url[atIndex..];
            }
        }
        return url;
    }

    private async Task GitAsyncWithTimeout(string arguments, int timeoutSeconds)
    {
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
        try
        {
            var result = await RunProcessAsyncWithTimeout("git", arguments, projectDir, timeoutSeconds, cts.Token);
            if (result.ExitCode != 0)
            {
                throw new InvalidOperationException(result.CombinedOutput);
            }
        }
        catch (OperationCanceledException)
        {
            throw new InvalidOperationException($"Git 操作超时（{timeoutSeconds}秒），服务器可能无法访问 GitHub。请检查网络或代理配置。");
        }
    }


    private async Task<ProcessResult> RunProcessAsyncWithTimeout(string fileName, string arguments, string workingDirectory, int timeoutSeconds, CancellationToken cancellationToken = default)
    {
        var output = new StringBuilder();
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            Arguments = arguments,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.GetEncoding("gbk"),
            StandardErrorEncoding = Encoding.GetEncoding("gbk"),
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is { Length: > 0 })
            {
                output.AppendLine(e.Data);
                BeginInvoke(() => Log(e.Data));
            }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is { Length: > 0 })
            {
                output.AppendLine(e.Data);
                BeginInvoke(() => Log(e.Data));
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        linkedCts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));

        try
        {
            await process.WaitForExitAsync(linkedCts.Token);
        }
        catch (OperationCanceledException)
        {
            try
            {
                process.Kill(entireProcessTree: true);
            }
            catch { }

            throw;
        }

        return new ProcessResult(process.ExitCode, output.ToString());
    }

    private async Task<string> ResolveBranchAsync()
    {
        if (!string.IsNullOrWhiteSpace(config.Branch))
        {
            return config.Branch.Trim();
        }

        var current = await RunProcessAsync("git", "rev-parse --abbrev-ref HEAD", projectDir, allowFailure: true);
        var currentBranch = current.Output.Trim();
        if (current.ExitCode == 0 && currentBranch.Length > 0 && currentBranch != "HEAD")
        {
            return currentBranch;
        }

        var remote = await RunProcessAsync("git", "remote show origin", projectDir, allowFailure: true);
        foreach (var line in remote.CombinedOutput.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None))
        {
            var marker = "HEAD branch:";
            var index = line.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (index >= 0)
            {
                var branch = line[(index + marker.Length)..].Trim();
                if (branch.Length > 0 && branch != "(unknown)")
                {
                    return branch;
                }
            }
        }

        var mainCheck = await RunProcessAsync("git", "rev-parse --verify origin/main", projectDir, allowFailure: true);
        if (mainCheck.ExitCode == 0)
        {
            return "main";
        }

        return "master";
    }

    private async Task BackupConflictingFilesAsync(string branch)
    {
        var tree = await RunProcessAsync("git", "ls-tree -r --name-only origin/" + QuoteForArgument(branch), projectDir);
        var files = tree.Output.Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);
        if (files.Length == 0)
        {
            return;
        }

        var backupRoot = Path.Combine(stateDir, "backup-" + DateTime.Now.ToString("yyyyMMdd-HHmmss"));
        var moved = 0;

        foreach (var relativeFile in files)
        {
            if (relativeFile.StartsWith(".git/", StringComparison.OrdinalIgnoreCase) ||
                relativeFile.StartsWith(".server-updater/", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var source = Path.GetFullPath(Path.Combine(projectDir, relativeFile.Replace('/', Path.DirectorySeparatorChar)));
            if (!source.StartsWith(projectDir, StringComparison.OrdinalIgnoreCase) || !File.Exists(source))
            {
                continue;
            }

            var destination = Path.Combine(backupRoot, relativeFile.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            File.Move(source, destination, overwrite: false);
            moved++;
        }

        if (moved > 0)
        {
            Log($"首次初始化前已备份 {moved} 个同名文件到：{backupRoot}");
        }
    }

    private async Task GitAsync(string arguments, bool allowFailure = false)
    {
        var result = await RunProcessAsync("git", arguments, projectDir);
        if (!allowFailure && result.ExitCode != 0)
        {
            throw new InvalidOperationException(result.CombinedOutput);
        }
    }

    private async Task EnsureFirewallRuleAsync(int port)
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var ruleName = $"{FirewallRulePrefix} {port}";
        var show = await RunProcessAsync("netsh", $"advfirewall firewall show rule name=\"{ruleName}\"", projectDir, allowFailure: true);
        if (show.ExitCode == 0 && show.CombinedOutput.Contains(ruleName, StringComparison.OrdinalIgnoreCase))
        {
            Log($"Firewall rule exists: TCP {port}");
            return;
        }

        Log($"Trying to allow Windows Firewall inbound TCP {port}.");
        var add = await RunProcessAsync(
            "netsh",
            $"advfirewall firewall add rule name=\"{ruleName}\" dir=in action=allow protocol=TCP localport={port}",
            projectDir,
            allowFailure: true);

        if (add.ExitCode == 0)
        {
            Log($"Windows Firewall allowed TCP {port}.");
        }
        else
        {
            Log($"Could not add Windows Firewall rule automatically. Run this manager as Administrator or add inbound TCP {port} manually.");
        }
    }

    private async Task<ProcessResult> RunProcessAsync(string fileName, string arguments, string workingDirectory, bool allowFailure = false)
    {
        var output = new StringBuilder();
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            Arguments = arguments,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.GetEncoding("gbk"),
            StandardErrorEncoding = Encoding.GetEncoding("gbk"),
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is { Length: > 0 })
            {
                output.AppendLine(e.Data);
                BeginInvoke(() => Log(e.Data));
            }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is { Length: > 0 })
            {
                output.AppendLine(e.Data);
                BeginInvoke(() => Log(e.Data));
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        await process.WaitForExitAsync();

        var result = new ProcessResult(process.ExitCode, output.ToString());
        if (!allowFailure && result.ExitCode != 0)
        {
            throw new InvalidOperationException(result.CombinedOutput);
        }

        return result;
    }

    private bool TryGetRunningService(out Process process)
    {
        process = null!;
        if (!TryReadPid(out var pid))
        {
            return false;
        }

        try
        {
            process = Process.GetProcessById(pid);
            if (!process.HasExited)
            {
                return true;
            }
        }
        catch
        {
            return false;
        }

        return false;
    }

    private bool TryReadPid(out int pid)
    {
        pid = 0;
        if (!File.Exists(pidFile))
        {
            return false;
        }

        return int.TryParse(File.ReadAllText(pidFile).Trim(), out pid);
    }

    private static bool IsProcessRunning(int pid)
    {
        try
        {
            return !Process.GetProcessById(pid).HasExited;
        }
        catch
        {
            return false;
        }
    }

    private void UpdateStatus()
    {
        statusLabel.Text = TryGetRunningService(out var process)
            ? $"状态：服务运行中，PID {process.Id}"
            : "状态：服务未运行";
    }

    private void Log(string message)
    {
        if (logBox.IsDisposed)
        {
            return;
        }

        logBox.AppendText(message + Environment.NewLine);
    }

    private static string ReadTail(string path)
    {
        if (!File.Exists(path))
        {
            return string.Empty;
        }

        var lines = File.ReadLines(path).TakeLast(20);
        return string.Join(Environment.NewLine, lines);
    }

    private static string QuoteForArgument(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static string QuoteForCmd(string value)
    {
        return "\"" + value.Replace("\"", "\"\"") + "\"";
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // Best effort cleanup.
        }
    }
}

internal sealed record ProcessResult(int ExitCode, string CombinedOutput)
{
    public string Output => CombinedOutput;
}

internal sealed class UpdaterConfig
{
    public string RepositoryUrl { get; set; } = "";
    public string Branch { get; set; } = "";
    public string StartCommand { get; set; } = "python start.py";
    public int Port { get; set; } = 5000;
    public int FetchTimeoutSeconds { get; set; } = 120;
    public string MirrorUrl { get; set; } = "";

    public static UpdaterConfig Load(string projectDir)
    {
        var path = Path.Combine(projectDir, "server-updater.json");
        if (!File.Exists(path))
        {
            return new UpdaterConfig();
        }

        try
        {
            var config = JsonSerializer.Deserialize<UpdaterConfig>(File.ReadAllText(path), new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
            return config ?? new UpdaterConfig();
        }
        catch
        {
            return new UpdaterConfig();
        }
    }
}
