# -*- coding: utf-8 -*-
"""Probe OpenRGB SDK: enumerate controllers, zones, LEDs and modes."""
import json
import sys

from openrgb import OpenRGBClient

HOST = "127.0.0.1"
PORT = 6742


def main() -> int:
    cli = OpenRGBClient(address=HOST, port=PORT, name="dsh-probe")
    devices = cli.devices
    print("controller_count = %d\n" % len(devices))

    dump = []
    for i, dev in enumerate(devices):
        info = {
            "index": i,
            "name": dev.name,
            "type": str(getattr(dev, "type", "?")),
            "description": getattr(dev, "description", ""),
            "vendor": getattr(dev, "vendor", ""),
            "version": getattr(dev, "version", ""),
            "serial": getattr(dev, "serial", ""),
            "location": getattr(dev, "location", ""),
            "active_mode": getattr(dev, "active_mode", None),
            "modes": [],
            "zones": [],
            "leds": [],
        }

        print("=" * 78)
        print("[%d] %s" % (i, dev.name))
        print("    type=%s  vendor=%s  version=%s" % (info["type"], info["vendor"], info["version"]))
        print("    desc=%s" % info["description"])
        print("    location=%s" % info["location"])

        cur = getattr(dev, "active_mode", None)
        print("    active_mode = %s" % cur)
        for m in getattr(dev, "modes", []):
            info["modes"].append({"name": m.name, "value": getattr(m, "value", None)})
            print("      mode: %-28s value=%s" % (m.name, getattr(m, "value", None)))

        print("    zones = %d" % len(getattr(dev, "zones", [])))
        for z in getattr(dev, "zones", []):
            leds = getattr(z, "leds", [])
            info["zones"].append(
                {
                    "name": z.name,
                    "type": str(getattr(z, "type", "?")),
                    "led_count": len(leds),
                    "resizable": getattr(z, "resizable", None),
                }
            )
            print("      zone: %-28s type=%-8s leds=%d resizable=%s"
                  % (z.name, getattr(z, "type", "?"), len(leds), getattr(z, "resizable", None)))

        print("    leds = %d" % len(getattr(dev, "leds", [])))
        for led in getattr(dev, "leds", []):
            info["leds"].append(led.name)
            print("      led: %s" % led.name)

        dump.append(info)

    with open("devices.json", "w", encoding="utf-8") as fh:
        json.dump(dump, fh, ensure_ascii=False, indent=2)
    print("\nwritten -> devices.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
