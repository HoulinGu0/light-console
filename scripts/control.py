# -*- coding: utf-8 -*-
"""
ASUS TUF GAMING B650M-PLUS WIFI 机箱/主板灯光控制
通过 OpenRGB SDK (127.0.0.1:6742) 驱动 AURA LED Controller (0B05:19AF)。

用法:
  python control.py list
  python control.py snapshot                # 保存当前状态到 state.json
  python control.py restore                 # 从 state.json 还原
  python control.py sweep                   # 三个 ARGB 排针分别点亮 绿/蓝/红 用于定位
  python control.py set --color FF0000                       # 全部灯区刷成红色
  python control.py set --zone header1 --color 00FF00        # 只刷 1 号 ARGB 排针
  python control.py set --zone mainboard --color FFFFFF      # 只刷主板自带灯
  python control.py mode --name Rainbow                      # 切内置灯效
  python control.py off
  python control.py anim --effect rainbow --seconds 15
  python control.py anim --effect breathe --color 0080FF --seconds 15
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

from openrgb import OpenRGBClient
from openrgb.utils import RGBColor

HOST = "127.0.0.1"
PORT = 6742
DEVICE_HINT = "ASUS TUF GAMING B650M-PLUS WIFI"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


# ---------------------------------------------------------------- helpers
def hex2rgb(value: str) -> RGBColor:
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError("颜色格式应为 RRGGBB 或 #RRGGBB，收到: %r" % value)
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def connect() -> OpenRGBClient:
    try:
        return OpenRGBClient(address=HOST, port=PORT, name="dsh-coldbrew")
    except Exception as exc:  # noqa: BLE001
        sys.exit(
            "无法连接 OpenRGB SDK %s:%d -> %s\n"
            "请先启动服务端: OpenRGB.exe --server --noautoconnect --startminimized" % (HOST, PORT, exc)
        )


def get_device(cli: OpenRGBClient):
    devices = cli.devices
    if not devices:
        sys.exit("OpenRGB 没有检测到任何 RGB 控制器")
    for dev in devices:
        if DEVICE_HINT.lower() in dev.name.lower():
            return dev
    return devices[0]


def is_header(zone) -> bool:
    return "addressable" in zone.name.lower() or "header" in zone.name.lower()


def header_zones(dev):
    return [z for z in dev.zones if is_header(z)]


def mainboard_zones(dev):
    return [z for z in dev.zones if not is_header(z)]


def pick_zone(dev, selector: str):
    """selector: all / mainboard / header1..3 / 完整灯区名 / 子串"""
    s = selector.strip().lower()
    if s in ("all", ""):
        return None
    if s in ("mainboard", "mb", "board"):
        return mainboard_zones(dev)
    if s.startswith("header"):
        num = s.replace("header", "").strip()
        for z in header_zones(dev):
            if num and num in z.name:
                return [z]
        return header_zones(dev)
    for z in dev.zones:
        if s in z.name.lower():
            return [z]
    sys.exit("找不到灯区 %r，可用: %s" % (selector, ", ".join(z.name for z in dev.zones)))


def ensure_direct(dev):
    try:
        dev.set_mode("Direct", force=True)
    except Exception as exc:  # noqa: BLE001
        sys.exit("切换到 Direct 模式失败: %s" % exc)


def resize_headers(dev, count: int):
    """ARGB 排针默认 LED 数为 0，必须先 resize 才能吃色。"""
    changed = []
    for z in header_zones(dev):
        if len(z.leds) != count:
            z.resize(count)
            changed.append("%s -> %d 灯珠" % (z.name, count))
    return changed


def describe(dev):
    lines = []
    lines.append("设备      : %s" % dev.name)
    lines.append("当前模式  : %s" % dev.modes[dev.active_mode].name)
    lines.append("灯区 %d 个 / LED %d 颗" % (len(dev.zones), len(dev.leds)))
    for z in dev.zones:
        lines.append("  - %-26s leds=%-4d" % (z.name, len(z.leds)))
    return "\n".join(lines)


# ---------------------------------------------------------------- commands
def cmd_list(_args):
    cli = connect()
    dev = get_device(cli)
    print(describe(dev))
    print("\n可用内置灯效:")
    for m in dev.modes:
        print("  - %s (value=%s)" % (m.name, m.value))


def cmd_snapshot(_args):
    cli = connect()
    dev = get_device(cli)
    data = {
        "device": dev.name,
        "active_mode": dev.modes[dev.active_mode].name,
        "zones": [],
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for z in dev.zones:
        colors = []
        for led in z.leds:
            c = getattr(led, "color", None)
            colors.append([c.red, c.green, c.blue] if c is not None else None)
        data["zones"].append({"name": z.name, "led_count": len(z.leds), "colors": colors})
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("已保存当前状态 -> %s" % STATE_FILE)
    print(describe(dev))


def cmd_restore(_args):
    if not os.path.exists(STATE_FILE):
        sys.exit("没有 state.json，无法还原。可先执行: python control.py snapshot")
    with open(STATE_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    cli = connect()
    dev = get_device(cli)
    for zone_state in data.get("zones", []):
        n = zone_state.get("led_count") or 0
        for z in dev.zones:
            if z.name == zone_state["name"] and n and len(z.leds) != n:
                z.resize(n)
    mode = data.get("active_mode")
    if mode:
        dev.set_mode(mode, force=True)
        print("已还原模式: %s" % mode)
    if data.get("active_mode") == "Direct":
        ensure_direct(dev)
        for zone_state in data.get("zones", []):
            cols = zone_state.get("colors") or []
            if not cols or any(c is None for c in cols):
                continue
            for z in dev.zones:
                if z.name != zone_state["name"] or len(cols) != len(z.leds):
                    continue
                z.set_colors([RGBColor(*c) for c in cols])
                print("已还原灯区 %s 的 %d 颗灯色" % (z.name, len(cols)))
    print(describe(dev))


def cmd_set(args):
    cli = connect()
    dev = get_device(cli)
    if args.leds:
        for note in resize_headers(dev, args.leds):
            print("尺寸调整: %s" % note)
    ensure_direct(dev)
    color = hex2rgb(args.color)
    target = pick_zone(dev, args.zone)
    zones = dev.zones if target is None else target
    if any(len(z.leds) == 0 for z in zones):
        sys.exit("目标灯区 LED 数为 0，请先加 --leds N（ARGB 排针必须指定灯珠数量）")
    for z in zones:
        z.set_color(color)
    print("已把 %s 设为 #%02X%02X%02X（%d 个灯区）"
          % (", ".join(z.name for z in zones), color.red, color.green, color.blue, len(zones)))


def cmd_sweep(args):
    """三个 ARGB 排针分别刷不同颜色，用来定位机箱灯接在哪一路。"""
    cli = connect()
    dev = get_device(cli)
    for note in resize_headers(dev, args.leds):
        print("尺寸调整: %s" % note)
    ensure_direct(dev)
    palette = [
        ("Addressable RGB Header 1", RGBColor(0, 255, 0), "绿 GREEN"),
        ("Addressable RGB Header 2", RGBColor(0, 0, 255), "蓝 BLUE"),
        ("Addressable RGB Header 3", RGBColor(255, 0, 0), "红 RED"),
    ]
    print("正在给三路 ARGB 排针刷不同颜色:")
    for name, color, label in palette:
        for z in header_zones(dev):
            if name.split()[-1] in z.name and len(z.leds) > 0:
                z.set_color(color)
                print("  %-26s -> %s" % (z.name, label))
    for z in mainboard_zones(dev):
        if len(z.leds) > 0:
            z.set_color(RGBColor(255, 255, 255))
            print("  %-26s -> 白 WHITE" % z.name)
    print("\n请查看机箱：出现 绿/蓝/红 哪一色，机箱灯就接在对应排针上。")
    print("主板自带灯应为白色。若全都没变化 -> 机箱灯没接主板 ARGB，是机箱独立控制器。")


def cmd_mode(args):
    cli = connect()
    dev = get_device(cli)
    names = {m.name.lower(): m.name for m in dev.modes}
    want = args.name.strip().lower()
    if want not in names:
        sys.exit("没有灯效 %r，可用: %s" % (args.name, ", ".join(m.name for m in dev.modes)))
    dev.set_mode(names[want], save=args.save, force=True)
    print("已切换灯效: %s%s" % (names[want], "（已写入设备）" if args.save else ""))


def cmd_off(_args):
    cli = connect()
    dev = get_device(cli)
    dev.off()
    print("已关闭灯光")


def cmd_anim(args):
    cli = connect()
    dev = get_device(cli)
    if args.leds:
        resize_headers(dev, args.leds)
    ensure_direct(dev)
    n = len(dev.leds)
    if n == 0:
        sys.exit("没有可控制的 LED，请加 --leds N")
    base = hex2rgb(args.color) if args.color else RGBColor(255, 255, 255)
    fps = max(1, args.fps)
    deadline = time.time() + args.seconds
    frame = 0
    print("动画 %s 跑 %ds @ %dfps（Ctrl+C 停止）" % (args.effect, args.seconds, fps))
    try:
        while time.time() < deadline:
            t = frame / fps
            colors = []
            for i in range(n):
                if args.effect == "rainbow":
                    hue = (i / max(1, n) + t * 0.35) % 1.0
                    colors.append(RGBColor.fromHSV(hue, 1.0, 1.0))
                elif args.effect == "breathe":
                    k = 0.5 + 0.5 * math.sin(t * 2.2)
                    colors.append(RGBColor(int(base.red * k), int(base.green * k), int(base.blue * k)))
                elif args.effect == "chase":
                    head = int(t * 8) % max(1, n)
                    on = (i - head) % max(1, n) < max(1, n // 6)
                    colors.append(base if on else RGBColor(0, 0, 0))
                else:
                    colors.append(base)
            dev.set_colors(colors, fast=True)
            frame += 1
            time.sleep(1.0 / fps)
    except KeyboardInterrupt:
        print("\n已中断")
    dev.show()
    print("动画结束，最后一帧已保留")


# ---------------------------------------------------------------- entry
def build_parser():
    p = argparse.ArgumentParser(description="ASUS Aura 机箱/主板灯光控制")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出设备、灯区与可用灯效").set_defaults(func=cmd_list)
    sub.add_parser("snapshot", help="保存当前灯效状态").set_defaults(func=cmd_snapshot)
    sub.add_parser("restore", help="还原到快照状态").set_defaults(func=cmd_restore)
    sub.add_parser("off", help="关灯").set_defaults(func=cmd_off)

    s = sub.add_parser("set", help="把指定灯区设为纯色")
    s.add_argument("--color", required=True, help="RRGGBB 或 #RRGGBB")
    s.add_argument("--zone", default="all", help="all / mainboard / header1 / 灯区名子串")
    s.add_argument("--leds", type=int, default=0, help="ARGB 排针灯珠数量（首次必须指定）")
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("sweep", help="三路 ARGB 排针分别点亮以定位机箱灯")
    s.add_argument("--leds", type=int, default=60, help="每路 ARGB 灯珠数量（默认 60）")
    s.set_defaults(func=cmd_sweep)

    s = sub.add_parser("mode", help="切换内置灯效")
    s.add_argument("--name", required=True)
    s.add_argument("--save", action="store_true", help="写入设备持久化")
    s.set_defaults(func=cmd_mode)

    s = sub.add_parser("anim", help="运行动画")
    s.add_argument("--effect", default="rainbow", choices=["rainbow", "breathe", "chase"])
    s.add_argument("--color", default=None)
    s.add_argument("--seconds", type=int, default=15)
    s.add_argument("--fps", type=int, default=20)
    s.add_argument("--leds", type=int, default=0)
    s.set_defaults(func=cmd_anim)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
