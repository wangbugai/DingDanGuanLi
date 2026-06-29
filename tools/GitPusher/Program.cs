using System.Diagnostics;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace GitPusher;

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
    private readonly Button pushButton = new();
    private readonly Button addCommitButton = new();
    private readonly Button pullButton = new();
    private readonly Button testProxyButton = new();
    private readonly TextBox logBox = new();
    private readonly Label statusLabel = new();
    private readonly TextBox proxyTextBox = new();
    private readonly CheckBox useProxyCheckBox = new();
    private readonly NumericUpDown retryUpDown = new();
    private readonly NumericUpDown timeoutUpDown = new();
    private readonly CheckBox pullBeforePushCheckBox = new();
    private readonly string projectDir;
    private readonly string configFile;
    private bool busy;
    private CancellationTokenSource? currentCts;

    public MainForm()
    {
        projectDir = Path.GetDirectoryName(Environment.ProcessPath) ?? AppContext.BaseDirectory;
        configFile = Path.Combine(projectDir, ".gitpusher.json");

        Text = "Git 提交推送工具";
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Microsoft YaHei UI", 10F);
        MinimumSize = new Size(820, 640);
        Size = new Size(860, 700);

        var title = new Label
        {
            Text = "Git 提交推送工具",
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

        var proxyPanel = new Panel
        {
            Dock = DockStyle.Top,
            Height = 40,
            Padding = new Padding(16, 6, 16, 6)
        };

        useProxyCheckBox.Text = "使用代理";
        useProxyCheckBox.Location = new Point(0, 8);
        useProxyCheckBox.Size = new Size(90, 24);
        useProxyCheckBox.Checked = true;

        var proxyLabel = new Label { Text = "地址(多个用|分隔)：", Location = new Point(95, 8), Size = new Size(160, 24) };
        proxyTextBox.Location = new Point(255, 5);
        proxyTextBox.Size = new Size(280, 28);
        proxyTextBox.Text = "127.0.0.1:7890";

        testProxyButton.Text = "测试连通";
        testProxyButton.Location = new Point(545, 4);
        testProxyButton.Size = new Size(90, 30);
        testProxyButton.FlatStyle = FlatStyle.System;

        proxyPanel.Controls.Add(useProxyCheckBox);
        proxyPanel.Controls.Add(proxyLabel);
        proxyPanel.Controls.Add(proxyTextBox);
        proxyPanel.Controls.Add(testProxyButton);

        var settingsPanel = new Panel
        {
            Dock = DockStyle.Top,
            Height = 40,
            Padding = new Padding(16, 6, 16, 6)
        };

        var retryLabel = new Label { Text = "重试次数：", Location = new Point(0, 8), Size = new Size(80, 24) };
        retryUpDown.Location = new Point(80, 5);
        retryUpDown.Size = new Size(60, 28);
        retryUpDown.Minimum = 1;
        retryUpDown.Maximum = 10;
        retryUpDown.Value = 3;

        var timeoutLabel = new Label { Text = "超时(秒)：", Location = new Point(155, 8), Size = new Size(80, 24) };
        timeoutUpDown.Location = new Point(235, 5);
        timeoutUpDown.Size = new Size(65, 28);
        timeoutUpDown.Minimum = 30;
        timeoutUpDown.Maximum = 600;
        timeoutUpDown.Value = 120;
        timeoutUpDown.Increment = 30;

        pullBeforePushCheckBox.Text = "推送前先拉取(pull)";
        pullBeforePushCheckBox.Location = new Point(320, 8);
        pullBeforePushCheckBox.Size = new Size(180, 24);
        pullBeforePushCheckBox.Checked = true;

        settingsPanel.Controls.Add(retryLabel);
        settingsPanel.Controls.Add(retryUpDown);
        settingsPanel.Controls.Add(timeoutLabel);
        settingsPanel.Controls.Add(timeoutUpDown);
        settingsPanel.Controls.Add(pullBeforePushCheckBox);

        var buttonPanel = new TableLayoutPanel
        {
            Dock = DockStyle.Top,
            Height = 60,
            ColumnCount = 3,
            Padding = new Padding(16, 10, 16, 10)
        };
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33F));
        buttonPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 34F));

        addCommitButton.Text = "添加并提交";
        addCommitButton.Dock = DockStyle.Fill;
        addCommitButton.Height = 38;
        addCommitButton.FlatStyle = FlatStyle.System;

        pullButton.Text = "拉取(pull)";
        pullButton.Dock = DockStyle.Fill;
        pullButton.Height = 38;
        pullButton.FlatStyle = FlatStyle.System;

        pushButton.Text = "推送(push)";
        pushButton.Dock = DockStyle.Fill;
        pushButton.Height = 38;
        pushButton.FlatStyle = FlatStyle.System;

        buttonPanel.Controls.Add(addCommitButton, 0, 0);
        buttonPanel.Controls.Add(pullButton, 1, 0);
        buttonPanel.Controls.Add(pushButton, 2, 0);

        statusLabel.Dock = DockStyle.Top;
        statusLabel.Height = 28;
        statusLabel.TextAlign = ContentAlignment.MiddleLeft;
        statusLabel.Padding = new Padding(16, 0, 16, 0);

        logBox.Dock = DockStyle.Fill;
        logBox.Multiline = true;
        logBox.ReadOnly = true;
        logBox.ScrollBars = ScrollBars.Vertical;
        logBox.Font = new Font("Consolas", 9.5F);
        logBox.BackColor = Color.White;
        logBox.Margin = new Padding(16);

        Controls.Add(logBox);
        Controls.Add(statusLabel);
        Controls.Add(buttonPanel);
        Controls.Add(settingsPanel);
        Controls.Add(proxyPanel);
        Controls.Add(pathLabel);
        Controls.Add(title);

        addCommitButton.Click += async (_, _) => await RunExclusiveAsync("添加并提交", AddAndCommitAsync);
        pushButton.Click += async (_, _) => await RunExclusiveAsync("推送", PushWithRetryAsync);
        pullButton.Click += async (_, _) => await RunExclusiveAsync("拉取", PullAsync);
        testProxyButton.Click += async (_, _) => await TestProxyAsync();
        useProxyCheckBox.CheckedChanged += (_, _) => proxyTextBox.Enabled = useProxyCheckBox.Checked;

        Shown += (_, _) =>
        {
            LoadConfig();
            Log("程序已打开。");
            if (!Directory.Exists(Path.Combine(projectDir, ".git")))
            {
                Log("警告：当前目录不是 Git 仓库。");
            }
        };

        FormClosing += (_, _) =>
        {
            currentCts?.Cancel();
            SaveConfig();
        };
    }

    private void LoadConfig()
    {
        try
        {
            if (!File.Exists(configFile)) return;
            var json = File.ReadAllText(configFile);
            var cfg = JsonSerializer.Deserialize<GitPusherConfig>(json);
            if (cfg != null)
            {
                proxyTextBox.Text = cfg.ProxyAddresses ?? "127.0.0.1:7890";
                useProxyCheckBox.Checked = cfg.UseProxy;
                retryUpDown.Value = Math.Clamp(cfg.RetryCount, 1, 10);
                timeoutUpDown.Value = Math.Clamp(cfg.TimeoutSeconds, 30, 600);
                pullBeforePushCheckBox.Checked = cfg.PullBeforePush;
            }
        }
        catch { }
    }

    private void SaveConfig()
    {
        try
        {
            var cfg = new GitPusherConfig
            {
                ProxyAddresses = proxyTextBox.Text.Trim(),
                UseProxy = useProxyCheckBox.Checked,
                RetryCount = (int)retryUpDown.Value,
                TimeoutSeconds = (int)timeoutUpDown.Value,
                PullBeforePush = pullBeforePushCheckBox.Checked
            };
            var json = JsonSerializer.Serialize(cfg, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(configFile, json);
        }
        catch { }
    }

    private List<string> GetProxyList()
    {
        if (!useProxyCheckBox.Checked) return [];
        var raw = proxyTextBox.Text.Trim();
        if (string.IsNullOrEmpty(raw)) return [];
        return raw.Split('|', StringSplitOptions.RemoveEmptyEntries)
                   .Select(p => p.Trim())
                   .Where(p => p.Length > 0)
                   .Select(NormalizeProxyUrl)
                   .ToList();
    }

    private static string NormalizeProxyUrl(string addr)
    {
        if (!addr.StartsWith("http://") && !addr.StartsWith("https://") && !addr.StartsWith("socks5://"))
        {
            addr = "http://" + addr;
        }
        return addr;
    }

    private async Task TestProxyAsync()
    {
        var proxies = GetProxyList();
        if (proxies.Count == 0)
        {
            Log("代理未启用或未填写地址。");
            return;
        }

        testProxyButton.Enabled = false;
        foreach (var proxyUrl in proxies)
        {
            Log($"正在测试代理 {proxyUrl} ...");
            try
            {
                var handler = new HttpClientHandler
                {
                    Proxy = new System.Net.WebProxy(proxyUrl),
                    UseProxy = true,
                };
                using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(10) };
                var response = await client.GetAsync("https://github.com");
                if (response.IsSuccessStatusCode)
                {
                    Log($"  ✓ 代理 {proxyUrl} 连通成功！状态码：{(int)response.StatusCode}");
                }
                else
                {
                    Log($"  ✗ 代理 {proxyUrl} 已连接，但 GitHub 返回状态码：{(int)response.StatusCode}");
                }
            }
            catch (Exception ex)
            {
                Log($"  ✗ 代理 {proxyUrl} 测试失败：{ex.Message}");
            }
        }
        testProxyButton.Enabled = true;
    }

    private async Task RunExclusiveAsync(string actionName, Func<Task> action)
    {
        if (busy) return;
        busy = true;
        currentCts = new CancellationTokenSource();
        addCommitButton.Enabled = false;
        pushButton.Enabled = false;
        pullButton.Enabled = false;
        testProxyButton.Enabled = false;
        try
        {
            Log("");
            Log($"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {actionName}开始...");
            await action();
            Log($"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {actionName}完成。");
        }
        catch (OperationCanceledException)
        {
            Log("操作已取消。");
        }
        catch (Exception ex)
        {
            Log($"错误：{ex.Message}");
            MessageBox.Show(this, ex.Message, "操作失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            busy = false;
            currentCts?.Dispose();
            currentCts = null;
            addCommitButton.Enabled = true;
            pushButton.Enabled = true;
            pullButton.Enabled = true;
            testProxyButton.Enabled = true;
        }
    }

    private void SetStatus(string text)
    {
        if (statusLabel.IsDisposed) return;
        statusLabel.Text = text;
        statusLabel.Refresh();
    }

    private async Task AddAndCommitAsync()
    {
        await RunGitAsync("add -A");

        var statusResult = await RunGitAsync("status --porcelain", allowFailure: true);
        if (string.IsNullOrWhiteSpace(statusResult))
        {
            Log("没有需要提交的更改。");
            return;
        }

        var commitMessage = ShowCommitDialog();
        if (commitMessage == null)
        {
            Log("已取消提交。");
            return;
        }

        await RunGitAsync($"commit -m {QuoteForArgument(commitMessage)}");
        Log("提交成功！");
    }

    private async Task PullAsync()
    {
        var proxyUrl = GetProxyList().FirstOrDefault() ?? "";
        await ConfigureProxyAsync(proxyUrl);
        try
        {
            await RunGitAsync("pull --rebase origin main");
            Log("拉取成功！");
        }
        finally
        {
            await ClearProxyAsync();
        }
    }

    private async Task PushWithRetryAsync()
    {
        var maxRetries = (int)retryUpDown.Value;
        var timeoutSec = (int)timeoutUpDown.Value;
        var proxies = GetProxyList();

        if (pullBeforePushCheckBox.Checked)
        {
            SetStatus("正在拉取远程更新...");
            try
            {
                var firstProxy = proxies.FirstOrDefault() ?? "";
                await ConfigureProxyAsync(firstProxy);
                await RunGitAsync("pull --rebase origin main", timeoutSeconds: timeoutSec);
                Log("拉取成功，开始推送...");
            }
            catch (Exception ex)
            {
                Log($"拉取失败（继续推送）：{TranslateOutput(ex.Message)}");
            }
            finally
            {
                await ClearProxyAsync();
            }
        }

        for (int attempt = 1; attempt <= maxRetries; attempt++)
        {
            string currentProxy = "";

            if (proxies.Count > 0)
            {
                currentProxy = proxies[(attempt - 1) % proxies.Count];
                SetStatus($"推送中... 第{attempt}/{maxRetries}次 代理：{currentProxy}");
            }
            else
            {
                SetStatus($"推送中... 第{attempt}/{maxRetries}次（无代理）");
            }

            try
            {
                await ConfigureProxyAsync(currentProxy);
                await RunGitAsync("push -u origin main", timeoutSeconds: timeoutSec);
                Log("推送成功！");
                SetStatus("推送成功！");
                return;
            }
            catch (Exception ex)
            {
                await ClearProxyAsync();
                var errorMsg = ex.Message;

                if (IsNetworkError(errorMsg))
                {
                    Log($"第{attempt}次推送失败（网络错误）：{TranslateOutput(errorMsg)}");

                    if (attempt < maxRetries)
                    {
                        var delay = attempt * 2;
                        if (proxies.Count > 1)
                        {
                            var nextProxy = proxies[attempt % proxies.Count];
                            Log($"  → {delay}秒后重试，切换代理到 {nextProxy} ...");
                        }
                        else
                        {
                            Log($"  → {delay}秒后重试...");
                        }
                        SetStatus($"推送失败，{delay}秒后重试 ({attempt}/{maxRetries})...");
                        await Task.Delay(delay * 1000);
                    }
                }
                else if (IsAuthError(errorMsg))
                {
                    Log($"推送失败（认证错误）：{TranslateOutput(errorMsg)}");
                    Log("请检查 Git Token 是否正确。");
                    SetStatus("推送失败：认证错误");
                    return;
                }
                else if (IsConflictError(errorMsg))
                {
                    Log($"推送失败（冲突）：{TranslateOutput(errorMsg)}");
                    Log("远程有新提交，请先拉取(pull)后再推送。");
                    SetStatus("推送失败：需要先拉取");
                    return;
                }
                else
                {
                    Log($"推送失败：{TranslateOutput(errorMsg)}");
                    SetStatus("推送失败");
                    return;
                }
            }
            finally
            {
                await ClearProxyAsync();
            }
        }

        Log($"已重试{maxRetries}次，推送仍然失败。");
        SetStatus("推送失败：已达最大重试次数");
        MessageBox.Show(this, $"已重试{maxRetries}次，推送仍然失败。\n请检查网络/代理设置。", "推送失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
    }

    private async Task ConfigureProxyAsync(string proxyUrl)
    {
        if (!string.IsNullOrEmpty(proxyUrl))
        {
            Log($"设置代理：{proxyUrl}");
            await RunGitAsync($"config http.proxy {QuoteForArgument(proxyUrl)}", allowFailure: true);
            await RunGitAsync($"config https.proxy {QuoteForArgument(proxyUrl)}", allowFailure: true);
        }
        else
        {
            await ClearProxyAsync();
        }
    }

    private async Task ClearProxyAsync()
    {
        await RunGitAsync("config --unset http.proxy", allowFailure: true);
        await RunGitAsync("config --unset https.proxy", allowFailure: true);
    }

    private static bool IsNetworkError(string errorMsg)
    {
        if (string.IsNullOrEmpty(errorMsg)) return false;
        var lower = errorMsg.ToLowerInvariant();
        return lower.Contains("443") ||
               lower.Contains("connection was reset") ||
               lower.Contains("timed out") ||
               lower.Contains("timeout") ||
               lower.Contains("could not resolve") ||
               lower.Contains("unable to access") ||
               lower.Contains("hung up") ||
               lower.Contains("connection refused") ||
               lower.Contains("ssl") && lower.Contains("error") ||
               lower.Contains("recv failure") ||
               lower.Contains("network") && lower.Contains("unreachable") ||
               lower.Contains("no route to host") ||
               lower.Contains("connection aborted");
    }

    private static bool IsAuthError(string errorMsg)
    {
        if (string.IsNullOrEmpty(errorMsg)) return false;
        var lower = errorMsg.ToLowerInvariant();
        return lower.Contains("authentication failed") ||
               lower.Contains("permission denied") ||
               lower.Contains("403") ||
               lower.Contains("access denied") ||
               lower.Contains("logon failed") ||
               lower.Contains("invalid token");
    }

    private static bool IsConflictError(string errorMsg)
    {
        if (string.IsNullOrEmpty(errorMsg)) return false;
        var lower = errorMsg.ToLowerInvariant();
        return lower.Contains("failed to push some refs") ||
               lower.Contains("non-fast-forward") ||
               lower.Contains("updates were rejected") ||
               lower.Contains("cannot lock ref");
    }

    private string? ShowCommitDialog()
    {
        var input = new Form
        {
            Text = "输入提交信息",
            Size = new Size(420, 180),
            StartPosition = FormStartPosition.CenterParent,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false,
            MinimizeBox = false,
            Font = new Font("Microsoft YaHei UI", 10F)
        };

        var label = new Label
        {
            Text = "提交信息：",
            Dock = DockStyle.Top,
            Height = 30,
            Padding = new Padding(12, 8, 12, 0)
        };

        var textBox = new TextBox
        {
            Dock = DockStyle.Top,
            Height = 36,
            Padding = new Padding(12, 0, 12, 0),
            Text = "update: 更新代码"
        };

        var btnPanel = new Panel { Dock = DockStyle.Bottom, Height = 50 };
        var okBtn = new Button { Text = "确定", DialogResult = DialogResult.OK, Size = new Size(90, 34), Location = new Point(120, 8) };
        var cancelBtn = new Button { Text = "取消", DialogResult = DialogResult.Cancel, Size = new Size(90, 34), Location = new Point(230, 8) };
        btnPanel.Controls.Add(okBtn);
        btnPanel.Controls.Add(cancelBtn);

        input.Controls.Add(textBox);
        input.Controls.Add(label);
        input.Controls.Add(btnPanel);
        input.AcceptButton = okBtn;
        input.CancelButton = cancelBtn;

        textBox.SelectAll();
        return input.ShowDialog(this) == DialogResult.OK ? textBox.Text.Trim() : null;
    }

    private async Task<string> RunGitAsync(string arguments, bool allowFailure = false, int timeoutSeconds = 0)
    {
        Log($"> git {arguments}");
        var result = await RunProcessAsync("git", arguments, projectDir, timeoutSeconds > 0 ? timeoutSeconds : (int)timeoutUpDown.Value);
        if (!allowFailure && result.ExitCode != 0)
        {
            throw new InvalidOperationException(TranslateOutput(result.CombinedOutput));
        }
        return result.Output.Trim();
    }

    private async Task<ProcessResult> RunProcessAsync(string fileName, string arguments, string workingDirectory, int timeoutSeconds)
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
                var translated = TranslateLine(e.Data);
                output.AppendLine(e.Data);
                BeginInvoke(() => Log("  " + translated));
            }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is { Length: > 0 })
            {
                var translated = TranslateLine(e.Data);
                output.AppendLine(e.Data);
                BeginInvoke(() => Log("  " + translated));
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            try
            {
                process.Kill(entireProcessTree: true);
            }
            catch { }
            throw new InvalidOperationException($"命令超时（{timeoutSeconds}秒）：git {arguments}");
        }

        return new ProcessResult(process.ExitCode, output.ToString());
    }

    private static string TranslateOutput(string output)
    {
        if (string.IsNullOrEmpty(output)) return output;
        var lines = output.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
        return string.Join(Environment.NewLine, lines.Select(TranslateLine));
    }

    private static string TranslateLine(string line)
    {
        var translations = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            { "fatal: not a git repository", "错误：不是Git仓库" },
            { "fatal: 'origin' does not appear to be a git repository", "错误：远程仓库 'origin' 不存在，请先配置远程仓库地址" },
            { "fatal: Could not read from remote repository", "错误：无法读取远程仓库，请检查网络或认证信息" },
            { "fatal: unable to access", "错误：无法访问远程仓库，网络连接失败" },
            { "fatal: the remote end hung up unexpectedly", "错误：远程服务器意外断开连接" },
            { "error: failed to push some refs", "错误：推送失败，远程有新提交，请先拉取" },
            { "error: src refspec main does not match any", "错误：没有可推送的提交，请先提交代码" },
            { "Everything up-to-date", "已是最新，无需推送" },
            { "nothing to commit", "没有需要提交的更改" },
            { "no changes added to commit", "没有添加任何更改到提交" },
            { "Branch 'main' set up to track remote branch", "分支 'main' 已设置跟踪远程分支" },
            { "To https://github.com", "→ 推送到 https://github.com" },
            { "new file:", "新文件：" },
            { "modified:", "已修改：" },
            { "deleted:", "已删除：" },
            { "renamed:", "已重命名：" },
            { "create mode", "创建模式" },
            { "delete mode", "删除模式" },
            { "rewrite", "重写" },
            { "1 file changed", "1个文件已更改" },
            { "files changed", "个文件已更改" },
            { "insertions(+)", "行新增" },
            { "deletions(-)", "行删除" },
            { "Recv failure: Connection was reset", "网络连接被重置，请检查VPN/代理" },
            { "Connection timed out", "连接超时，请检查网络" },
            { "SSL certificate problem", "SSL证书问题" },
            { "Authentication failed", "认证失败，请检查Token" },
            { "Permission denied", "权限被拒绝" },
            { "remote: Resolving deltas", "远程：正在解析差异" },
            { "remote: Counting objects", "远程：正在统计对象" },
            { "remote: Compressing objects", "远程：正在压缩对象" },
            { "Writing objects", "正在写入对象" },
            { "Total", "总计" },
            { "Delta compression using up to", "使用差异压缩，线程数" },
            { "Compressing objects", "正在压缩对象" },
            { "Already up to date", "已是最新" },
            { "Fast-forward", "快进合并" },
            { "Updating", "更新中" },
            { "Successfully rebased and updated", "变基成功并已更新" },
            { "Applying:", "应用提交：" },
            { "Rebasing", "变基中" },
            { "CONFLICT", "冲突" },
        };

        foreach (var kvp in translations)
        {
            if (line.Contains(kvp.Key, StringComparison.OrdinalIgnoreCase))
            {
                return line.Replace(kvp.Key, kvp.Value, StringComparison.OrdinalIgnoreCase);
            }
        }

        return line;
    }

    private void Log(string message)
    {
        if (logBox.IsDisposed) return;
        logBox.AppendText(message + Environment.NewLine);
    }

    private static string QuoteForArgument(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}

internal sealed record ProcessResult(int ExitCode, string CombinedOutput)
{
    public string Output => CombinedOutput;
}

internal sealed class GitPusherConfig
{
    [JsonPropertyName("proxy_addresses")]
    public string ProxyAddresses { get; set; } = "127.0.0.1:7890";

    [JsonPropertyName("use_proxy")]
    public bool UseProxy { get; set; } = true;

    [JsonPropertyName("retry_count")]
    public int RetryCount { get; set; } = 3;

    [JsonPropertyName("timeout_seconds")]
    public int TimeoutSeconds { get; set; } = 120;

    [JsonPropertyName("pull_before_push")]
    public bool PullBeforePush { get; set; } = true;
}
