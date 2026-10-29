# 参与贡献 · Contributing

谢谢有兴趣。这个项目是围绕**一台具体机器**写出来的，所以最需要的贡献不是新功能，
而是**「在别的板子上它坏了/能用了」这类实机反馈**。

---

## 一、开 issue 之前

请先按顺序做完这三件事，能省掉一半往返：

1. **跑一遍排错文档** → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
2. **跑诊断脚本**，把输出附上：
   ```powershell
   python scripts/probe_devices.py        # 设备/灯区/灯效结构
   python scripts/diag_chase.py 5         # 流光是否真的在推进
   python scripts/diag_gpu_poll.py        # GPU 遥测是否可用
   ```
3. **收集环境信息**：
   ```powershell
   python --version; pwsh -version
   Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match 'AURA|RGB|LED' } |
     Select-Object FriendlyName, InstanceId
   (Invoke-WebRequest http://127.0.0.1:8099/api/state -UseBasicParsing).Content
   Get-ChildItem "$env:APPDATA\OpenRGB\logs" | Sort-Object LastWriteTime -Desc |
     Select-Object -First 1 | Get-Content
   ```

> 贴日志前**打码**掉序列号、主机名、用户名。

---

## 二、特别欢迎的贡献

| 类型 | 说明 |
|---|---|
| **其它主板的实测报告** | 技嘉 / 微星 / 华擎 / 七彩虹…… 灯区名长什么样、能不能 resize、标定后是否正常 |
| **LED 数/扇的实测数据** | 你风扇的真实灯珠数，用来修正文档里的参考值 |
| **OpenRGB 上游补丁的验证** | 你有 `0x18CC` 之外的变体，或能在别的驱动版本上验证 `patches/` |
| 屏幕同步的性能优化 | 尤其是 4K/超宽屏下的抓屏开销 |
| 翻译 | README 的其它语种版本 |

---

## 三、本地开发

```powershell
git clone https://github.com/HoulinGu0/light-console.git
cd light-console
pwsh -File scripts/fetch_openrgb.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt      # 仅 Pillow，用于重新生成 README 的 GIF
python scripts/server.py
```

**没有构建步骤**：前端就是 `scripts/index.html` 一个文件，改完刷新浏览器即可。

改了后端（`server.py`）需要重启；改了前端不用。

### 目录速查

| 文件 | 职责 |
|---|---|
| `scripts/server.py` | HTTP API + 灯效引擎 + 配置持久化 |
| `scripts/index.html` | 全部前端（HTML/CSS/JS 内联） |
| `scripts/screen_worker.py` | 屏幕取色子进程 |
| `scripts/control.py` | 命令行工具 |
| `docs/DEVELOPMENT.md` | **改代码前必读**，里面是历次踩坑的测量数据 |

---

## 四、四条不能破坏的规矩

这些不是风格偏好，是踩过坑换来的。改坏了会有具体故障：

1. **只有灯效工作线程能碰 SDK socket。**
   HTTP 线程若直接调用 SDK，两条线程并发读写同一 socket 会串包，
   表现为浏览器轮询 `ERR_CONNECTION_TIMED_OUT`。详见 DEVELOPMENT.md §2。

2. **1 秒轮询不得覆盖待提交值。**
   标定滑条是 320 ms 防抖的，轮询必须跳过 `pendingLeds` / `pendingToggle` 里的键，
   否则滑到 32 实际提交 60。

3. **灯珠数偏大或偏小都会出故障，两个方向都要考虑。**
   偏小 → 链路末尾截断（风扇内圈不亮）；偏大 → 动画有空白行程（看起来像卡住）。
   任何跟灯珠数相关的改动，两个方向都要验证。

4. **颜色必须走 CSS 令牌，不要硬编码。**
   项目有白日/黑夜两套主题。新加组件时如果直接写死颜色，浅色主题下必然露馅。
   结构性颜色（输入框、轨道、开关、遮罩……）请加到 `:root` 与
   `[data-theme="light"]` 两处。

---

## 五、代码风格

- Python：标准库优先，**不轻易加依赖**。新增依赖必须先想清楚许可兼容性
  （见 [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md)），因为 GPL-3.0 的约束很实际。
- 注释写**为什么**，不写**是什么**。特别是绕过平台坑的地方，把坑写清楚。
- 前端保持零构建：不引入打包器、不引入框架。单文件 HTML 是刻意的选择。
- 面向用户的文本目前是中文，双语是目标但不是硬门槛。

---

## 六、提交与 PR

提交信息用 Conventional Commits 风格：

```
fix(chase): 亚灯珠插值，消除整数步进的卡顿
feat(ui): 白日/黑夜主题
docs(readme): 补首屏 GIF 与英文摘要
```

PR 请确认：

- [ ] 本地跑过 `python scripts/server.py`，界面无控制台报错
- [ ] 涉及灯珠数的改动，**偏大和偏小两种情况都试过**
- [ ] 涉及颜色的改动，**两套主题都看过**
- [ ] 涉及 SDK 的改动，**仍然只在工作线程里调用**
- [ ] 相关文档已同步（README / docs/*）

---

## 七、贡献的许可

本项目以 [GPL-3.0](LICENSE) 发布。提交 PR 即表示你同意你的贡献以同一许可发布。

---

## 八、行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
