# 配置参考 · Configuration

配置文件是项目根目录的 **`config.json`**，由首次运行向导生成。
所有改动都可以直接在网页上做，改完即时落盘；手工编辑该文件后需重启服务生效。

```jsonc
{
  "setup_done": true,
  "mode": "static",
  "color": "#00A8FF",
  "brightness": 100,
  "speed": 5,
  "device": "",
  "zones": {
    "aura_mainboard": { "enabled": true, "color": "#FFFFFF" },
    "addressable_rgb_header_1": { "enabled": true, "color": "#00A8FF" }
  },
  "leds": {
    "aura_mainboard": 1,
    "addressable_rgb_header_1": 24
  }
}
```

---

## 顶层字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `setup_done` | bool | `false` | 是否已完成首次向导。设为 `false` 后下次打开页面会自动弹向导。 |
| `mode` | string | `static` | 灯效，取值见下表。 |
| `color` | string | `#00A8FF` | 主色，`#RRGGBB`。用于静态灯效、呼吸/流光的基色，以及未单独配色的灯区。 |
| `brightness` | int | `100` | 全局亮度 `0`–`100`，软件侧缩放 RGB，不依赖灯效的亮度字段。 |
| `speed` | int | `5` | 动画速度 `1`–`10`。 |
| `device` | string | `""` | 空 = 按能力自动挑选控制器；填名称片段（不区分大小写）则强制匹配该控制器。 |
| `zones` | object | `{}` | 逐灯区配置，键为灯区 slug。启动时按实际灯区自动补全。 |
| `leds` | object | `{}` | 逐灯区灯珠数。`0`（或缺省）= 尚未标定，不会触发 resize。 |

### `mode` 取值

| 值 | 名称 | 说明 |
|---|---|---|
| `static` | 静态 | 每个灯区用自己配置的 `color` 常亮 |
| `rainbow` | 彩虹 | 色相沿灯链流动 |
| `breathe` | 呼吸 | 整体明暗起伏 |
| `chase` | 流光 | 彗尾追逐，一圈耗时 = `24 / speed` 秒 |
| `wave` | 波浪 | 色波推进 |
| `gpu` | GPU 联动 | 温度 → 色相（30°C 蓝 → 75°C 红），占用 → 亮度（30% → 100%） |
| `screen` | 屏幕同步 | 屏幕横向 16 段取色映射到灯珠 |
| `off` | 关闭 | 调用控制器的 Off 模式 |

---

## 灯区键名是怎么来的

**不写死任何厂商命名。** 键名是灯区名经过 slug 化得到的：

```
"Aura Mainboard"            → aura_mainboard
"Addressable RGB Header 1"  → addressable_rgb_header_1
"LED Strip" ×3              → led_strip / led_strip_2 / led_strip_3
"主板灯区" / "风扇 1"        → zone_0 / zone_1        （非 ASCII 回退为序号）
```

规则细节：

- 转小写，非 `[a-z0-9]` 字符压成单个 `_`，去掉首尾 `_`
- 结果为纯数字或空 → 回退 `zone_<下标>`
- 同名灯区按下标追加 `_2`、`_3`

键名与设备灯区**按下标配对**（不是按名字查字典），所以重名灯区不会互相覆盖。

---

## 旧配置迁移

早期版本用的是写死的 `mainboard` / `header1` / `header2` / `header3`。加载时会自动改名：

| 旧键 | 新键 |
|---|---|
| `mainboard` | `aura_mainboard` |
| `header1` | `addressable_rgb_header_1` |
| `header2` | `addressable_rgb_header_2` |
| `header3` | `addressable_rgb_header_3` |

同时：

- 旧位置的 `runtime/ui_settings.json` 会被自动迁移到根目录 `config.json`，
  并把 `setup_done` 置为 `true`（避免迁移后又被向导覆盖一遍）
- `leds` 里遗留的 `mainboard = 60` 之类脏键会被清掉

迁移只影响这四个已知键，其它键原样保留。

---

## 多控制器：如何指定

一台机器上可能有多个 OpenRGB 控制器（主板、显卡、内存、键鼠……）。默认策略是
**按能力打分挑选**：

```
排序键 = (灯区数, 灯珠总数)   取最大者
```

真正的灯控板通常灯区最多；键盘鼠标往往只有一个灯区，因此不会抢走控制权。

需要强制指定时，把 `device` 设成目标控制器名字的一段：

```jsonc
{ "device": "B650M" }
```

匹配是**不区分大小写的子串匹配**，命中第一个即用。没命中会打一行警告并回退自动选择。

> 页面顶部设备胶囊显示的 `· 4 区 / 97 灯` 和悬停提示可以看到实际选中的是谁、
> 以及本轮一共枚举到几个控制器。

---

## 相关文件

| 路径 | 是否入库 | 说明 |
|---|---|---|
| `config.json` | 否（已 gitignore） | 你的配置 |
| `runtime/` | 否 | 运行时产物 |
| `assets/OpenRGB/` | 否 | 由 `scripts/fetch_openrgb.ps1` 下载 |
| `%TEMP%\light_console_bands.json` | — | 屏幕取色子进程写出的中间结果 |
| `%TEMP%\light_console_gpu_query.txt` | — | `nvidia-smi` 临时输出（必须放 ASCII 路径） |
| `%APPDATA%\OpenRGB\logs\` | — | OpenRGB 自己的日志，排查设备识别问题时看这里 |
