#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""半修检测器（half-fix detector）。

## 它解决什么问题

`check_anchors.py` 保证"路径存在、行号在范围内"。它看不见**同一句断言在多处副本之间不一致**，
而这正是第五轮四个缺陷的共同形态：

  1. 表头改成 31/730，正文三处仍是 29/655
  2. 正文锚点改成 `README.md:57`，锚点汇总与评审表仍写 `:48-49`（其中一处还打着 ✅）
  3. `2.2` 撤回了"heartbeat 被删除"，`harness/README`、`02-Boundaries/README`、证据台账三处仍在断言
  4. `4.1` 写"全部数字实测复现，无一处需要改"，而同一文件另有两处被证伪

共同点：**改矛盾的一端、留另一端**。两端都错只断言一件错事；半修之后同时断言两件互斥的事。

## 用法

    python3 _digested/_tools/check_half_fixes.py --phrases "heartbeat 删除" "两次兑现"
    python3 _digested/_tools/check_half_fixes.py            # 用内置的已知撤回清单

退出码：0 = 无未标注残留；1 = 有。

## 判定规则

一句含某短语的行，如果**同时**含有撤回标记（`撤回`/`~~`/`从未`/`零命中`/`不存在`/`已删`/`实为`/`不是`），
视为已标注，跳过。否则报告为"未标注残留"。

## 已知局限（必须知道）

- **不读语义**：它分不清"X 是错的"和"X 是正确的"。一处正常引用别人错误的行会被误报。
- **短语要人工给**：它不知道哪些断言被撤回过。内置清单是本套文档的已知账，新撤回要手动加。
- **中文引号既表引用又表转述**：与 `REVIEW_PROTOCOL.md` 第 4 类盲区同源，不做引文校验。
- 因此它是**复核辅助**，不是门禁。红灯要人看一眼；但**绿灯之前它确实跑过了**——
  这比"我记得我改完了"强。
"""

import argparse
import glob
import io
import sys

# 本套文档里已被撤回/证伪、但仍可能以肯定形式残留在别处的断言
KNOWN_RETRACTED = [
    "heartbeat 删除",
    "heartbeat** 删除",
    "两次兑现",
    "兑现了两次",
    "实打实发生了两次",
    "无一处需要改",
    "v0.5.0 又演示了第二次",
    # 注意：「prune_orphans」不列入——它只在"版本间变化"台账里以"已删除"形式出现，那是正确用法

    "use_rerank=False",
    "future updates will be centrally published there",
    "人类认知模式的简化映射",
    "TODO: control bubbling frequency",
]

# 出现即视为"这行是在讲它已失效"，跳过
RETRACT_MARKERS = (
    "撤回", "~~", "从未", "零命中", "不存在", "已删", "实为",
    "不是", "错", "该端点", "非死锚", "编的", "那句话是", "曾引", "曾写", "曾把",
    "本身还在", "已被", "仍在断言",
)

SCAN_GLOBS = ("_digested/**/*.md", "_faq_on_digested/**/*.md")


def scan(phrases, quiet=False):
    files = []
    for g in SCAN_GLOBS:
        files.extend(glob.glob(g, recursive=True))
    files.sort()

    total = 0
    for ph in phrases:
        bad = []
        for f in files:
            try:
                lines = io.open(f, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            in_fence = False
            for n, line in enumerate(lines, 1):
                # 代码围栏内是示例/探针，不是文档断言
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                if ph not in line:
                    continue
                if any(m in line for m in RETRACT_MARKERS):
                    continue
                bad.append((f, n, line.strip()))
        if bad:
            total += len(bad)
            print(f"\n[{len(bad)} 处未标注] {ph}")
            for f, n, t in bad:
                print(f"   {f}:{n}")
                print(f"     {t[:120]}")
        elif not quiet:
            print(f"[clean] {ph}")
    return total


def main():
    ap = argparse.ArgumentParser(description="检测被撤回断言在多处副本里的残留")
    ap.add_argument("--phrases", nargs="*", help="要检查的短语（默认用内置撤回清单）")
    ap.add_argument("--quiet", action="store_true", help="只打印有问题项")
    args = ap.parse_args()

    phrases = args.phrases or KNOWN_RETRACTED
    print(f"扫 {len(phrases)} 个短语，范围 {', '.join(SCAN_GLOBS)}")
    n = scan(phrases, quiet=args.quiet)
    print()
    if n:
        print(f"⚠️  {n} 处未标注残留——逐条确认是真残留还是误报（引述别人错误的行是误报）")
        return 1
    print("✅ 无未标注残留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
