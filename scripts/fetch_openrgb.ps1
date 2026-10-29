# NO WARRANTY — see LICENSE
<#
.SYNOPSIS
    下载官方 OpenRGB 便携版到 assets/OpenRGB/，校验 SHA-256，可选打上 0x18CC 补丁。

.DESCRIPTION
    本仓库不收录 OpenRGB 的二进制（GPL-2.0 且约 58MB）。首次使用请运行本脚本。

.PARAMETER Version
    OpenRGB 发布版本，默认 1.1。

.PARAMETER ApplyPatch
    下载后顺带打上 patches/0001 对应的单字节二进制补丁（0x18CB -> 0x18CC）。
    仅对 RTX 4080 SUPER Founders Edition 的某个变体有意义，其它显卡请勿使用。

.PARAMETER Force
    已存在时强制重新下载。

.EXAMPLE
    pwsh -File scripts/fetch_openrgb.ps1
    pwsh -File scripts/fetch_openrgb.ps1 -ApplyPatch
#>
[CmdletBinding()]
param(
    [string]$Version = '1.1',
    [switch]$ApplyPatch,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $root 'assets'
$target = Join-Path $assets 'OpenRGB'
$zipPath = Join-Path $assets "OpenRGB_${Version}_Windows_64.zip"

# 已知版本 -> (下载地址, 期望 SHA-256)
$catalog = @{
    '1.1' = @{
        Url  = 'https://github.com/CalcProgrammer1/OpenRGB/releases/download/release_1.1/OpenRGB_1.1_Windows_64_8e16de2.zip'
        Sha  = '63291726C6FC84EB479EF2EE752E97E1187F6CE9C49FD27EEE40DED588A8172A'
    }
}

if (-not $catalog.ContainsKey($Version)) {
    throw "未收录的版本: $Version（已收录: $($catalog.Keys -join ', ')）"
}
$info = $catalog[$Version]

$exeGuess = Join-Path $target 'OpenRGB Windows 64-bit\OpenRGB.exe'
if ((Test-Path $exeGuess) -and -not $Force) {
    Write-Host "[=] 已存在: $exeGuess" -ForegroundColor Yellow
    Write-Host "    如需重新下载请加 -Force"
    if ($ApplyPatch) { & (Join-Path $PSScriptRoot '..\patches\apply-binary-patch.ps1') }
    return
}

New-Item -ItemType Directory -Force -Path $assets | Out-Null

if (-not (Test-Path $zipPath) -or $Force) {
    Write-Host "[*] 下载 OpenRGB $Version ..." -ForegroundColor Cyan
    Write-Host "    $($info.Url)"
    curl.exe -L --fail --retry 2 --progress-bar -o $zipPath $info.Url
    if ($LASTEXITCODE -ne 0) { throw "下载失败（curl exit $LASTEXITCODE）" }
}

Write-Host "[*] 校验 SHA-256 ..." -ForegroundColor Cyan
$actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
if ($actual -ne $info.Sha) {
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    throw "SHA-256 不匹配，已删除下载文件。`n  期望: $($info.Sha)`n  实际: $actual"
}
Write-Host "[+] 校验通过" -ForegroundColor Green

Write-Host "[*] 解压到 $target ..." -ForegroundColor Cyan
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Expand-Archive -LiteralPath $zipPath -DestinationPath $target -Force

$exe = Get-ChildItem $target -Recurse -Filter 'OpenRGB.exe' -File |
    Where-Object { $_.Directory.Name -like '*Windows 64-bit*' } |
    Select-Object -First 1
if (-not $exe) { $exe = Get-ChildItem $target -Recurse -Filter 'OpenRGB.exe' -File | Select-Object -First 1 }
if (-not $exe) { throw "解压后没找到 OpenRGB.exe" }

Write-Host "[+] 就绪: $($exe.FullName)" -ForegroundColor Green

if ($ApplyPatch) {
    Write-Host "[*] 应用 0x18CC 二进制补丁 ..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot '..\patches\apply-binary-patch.ps1') -ExePath $exe.FullName
}

Write-Host ""
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host "  1) pip install -r requirements.txt"
Write-Host "  2) 双击 启动灯光控制台.cmd   （或 pwsh: python scripts/server.py）"
Write-Host "  3) 浏览器打开 http://127.0.0.1:8099/ ，按首次运行向导完成灯区标定"
