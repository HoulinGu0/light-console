# -*- coding: utf-8 -*-
"""把 docs/images/frames/*.png 合成首屏 GIF（仅开发期需要 Pillow）。"""
import glob
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(HERE, "frames")
OUT = os.path.join(HERE, "demo.gif")

WIDTH = 880
DURATION_MS = 900
LAST_HOLD_MS = 2200


def main():
    files = sorted(glob.glob(os.path.join(FRAMES, "*.png")))
    if not files:
        sys.exit("没有帧文件，先运行抓帧步骤")

    imgs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        ratio = WIDTH / im.width
        im = im.resize((WIDTH, int(im.height * ratio)), Image.LANCZOS)
        imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=128))
        print("  %-10s -> %dx%d" % (os.path.basename(f), im.width, im.height))

    durations = [DURATION_MS] * (len(imgs) - 1) + [LAST_HOLD_MS]
    imgs[0].save(OUT, save_all=True, append_images=imgs[1:],
                 duration=durations, loop=0, optimize=True, disposal=2)

    size = os.path.getsize(OUT)
    print("\n已生成: %s" % OUT)
    print("尺寸: %dx%d  帧数: %d  体积: %.1f KB"
          % (imgs[0].width, imgs[0].height, len(imgs), size / 1024))
    if size > 8 * 1024 * 1024:
        print("[!] 超过 8MB，GitHub 首屏加载会慢，建议减小 WIDTH 或减少配色数")
    return 0


if __name__ == "__main__":
    sys.exit(main())
