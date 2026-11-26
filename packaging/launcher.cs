using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static void Main()
    {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(folder, ".gogdl-runtime", "pythonw.exe");
        try
        {
            Process.Start(new ProcessStartInfo(python, "\"gogdl_window.py\"")
            {
                WorkingDirectory = folder,
                UseShellExecute = false,
                CreateNoWindow = true
            });
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "GOGDL", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
