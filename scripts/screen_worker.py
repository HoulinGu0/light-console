# -*- coding: utf-8 -*-
"""
屏幕取色工作进程。

为什么独立进程：
    mss 每帧要 BitBlt + 分配约 19MB 缓冲（3440x1440x4），在线程里跑会
    持续制造 GC 压力并占住 GIL，实测会让 /api/state 偶发 5 秒级超时。
    拆成独立进程后，主服务只读一个几百字节的 JSON，HTTP 延迟回到毫秒级。

由 server.py 在切到 screen 模式时拉起，退出该模式时终止。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time


def enhance(r, g, b):
    """暗场提亮 + 拉开饱和度，保留色相。"""
    mx = max(r, g, b)
    if mx <= 0:
        return [6, 6, 6]
    gain = (mx / 255.0) ** 0.6
    s = (255.0 * gain) / mx
    r2, g2, b2 = r * s, g * s, b * s
    mean = (r2 + g2 + b2) / 3.0
    sat = 1.28
    return [int(max(0.0, min(255.0, mean + (c - mean) * sat))) for c in (r2, g2, b2)]


def parent_alive(pid):
    """判断父进程是否还活着。

    注意：Windows 上 os.kill(pid, 0) 并不是"探测存活"，
    CPython 会走 TerminateProcess(handle, 0) —— 那会把父进程杀掉。
    这里改用 OpenProcess + WaitForSingleObject 安全探测。
    """
    if not pid:
        return True
    try:
        import ctypes
        SYNCHRONIZE = 0x00100000
        WAIT_TIMEOUT = 0x00000102
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return False
        try:
            return k32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            k32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bands", type=int, default=16)
    ap.add_argument("--fps", type=float, default=8.0)
    ap.add_argument("--stride", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parent-pid", type=int, default=0)
    args = ap.parse_args()

    try:
        import mss
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        _write(args.out, {"ok": False, "bands": [], "error": "缺少依赖: %s" % exc})
        return 1

    try:
        sct = mss.mss()
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
    except Exception as exc:  # noqa: BLE001
        _write(args.out, {"ok": False, "bands": [], "error": "无法初始化抓屏: %s" % exc})
        return 1

    interval = 1.0 / max(1.0, args.fps)
    parent = args.parent_pid
    tmp = args.out + ".%d.tmp" % os.getpid()

    while True:
        if not parent_alive(parent):
            return 0
        t0 = time.time()
        try:
            shot = sct.grab(mon)
            arr = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
            sub = arr[::args.stride, ::args.stride, :3].astype(np.float32)
            h, w, _ = sub.shape
            bands = []
            for i in range(args.bands):
                x0 = int(w * i / args.bands)
                x1 = int(w * (i + 1) / args.bands)
                b, g, r = sub[:, x0:x1].reshape(-1, 3).mean(axis=0)
                bands.append(enhance(int(r), int(g), int(b)))
            payload = {"ok": True, "bands": bands, "error": "", "ts": time.time()}
        except Exception as exc:  # noqa: BLE001
            payload = {"ok": False, "bands": [], "error": str(exc), "ts": time.time()}

        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, args.out)
        except OSError:
            pass

        dt = time.time() - t0
        time.sleep(max(0.0, interval - dt))


def _write(path, payload):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
