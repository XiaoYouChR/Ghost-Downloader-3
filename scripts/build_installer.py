# ponytail: clean single-purpose C# installer compilation script
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent



def buildInstaller() -> int:
    if sys.platform != "win32":
        print("Installer compilation is only applicable on Windows.")
        return 0

    cscPath = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    if not cscPath.is_file():
        print(f"Error: C# compiler not found at {cscPath}")
        return 1

    iconPath = REPO / "app" / "assets" / "installer_logo.ico"
    if not iconPath.is_file():
        iconPath = REPO / "app" / "assets" / "logo.ico"

    outputExe = REPO / "Installer.exe"

    csCode = r"""using System;
using System.Diagnostics;
using System.IO;

class Program {
    static void Main(string[] args) {
        Console.Title = "Ghost Downloader 3 - Installer";
        Console.WriteLine("=======================================================");
        Console.WriteLine("         Ghost Downloader 3 - 1-Click Installer       ");
        Console.WriteLine("=======================================================");
        Console.WriteLine();

        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        Directory.SetCurrentDirectory(baseDir);

        Console.WriteLine("[1/4] Checking environment dependencies...");
        bool hasUv = CommandExists("uv");
        if (!hasUv) {
            Console.WriteLine("'uv' package manager not found. Installing 'uv'...");
            if (CommandExists("python")) {
                RunCommand("python", "-m pip install --upgrade uv");
            } else {
                RunCommand("powershell.exe", "-ExecutionPolicy Bypass -Command \"irm https://astral.sh/uv/install.ps1 | iex\"");
            }
        }
        Console.WriteLine("[✓] Environment check complete.\n");

        Console.WriteLine("[2/4] Installing project dependencies (uv sync)...");
        int syncExit = RunCommand("cmd.exe", "/c uv sync");
        if (syncExit != 0) {
            Console.WriteLine("[!] Warning: uv sync returned non-zero exit code (" + syncExit + ").");
        } else {
            Console.WriteLine("[✓] Dependencies installed successfully.\n");
        }

        Console.WriteLine("[3/4] Checking launcher executable...");
        string launcherExe = Path.Combine(baseDir, "Ghost-Downloader.exe");
        if (!File.Exists(launcherExe) && File.Exists(Path.Combine(baseDir, "scripts", "build_launcher.py"))) {
            RunCommand("cmd.exe", "/c uv run python scripts\\build_launcher.py");
        }
        Console.WriteLine("[✓] Launcher ready.\n");

        Console.WriteLine("[4/4] Creating Desktop Shortcut...");
        try {
            string desktopPath = Environment.GetFolderPath(Environment.SpecialFolder.Desktop);
            string shortcutPath = Path.Combine(desktopPath, "Ghost Downloader 3.lnk");
            string targetExe = File.Exists(launcherExe) ? launcherExe : Path.Combine(baseDir, "Launch-Ghost-Downloader.bat");
            string iconPath = Path.Combine(baseDir, "app", "assets", "logo.ico");

            string psScript = string.Format(
                "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('{0}'); $s.TargetPath = '{1}'; $s.WorkingDirectory = '{2}'; if (Test-Path '{3}') {{ $s.IconLocation = '{4}' }}; $s.Save()",
                shortcutPath.Replace("'", "''"),
                targetExe.Replace("'", "''"),
                baseDir.TrimEnd('\\').Replace("'", "''"),
                iconPath.Replace("'", "''"),
                iconPath.Replace("'", "''")
            );

            RunCommand("powershell.exe", "-ExecutionPolicy Bypass -NoProfile -Command \"" + psScript + "\"");
            Console.WriteLine("[✓] Desktop shortcut created: Ghost Downloader 3.lnk\n");
        } catch (Exception ex) {
            Console.WriteLine("[!] Shortcut creation failed: " + ex.Message + "\n");
        }

        Console.WriteLine("=======================================================");
        Console.WriteLine("          Installation Completed Successfully!         ");
        Console.WriteLine("=======================================================");
        Console.WriteLine();
        Console.Write("Do you want to launch Ghost Downloader 3 now? (Y/N): ");
        string resp = Console.ReadLine();
        if (resp != null && resp.Trim().Equals("Y", StringComparison.OrdinalIgnoreCase)) {
            string targetToRun = File.Exists(launcherExe) ? launcherExe : Path.Combine(baseDir, "Launch-Ghost-Downloader.bat");
            ProcessStartInfo psi = new ProcessStartInfo(targetToRun);
            psi.WorkingDirectory = baseDir;
            Process.Start(psi);
        }
    }

    static bool CommandExists(string cmd) {
        try {
            ProcessStartInfo psi = new ProcessStartInfo("cmd.exe", "/c where " + cmd);
            psi.CreateNoWindow = true;
            psi.UseShellExecute = false;
            psi.RedirectStandardOutput = true;
            Process p = Process.Start(psi);
            p.WaitForExit();
            return p.ExitCode == 0;
        } catch {
            return false;
        }
    }

    static int RunCommand(string fileName, string args) {
        try {
            ProcessStartInfo psi = new ProcessStartInfo(fileName, args);
            psi.UseShellExecute = false;
            Process p = Process.Start(psi);
            p.WaitForExit();
            return p.ExitCode;
        } catch (Exception ex) {
            Console.WriteLine("Error running command: " + ex.Message);
            return -1;
        }
    }
}
"""

    tempCs = REPO / "temp_installer.cs"
    tempCs.write_text(csCode, encoding="utf-8")

    cmd = [
        str(cscPath),
        "/nologo",
        "/target:exe",
        f"/win32icon:{iconPath}",
        f"/out:{outputExe}",
        str(tempCs),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if tempCs.is_file():
            tempCs.unlink()

        if res.returncode == 0:
            print(f"Successfully compiled installer: {outputExe}")
            return 0
        else:
            print(f"Compilation failed:\n{res.stderr}")
            return res.returncode
    except Exception as e:
        if tempCs.is_file():
            tempCs.unlink()
        print(f"Build error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(buildInstaller())
