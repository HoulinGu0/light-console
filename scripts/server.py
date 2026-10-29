# -*- coding: utf-8 -*-
"""
机箱灯光控制台 —— 本地 Web UI

架构要点:
    HTTP 线程只读写 Python 侧的 settings, **绝不直接碰 SDK socket**。
    所有 OpenRGB SDK 调用(建连接 / resize / set_mode / 推帧)统一由灯效工作线程执行,
    避免两条线程在同一 socket 上并发读写导致协议流串包。

依赖: openrgb-python (已安装), OpenRGB.exe (已解压到 ../OpenRGB/)

启动:
    python server.py                # 自动拉起 OpenRGB 服务端 + 打开浏览器
    python server.py --no-browser
"""
from __future__ import annotations

import colorsys
import json
import math
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNTIME = os.path.join(ROOT, "runtime")


def find_openrgb_exe():
    """在几种可能的布局里定位 OpenRGB.exe，避免目录搬迁后失效。"""
    candidates = []
    for base in (HERE, ROOT):
        candidates += [
            os.path.join(base, "OpenRGB", "OpenRGB Windows 64-bit", "OpenRGB.exe"),
            os.path.join(base, "assets", "OpenRGB", "OpenRGB Windows 64-bit", "OpenRGB.exe"),
            os.path.join(base, "OpenRGB.exe"),
        ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        if "OpenRGB.exe" in filenames:
            return os.path.join(dirpath, "OpenRGB.exe")
    return None


OPENRGB_EXE = find_openrgb_exe()
os.makedirs(RUNTIME, exist_ok=True)
SETTINGS_FILE = os.path.join(ROOT, "config.json")
LEGACY_SETTINGS_FILE = os.path.join(RUNTIME, "ui_settings.json")

SDK_HOST = "127.0.0.1"
SDK_PORT = 6742
WEB_PORT = int(os.environ.get("LIGHT_WEB_PORT", "8099"))
FPS_TARGET = 30.0
NVSMI = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
GPU_POLL_INTERVAL = 1.0
SCREEN_BANDS = 16          # 屏幕横向切段数，映射到灯珠
SCREEN_FPS = 8.0           # 抓屏频率（仅 screen 模式下生效）
SCREEN_STRIDE = 8          # 抓屏后隔点采样，降低 numpy 开销

# 旧版配置里写死的键 -> 新的通用 slug，仅用于迁移，不再参与判断逻辑
LEGACY_ZONE_KEYS = {
    "mainboard": "aura_mainboard",
    "header1": "addressable_rgb_header_1",
    "header2": "addressable_rgb_header_2",
    "header3": "addressable_rgb_header_3",
}

DEFAULT_SETTINGS = {
    "setup_done": False,          # 首次运行向导是否已完成
    "mode": "static",
    "color": "#00A8FF",
    "brightness": 100,
    "speed": 5,
    "device": "",                 # 留空 = 自动挑选；填子串则强制匹配该控制器
    "zones": {},                  # 按实际灯区自动生成，不再预置 header1/2/3
    "leds": {},                   # 0 表示「未标定」，非 0 才会 resize
}


# ------------------------------------------------------------------ 工具
def zone_key(name: str, index: int = 0) -> str:
    """把灯区名转成稳定的配置键。不依赖任何厂商命名，任何控制器都能用。"""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    # 纯数字（如「风扇 1」被剥离成 "1"）不可用作语义键，回退到序号
    if not slug or slug.isdigit():
        slug = "zone_%d" % index
    return slug


def unique_zone_keys(names):
    """返回与 names **按下标对齐** 的键列表。

    刻意不用 dict：同名的多个灯区会在字典里互相覆盖
    （实测 3 个 'LED Strip' 只剩最后一个），按下标才安全。
    """
    seen = {}
    keys = []
    for i, name in enumerate(names):
        base = zone_key(name, i)
        n = seen.get(base, 0) + 1
        seen[base] = n
        keys.append(base if n == 1 else "%s_%d" % (base, n))
    return keys


def hex_to_rgb(value):
    h = str(value or "#000000").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return 0, 0, 0
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0, 0, 0


def sdk_port_open(timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((SDK_HOST, SDK_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_openrgb_server() -> bool:
    if sdk_port_open():
        return True
    if not OPENRGB_EXE or not os.path.exists(OPENRGB_EXE):
        print("[!] 找不到 OpenRGB.exe，请把 OpenRGB 便携版解压到 assets/OpenRGB/")
        return False
    print("[*] 启动 OpenRGB 服务端 ...")
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [OPENRGB_EXE, "--server", "--noautoconnect", "--startminimized"],
        cwd=os.path.dirname(OPENRGB_EXE),
        creationflags=flags,
        close_fds=True,
    )
    for _ in range(60):
        time.sleep(0.5)
        if sdk_port_open():
            print("[+] OpenRGB SDK 已就绪")
            return True
    print("[!] OpenRGB SDK 启动超时")
    return False


# ------------------------------------------------------------------ 引擎
class LightEngine:
    """settings 由 HTTP 线程修改；SDK 只由本类的工作线程触碰。"""

    def __init__(self):
        self.lock = threading.RLock()
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.load_settings()
        self._sanitize()
        self.cli = None
        self.dev = None
        self.device_count = 0
        self.device_vendor = ""
        self.zone_keys = {}          # 灯区名 -> 通用配置键
        self._settled = False
        self.running = True
        self.last_error = ""
        self.frames = 0
        self.fps = 0.0
        self.dt_hist = []          # 最近若干帧间隔，用于抖动诊断
        self.last_frame_t = None
        self.gpu = {"ok": False, "util": 0, "temp": 0, "power": 0.0}
        self.screen = {"ok": False, "bands": [], "error": ""}
        threading.Thread(target=self._gpu_loop, name="gpu-poll", daemon=True).start()
        threading.Thread(target=self._screen_loop, name="screen-poll", daemon=True).start()
        self.need_resize = True
        self.applied_mode = None
        self.thread = threading.Thread(target=self._loop, name="light-engine", daemon=True)
        self.thread.start()

    # -------------------------------------------------- 持久化
    def load_settings(self):
        """配置写在项目根目录的 config.json。
        若不存在但存在旧版 runtime/ui_settings.json，则迁移过来并标记已初始化。"""
        path = SETTINGS_FILE
        migrated = False
        if not os.path.exists(path) and os.path.exists(LEGACY_SETTINGS_FILE):
            path = LEGACY_SETTINGS_FILE
            migrated = True
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
            for k, v in saved.items():
                if k == "zones" and isinstance(v, dict):
                    for zk, zv in v.items():
                        self.settings["zones"].setdefault(zk, {}).update(zv)
                elif k == "leds" and isinstance(v, dict):
                    self.settings["leds"].update(v)
                else:
                    self.settings[k] = v
            if migrated:
                self.settings["setup_done"] = True
                print("[*] 已从旧配置迁移: %s -> %s" % (LEGACY_SETTINGS_FILE, SETTINGS_FILE))
                self.save_settings()
        except Exception:  # noqa: BLE001
            pass

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.settings, fh, ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001
            pass

    def _sanitize(self):
        """把旧配置里写死的 header1/2/3、mainboard 迁移成通用 slug 键。"""
        for section in ("zones", "leds"):
            data = self.settings.get(section)
            if not isinstance(data, dict):
                continue
            for legacy, slug in LEGACY_ZONE_KEYS.items():
                if legacy in data:
                    val = data.pop(legacy)
                    data.setdefault(slug, val)
        self.settings["leds"].pop("mainboard", None)

    # -------------------------------------------------- GPU 轮询（独立线程）
    def _gpu_loop(self):
        """每秒读一次显卡温度/占用/功耗。
        注意：nvidia-smi 的 -f 参数无法写入含中文的路径（实测 returncode 255、文件不生成），
        所以临时文件固定放在纯 ASCII 的临时目录里 —— 即使项目被移到中文路径也不会坏。"""
        tmpf = os.path.join(tempfile.gettempdir(), "light_console_gpu_query.txt")
        flags = 0x08000000  # CREATE_NO_WINDOW
        while self.running:
            try:
                if not os.path.exists(NVSMI):
                    raise FileNotFoundError(NVSMI)
                try:
                    if os.path.exists(tmpf):
                        os.remove(tmpf)
                except OSError:
                    pass
                subprocess.run(
                    [NVSMI,
                     "--query-gpu=utilization.gpu,temperature.gpu,power.draw",
                     "--format=csv,noheader,nounits",
                     "-f", tmpf],
                    timeout=5, creationflags=flags,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(tmpf):
                    with open(tmpf, encoding="utf-8", errors="ignore") as fh:
                        line = fh.read().strip().splitlines()[0]
                    parts = [p.strip() for p in line.split(",")]
                    self.gpu = {
                        "ok": True,
                        "util": int(float(parts[0])),
                        "temp": int(float(parts[1])),
                        "power": round(float(parts[2]), 1),
                    }
            except Exception:  # noqa: BLE001
                self.gpu = {"ok": False, "util": 0, "temp": 0, "power": 0.0}
            time.sleep(GPU_POLL_INTERVAL)

    # -------------------------------------------------- 屏幕取色（监护独立进程）
    def _screen_loop(self):
        """守护 screen_worker.py 子进程。

        抓屏放在独立进程里，理由见 screen_worker.py 顶部注释：
        每帧 19MB 的位图分配会制造 GC 停顿并占住 GIL，把 HTTP 线程拖到 5 秒级超时。
        本方法只负责按模式启停子进程，并读取它写出的几百字节 JSON。
        """
        outfile = os.path.join(tempfile.gettempdir(), "light_console_bands.json")
        worker = os.path.join(HERE, "screen_worker.py")
        proc = None
        last_mtime = 0.0
        flags = 0x08000000  # CREATE_NO_WINDOW

        def stop_worker():
            nonlocal proc
            if proc is None:
                return
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            proc = None

        while self.running:
            try:
                active = self.settings.get("mode") == "screen"
                if active and proc is None:
                    try:
                        if os.path.exists(outfile):
                            os.remove(outfile)
                    except OSError:
                        pass
                    last_mtime = 0.0
                    proc = subprocess.Popen(
                        [sys.executable, worker,
                         "--bands", str(SCREEN_BANDS),
                         "--fps", str(SCREEN_FPS),
                         "--stride", str(SCREEN_STRIDE),
                         "--out", outfile,
                         "--parent-pid", str(os.getpid())],
                        creationflags=flags,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.screen = {"ok": False, "bands": [], "error": "启动抓屏进程…"}
                elif not active and proc is not None:
                    stop_worker()
                    self.screen = {"ok": False, "bands": [], "error": ""}

                if proc is not None and proc.poll() is not None:
                    proc = None

                if proc is not None and os.path.exists(outfile):
                    mt = os.path.getmtime(outfile)
                    if mt != last_mtime:
                        last_mtime = mt
                        with open(outfile, encoding="utf-8") as fh:
                            data = json.load(fh)
                        self.screen = {
                            "ok": bool(data.get("ok")),
                            "bands": [tuple(b) for b in data.get("bands", [])],
                            "error": data.get("error", ""),
                        }
            except Exception as exc:  # noqa: BLE001
                self.screen = {"ok": False, "bands": [], "error": str(exc)}
            time.sleep(0.15)

        stop_worker()

    # -------------------------------------------------- 仅工作线程调用
    @staticmethod
    def _score_device(dev):
        """给控制器打分：灯区数优先，其次灯珠总数。
        真正的灯控（主板/一体式灯控）通常灯区最多；键盘鼠标只有一个灯区。"""
        try:
            zones = list(dev.zones)
        except Exception:  # noqa: BLE001
            return (0, 0)
        return (len(zones), sum(len(z.leds) for z in zones))

    def _pick_device(self, devices):
        """选控制器。不再按 'asus'/'tuf' 名字硬匹配，改为按能力打分；
        需要指定时可在设置里写 `device`（子串匹配，优先于自动选择）。"""
        want = str(self.settings.get("device") or "").strip().lower()
        if want:
            for d in devices:
                if want in d.name.lower():
                    print("[+] 按设置指定控制器: %s" % d.name)
                    return d
            print("[!] 设置里的 device=%r 没匹配到任何控制器，回退自动选择" % want)
        best, best_key = None, (-1, -1)
        for d in devices:
            key = self._score_device(d)
            if key > best_key:
                best, best_key = d, key
        return best or devices[0]

    def _key_at(self, index, name):
        """取下标对应的配置键；键表与设备灯区不同步时回退为即时计算。"""
        try:
            return self.zone_keys[index]
        except (IndexError, TypeError):
            return zone_key(name, index)

    def _refresh_zones(self):
        """按当前设备的实际灯区重建键表，并为新灯区补上配置项。
        不预设任何厂商命名 —— 有几个灯区就配几个。"""
        try:
            zones = list(self.dev.zones)
        except Exception:  # noqa: BLE001
            return
        self.zone_keys = unique_zone_keys([z.name for z in zones])
        with self.lock:
            for i, z in enumerate(zones):
                key = self._key_at(i, z.name)
                cfg = self.settings["zones"].setdefault(key, {})
                cfg.setdefault("color", self.settings.get("color", "#00A8FF"))
                # 默认全开；未接灯的排针由用户在向导里关掉
                cfg.setdefault("enabled", True)
                if key not in self.settings["leds"]:
                    # 设备已报告实际灯珠数就直接采纳；0 表示尚未标定
                    self.settings["leds"][key] = len(z.leds)
        self.save_settings()

    def _connect(self):
        if not ensure_openrgb_server():
            raise RuntimeError("OpenRGB SDK 不可用")
        cli = OpenRGBClient(address=SDK_HOST, port=SDK_PORT, name="light-console")
        devices = cli.devices
        if not devices:
            raise RuntimeError("OpenRGB 未检测到 RGB 控制器")
        # OpenRGB 的设备检测是异步的：实测主板 ~0.2s 注册、显卡 ~1.8s 才注册。
        # SDK 端口一就绪就连过去会漏掉后注册的控制器。
        # 注意 openrgb-python 的 `devices` 是构造时建的一次性列表，不是属性，
        # 想拿到新设备必须显式调 update()（它会重新请求设备数量并补齐列表）。
        if not self._settled:
            time.sleep(2.5)
            self._settled = True
            try:
                cli.update()
            except Exception:  # noqa: BLE001
                pass
            devices = cli.devices or devices
        dev = self._pick_device(devices)
        self.cli, self.dev = cli, dev
        self.applied_mode = None
        self.device_count = len(devices)
        self.device_vendor = (getattr(dev, "vendor", "") or "").strip()
        zc, lc = self._score_device(dev)
        print("[+] 已连接控制器: %s（%d 个灯区 / %d 颗灯珠；共枚举到 %d 个控制器）"
              % (dev.name, zc, lc, self.device_count))
        self._refresh_zones()

    def _apply_resize(self):
        """按配置里的灯珠数调整灯区尺寸。

        不再按 'addressable' 之类的厂商命名白名单判断，改为通用规则：
          - 配置值为 0 或未设置 -> 视为「未标定」，不动
          - 当前已是目标值 -> 不动
          - 当前只有 1 颗灯的灯区 -> 不动（单灯区域如主板标识灯，resize 没有意义，早期据此出过 bug）
        其余一律尝试 resize，失败只记录不中断。
        """
        with self.lock:
            targets = dict(self.settings["leds"])
        for i, z in enumerate(self.dev.zones):
            key = self._key_at(i, z.name)
            want = int(targets.get(key, 0) or 0)
            if want <= 0 or want == len(z.leds):
                continue
            if len(z.leds) <= 1:
                continue
            try:
                z.resize(want)
            except Exception as exc:  # noqa: BLE001
                print("[!] 调整灯区 %s 到 %d 颗失败: %s" % (z.name, want, exc))

    def _zone_colors(self, key, count, t, mode, base_rgb, speed):
        if count <= 0:
            return []
        zone_cfg = self.settings["zones"].get(key, {})
        if not zone_cfg.get("enabled", True):
            return [(0, 0, 0)] * count

        if mode == "static":
            return [hex_to_rgb(zone_cfg.get("color", self.settings["color"]))] * count

        if mode == "rainbow":
            out = []
            for i in range(count):
                hue = (i / max(1, count) + t * (speed * 0.05)) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                out.append((int(r * 255), int(g * 255), int(b * 255)))
            return out

        if mode == "breathe":
            k = 0.15 + 0.85 * (0.5 + 0.5 * math.sin(t * (speed * 0.35)))
            return [(int(base_rgb[0] * k), int(base_rgb[1] * k), int(base_rgb[2] * k))] * count

        if mode == "chase":
            # 以「一圈耗时」为基准，与灯珠数量无关，速度手感一致
            lap = 24.0 / max(0.5, speed)          # speed=1 -> 24s/圈, speed=10 -> 2.4s/圈
            # 光头用浮点位置 + 相邻灯珠亮度插值 = 亚灯珠级平滑，避免整数步进的卡顿
            pos = ((t % lap) / lap) * count
            tail = max(3.0, count / 5.0)          # 拖尾长度随灯珠数缩放
            out = []
            for i in range(count):
                d = (pos - i) % count             # 沿环路到光头的距离
                if d < tail:
                    f = 1.0 - (d / tail)
                    f = f * f                     # 平方衰减，更像彗尾
                    out.append((int(base_rgb[0] * f), int(base_rgb[1] * f), int(base_rgb[2] * f)))
                else:
                    out.append((0, 0, 0))
            return out

        if mode == "wave":
            out = []
            for i in range(count):
                hue = (i / max(1, count) * 0.5 + t * (speed * 0.08)) % 1.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.95, 1.0)
                out.append((int(r * 255), int(g * 255), int(b * 255)))
            return out

        if mode == "gpu":
            # 显卡联动：温度决定色相（凉蓝 -> 烫红），占用决定亮度
            gg = self.gpu
            if not gg.get("ok"):
                return [hex_to_rgb(zone_cfg.get("color", self.settings["color"]))] * count
            t2 = max(0.0, min(1.0, (float(gg["temp"]) - 30.0) / 45.0))   # 30C..75C
            hue = (240.0 / 360.0) * (1.0 - t2)                           # 240 蓝 -> 0 红
            r, g2, b = colorsys.hsv_to_rgb(hue, 0.92, 1.0)
            k = 0.30 + 0.70 * max(0.0, min(1.0, float(gg["util"]) / 100.0))
            base = (int(r * 255 * k), int(g2 * 255 * k), int(b * 255 * k))
            return [base] * count

        if mode == "screen":
            # 屏幕取色：把横向 16 段颜色映射到该灯区的灯珠上
            sc = self.screen
            bands = sc.get("bands") if sc.get("ok") else None
            if not bands:
                return [hex_to_rgb(zone_cfg.get("color", self.settings["color"]))] * count
            n = len(bands)
            out = []
            for i in range(count):
                bi = 0 if count <= 1 else int(i / (count - 1) * (n - 1))
                out.append(bands[max(0, min(n - 1, bi))])
            return out

        return [hex_to_rgb(zone_cfg.get("color", self.settings["color"]))] * count

    def _build_frame(self, t):
        mode = self.settings["mode"]
        speed = float(self.settings["speed"])
        base_rgb = hex_to_rgb(self.settings["color"])
        bright = max(0.0, min(1.0, float(self.settings["brightness"]) / 100.0))
        colors = []
        for i, z in enumerate(self.dev.zones):
            for r, g, b in self._zone_colors(self._key_at(i, z.name),
                                             len(z.leds), t, mode, base_rgb, speed):
                colors.append(RGBColor(int(r * bright), int(g * bright), int(b * bright)))
        return colors

    # -------------------------------------------------- 工作线程主循环
    def _loop(self):
        t0 = time.time()
        next_t = time.time()
        window = []
        while self.running:
            try:
                if self.dev is None:
                    self._connect()
                if self.need_resize:
                    self.need_resize = False
                    self._apply_resize()
                    self.applied_mode = None

                mode = self.settings["mode"]

                if mode == "off":
                    if self.applied_mode != "off":
                        self.dev.set_mode("Off", force=True)
                        self.applied_mode = "off"
                    self.last_error = ""
                    time.sleep(0.25)
                    next_t = time.time()
                    continue

                if self.applied_mode != mode:
                    self.dev.set_mode("Direct", force=True)
                    self.applied_mode = mode

                frame = self._build_frame(time.time() - t0)
                if frame:
                    self.dev.set_colors(frame, fast=True)
                    self.frames += 1

                now = time.time()
                window.append(now)
                window = [x for x in window if now - x <= 1.0]
                self.fps = len(window)
                self.last_error = ""

                # 帧间隔采集：p95 明显超过 1/FPS_TARGET 就说明引擎在掉帧
                if self.last_frame_t is not None:
                    self.dt_hist.append((now - self.last_frame_t) * 1000.0)
                    if len(self.dt_hist) > 90:
                        del self.dt_hist[0]
                self.last_frame_t = now

                next_t += 1.0 / FPS_TARGET
                delay = next_t - time.time()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.time()
            except Exception as exc:  # noqa: BLE001
                self.last_error = "%s: %s" % (type(exc).__name__, exc)
                print("[!] 引擎异常，准备重连：%s" % self.last_error)
                try:
                    if self.cli is not None:
                        self.cli.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                self.dev = None
                self.cli = None
                self.applied_mode = None
                self.need_resize = True
                self.fps = 0
                time.sleep(2.0)

    # -------------------------------------------------- 供 HTTP 线程调用（仅碰 settings）
    def state(self):
        zones = []
        dev = self.dev
        if dev is not None:
            try:
                for i, z in enumerate(dev.zones):
                    key = self._key_at(i, z.name)
                    cfg = self.settings["zones"].get(key, {})
                    zones.append(
                        {
                            "key": key,
                            "name": z.name,
                            "leds": len(z.leds),
                            "target_leds": int(self.settings["leds"].get(key, 0) or 0),
                            "resizable": len(z.leds) > 1,
                            "enabled": bool(cfg.get("enabled", True)),
                            "color": cfg.get("color", self.settings["color"]),
                        }
                    )
            except Exception:  # noqa: BLE001
                zones = []
        return {
            "device": dev.name if dev is not None else None,
            "device_vendor": self.device_vendor,
            "device_zones": len(dev.zones) if dev is not None else 0,
            "device_leds": (sum(len(z.leds) for z in dev.zones) if dev is not None else 0),
            "device_count": self.device_count,
            "connected": dev is not None,
            "setup_done": bool(self.settings.get("setup_done")),
            "mode": self.settings["mode"],
            "color": self.settings["color"],
            "brightness": self.settings["brightness"],
            "speed": self.settings["speed"],
            "leds": dict(self.settings["leds"]),
            "zones": zones,
            "fps": self.fps,
            "frames": self.frames,
            "gpu": dict(self.gpu),
            "screen": {
                "ok": bool(self.screen.get("ok")),
                "bands": ["#%02X%02X%02X" % tuple(b) for b in self.screen.get("bands", [])],
                "error": self.screen.get("error", ""),
            },
            "dt_p50": round(self._pct(0.50), 1),
            "dt_p95": round(self._pct(0.95), 1),
            "error": self.last_error,
        }

    def _pct(self, q):
        hist = sorted(self.dt_hist)
        if not hist:
            return 0.0
        return hist[min(len(hist) - 1, int(len(hist) * q))]

    def apply(self, payload):
        """只更新设置，不下发 SDK；工作线程下一帧自然生效。"""
        with self.lock:
            for key in ("mode", "color", "brightness", "speed"):
                if key in payload:
                    self.settings[key] = payload[key]
            if isinstance(payload.get("zones"), dict):
                for zk, zv in payload["zones"].items():
                    if isinstance(zv, dict):
                        self.settings["zones"].setdefault(zk, {}).update(zv)
            if isinstance(payload.get("leds"), dict):
                for zk, zv in payload["leds"].items():
                    try:
                        n = max(0, min(400, int(zv)))
                    except (TypeError, ValueError):
                        continue
                    if self.settings["leds"].get(zk) != n:
                        self.settings["leds"][zk] = n
                        self.need_resize = True
        self.save_settings()
        return self.state()

    def snapshot(self):
        with self.lock:
            payload = json.loads(json.dumps(self.settings))
        path = os.path.join(RUNTIME, "ui_snapshot.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return {"ok": True, "message": "已保存当前配置快照", "path": path}

    def finish_setup(self):
        """首次运行向导完成：落盘 setup_done，之后不再自动弹出。"""
        with self.lock:
            self.settings["setup_done"] = True
        self.save_settings()
        return {"ok": True, "config": SETTINGS_FILE}


ENGINE = None


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "LightConsole/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            self._json(ENGINE.state())
            return
        self._json({"ok": False, "message": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._json({"ok": False, "message": "bad json"}, 400)
            return
        try:
            if path == "/api/apply":
                self._json({"ok": True, "state": ENGINE.apply(payload)})
                return
            if path == "/api/snapshot":
                self._json(ENGINE.snapshot())
                return
            if path == "/api/setup/done":
                self._json(dict(ENGINE.finish_setup(), state=ENGINE.state()))
                return
            if path == "/api/reset":
                self._json({"ok": True, "state": ENGINE.apply(json.loads(json.dumps(DEFAULT_SETTINGS)))})
                return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json({"ok": False, "message": str(exc)}, 500)
            return
        self._json({"ok": False, "message": "not found"}, 404)


def main():
    global ENGINE
    ensure_openrgb_server()
    print("[*] 初始化灯光引擎 ...")
    ENGINE = LightEngine()
    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer(("127.0.0.1", WEB_PORT), Handler)
    url = "http://127.0.0.1:%d/" % WEB_PORT
    print("[+] 控制台已启动: %s" % url)
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] 退出")
    finally:
        if ENGINE:
            ENGINE.running = False
        server.server_close()


if __name__ == "__main__":
    main()
