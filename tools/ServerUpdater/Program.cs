using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;

namespace ServerUpdater;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class MainForm : Form
{
    private readonly Button startButton = new();
    private readonly Button restartButton = new();
    private readonly Button updateRestartButton = new();
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
            ColumnCount = 3,
            Padding = new Padding(16, 12, 16, 12)
        };
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.333F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.333F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.333F));

        ConfigureButton(startButton, "启动服务");
        ConfigureButton(restartButton, "重启服务");
        ConfigureButton(updateRestartButton, "拉取最新并重启服务");
        buttonPanel.Controls.Add(startButton, 0, 0);
        buttonPanel.Controls.Add(restartButton, 1, 0);
        buttonPanel.Controls.Add(updateRestartButton, 2, 0);

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

        if (!string.IsNullOrWhiteSpace(config.RepositoryUrl))
        {
            var remote = await RunProcessAsync("git", "remote get-url origin", projectDir, allowFailure: true);
            if (remote.ExitCode == 0)
            {
                await GitAsync("remote set-url origin " + QuoteForArgument(config.RepositoryUrl));
            }
            else
            {
                await GitAsync("remote add origin " + QuoteForArgument(config.RepositoryUrl));
            }
        }

        Log("正在拉取远程代码。");
        await GitAsync("fetch --prune origin");

        var branch = await ResolveBranchAsync();
        Log($"使用远程分支：origin/{branch}");

        if (!isGitRepo)
        {
            await BackupConflictingFilesAsync(branch);
        }

        await GitAsync("checkout -B " + QuoteForArgument(branch) + " " + QuoteForArgument("origin/" + branch));
        await GitAsync("reset --hard " + QuoteForArgument("origin/" + branch));
        Log("代码已更新到远程最新版本。");
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

    private async Task GitAsync(string arguments)
    {
        var result = await RunProcessAsync("git", arguments, projectDir);
        if (result.ExitCode != 0)
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
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
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
