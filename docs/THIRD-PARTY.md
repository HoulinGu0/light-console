# 第三方组件与许可证说明

本仓库**不是** MIT。原因见第 1 条 —— 请先读完再决定怎么用。

---

## 1. `openrgb-python` — GPL-3.0（决定本仓库的许可证）

- 包名：`openrgb-python`
- 版本：`0.3.8`
- 许可证：**GNU General Public License v3.0**
- 用途：`scripts/server.py`、`scripts/control.py`、`scripts/probe_devices.py`、
  `scripts/diag_chase.py`、`scripts/bench_write.py` 全部 `import openrgb`

**为什么这决定了本仓库的许可证**：本项目在 Python 层直接 `import` 该库并调用其 API，
属于 GPL 意义上的衍生作品，因此本仓库整体以 **GPL-3.0** 发布（见根目录 `LICENSE`）。

> **想改成 MIT 的唯一办法**：自己实现 OpenRGB SDK 协议客户端，去掉 `openrgb-python` 依赖。
> 协议本身是公开的（`ORGB` 魔数 + 16 字节头 + 包体），工作量约 300～400 行。
> 在去掉之前，任何 `LICENSE` 改成 MIT 的做法都是错的。

---

## 2. 其余运行时依赖

| 组件 | 版本 | 许可证 | 用途 |
|---|---|---|---|
| `mss` | 10.1.0 | **MIT** | 屏幕抓取（`screen_worker.py`） |
| `numpy` | 2.4.6 | **BSD-3-Clause** | 抓屏后降采样与分段取色 |
| `Pillow` | 12.1.1 | **MIT-CMU** | 仅开发期：生成 README 首屏 GIF，非运行时依赖 |

---

## 3. OpenRGB 本体 — GPL-2.0（**外部程序，不经网络协议传染**）

- 项目：https://github.com/CalcProgrammer1/OpenRGB
- 许可证：**GPL-2.0**
- 本仓库**不包含**它的任何二进制或源码，`.gitignore` 已排除 `assets/OpenRGB/`，
  由 `fetch_openrgb.ps1` 在用户机器上从官方 Release 下载。

**关系界定**：本项目通过 **TCP 6742 端口上的 OpenRGB SDK 协议** 与之通信。
两个通过公开网络协议交互的独立程序，不构成衍生作品关系，
因此 OpenRGB 的 GPL-2.0 不会传染到本仓库代码。

> ⚠️ **但如果你分发了「打过补丁的 OpenRGB.exe」，那份二进制就是 GPL-2.0 的衍生作品**，
> 必须随附对应的修改后源码获取方式。详见 `patches/README.md`。
> 本仓库的做法：**只分发补丁**，不分发二进制。

---

## 4. 使用到的协议与数据

- **OpenRGB SDK 协议**：通过 `openrgb-python` 间接使用，属公开接口。
- **NVAPI**：通过 OpenRGB 间接使用，本项目未直接链接 NVIDIA 任何库。
- **`nvidia-smi`**：调用系统自带命令行工具读取温度/占用/功耗，属正常系统调用。

---

## 5. 硬件兼容性声明

本项目针对个人一台机器（ASUS TUF GAMING B650M-PLUS WIFI + RTX 4080 SUPER FE）
调校并验证。README「已知限制」一节有完整说明。
**不提供任何硬件厂商背书，也不保证在其它主板上可用。**
