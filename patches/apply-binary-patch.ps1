# NO WARRANTY — see ../LICENSE
<#
.SYNOPSIS
    给官方 OpenRGB.exe 打单字节补丁，使 NVIDIA Illumination 探测接受 RTX 4080 SUPER FE 的 0x18CC 变体。

.DESCRIPTION
    背景：OpenRGB 的 NVIDIA 照明驱动按 PCI 四元组精确匹配设备，
    pci_ids.h 里 `NVIDIA_RTX4080S_FE_SUB_DEV = 0x18CB`，而部分零售 FE 卡报告 0x18CC。
    差一个数，探测直接跳过，且不打任何日志。

    本脚本对该板卡在 device_list 表中的条目做 1 字节修改：0x18CB -> 0x18CC。

    定位方式不是硬编码偏移，而是按「结构体签名」搜索：
        DE 10 00 00   vendor      = 0x10DE
        02 27 00 00   device      = 0x2702  (RTX 4080 SUPER)
        DE 10 00 00   subsystem v = 0x10DE
        CB 18 00 00   subsystem d = 0x18CB  <-- 待改
    要求该签名在文件中**唯一命中**，否则拒绝修改。

.PARAMETER ExePath
    OpenRGB.exe 路径。默认找 assets/OpenRGB/*Windows 64-bit/OpenRGB.exe。

.PARAMETER Revert
    从 .bak 还原。

.EXAMPLE
    pwsh -File patches/apply-binary-patch.ps1
    pwsh -File patches/apply-binary-patch.ps1 -Revert
#>
[CmdletBinding()]
param(
    [string]$ExePath,
    [switch]$Revert
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# 已知官方 1.1 便携版原始哈希（用于确认没改错文件）
$KNOWN_ORIGINAL = @{
    'E26AE71162795A8ABCFB90C05C1572A00BA06CA63B886ACA57392A0138963B1E' = 'OpenRGB 1.1 Windows x64 (官方原版)'
}
# 打完补丁后的哈希
$KNOWN_PATCHED = 'B937CD8C6F6C98F42B966F937C0F163A0F8896DE541C2B7473A88CB16AB35040'

if (-not $ExePath) {
    $found = Get-ChildItem (Join-Path $root 'assets') -Recurse -Filter 'OpenRGB.exe' -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $found) { throw "找不到 OpenRGB.exe，请先运行 scripts/fetch_openrgb.ps1" }
    $ExePath = $found.FullName
}
if (-not (Test-Path -LiteralPath $ExePath)) { throw "文件不存在: $ExePath" }

$bak = "$ExePath.bak"

if ($Revert) {
    if (-not (Test-Path -LiteralPath $bak)) { throw "没有备份文件: $bak" }
    Copy-Item -LiteralPath $bak -Destination $ExePath -Force
    Write-Host "[+] 已还原: $ExePath" -ForegroundColor Green
    Write-Host "    SHA-256: $((Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash)"
    return
}

$bytes = [System.IO.File]::ReadAllBytes($ExePath)
$sha = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash
Write-Host "[i] 当前文件 SHA-256: $sha"

if ($sha -eq $KNOWN_PATCHED) {
    Write-Host "[=] 已经是补丁后的版本，无需重复操作" -ForegroundColor Yellow
    return
}
if (-not $KNOWN_ORIGINAL.ContainsKey($sha)) {
    Write-Host "[!] 这个哈希不在已知清单里（可能存在版本差异）" -ForegroundColor Yellow
    Write-Host "    已知清单: $($KNOWN_ORIGINAL.Keys -join ', ')"
    $ans = Read-Host "仍要继续尝试吗？(y/N)"
    if ($ans -ne 'y') { Write-Host "已取消"; return }
}

# ---- 按结构体签名定位 ----
$signature = [byte[]](0xDE,0x10,0x00,0x00, 0x02,0x27,0x00,0x00, 0xDE,0x10,0x00,0x00, 0xCB,0x18,0x00,0x00)
$hits = New-Object System.Collections.Generic.List[int]
for ($i = 0; $i -le $bytes.Length - $signature.Length; $i++) {
    if ($bytes[$i]   -eq 0xDE -and $bytes[$i+1] -eq 0x10 -and $bytes[$i+2] -eq 0x00 -and $bytes[$i+3] -eq 0x00 -and
        $bytes[$i+4] -eq 0x02 -and $bytes[$i+5] -eq 0x27 -and $bytes[$i+6] -eq 0x00 -and $bytes[$i+7] -eq 0x00 -and
        $bytes[$i+8] -eq 0xDE -and $bytes[$i+9] -eq 0x10 -and $bytes[$i+10] -eq 0x00 -and $bytes[$i+11] -eq 0x00 -and
        $bytes[$i+12] -eq 0xCB -and $bytes[$i+13] -eq 0x18 -and $bytes[$i+14] -eq 0x00 -and $bytes[$i+15] -eq 0x00) {
        $hits.Add($i)
    }
}

Write-Host "[i] 结构体签名命中: $($hits.Count) 处"
if ($hits.Count -ne 1) {
    throw "命中数不为 1，拒绝修改（避免打错地方）。命中: $($hits -join ', ')"
}

$off = $hits[0] + 12   # 0xCB 所在的偏移
Write-Host "[i] 目标偏移: 0x$($off.ToString('X'))  原值: 0x$($bytes[$off].ToString('X2'))"
if ($bytes[$off] -ne 0xCB) { throw "偏移处字节不是 0xCB，拒绝修改" }

if (-not (Test-Path -LiteralPath $bak)) {
    Copy-Item -LiteralPath $ExePath -Destination $bak -Force
    Write-Host "[+] 已备份: $bak"
}

$bytes[$off] = 0xCC
[System.IO.File]::WriteAllBytes($ExePath, $bytes)

$after = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash
Write-Host "[+] 补丁完成: 0x18CB -> 0x18CC" -ForegroundColor Green
Write-Host "    新 SHA-256: $after"
if ($after -eq $KNOWN_PATCHED) {
    Write-Host "    ✓ 与已验证的补丁版本哈希一致" -ForegroundColor Green
}
Write-Host ""
Write-Host "验证方式：启动 OpenRGB 后查看日志（%APPDATA%\OpenRGB\logs）应出现" -ForegroundColor Cyan
Write-Host '  Registering RGB controller NVIDIA GeForce RTX 4080 SUPER FE'
Write-Host ""
Write-Host "还原：pwsh -File patches/apply-binary-patch.ps1 -Revert" -ForegroundColor Cyan
