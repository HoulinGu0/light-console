# -*- coding: utf-8 -*-
"""
复现并验证：nvidia-smi 的 -f 无法写入含中文的路径。

背景：项目原先位于 C:\\Users\\Louis\\Desktop\\开发\\project\\...，
`nvidia-smi ... -f <该路径>` 直接返回 255 且不生成文件，导致 GPU 遥测一直 ok=False。
目录后来改名为 `dev`，问题随之消失；但本脚本用临时目录里的中/英文子目录来
独立复现，因此不依赖项目所在位置。
"""
import os
import shutil
import subprocess
import tempfile

NVSMI = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
ARGS = ["--query-gpu=utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"]


def run_case(label, directory, filename):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    print("--- %s ---" % label)
    print("  路径: %s" % path)
    try:
        r = subprocess.run([NVSMI] + ARGS + ["-f", path], timeout=8,
                           creationflags=0x08000000,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  returncode = %s" % r.returncode)
    except Exception as exc:  # noqa: BLE001
        print("  异常: %s: %s" % (type(exc).__name__, exc))
    ok = os.path.exists(path)
    print("  文件生成: %s" % ok)
    if ok:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            print("  内容: %r" % fh.read().strip())
    return ok


def main():
    base = tempfile.gettempdir()
    ascii_dir = os.path.join(base, "light_console_probe_ascii")
    cn_dir = os.path.join(base, "光照测试目录")

    a = run_case("纯 ASCII 路径", ascii_dir, "gpu_query.txt")
    c = run_case("含中文的路径", cn_dir, "gpu_query.txt")

    print("\n--- 对照：管道捕获（不受路径影响） ---")
    try:
        r = subprocess.run([NVSMI] + ARGS, capture_output=True, text=True,
                           timeout=8, creationflags=0x08000000)
        print("  rc=%s stdout=%r" % (r.returncode, r.stdout.strip()))
    except Exception as exc:  # noqa: BLE001
        print("  异常: %s: %s" % (type(exc).__name__, exc))

    print("\n结论：ASCII 路径 %s / 中文路径 %s"
          % ("成功" if a else "失败", "成功" if c else "失败"))
    for d in (ascii_dir, cn_dir):
        shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
