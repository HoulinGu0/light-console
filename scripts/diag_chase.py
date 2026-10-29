# -*- coding: utf-8 -*-
"""
流光追逐诊断：采样 OpenRGB 控制器真实颜色，验证光头是否持续推进并绕回。
用法: python diag_chase.py [采样秒数]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request

from openrgb import OpenRGBClient

BASE = "http://127.0.0.1:8099"
SDK = ("127.0.0.1", 6742)


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read())


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0

    state = get("/api/state")
    speed = state["speed"]
    print("设置: speed=%s  color=%s" % (speed, state["color"]))
    post("/api/apply", {"mode": "chase"})
    time.sleep(0.4)

    cli = OpenRGBClient(address=SDK[0], port=SDK[1], name="diag-chase")
    dev = cli.devices[0]
    print("设备: %s\n" % dev.name)

    t0 = time.time()
    print("%-7s %-9s %-28s %-8s %s" % ("t(s)", "zone_leds", "frame_sha1", "head", "lit_count"))
    print("-" * 78)

    last_by_zone = {}
    while time.time() - t0 < seconds:
        dev.update()
        row = []
        for z in dev.zones:
            cols = [(l.colors[0].red, l.colors[0].green, l.colors[0].blue) for l in z.leds]
            if not cols:
                continue
            blob = bytes([c for rgb in cols for c in rgb])
            sha = hashlib.sha1(blob).hexdigest()[:10]
            # 光头 = 最亮的那颗
            lum = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in cols]
            head = lum.index(max(lum))
            lit = sum(1 for x in lum if x > 2)
            prev = last_by_zone.get(z.name)
            changed = "" if prev is None or prev != sha else "  <-- 未变化"
            last_by_zone[z.name] = sha
            row.append((z.name, len(z.leds), sha, head, lit, changed))
        for name, n, sha, head, lit, changed in row:
            print("%-7.2f %-9s %-28s %-8s %-9s%s"
                  % (time.time() - t0, "%s:%d" % (name.split()[-1], n), sha, head, lit, changed))
        print("")
        time.sleep(0.5)

    post("/api/apply", {"mode": "static"})
    print("已恢复 static")


if __name__ == "__main__":
    main()
