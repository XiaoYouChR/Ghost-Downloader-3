import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def buildLauncher() -> int:
    if sys.platform != "win32":
        print("Launcher compilation is only applicable on Windows.")
        return 0

    cscPath = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    if not cscPath.is_file():
        print(f"Error: C# compiler not found at {cscPath}")
        return 1

    iconPath = REPO / "app" / "assets" / "logo.ico"
    outputExe = REPO / "Ghost-Downloader.exe"

    csCode = """using System;
using System.Diagnostics;

class Program {
    static void Main(string[] args) {
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = "cmd.exe";
        psi.Arguments = "/c uv run python Ghost-Downloader-3.py " + string.Join(" ", args);
        psi.WindowStyle = ProcessWindowStyle.Hidden;
        psi.CreateNoWindow = true;
        psi.UseShellExecute = false;
        psi.WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory;
        Process.Start(psi);
    }
}
"""

    tempCs = REPO / "temp_launcher.cs"
    tempCs.write_text(csCode, encoding="utf-8")

    cmd = [
        str(cscPath),
        "/nologo",
        "/target:winexe",
        f"/win32icon:{iconPath}",
        f"/out:{outputExe}",
        str(tempCs),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if tempCs.is_file():
            tempCs.unlink()

        if res.returncode == 0:
            print(f"Successfully compiled launcher: {outputExe}")
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
    raise SystemExit(buildLauncher())
