#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XHS 半自动发布器 — 合规优先（真人确认）

设计原则（对应 references/compliance-anti-ban.md）：
  · 默认「仅自己可见」发布，仅作预览；要公开必须显式 --public。
  · 公开发布前**强制**打印 7 项合规自查 + 要求真人手动键入确认（--yes 可跳过，但不建议）。
  · 本脚本只做「单篇、真人触发」的发布，**不做**无人值守的批量/定时全自动闭环。

依赖:  pip install xhs python-dotenv
登录:  在项目根目录建 .env，写入  XHS_COOKIE=...
       获取：浏览器登录小红书 → F12 → Network → 任意请求的 Cookie 头，整串复制。
       （.env 已被 .gitignore 忽略，切勿提交/分享）

用法:
  # 1) 先 dry-run 校验（不发）
  python scripts/publish_xhs.py -t "标题" -d "正文" -i cover.png card_1.png --dry-run
  # 2) 仅自己可见（预览，默认）
  python scripts/publish_xhs.py -t "标题" -d "正文" -i cover.png card_1.png
  # 3) 确认无误后公开（会要求真人键入确认）
  python scripts/publish_xhs.py -t "标题" -d "正文" -i cover.png card_1.png --public

致谢：发布链路参考 Auto-Redbook-Skills (github.com/comeonzhj/Auto-Redbook-Skills)
      与 xhs 客户端 (github.com/ReaJason/xhs)。
"""
import argparse
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

CHECKLIST = [
    "内容基于真实经验，没有虚构人设/伪造经历？",
    "今天发布数 ≤ 2 篇，没有刷屏？",
    "发布时间是真人作息时段、非整点机器式？",
    "评论会由真人回复，没开自动回复机器人？",
    "没有用同一设备/Cookie 操作多个账号？",
    "图片是排版设计图；若含 AI 合成画面，已按规打标？",
    "我（真人）已亲自审过这篇再发？",
]


def load_cookie() -> str:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("缺少依赖，请运行: pip install python-dotenv xhs")
        sys.exit(1)
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if p.exists():
            load_dotenv(p)
            break
    cookie = os.getenv("XHS_COOKIE")
    if not cookie:
        print("❌ 未找到 XHS_COOKIE。请在项目根目录 .env 写入：XHS_COOKIE=你的cookie")
        sys.exit(1)
    return cookie


def check_cookie(cookie: str):
    fields = {kv.split("=", 1)[0].strip() for kv in cookie.split(";") if "=" in kv}
    missing = [f for f in ("a1", "web_session") if f not in fields]
    if missing:
        print(f"⚠️ Cookie 可能不完整，缺少字段: {', '.join(missing)}（可能导致签名失败）")


def valid_images(paths):
    out = []
    for p in paths:
        if os.path.exists(p):
            out.append(os.path.abspath(p))
        else:
            print(f"⚠️ 图片不存在，已跳过: {p}")
    if not out:
        print("❌ 没有有效的图片文件")
        sys.exit(1)
    return out


def compliance_gate(skip: bool) -> bool:
    """公开发布前的真人确认闸门。"""
    print("\n🛡  公开发布前合规自查（对照 references/compliance-anti-ban.md）：")
    for i, item in enumerate(CHECKLIST, 1):
        print(f"   {i}. {item}")
    if skip:
        print("\n（--yes 已跳过手动确认；请确保你已逐条核对）")
        return True
    ans = input('\n以上全部为「是」请键入「确认发布」并回车（其他任意键取消）: ').strip()
    return ans in ("确认发布", "确认", "yes", "y")


def main():
    ap = argparse.ArgumentParser(description="小红书半自动发布器（合规优先·真人确认）")
    ap.add_argument("-t", "--title", required=True, help="笔记标题（≤20字）")
    ap.add_argument("-d", "--desc", default="", help="正文内容")
    ap.add_argument("-i", "--images", nargs="+", required=True, help="图片路径（可多个）")
    ap.add_argument("--public", action="store_true", help="公开发布（默认仅自己可见）")
    ap.add_argument("--post-time", default=None, help="定时发布 'YYYY-MM-DD HH:MM:SS'")
    ap.add_argument("--dry-run", action="store_true", help="仅校验不发布")
    ap.add_argument("--yes", action="store_true", help="跳过手动确认（不建议）")
    args = ap.parse_args()

    if len(args.title) > 20:
        print("⚠️ 标题超过20字，将被截断")
        args.title = args.title[:20]

    cookie = load_cookie()
    check_cookie(cookie)
    images = valid_images(args.images)
    is_private = not args.public

    print("\n📋 待发布：")
    print(f"   标题: {args.title}")
    print(f"   正文: {args.desc[:50]}{'...' if len(args.desc) > 50 else ''}")
    print(f"   图片: {len(images)} 张")
    print(f"   可见性: {'仅自己可见(预览)' if is_private else '🌍 公开'}")
    print(f"   定时: {args.post_time or '立即'}")

    if args.dry_run:
        print("\n🔍 dry-run：校验通过，未实际发布。")
        return

    # 公开发布 → 真人确认闸门
    if not is_private:
        if not compliance_gate(args.yes):
            print("已取消。可先用默认（仅自己可见）预览，确认后再 --public。")
            return

    try:
        from xhs import XhsClient
        from xhs.help import sign as local_sign
    except ImportError:
        print("❌ 缺少 xhs 库，请运行: pip install xhs")
        sys.exit(1)

    a1 = next((kv.split("=", 1)[1] for kv in cookie.split(";") if kv.strip().startswith("a1=")), "")
    client = XhsClient(cookie=cookie, sign=lambda uri, data=None, a1_param="", web_session="": local_sign(uri, data, a1=a1 or a1_param))

    try:
        info = client.get_self_info()
        print(f"\n👤 当前账号: {info.get('nickname', '未知')}")
    except Exception as e:
        print(f"⚠️ 获取用户信息失败（可继续）: {e}")

    try:
        res = client.create_image_note(
            title=args.title, desc=args.desc, files=images,
            is_private=is_private, post_time=args.post_time,
        )
        nid = (res or {}).get("note_id") or (res or {}).get("id")
        print("\n✨ 发布成功！" + (f"\n   🔗 https://www.xiaohongshu.com/explore/{nid}" if nid else ""))
        if is_private:
            print("   （当前为「仅自己可见」，确认满意后加 --public 再发一次即可公开）")
    except Exception as e:
        msg = str(e)
        print(f"\n❌ 发布失败: {msg}")
        if "sign" in msg.lower() or "cookie" in msg.lower():
            print("💡 多为 Cookie 过期/不全，请重新抓取 a1 与 web_session 后再试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
