# 故障排查 · Troubleshooting

本文按**症状**组织，全部条目都来自实机踩过的坑，不是想象出来的。

先做一件事：确认是**软件问题**还是**灯珠数标定问题**。

```powershell
python scripts/control.py set --color FF0000
```

- 整体变红 → 链路通，问题多半在灯珠数/灯区开关/灯效上
- 完全没反应 → 继续看下面的「连不上」

---

## 一、连不上

### `OpenRGB SDK 不可用`

控制台连不上 `127.0.0.1:6742`。

1. 确认 OpenRGB 存在：
   ```powershell
   Test-Path .\assets\OpenRGB\OpenRGB Windows 64-bit\OpenRGB.exe
   ```
   不存在就跑 `pwsh -File scripts/fetch_openrgb.ps1`。

2. 确认端口没被占：
   ```powershell
   Get-NetTCPConnection -State Listen -LocalPort 6742
   ```
   有输出说明已在跑（可能是你没关掉的旧实例），可以直接用；想重启就先结束那个进程。

3. 手动验证 OpenRGB 本身是否正常：
   ```powershell
   .\assets\OpenRGB\OpenRGB\...\OpenRGB.exe --server --noautoconnect
   ```
   打开它的图形界面，看左侧设备列表里有没有你的板子。

### 界面里一个灯区都没有

OpenRGB 没识别到任何控制器。看它自己的日志：

```powershell
Get-Content "$env:APPDATA\OpenRGB\logs\$(Get-ChildItem "$env:APPDATA\OpenRGB\logs" | Sort-Object LastWriteTime -Desc | Select-Object -First 1 -ExpandProperty Name)"
```

关键行是 `Registering RGB controller ...`。一行都没有 → OpenRGB 不支持你的灯控芯片，
本项目也救不了。

### 所有设备都识别到了，但项目选错了控制器

顶部胶囊显示的不是你的主板。看悬停提示里的「本轮共枚举到 N 个控制器」，
然后在 `config.json` 里指定：

```jsonc
{ "device": "B650M" }
```

详见 [CONFIGURATION.md](CONFIGURATION.md#多控制器如何指定)。

---

## 二、灯不亮 / 只亮一部分

### 某一路完全不亮

按顺序排：

1. **该灯区开关是不是关的**（界面上那个滑块）。关掉的灯区只会收到黑色。
2. **灯珠数是不是 0**（未标定）。可寻址排针在标定前 OpenRGB 报 0 颗灯，写进去也不会亮。
3. **物理接线**：排针有没有插紧、风扇的 ARGB 线有没有插到主板而不是机箱控制盒。
4. 用定位命令确认是哪一路：
   ```powershell
   python scripts/control.py sweep --leds 60
   ```
   三路分别亮 绿/蓝/红，看机箱里哪组变成哪个色。

### 风扇外圈亮，内圈不亮

**灯珠数填小了**。链路末尾的灯珠被截断，而内圈通常排在链尾。

把标定滑条往右拖，直到整个扇叶全亮。「刚好全亮」那个数才是真实值。

> 实测参考：常见 ARGB 风扇是 **12 颗/扇**。2 个风扇 = 24，4 个风扇 = 48。
> 按 8 颗/扇去填会正好切掉内圈。

### 流光/彩虹"跑一段就停住"

**灯珠数填大了**。光头走到了不存在的灯珠上，真实灯珠全黑，看起来像停了。

往左调到「刚好全亮」为止。判断方法：如果一圈里有一段明显的全黑间隙，就是填大了。

### 流光一开始"只转一圈"

两个原因叠加，都要看：

1. **速度太低** —— `speed=1` 时一圈是 24 秒，本来就很慢
2. **灯珠数偏大** —— 一圈里有大段行程落在空位上

先把标定做对，再把速度调到 5 左右（一圈约 4.8 秒）。

---

## 三、效果/性能

### 动画"一卡一卡"

先看是不是引擎掉帧。页面顶部有 FPS，或者直接查接口：

```powershell
(Invoke-WebRequest http://127.0.0.1:8099/api/state -UseBasicParsing).Content | ConvertFrom-Json |
  Select-Object fps, dt_p50, dt_p95
```

- `dt_p50 ≈ 33.3ms`、`dt_p95 < 40ms` → **引擎没掉帧**，是图案本身的问题
  （多半是灯珠数与真实链路不符，见上一节）
- `dt_p95` 明显偏大 → 引擎在掉帧，看看是不是同时跑了重负载程序

### 屏幕同步让网页变卡 / 接口超时

抓屏很吃内存（3440×1440 每帧约 19MB）。正常情况下它在**独立子进程**里跑，
切到别的灯效会自动退出。

如果卡，先确认子进程状态：

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*screen_worker*' }
Test-Path "$env:TEMP\light_console_bands.json"
```

`light_console_bands.json` 不生成或时间戳不更新 → 子进程没工作，重新切一次屏幕同步模式。
只想省资源就别用这个模式。

### GPU 胶囊显示 `GPU —`

```powershell
python scripts/diag_gpu_poll.py
```

这个脚本会对比「纯 ASCII 路径」和「含中文路径」写入 `nvidia-smi` 输出的结果。典型输出：

```
--- 纯 ASCII 路径 ---    returncode = 0     文件生成: True
--- 含中文的路径 ---     returncode = 255   文件生成: False
结论：ASCII 路径 成功 / 中文路径 失败
```

看到 255 就说明 `nvidia-smi -f` 无法写入中文路径。运行时代码已经把临时文件放到
`%TEMP%`（纯 ASCII），所以只要项目本身不在中文路径下就不会触发；
如果还是失败，检查 `C:\Windows\System32\nvidia-smi.exe` 是否存在、驱动是否装好。

---

## 四、显卡灯

### OpenRGB 设备列表里没有我的 NVIDIA 卡

上游 OpenRGB 按 PCI 四元组精确匹配设备。部分 RTX 4080 SUPER FE 报告的是
`SUBSYS_18CC10DE`，而上游只定义了 `0x18CB`，于是**静默跳过**（连日志都不打）。

```powershell
# 先确认你的子系统 ID
Get-PnpDevice -Class Display -PresentOnly | Where-Object { $_.FriendlyName -match 'NVIDIA' } |
  Select-Object -ExpandProperty InstanceId
```

如果结尾是 `SUBSYS_18CC1DE`，见 [patches/README.md](../patches/README.md)。

### 打完补丁卡被识别了，但灯还是改不了

**这是已知的、预期内的结果。** 补丁只修「识别」，不修「能不能控」。

打补丁后日志会出现：

```
Registering RGB controller NVIDIA GeForce RTX 4080 SUPER FE
```

但紧接着 `NvAPI_GPU_ClientIllumZonesGetControl` 返回的 `numIllumZonesControl` 仍是 **0** ——
驱动层没有暴露任何可控灯区。已排除的可能：

| 假设 | 结论 |
|---|---|
| 权限不足 | 以管理员身份验证过，同样 0 灯区 |
| 缺 PawnIO 驱动 | 照明走 NVAPI，不走 I2C/SMBus，无关 |
| 结构体版本号过时 | `72012 = 6476 | (1<<16)` 与 `MAKE_NVAPI_VERSION` 编码吻合，驱动未报不兼容 |
| NVIDIA 官方有灯控入口 | 全量扫描 NVIDIA App / NvContainer，`Illumination` 命中 0 处 |

想要显卡附近也有灯，实际可行的办法是：**把一条 ARGB 灯带接到空闲的主板 ARGB 排针上**，
它会作为新的灯区出现在向导里，与机箱风扇同步跑同一套效果。

---

## 五、界面

### 页面打开是白屏 / 样式全乱

浏览器缓存了旧版本。强制刷新（`Ctrl+F5`）。控制台不发送缓存头，正常不会发生。

### 主题在黑白之间闪一下

理论上不应该。已经在 `<head>` 内联脚本里于首帧前写入 `data-theme`。
如果仍然闪，可能是浏览器插件注入了样式，试着禁用插件。

### 开关点一次就再也开不回来

这是 v1 的已知严重 Bug，**v2 已修复**（取反改为读权威状态 + 乐观更新 + `pendingToggle` 防轮询覆盖）。
如果你还在旧版本上，拉最新代码即可。

---

## 六、还是不行

收集这些信息再开 issue：

```powershell
# 1. 环境
python --version; pwsh -version
Get-PnpDevice -Class Display -PresentOnly | Select-Object FriendlyName, InstanceId

# 2. 状态
(Invoke-WebRequest http://127.0.0.1:8099/api/state -UseBasicParsing).Content

# 3. OpenRGB 日志（最近一份）
Get-ChildItem "$env:APPDATA\OpenRGB\logs" | Sort-Object LastWriteTime -Desc |
  Select-Object -First 1 | Get-Content
```

请**打码**掉序列号、主机名、用户名等个人信息后再贴出来。
