# 更新日志 · Changelog

本文件格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

版本号在 1.0.0 之前，`0.x` 的次版本号代表**可能不兼容的配置变更**。

---

## [Unreleased]

### Planned

- 更多厂商主板的实测适配（当前只在一张华硕板子上验证过）
- 屏幕同步在 4K / 超宽屏下的抓屏开销优化
- README 的其它语种翻译

---

## [0.2.0] — 2026-10-28

这一版把项目从「能用的脚本」推向「可以公开发布」。**配置格式有变更**，但会自动迁移。

### Added

- **首次运行向导**：三步（控制器 → 逐灯区标定 → 完成），配置写入 `config.json`；
  底部「重新配置」可随时重跑
- **GPU 联动灯效**：读 `nvidia-smi` 的温度/占用/功耗，温度决定色相、占用决定亮度，
  不需要任何额外硬件
- **屏幕同步灯效**：屏幕横向 16 段取平均色映射到灯珠；抓屏跑在独立子进程里
- **白日 / 黑夜主题**：跟随系统偏好、记住选择、首帧前写入避免闪烁
- **灯效从 5 种增至 8 种**：新增 GPU 联动、屏幕同步
- **UI v2 商业级重做**：统一设计令牌、8 个内联 SVG 图标、明确的
  hover/active/focus-visible 状态、`role=switch` / `aria-pressed` 无障碍语义、响应式双栏
- **工程文件**：`LICENSE`（GPL-3.0）、`.gitignore`、`requirements.txt`、
  `scripts/fetch_openrgb.ps1`（下载官方 OpenRGB 并校验 SHA-256）
- **`patches/`**：针对 RTX 4080 SUPER FE `0x18CC` 变体的 OpenRGB 补丁，
  含源码补丁（`git apply` 已验证）与二进制补丁脚本（结构体签名定位 + 可还原）
- **文档**：`docs/GETTING-STARTED.md`（教程）、`CONFIGURATION.md`、`TROUBLESHOOTING.md`、
  `DEVELOPMENT.md`、`THIRD-PARTY.md`、`nvidia-fe-illumination.md`
- 中英双语 README + 首屏 GIF
- `/api/setup/done` 端点

### Changed

- **配置位置**：`runtime/ui_settings.json` → 根目录 **`config.json`**
- **灯区键名不再写死**：`header1/2/3`、`mainboard` → 由灯区名生成的 slug
  （如 `addressable_rgb_header_1`）；旧键会自动迁移
- **控制器选择逻辑**：从按品牌名硬匹配改为按能力打分 `(灯区数, 灯珠总数)`，
  并支持 `config.json` 的 `device` 字段手动指定
- **resize 规则**：从「名字含 `addressable` 才 resize」改为通用规则
  （未标定 / 已达目标 / 单灯区域跳过，其余尝试）
- 设备胶囊显示 `· N 区 / M 灯`，悬停提示说明「这是控制器名，不一定是主板型号」
- OpenRGB 二进制不再随仓库分发，改由 `fetch_openrgb.ps1` 下载

### Fixed

- **灯区开关只能单向关闭**（严重）：取反依赖 DOM class，而就地渲染从不刷新该 class，
  导致点一次变黑后再也开不回来。改为读权威状态 + 乐观更新 + `pendingToggle` 防轮询覆盖
- **`device_count` 恒为 1**：OpenRGB 设备检测是异步的（主板 ~0.2s、GPU ~1.8s），
  端口就绪即连接会漏掉后注册的控制器；且 `openrgb-python` 的 `devices` 是构造时的
  一次性列表，必须显式 `cli.update()` 才能刷新
- **流光整数步进卡顿**：`int()` 截断使 16 颗灯珠只能每秒跳 3.3 次，
  改为浮点位置 + 平方衰减的亚灯珠插值
- **流光一圈时长随灯珠数变化**：改为 `lap = 24 / speed`，与灯珠数解耦
- **屏幕取色拖垮 HTTP**：线程内抓屏每帧分配 19 MB，触发 GC 停顿并占住 GIL，
  造成 `/api/state` 偶发 5 秒级超时。拆为独立子进程后 p99 降到 11 ms
- **抓屏子进程一启动就退出**：Windows 上 `os.kill(pid, 0)` 会走 `TerminateProcess`，
  不是探活。改用 `OpenProcess` + `WaitForSingleObject`
- **GPU 遥测恒为不可用**：`nvidia-smi -f` 无法写入含中文的路径（returncode 255），
  改用纯 ASCII 临时目录
- **同名灯区互相覆盖**：键表原为 `{name: key}` 字典，重名灯区只剩最后一个；改为按下标对齐的列表
- **非 ASCII 灯区名生成坏键**：`"风扇 1"` slug 化后变成 `"1"`，回退为 `zone_<下标>`
- 弹窗在 720p 下溢出，按钮被裁到折叠线以下；改为双栏布局 + `flex-start` + `margin:auto`

---

## [0.1.0] — 2026-10-27

首个可用版本。

### Added

- 通过 OpenRGB SDK 驱动 AURA LED Controller（`0B05:19AF`，HID `mi_02`，UsagePage `0xFF72`）
- 网页控制台：静态 / 彩虹 / 呼吸 / 流光 / 波浪 / 关闭 六种状态
- HSV 色轮 + 84 格调色盘 + 最近使用
- 逐灯区开关、配色、灯珠数标定（带实时 resize）
- 亮度 / 速度滑条
- 命令行工具 `control.py`：`list / set / mode / off / anim / sweep / snapshot / restore`
- 诊断脚本：`probe_devices.py`、`diag_chase.py`、`bench_write.py`
