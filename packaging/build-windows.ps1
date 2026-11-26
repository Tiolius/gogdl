param(
    [string]$OutputZip = "dist/GOGDL-Windows-x64.zip"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$zip = [IO.Path]::GetFullPath((Join-Path $root $OutputZip))
$staging = Join-Path ([IO.Path]::GetTempPath()) ("gogdl-build-" + [Guid]::NewGuid())
$app = Join-Path $staging 'GOGDL'
$runtime = Join-Path $app '.gogdl-runtime'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE."
    }
}

try {
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $version = & python.exe -c "import platform; print(platform.python_version())"
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^3\.\d+\.\d+$') {
        throw 'A supported x64 Python release is required to build GOGDL.'
    }

    $pythonZip = Join-Path $staging 'python.zip'
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$version/python-$version-embed-amd64.zip" -OutFile $pythonZip
    Expand-Archive -Path $pythonZip -DestinationPath $runtime
    $pythonPathConfig = Get-ChildItem -Path $runtime -Filter 'python*._pth' | Select-Object -First 1
    if (-not $pythonPathConfig) { throw 'Python path configuration is missing.' }
    $importPaths = @(Get-Content -LiteralPath $pythonPathConfig.FullName) + '..'
    Set-Content -LiteralPath $pythonPathConfig.FullName -Value $importPaths -Encoding ASCII

    Invoke-Checked python.exe @('-m', 'pip', 'install', '--target', $runtime, '-r', (Join-Path $root 'requirements.txt'))

    foreach ($name in @('assets', 'packaging', 'gogdl_backend.py', 'gogdl_settings.py', 'gogdl_updater.py', 'gogdl_window.py', 'gogrepoc.py', 'LICENSE-gogrepoc.txt', 'README.md', 'requirements.txt', 'Setup-GOGDL.cmd', 'Start-GOGDL.cmd')) {
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $app -Recurse
    }
    Add-Type -Path (Join-Path $PSScriptRoot 'launcher.cs') -ReferencedAssemblies System.Windows.Forms.dll -OutputAssembly (Join-Path $app 'GOGDL.exe') -OutputType WindowsApplication

    Push-Location $app
    try {
        $python = Join-Path $runtime 'python.exe'
        Invoke-Checked $python @('-B', '-c', "import clr, html5lib, requests, psutil; from pathlib import Path; from gogdl_backend import Backend; assert Backend().settings_info()['version']['number']; from gogdl_window import HOME; assert HOME; dlls = Path('.gogdl-runtime/webview/lib'); clr.AddReference(str((dlls / 'Microsoft.Web.WebView2.Core.dll').resolve())); clr.AddReference(str((dlls / 'Microsoft.Web.WebView2.WinForms.dll').resolve())); from Microsoft.Web.WebView2.WinForms import WebView2")
        Invoke-Checked $python @('-B', 'gogrepoc.py', '--version')
    } finally {
        Pop-Location
    }

    $zipParent = Split-Path $zip -Parent
    New-Item -ItemType Directory -Path $zipParent -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $temporaryZip = Join-Path $zipParent ("gogdl-" + [Guid]::NewGuid() + ".zip")
    try {
        $archive = [IO.Compression.ZipFile]::Open($temporaryZip, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($file in Get-ChildItem -LiteralPath $app -Recurse -File -Force) {
                $entry = 'GOGDL/' + $file.FullName.Substring($app.Length + 1).Replace('\', '/')
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $entry, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        } finally {
            $archive.Dispose()
        }
        $archive = [IO.Compression.ZipFile]::OpenRead($temporaryZip)
        try {
            foreach ($entry in @('GOGDL/GOGDL.exe', 'GOGDL/.gogdl-runtime/pythonw.exe', 'GOGDL/assets/index.html', 'GOGDL/gogrepoc.py')) {
                if (-not $archive.GetEntry($entry)) { throw "Missing archive entry: $entry" }
            }
        } finally {
            $archive.Dispose()
        }
        Move-Item -LiteralPath $temporaryZip -Destination $zip -Force
    } finally {
        Remove-Item -LiteralPath $temporaryZip -Force -ErrorAction SilentlyContinue
    }
} finally {
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}
