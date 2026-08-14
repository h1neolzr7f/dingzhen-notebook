using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Windows.Forms;

internal static class FenbiStudyInstaller
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool verifyOnly = args.Length > 0 && args[0] == "/verify-only";
        try
        {
            string source = AppDomain.CurrentDomain.BaseDirectory;
            string archive = Path.Combine(source, "FenbiStudy.zip");
            string hashFile = Path.Combine(source, "FenbiStudy.sha256");
            VerifyArchive(archive, hashFile);
            if (verifyOnly) return 0;

            string target = Path.GetFullPath(Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FenbiStudy"));
            string app = Path.Combine(target, "app");
            string pending = Path.Combine(target, "app.new");
            Directory.CreateDirectory(target);
            if (Directory.Exists(pending)) Directory.Delete(pending, true);
            ZipFile.ExtractToDirectory(archive, pending);
            if (!File.Exists(Path.Combine(pending, "FenbiStudy.exe")))
                throw new InvalidDataException("The application archive does not contain FenbiStudy.exe.");
            if (Directory.Exists(app)) Directory.Delete(app, true);
            Directory.Move(pending, app);
            Directory.CreateDirectory(Path.Combine(target, "config"));
            Directory.CreateDirectory(Path.Combine(target, "data"));
            Directory.CreateDirectory(Path.Combine(target, "exports"));
            CopyConfigIfMissing(source, target, "update.json");
            CopyConfigIfMissing(source, target, "stability.json");
            CreateShortcut(Path.Combine(app, "FenbiStudy.exe"), target);
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = Path.Combine(app, "FenbiStudy.exe"),
                WorkingDirectory = target,
                UseShellExecute = true
            });
            MessageBox.Show("安装完成。用户数据库保存在 " + Path.Combine(target, "data"),
                "粉笔学习数据处理系统", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception error)
        {
            if (!verifyOnly)
                MessageBox.Show(error.Message, "安装失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static void VerifyArchive(string archive, string hashFile)
    {
        if (!File.Exists(archive) || !File.Exists(hashFile))
            throw new FileNotFoundException("FenbiStudy.zip or FenbiStudy.sha256 is missing.");
        string expected = File.ReadAllText(hashFile).Trim().Split(' ')[0].ToLowerInvariant();
        string actual;
        using (SHA256 sha = SHA256.Create())
        using (FileStream stream = File.OpenRead(archive))
            actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        if (!String.Equals(expected, actual, StringComparison.Ordinal))
            throw new InvalidDataException("FenbiStudy.zip SHA-256 verification failed.");
    }

    private static void CopyConfigIfMissing(string source, string target, string name)
    {
        string destination = Path.Combine(target, "config", name);
        string input = Path.Combine(source, name);
        if (!File.Exists(destination) && File.Exists(input)) File.Copy(input, destination);
    }

    private static void CreateShortcut(string executable, string workingDirectory)
    {
        string shortcutPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Programs), "粉笔学习数据处理系统.lnk");
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell,
            new object[] { shortcutPath });
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { executable });
        shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut,
            new object[] { workingDirectory });
        shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
    }
}
