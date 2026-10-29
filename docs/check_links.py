# -*- coding: utf-8 -*-
"""校验文档里的相对链接与图片是否都真实存在。仅开发期使用。"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HTML_IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_SRC = re.compile(r'<img[^>]+src="([^"]+)"')
CODE_SPAN = re.compile(r"`[^`]*`")


def iter_md(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "__pycache__"}]
        for n in filenames:
            if n.lower().endswith(".md"):
                yield os.path.join(dirpath, n)


def main(base):
    problems = []
    checked = 0
    for path in iter_md(base):
        rel_doc = os.path.relpath(path, base)
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        text = CODE_SPAN.sub("", text)          # 忽略行内代码里的"链接"
        refs = set(MD_LINK.findall(text)) | set(HTML_IMG.findall(text)) | set(HTML_SRC.findall(text))
        for ref in refs:
            ref = ref.strip()
            if not ref or ref.startswith(("http://", "https://", "mailto:", "#", "<")):
                continue
            target = ref.split("#")[0]
            if not target:
                continue
            checked += 1
            full = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(full):
                problems.append((rel_doc, ref, os.path.relpath(full, base)))
    print("检查链接数: %d" % checked)
    if problems:
        print("\n失效引用 %d 处：" % len(problems))
        for doc, ref, resolved in problems:
            print("  %-34s -> %-46s (解析为 %s)" % (doc, ref, resolved))
        return 1
    print("全部有效 ✓")
    return 0


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(main(root))
