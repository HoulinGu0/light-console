# patches/

针对 OpenRGB 的补丁：让 NVIDIA 照明驱动接受 **RTX 4080 SUPER Founders Edition 的 `0x18CC` 变体**。

---

## 问题

OpenRGB 的 NVIDIA 照明驱动在
`Controllers/NVIDIAIlluminationController/NVIDIAIlluminationControllerDetect_Windows_Linux.cpp`
里用 **PCI 四元组精确匹配** 判定设备：

```c
if (pci_vendor == dev.pci_vendor && pci_device == dev.pci_device &&
    pci_subsystem_vendor == dev.pci_subsystem_vendor &&
    pci_subsystem_device == dev.pci_subsystem_device) { /* 注册控制器 */ }
```

而 `pci_ids/pci_ids.h` 里只定义了：

```c
#define NVIDIA_RTX4080S_FE_SUB_DEV   0x18CB
```

部分零售 FE 卡报告的是 **`0x18CC`**，于是：

- 不匹配 → 探测**静默跳过**（连一行日志都不打）
- 现象：OpenRGB 设备列表里根本没有显卡，用户完全无从下手

实测本机：`PCI\VEN_10DE&DEV_2702&SUBSYS_18CC10DE`

---

## 两种应用方式

### A. 源码补丁（推荐，可提交上游）

```bash
git clone https://github.com/CalcProgrammer1/OpenRGB.git
cd OpenRGB
git checkout release_1.1
git apply /path/to/0001-add-rtx4080s-0x18cc.patch
```

已验证：`git apply --check` 与 `git apply` 在 `release_1.1` 上均返回 0，
应用后两处改动正确（新增 `NVIDIA_RTX4080S_FE_SUB_DEV2 0x18CC` 与对应的 device_list 条目）。

改动内容：

| 文件 | 改动 |
|---|---|
| `pci_ids/pci_ids.h` | 新增 `#define NVIDIA_RTX4080S_FE_SUB_DEV2 0x18CC` |
| `.../NVIDIAIlluminationControllerDetect_Windows_Linux.cpp` | device_list 新增一条 4080 SUPER FE (0x18CC) 条目 |

### B. 二进制补丁（给用官方预编译版的人）

```powershell
pwsh -File patches/apply-binary-patch.ps1
# 还原
pwsh -File patches/apply-binary-patch.ps1 -Revert
```

不是硬编码偏移，而是按**结构体签名**搜索（4 个 32 位整数依次为
`0x10DE / 0x2702 / 0x10DE / 0x18CB`），并要求**唯一命中**才动手。
改的是第 13 个字节：`0xCB → 0xCC`。

| 项 | 值 |
|---|---|
| 官方 1.1 x64 原始 SHA-256 | `E26AE71162795A8ABCFB90C05C1572A00BA06CA63B886ACA57392A0138963B1E` |
| 补丁后 SHA-256 | `B937CD8C6F6C98F42B966F937C0F163A0F8896DE541C2B7473A88CB16AB35040` |

---

## ⚠️ GPL 合规说明（重要）

OpenRGB 以 **GPL-2.0** 发布。

- **分发本仓库的 `.patch` 文件是安全的**：补丁本身是「改动的描述」，不是完整程序。
- **分发打过补丁的 `OpenRGB.exe` 会触发 GPL-2.0 的源码提供义务**：那份二进制是
  OpenRGB 的衍生作品，你必须同时提供修改后的完整源码（或书面提供获取方式）。
- **本仓库的做法**：`.gitignore` 排除 `assets/OpenRGB/`，二进制由
  `scripts/fetch_openrgb.ps1` 在用户机器上从官方 Release 下载，
  **仓库里只有补丁和下载脚本，不含任何第三方二进制**。

自己的构建请走方式 A（源码补丁 + 自行编译），那样合规且干净。

---

## 诚实的边界：补丁只修「识别」，不修「能不能控」

打上补丁后日志确实会出现：

```
Nvidia NvAPI Illumination GPU found
Registering RGB controller NVIDIA GeForce RTX 4080 SUPER FE
```

但**紧接着** `NvAPI_GPU_ClientIllumZonesGetControl` 返回的
`numIllumZonesControl` 仍然是 **0** —— 驱动没有暴露任何可控灯区，所以依旧改不了颜色。

已排除的可能：

| 假设 | 结论 |
|---|---|
| 权限不足 | 已用管理员身份验证，同样 0 灯区 |
| PawnIO 未装 | 照明走 NvAPI，不走 I2C/SMBus，无关 |
| 结构体版本号过时 | `72012 = 6476 | (1<<16)` 与 `MAKE_NVAPI_VERSION` 编码吻合，驱动未返回不兼容 |
| NVIDIA 官方有灯控入口 | 全量扫描 NVIDIA App / NvContainer 的 dll/exe/js/json/pak，`Illumination` 命中 **0** 处 |

所以这个补丁的价值是：**让 OpenRGB 正确识别该变体**（对未来驱动或其它 0x18CC 设备有用），
而不是让灯立刻能亮。提交上游时请如实描述，不要承诺「修好了灯效」。

---

## 提交上游建议

- 目标仓库：https://github.com/CalcProgrammer1/OpenRGB
- 模板：`.gitlab/issue_templates/New Device.md`（该项目在 GitLab 镜像也有 issue 区）
- 需要附上：
  1. `PCI\VEN_10DE&DEV_2702&SUBSYS_18CC10DE&REV_A1` 完整 PNP ID
  2. `nvidia-smi -q` 中的 VBIOS 与驱动版本
  3. 打补丁前后的 OpenRGB 日志（`--loglevel 6`）
  4. **明确说明 `numIllumZonesControl = 0`**，否则维护者会以为是能控但报错了
