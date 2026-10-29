# Light Console

**A local web control panel for motherboard ARGB — without Armoury Crate, Mystic Light or RGB Fusion.**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Platform: Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4.svg)](#requirements)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](requirements.txt)
[![OpenRGB SDK](https://img.shields.io/badge/backend-OpenRGB%20SDK-informational.svg)](https://github.com/CalcProgrammer1/OpenRGB)

[English](README.md) · [简体中文](README.zh-CN.md)

![Light Console demo](docs/images/demo.gif)

Light Console talks to [OpenRGB](https://github.com/CalcProgrammer1/OpenRGB) over its SDK socket and
exposes your case lighting as a browser UI: HSV colour wheel, 84-swatch palette, per-zone colour and
LED-count calibration, eight effects, dark/light themes, and a first-run setup wizard.

Two effects need **no extra hardware**:

| Effect | What it does |
|---|---|
| **GPU-linked** | Reads GPU temperature / utilisation / power from `nvidia-smi`. Hue follows temperature (blue → red), brightness follows utilisation. |
| **Screen sync** | Slices the screen into 16 horizontal bands and maps them onto the LED chain, so the fans show the left-to-right colour distribution of whatever is on screen. |

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The two things that trip everyone up](#the-two-things-that-trip-everyone-up)
- [Configuration](#configuration)
- [Command line](#command-line)
- [Troubleshooting](#troubleshooting)
- [Compatibility and scope](#compatibility-and-scope)
- [Project layout](#project-layout)
- [The OpenRGB patch](#the-openrgb-patch)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Eight effects** — Static, Rainbow, Breathing, Chase, Wave, GPU-linked, Screen sync, Off.
- **Per-zone control** — every zone gets its own switch, colour and LED count. Disabling a zone
  simply sends black to it; other zones are unaffected.
- **Colour picker** — HSV wheel plus an 84-swatch palette, live preview while dragging,
  hex/RGB inputs, and a 14-entry recent-colours history.
- **LED-count calibration** — addressable headers report `0` LEDs until you tell the software how
  many are actually attached. A slider with live resize solves that.
- **Dark / light theme** — follows the OS preference on first visit, remembers your choice,
  no flash of the wrong theme.
- **First-run wizard** — enumerates whatever controllers OpenRGB found, walks you through each zone,
  writes `config.json`.
- **Command line** — `scripts/control.py` covers everything the UI does, for scripting.
- **Safe by default** — binds to `127.0.0.1` only; nothing leaves your machine.

## Requirements

| | |
|---|---|
| OS | Windows 10 / 11 (uses `nvidia-smi` and Windows process APIs) |
| Python | 3.10 or newer |
| OpenRGB | 1.1 portable, downloaded by `scripts/fetch_openrgb.ps1` |
| GPU telemetry | NVIDIA driver with `nvidia-smi` (optional — only the GPU-linked effect needs it) |

> **No administrator rights required** for the normal HID path. Running OpenRGB elevated is only
> needed if you also want SMBus devices (DRAM, some AIB GPUs) — this project does not use them.

## Installation

```powershell
git clone https://github.com/HoulinGu0/light-console.git
cd light-console

# 1. Download the official OpenRGB portable build (SHA-256 verified, ~22 MB)
pwsh -File scripts/fetch_openrgb.ps1

# 2. Install Python dependencies
pip install -r requirements.txt
```

The OpenRGB binary is **not** vendored in this repository. `assets/OpenRGB/` is git-ignored and
populated by the fetch script.

## Quick start

```powershell
python scripts/server.py
# or double-click 启动灯光控制台.cmd
```

The server will:

1. Reuse a running OpenRGB at `127.0.0.1:6742`, or launch the bundled one with `--server`.
2. Serve the console at <http://127.0.0.1:8099/>.
3. Open your browser.

On first run a **setup wizard** appears: it lists the controllers and zones OpenRGB reported, lets
you toggle each zone and drag a calibration slider, then writes `config.json`. You can re-run it any
time from **重新配置** in the footer.

| Wizard | Main UI (dark) | Main UI (light) |
|---|---|---|
| ![](evidence/wizard-step2.png) | ![](evidence/ui-v2.png) | ![](evidence/ui-v2-light.png) |

## The two things that trip everyone up

**1. Addressable headers report 0 LEDs until calibrated.**
OpenRGB cannot know how many LEDs are on your strip. Set the LED count for each zone — drag the
**标定 / calibrate** slider until the whole strip is lit and stop there. Getting this wrong causes
two very different bugs:

| LED count | Symptom |
|---|---|
| **Too low** | The tail of the chain never lights up (often the inner ring of the fans). |
| **Too high** | Chase/rainbow spend part of their travel on LEDs that do not exist — the strip looks like it stops for a while. |

**2. The name in the header is the RGB controller's name, not your motherboard model.**
OpenRGB reports whatever the controller calls itself. It *happens* to be the board name on ASUS Aura;
Gigabyte/MSI/ASRock usually report `RGB Fusion 2.0` / `Mystic Light` / `Polychrome`, or a chip name.
Hover the badge to see vendor, zone count and how many controllers were enumerated.

## Configuration

Settings live in `config.json` at the project root, created by the wizard.

```jsonc
{
  "setup_done": true,          // false re-opens the wizard on next load
  "mode": "static",            // static | rainbow | breathe | chase | wave | gpu | screen | off
  "color": "#00A8FF",
  "brightness": 100,           // 0-100
  "speed": 5,                  // 1-10
  "device": "",                // empty = auto-pick; or a name substring to force a controller
  "zones": {
    "addressable_rgb_header_1": { "enabled": true, "color": "#00A8FF" }
  },
  "leds": { "addressable_rgb_header_1": 24 }   // 0 = not calibrated yet
}
```

Zone keys are derived from the zone names OpenRGB reports (`slug(name)`), so **no vendor naming is
hard-coded** — a controller with five zones simply produces five keys. See
[docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference and the legacy migration rules.

## Command line

```bash
python scripts/control.py list                        # controllers, zones, available modes
python scripts/control.py set --color 00A8FF          # paint every zone
python scripts/control.py set --zone header1 --color FF3B30 --leds 60
python scripts/control.py mode --name Rainbow         # use the controller's built-in effect
python scripts/control.py off
python scripts/control.py anim --effect rainbow --seconds 30
python scripts/control.py sweep --leds 60             # light each header a different colour
python scripts/control.py snapshot / restore          # save / roll back a state
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `OpenRGB SDK 不可用` | Run `pwsh -File scripts/fetch_openrgb.ps1`, then check nothing else holds port 6742. |
| No zones listed | OpenRGB found no controllers. Check `%APPDATA%\OpenRGB\logs`. |
| A zone's LEDs stay dark | Its switch may be off, or its LED count is 0 (uncalibrated). |
| Inner ring of the fans dark | LED count too low — raise it. |
| Chase seems to pause | LED count too high — lower it until the strip just stays fully lit. |
| GPU badge shows `—` | `nvidia-smi` missing or failing; see `scripts/diag_gpu_poll.py`. |
| Screen sync lags, API timeouts | `screen_worker.py` did not start — check `%TEMP%\light_console_bands.json`. |

More: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Compatibility and scope

This is a **personal project tuned for one machine** — ASUS TUF GAMING B650M-PLUS WIFI with
6 ARGB case fans (2 on header 1, 4 on header 3), plus an RTX 4080 SUPER Founders Edition.
It is not a universal RGB manager.

- The HID path and the OpenRGB SDK are vendor-neutral, and zone keys adapt to whatever a controller
  reports, so other boards generally work — but the defaults, the calibration guidance and the
  documentation are shaped by that one machine.
- Only devices wired to **motherboard ARGB headers** are controlled. A case with its own built-in
  controller is out of reach.
- The GPU's own logo LED is **not** controllable — see below.

## Project layout

```
light-console/
├── LICENSE                 GPL-3.0
├── README.md · README.zh-CN.md
├── requirements.txt · requirements-dev.txt
├── config.json             created by the wizard (git-ignored)
├── 启动灯光控制台.cmd        one-click launcher
├── .github/                issue & PR templates
├── docs/                   getting started, config, troubleshooting, dev notes
├── patches/                the OpenRGB patch (source + binary form)
├── scripts/
│   ├── server.py           HTTP API + lighting engine
│   ├── index.html          the whole front end (no build step)
│   ├── control.py          command line
│   ├── screen_worker.py    screen capture in a separate process
│   ├── fetch_openrgb.ps1   downloads OpenRGB, verifies SHA-256
│   └── diag_*.py           diagnostics kept from development
├── assets/                 OpenRGB lives here after fetching (git-ignored)
├── evidence/               screenshots used in the docs
└── runtime/                runtime artefacts (git-ignored)
```

## The OpenRGB patch

[`patches/`](patches/) contains a two-line fix that makes OpenRGB's NVIDIA illumination probe accept
the `0x18CC` variant of the RTX 4080 SUPER Founders Edition. Upstream matches PCI IDs as an exact
quadruple and only defines `0x18CB`, so the probe skips the card **silently**.

The patch makes OpenRGB register the controller — it does **not** make the logo LED controllable:
`NvAPI_GPU_ClientIllumZonesGetControl` still reports `numIllumZonesControl = 0` on this driver.
Read [patches/README.md](patches/README.md) before filing an upstream issue, and note the GPL-2.0
obligations described there.

## Contributing

Issues and pull requests are welcome — please read [CONTRIBUTING.md](CONTRIBUTING.md) first.
For anything security-related, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## License

[GPL-3.0](LICENSE). This is not a free choice: the project imports
[`openrgb-python`](https://github.com/jath03/openrgb-python), which is GPL-3.0, so the combined work
must be GPL-3.0. See [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md) for the full dependency picture and
what it would take to relicense.

## Credits

- [OpenRGB](https://github.com/CalcProgrammer1/OpenRGB) — the hardware layer this depends on.
- [openrgb-python](https://github.com/jath03/openrgb-python) — the SDK client.
- [mss](https://github.com/BoboTiG/python-mss) and [NumPy](https://numpy.org/) — screen sampling.
