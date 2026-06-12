#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XHS Cover Renderer — 小红书「钩子封面」渲染器

把一份带 YAML 头部的 Markdown 渲染成一张 1080x1440 的小红书封面 PNG。
设计目标：在白底明亮的小红书信息流里「跳出来」——大标题、关键词高亮、
配色按内容类型区分（蓝=知识/绿=干货/红=观点/白=清新）。

用法:
    python scripts/render_cover.py demos/sample_note.md
    python scripts/render_cover.py note.md -o output/ -t green

YAML 头部字段:
    theme:      blue | green | red | light      （默认 blue）
    tag:        左上角小标签文字
    eyebrow:    （可选）主标题上方的小一号引导行
    title:      主标题，支持 \\n 换行，**关键词** 自动高亮
    subtitle:   副标题，支持 **加粗** 与 \\n 换行
    chips:      底部关键词列表（YAML 数组）
    author:     署名（昵称）
    author_sub: 署名副标题（一句话简介）
    avatar:     头像里显示的 1 个字（默认取 author 首字）

依赖: PyYAML（pip install pyyaml）。渲染走系统已安装的 Chrome/Edge，无需 playwright。
环境变量 CHROME_PATH 可指定浏览器可执行文件路径。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("缺少依赖 PyYAML，请运行: pip install pyyaml")
    sys.exit(1)

# Windows 控制台默认 GBK，统一切到 UTF-8 避免 emoji/中文打印报错
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "assets" / "cover_template.html"
THEMES = ROOT / "assets" / "themes.json"


def find_chrome() -> str:
    """定位 Chrome / Edge 可执行文件。"""
    if os.getenv("CHROME_PATH"):
        return os.getenv("CHROME_PATH")
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    print("未找到 Chrome/Edge，请用环境变量 CHROME_PATH 指定路径。")
    sys.exit(1)


def parse_front_matter(text: str) -> dict:
    """提取 Markdown 顶部的 YAML 头部。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        print("文件缺少 YAML 头部（--- 包裹的元数据）。")
        sys.exit(1)
    return yaml.safe_load(m.group(1)) or {}


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_title(s: str) -> str:
    """换行 \\n -> <br>，**关键词** -> 高亮 span。"""
    s = esc(s)
    s = s.replace("\\n", "<br>").replace("\n", "<br>")
    s = re.sub(r"\*\*(.+?)\*\*", r'<span class="hl">\1</span>', s)
    return s


def fmt_sub(s: str) -> str:
    s = esc(s)
    s = s.replace("\\n", "<br>").replace("\n", "<br>")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return s


def build_html(meta: dict) -> str:
    themes = json.loads(THEMES.read_text(encoding="utf-8"))
    theme_key = meta.get("theme", "blue")
    if theme_key not in themes:
        print(f"未知主题 '{theme_key}'，可选: {', '.join(themes)}。改用 blue。")
        theme_key = "blue"
    t = themes[theme_key]

    author = meta.get("author", "你的昵称")
    avatar = meta.get("avatar") or (author[0] if author else "笔")
    chips = meta.get("chips", []) or []
    chips_html = "".join(f'<div class="chip">{esc(c)}</div>' for c in chips)
    eyebrow = meta.get("eyebrow")
    eyebrow_block = f'<div class="eyebrow">{fmt_title(eyebrow)}</div>' if eyebrow else ""

    html = TEMPLATE.read_text(encoding="utf-8")
    mapping = {
        "BG": t["bg"], "BORDER": t["border"], "GLOW1": t["glow1"], "GLOW2": t["glow2"],
        "TAG_BG": t["tag_bg"], "TAG_FG": t["tag_fg"], "TAG_DOT": t["tag_dot"],
        "HL": t["hl"], "TITLE_FG": t["title_fg"], "SUB_FG": t["sub_fg"], "SUB_B": t["sub_b"],
        "CHIP_BG": t["chip_bg"], "CHIP_BORDER": t["chip_border"], "CHIP_FG": t["chip_fg"],
        "AVATAR_GRAD": t["avatar_grad"], "ME_SUB": t["me_sub"],
        "TAG": esc(meta.get("tag", "笔记分享")),
        "EYEBROW_BLOCK": eyebrow_block,
        "TITLE": fmt_title(meta.get("title", "在这里写你的大标题")),
        "SUBTITLE": fmt_sub(meta.get("subtitle", "")),
        "CHIPS": chips_html,
        "AVATAR_TEXT": esc(avatar),
        "AUTHOR": esc(author),
        "AUTHOR_SUB": esc(meta.get("author_sub", "")),
    }
    for k, v in mapping.items():
        html = html.replace("{{" + k + "}}", str(v))
    return html


def render(html: str, out_png: Path, chrome: str):
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_png = out_png.resolve()  # Chrome headless 对相对路径写图会静默失败
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    try:
        subprocess.run([
            chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--screenshot={out_png}", "--window-size=1080,1440",
            Path(tmp).as_uri(),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(tmp)
    print(f"✅ 已生成封面: {out_png}")


def main():
    ap = argparse.ArgumentParser(description="小红书钩子封面渲染器（HTML→PNG, 1080x1440）")
    ap.add_argument("markdown", help="带 YAML 头部的 Markdown 文件")
    ap.add_argument("-o", "--output", default=None, help="输出 PNG 路径或目录（默认同名 .png）")
    ap.add_argument("-t", "--theme", default=None, help="覆盖主题: blue/green/red/light")
    args = ap.parse_args()

    src = Path(args.markdown)
    if not src.exists():
        print(f"文件不存在: {src}")
        sys.exit(1)

    meta = parse_front_matter(src.read_text(encoding="utf-8"))
    if args.theme:
        meta["theme"] = args.theme

    if args.output:
        out = Path(args.output)
        if out.is_dir() or args.output.endswith(("/", "\\")):
            out = out / (src.stem + ".png")
    else:
        out = src.with_suffix(".png")

    render(build_html(meta), out, find_chrome())


if __name__ == "__main__":
    main()
