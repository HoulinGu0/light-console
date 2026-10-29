# 开发笔记 · Development Notes

给想改代码的人看的。每条都是实机踩过并验证过的，带有当时的测量数据。

---

## 1. 架构总览

```
浏览器 ──HTTP──> server.py (ThreadingHTTPServer)
                    │
                    │ 只改 Python 侧 settings
                    ▼
              config.json / self.settings
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   灯效工作线程            屏幕取色子进程
   (唯一碰 SDK 的线程)     (screen_worker.py)
         │                     │ 写 JSON
         ▼                     ▼
   OpenRGB SDK :6742  <──── 主线程读取
         │
         ▼
   AURA LED Controller (HID)
```

**核心约束：只有灯效工作线程可以碰 SDK socket。** 见第 2 节。

---

## 2. SDK 必须单线程收敛

HTTP 线程只修改 `self.settings`，**绝不直接调用 SDK**。所有 SDK 操作
（连接、`resize`、`set_mode`、`set_colors`）都在 `LightEngine._loop` 这一个线程里执行。

**为什么**：两条线程在同一个 socket 上并发读写会串包，表现为浏览器轮询
`/api/state` 偶发 `ERR_CONNECTION_TIMED_OUT`。

改完后的并发压测：**40 个并发请求 0 失败**。

---

## 3. OpenRGB 的设备检测是异步的

实测时间线：

| 阶段 | 耗时 |
|---|---|
| SDK 端口就绪 | ~0.2 s |
| 主板控制器注册 | ~0.2 s |
| 显卡控制器注册 | **~1.8 s** |

SDK 端口一就绪就连过去，会**漏掉后注册的控制器**（`device_count` 一直是 1）。

而且 `openrgb-python` 的 `cli.devices` 是构造时建的一次性 list，**不是 property**，
光等待没用，必须显式调用 `cli.update()`（它会重新请求设备数量并补齐列表）。

```python
if not self._settled:
    time.sleep(2.5)
    self._settled = True
    cli.update()              # 关键：不调用的话 devices 永远是 1 个
    devices = cli.devices
```

修复后 `device_count` 正确变成 2。

---

## 4. 选控制器：按能力打分，不认品牌名

早期版本用 `"tuf gaming" in name or "asus" in name` ——那只是为一台机器写的特例，
换台机器可能选到键鼠。

现改为：

```python
排序键 = (灯区数, 灯珠总数)   # 取最大者
```

真正的灯控板灯区最多；键盘鼠标通常只有一个灯区。本机实测：
ASUS `(4, 97)` 胜出，NVIDIA GPU `(0, 0)` 落选。

需要强制指定时用 `config.json` 的 `device` 字段（不区分大小写的子串匹配）。

---

## 5. 灯区键名：按下标对齐，不用字典

`slug(name)` 生成键名，但**不能**用 `{name: key}` 的字典存——同名的多个灯区会互相覆盖
（实测 3 个 `LED Strip` 只剩最后一个）。改用与 `dev.zones` 下标对齐的 list：

```python
keys = unique_zone_keys([z.name for z in zones])   # list
key = self._key_at(i, z.name)
```

另外非 ASCII 名字 slug 化后会变空或纯数字（`"风扇 1"` → `"1"`），这类回退为 `zone_<下标>`。

---

## 6. resize 规则

```
配置值 <= 0                 → 未标定，不动
want == 当前灯珠数           → 不动
当前灯珠数 <= 1             → 不动（单灯区域，如主板标识灯）
其余                        → 尝试 resize，失败只记录不中断
```

早期用的是「名字里含 `addressable` 才 resize」的白名单，既绑死厂商命名，
又因为 `settings.leds` 里混进 `mainboard = 60` 而误 resize 过主板标识灯。
现在改成上面这套通用规则，并在 `apply()` 里也拒绝小于等于 1 的目标值。

---

## 7. 帧循环与抖动

- 目标 **30 fps**，实测稳定 30–31 fps
- 节拍用**绝对时间推进**（`next_t += 1/30`），不用 `elapsed` 自减——后者会让帧率翻倍
- 单帧一次 `set_colors(fast=True)` 合并写入
- 写入延迟基准（`scripts/bench_write.py`）：单次 **0.04 ms**（p99 0.08 ms）
  → 瓶颈根本不在写入，不必为了流畅去堆帧率

### 抖动遥测

`/api/state` 暴露 `dt_p50` / `dt_p95`（最近 90 帧间隔，毫秒）。实测 **33.3 / 33.7 ms**。

判断「卡」是图案问题还是引擎问题，看这两个数就够了。

### 亚灯珠插值（流光）

早期流光用 `head = int(...)`，16 颗灯珠的灯区在 `speed=5` 下每秒只有 **3.3 次**可见位移，
中间 30 帧画的是同一幅图 —— 观感就是"一卡一卡"。

改成浮点位置 + 按距离做平方衰减后，单颗灯珠亮度变成连续渐变：

```
LED0: 220 → 174 → 132 → 97 → 67 → 42 → 23 → 10 → 2 → 0
```

### 一圈耗时与灯珠数解耦

```python
lap  = 24.0 / speed              # speed=1 → 24s/圈, speed=5 → 4.8s/圈
head = (t % lap) / lap * count
```

早期是 `t * speed * 1.4`，一圈时长随灯珠数变化，换灯区尺寸速度会突变。

---

## 8. 屏幕取色：必须独立进程

`mss` 每帧要 BitBlt 并分配约 **19 MB**（3440×1440×4）。在服务线程里跑会持续制造 GC 压力
并占住 GIL，实测让 `/api/state` 偶发 **1057 ms ~ 5 s** 级超时，浏览器直接 `Failed to fetch`。

拆成 `screen_worker.py` 子进程后，主服务只读一个几百字节的 JSON：

| | p50 | p95 | p99 | 失败率 |
|---|---|---|---|---|
| 线程内抓屏 | 1 ms | 22 ms | — | 偶发 5 s 超时 |
| 独立进程 | 1.3 ms | 1.9 ms | 11 ms | 120 次采样 0 失败 |

只在 `screen` 模式下才拉起子进程，切走即 `terminate`。

### ⚠️ Windows 上 `os.kill(pid, 0)` 不是探活

CPython 在 Windows 上会走 `TerminateProcess(handle, 0)` —— **等于把目标进程杀掉**。
用它做父进程存活检测，抓屏子进程一启动就自杀。

正确做法：

```python
h = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
alive = kernel32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
```

---

## 9. GPU 遥测：`nvidia-smi -f` 写不了中文路径

`nvidia-smi --query-gpu=... -f <path>` 在路径含中文时直接 **returncode 255**、文件不生成，
导致 GPU 遥测一直 `ok=False`。与 Python 无关（PowerShell 同样失败）。

复现脚本 `scripts/diag_gpu_poll.py` 用中/英文临时目录对比：

```
纯 ASCII 路径  → returncode=0     成功
含中文的路径   → returncode=255   失败
```

所以运行时固定写 `%TEMP%\light_console_gpu_query.txt`（纯 ASCII），
即便项目被移到中文路径也不会坏。

---

## 10. 前端：三个容易复发的坑

### 模式以 UI 激活按钮为准

`push()` 前从 `.mode[aria-pressed="true"]` **回读**模式，不依赖可变本地变量。
点模式按钮时先乐观切 `aria-pressed` 再 push，否则激活态滞后会把旧模式推上去。

曾出现：颜色对了，但 `mode` 被写成 `off`。

### 轮询不得覆盖待提交值

1 秒一次的 `/api/state` 轮询会把 `state.leds` 写回服务端旧值，冲掉标定滑条
320 ms 防抖窗口里的输入——实测滑到 32 却提交了 60。

修法：`pendingLeds` / `pendingToggle` 两个集合，在提交落地前跳过覆盖。

### 开关曾是单向阀（严重）

旧代码用 `sw.classList.contains("on")` 取反，而 `render()` 的就地分支**从不刷新该 class**，
于是开关永远以为自己"开着"，每次点击都算出 `enabled=false`。

表现：点一次灯区变黑，**之后怎么点都开不回来**，界面还一直显示它是开着的。

修法三点：取反改读权威状态、点击时立即乐观切 class、就地渲染分支补上 `.sw` 与 `.zone.is-off` 同步。

---

## 11. 主题必须令牌化

深色主题里大量颜色是硬编码的（输入框 `#0a0e15`、滑条轨道 `#202834`、开关 `#242c3a`、
遮罩 `rgba(3,5,9,.74)`……），只加一条浅色规则会漏一大片。

做法：把 12 个「结构性颜色」提成 CSS 变量，两套主题各覆盖一次：

```
--field-bg  --track  --switch-off  --switch-knob  --band-base  --overlay
--picker-grad  --picker-line  --mode-active-bg  --line-hover  --edge  --edge-soft
```

再用 `color-scheme: dark|light` 让原生数字输入框与滚动条也跟着变。

主题在 `<head>` 的内联脚本里于首帧前写入 `data-theme`，避免白/黑闪烁。

---

## 12. 调色盘拖动节流

拖动色轮时实时刷灯，但用 60 ms 节流，不会把每一帧 `pointermove` 都打到服务端。

---

## 13. 保留的诊断脚本

| 脚本 | 用途 |
|---|---|
| `diag_chase.py` | 采样控制器里真实灯珠颜色，验证流光光头是否推进/绕回 |
| `bench_write.py` | `set_colors` 单次写入耗时分布 |
| `diag_gpu_poll.py` | 复现 `nvidia-smi` 中文路径失败 |
| `probe_devices.py` | 打印设备/灯区/灯效的完整结构 |

出问题时先跑它们，比看日志快。
