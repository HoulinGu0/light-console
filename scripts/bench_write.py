# -*- coding: utf-8 -*-
"""
写入延迟基准：测 set_colors 单次调用耗时分布，判断能否提高帧率。
用法: python bench_write.py [次数]
注意：运行前建议把模式设为 off，避免与控制台引擎抢写。
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request

from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

BASE = "http://127.0.0.1:8099"


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200

    print("暂停引擎写入 (mode=off) ...")
    post("/api/apply", {"mode": "off"})
    time.sleep(1.0)

    cli = OpenRGBClient(address="127.0.0.1", port=6742, name="bench")
    dev = cli.devices[0]
    dev.set_mode("Direct", force=True)
    time.sleep(0.2)

    total = sum(len(z.leds) for z in dev.zones)
    print("设备 %s, 总灯珠 %d\n" % (dev.name, total))

    samples = []
    for k in range(n):
        # 每帧换一下图案，确保不是被去重
        frame = []
        for z in dev.zones:
            for i in range(len(z.leds)):
                v = (i * 7 + k * 13) % 256
                frame.append(RGBColor(v, (v * 3) % 256, (v * 5) % 256))
        t0 = time.perf_counter()
        dev.set_colors(frame, fast=True)
        samples.append((time.perf_counter() - t0) * 1000.0)   # ms

    samples.sort()
    p = lambda q: samples[min(len(samples) - 1, int(len(samples) * q))]
    print("%-14s %8.2f ms" % ("min", samples[0]))
    print("%-14s %8.2f ms" % ("p50", p(0.50)))
    print("%-14s %8.2f ms" % ("p90", p(0.90)))
    print("%-14s %8.2f ms" % ("p99", p(0.99)))
    print("%-14s %8.2f ms" % ("max", samples[-1]))
    print("%-14s %8.2f ms" % ("mean", statistics.mean(samples)))
    print("")
    print("单次写入均值 %.2f ms -> 理论上限 %.0f fps" % (statistics.mean(samples), 1000.0 / max(0.01, statistics.mean(samples))))
    print("p90 写入 %.2f ms -> 保守上限 %.0f fps" % (p(0.90), 1000.0 / max(0.01, p(0.90))))

    post("/api/apply", {"mode": "chase"})


if __name__ == "__main__":
    main()
