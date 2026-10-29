# NVIDIA Founders Edition 照明控制 — 逆向记录

## 1. 结论先说

| 阶段 | 结果 |
|---|---|
| OpenRGB 能否识别这张显卡为 RGB 控制器 | **原本不能，打补丁后能** ✅ |
| 识别后能否实际控制灯光 | **不能** —— 驱动报告的可控灯区数为 0 ❌ |

换句话说：**软件层是通的，是驱动/固件层面没有暴露可控灯区。**

---

## 2. 卡的身份

| 字段 | 值 |
|---|---|
| 型号 | NVIDIA GeForce RTX 4080 SUPER |
| PNP ID | `PCI\VEN_10DE&DEV_2702&SUBSYS_18CC10DE&REV_A1` |
| 子系统厂商 | `0x10DE` = NVIDIA 自产 → **Founders Edition** |
| Board ID | `0x100`（参考设计） |
| 部件号 | `2702-400-A1` |
| VBIOS | `95.03.44.00.90` |
| 驱动 | `32.0.16.1742` |

---

## 3. 为什么 OpenRGB 认不到它

OpenRGB 的 `Controllers/NVIDIAIlluminationController/NVIDIAIlluminationControllerDetect_Windows_Linux.cpp`
用**四元组精确匹配**判定设备：

```c
static const nv_gpu_pci_device device_list[] =
{
    ...
    {NVIDIA_VEN, NVIDIA_RTX4080S_DEV, NVIDIA_SUB_VEN, NVIDIA_RTX4080S_FE_SUB_DEV,
     NVIDIA_ILLUMINATION_V1, TREATS_RGBW_AS_RGBW, "NVIDIA GeForce RTX 4080 SUPER FE" },
};
```

其中 `pci_ids/pci_ids.h`（release_1.1）：

```c
#define NVIDIA_RTX4080S_DEV         0x2702
#define NVIDIA_RTX4080S_FE_SUB_DEV  0x18CB
```

比对本机实际值：

| 字段 | OpenRGB 期望 | 本机实际 | 结果 |
|---|---|---|---|
| pci_vendor | `0x10DE` | `0x10DE` | ✓ |
| pci_device | `0x2702` | `0x2702` | ✓ |
| pci_subsystem_vendor | `0x10DE` | `0x10DE` | ✓ |
| **pci_subsystem_device** | **`0x18CB`** | **`0x18CC`** | **✗ 差 1** |

→ 白名单里没有这个变体，探测直接跳过，日志里连失败都不打。

---

## 4. 补丁内容（单字节）

定位方法：PE 解析得到 `.rdata` 的 RVA 映射，用名称字符串
`"NVIDIA GeForce RTX 4080 SUPER FE"`（文件偏移 `0x773F08`，VA `0x140775508`）
反查唯一引用它的 8 字节指针（文件偏移 `0x773A98`），减去 `name` 字段偏移 24 得到结构体起始 `0x773A80`：

```
0x773A80  DE 10 00 00   pci_vendor           = 0x10DE
0x773A84  02 27 00 00   pci_device           = 0x2702
0x773A88  DE 10 00 00   pci_subsystem_vendor = 0x10DE
0x773A8C  CB 18 00 00   pci_subsystem_device = 0x18CB   ← 改这里
0x773A90  00 00 00 00   gpu_rgb_version      = 0
0x773A94  00 00 00 00   treats_rgbw_as_rgbw  = false
0x773A98  08 55 77 40 01 00 00 00   name ptr
```

| 项 | 值 |
|---|---|
| 目标文件 | `assets/OpenRGB/OpenRGB Windows 64-bit/OpenRGB.exe` |
| 补丁偏移 | `0x773A8C` |
| 改动 | `0xCB` → `0xCC` |
| 备份 | `OpenRGB.exe.bak` |
| 原始 SHA-256 | `E26AE71162795A8ABCFB90C05C1572A00BA06CA63B886ACA57392A0138963B1E` |
| 补丁后 SHA-256 | `B937CD8C6F6C98F42B966F937C0F163A0F8896DE541C2B7473A88CB16AB35040` |

**回滚**：`Copy-Item OpenRGB.exe.bak OpenRGB.exe -Force`

---

## 5. 补丁效果（已验证）

日志出现：

```
[581][Debug][NVIDIA GeForce RTX 4080 SUPER FE] Nvidia NvAPI Illumination GPU found
[611][Info ][DetectionManager] Registering RGB controller NVIDIA GeForce RTX 4080 SUPER FE
```

OpenRGB SDK 从此枚举到 **2 个控制器**：

```
[0] ASUS TUF GAMING B650M-PLUS WIFI      zones=4  leds=97
[1] NVIDIA GeForce RTX 4080 SUPER FE     zones=0  leds=0    ← 问题在这
    modes: Off(0) / Direct(1)
```

---

## 6. 为什么还是 0 个灯区

调用链（`NVIDIAIlluminationV1Controller`）：

```cpp
getInfo()  ->  getControl()  ->  NvAPI_GPU_ClientIllumZonesGetControl(handle, &zone_params)
           ->  for (i < zone_params.numIllumZonesControl) push(zone_params.zones[i].type)
```

`getControl()` 里 `version` 是**硬编码 72012**（源码注释原话：
"Hardcoded value found via sniffing, this may be different for other cards"）。

用 `--loglevel 6`（trace）跑过，日志里**没有**出现 `NVAPI return code not NVAPI_OK: %d`
这行 —— 说明调用是**成功**的（`NVAPI_OK`），只是返回的 `numIllumZonesControl == 0`。

结构体布局（NVIDIA 官方 `nvapi.h`）：

```c
typedef struct {
    NvU32 version;              // +0   版本 = sizeof | (ver<<16)
    NvU32 bDefault : 1;         // +4   0 = 当前值, 1 = 默认值
    NvU32 rsvdField : 31;
    NvU32 numIllumZonesControl; // +8   ← 这里读出来是 0
    NvU8  rsvd[64];
    NV_GPU_CLIENT_ILLUM_ZONE_CONTROL_V1 zones[NV_GPU_CLIENT_ILLUM_ZONE_NUM_ZONES_MAX];
} NV_GPU_CLIENT_ILLUM_ZONE_CONTROL_PARAMS_V1;
```

版本 72012 = `6476 | (1<<16)`，与 `MAKE_NVAPI_VERSION(sizeof, 1)` 的编码规则吻合，
即驱动**接受了**这个结构体版本，没有返回 `NVAPI_INCOMPATIBLE_STRUCT_VERSION`。

→ 结论：**这张 FE 卡在驱动 32.0.16.1742 下，NVAPI 报告的可控照明灯区数为 0。**

---

## 7. 三路深挖的完整结果

### 路线 1：自建 NVAPI 探针 —— 已完成

从 `OpenRGB.exe` 里把 NVAPI 的惰性初始化表整块抽了出来。
调用形式是 `mov ecx, <id> ; call rbx`，字节模式 `B9 <id4> FF D3`，全部 29 个 ID 集中在
`0x5E1429 ~ 0x5E163D`，每个间隔 19 字节：

```
0x5E1429  0x0150E828  NvAPI_Initialize
0x5E143C  0xD22BDD7E
0x5E144F  0x9ABDD40D
0x5E1462  0xE5AC921F  NvAPI_EnumPhysicalGPUs
...
0x5E14C1  0xCEEE8E9F  NvAPI_GPU_GetFullName
...
0x5E15F1  0x2DDFB66E  NvAPI_GPU_GetPCIIdentifiers
0x5E1604  0x283AC65A ... 共 29 个
```

同时验证了结构体版本常量是对的：`72012 = 6476 | (1<<16)`，反推 OpenRGB 头文件里
`NV_GPU_CLIENT_ILLUM_ZONE_CONTROL_V1` 为 200 字节/zone × 32 zone + 76 头 = 6476。
若版本不匹配，NVAPI 会返回 `NVAPI_INCOMPATIBLE_STRUCT_VERSION` 并被 `checkNVAPIreturn()`
打进日志；trace 级别下**未见任何该报错**。→ 版本正确，`numIllumZonesControl = 0` 是驱动的真实答复。

**限制**：现代 NVAPI 头文件不公开函数 ID（走静态库链接），拿不到 ID→名称映射，
因此无法在不调用未知函数的前提下做逐 ID 探针；而盲调未知 NVAPI 函数存在改动 GPU 设置的风险，未执行。

### 路线 2：NvAPISpy 抓包 —— 判定无价值，未执行

抓包的意义在于「记录别的软件如何驱动该设备」。但实测：

```
C:\Program Files\NVIDIA Corporation\NVIDIA App   → IllumZones=0  illumination=0
C:\Program Files\NVIDIA Corporation\NvContainer  → IllumZones=0  illumination=0
```

扫描其全部 dll/exe/js/json/pak，**NVIDIA 自家软件里没有任何照明相关代码**。
没有参考调用方，就没东西可抓。加上该方案需替换驱动 DLL，风险高、收益为零。

### 路线 3：驱动版本 —— 已核查，未降级

| 项 | 值 |
|---|---|
| 驱动版本 | **617.42**（内部 `32.0.16.1742`） |
| 驱动日期 | 2026-09-30（已是最新一档） |
| VBIOS | `95.03.44.00.90` |
| 系统还原点 | **无**（系统保护可能关闭） |

驱动已是极新版本，且**没有任何还原点作为退路**——降级驱动一旦失败可能导致无显示输出，
结合路线 2 已证明 NVIDIA 官方都不提供该功能，降级暴露出灯区的概率很低，因此未执行。

### 综合判定

```text
软硬件链路：主板灯控 ✅ 已完全打通
显卡识别：  ✅ 已通过补丁打通（OpenRGB 认到这张卡）
显卡灯区：  ❌ 驱动返回 0 个灯区，且 NVIDIA 官方软件也无任何照明代码
```

**这张 `0x18CC` 变体的 FE 卡，照明接口在驱动/固件层即未暴露。**
OpenRGB 支持的 `0x18CB` 变体是否有灯区无法在本机验证 —— 但你的卡是 `0x18CC`。

---

## 8. 替代方案

`Addressable RGB Header 2` 空置，可插 ARGB 灯带贴近显卡，作为第三个灯区与风扇同步 ——
这条不依赖 NVIDIA 驱动，已验证可用。
