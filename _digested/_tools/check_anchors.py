#!/usr/bin/env python3
"""Anchor checker for _digested/ and _faq_on_digested/.

Every `path/to/file.ext:LINE` reference in the research docs is resolved
against the working tree and checked for two failure modes:

  1. NOFILE  -- no file with that basename exists in the tree at all
  2. OOB     -- the file exists but is shorter than the cited line

It is a *bounds* check, not a semantic one: a passing anchor may still
point at the wrong thing. Its job is to catch the cheap, mechanical half
of anchor rot, which is the half that silently accumulates.

Anchor whose target was deliberately deleted upstream can be suppressed
by writing the line reference inside `~~strikethrough~~` or by putting
`（已删除` / `旧基线` on the same line -- those are tombstones, not
claims, and the checker skips any line containing them.

Usage:
    python3 _digested/_tools/check_anchors.py           # report
    python3 _digested/_tools/check_anchors.py --strict  # non-zero on findings
"""

import argparse
import collections
import glob
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DOC_GLOBS = ["_digested/**/*.md", "_faq_on_digested/**/*.md"]

# The tool's own docs quote anchors as examples; don't scan them.
SKIP_DOCS = ("_digested/_tools/",)

# `foo.py:12`, `foo.py:12-34`, `foo.py:12,34`
ANCHOR_RE = re.compile(
    r"`([A-Za-z0-9_\-/\.]+\.(?:py|rs|cpp|h|hpp|toml|json|mjs|js|ts|tsx|sh|sql))"
    r":([0-9]+)(?:[-,]\s*([0-9]+))?`"
)

# A line carrying any of these is a tombstone, not a live claim.
TOMBSTONE_MARKERS = ("~~", "旧基线", "已删除", "被删", "不存在",
                     "旧锚点", "已缩到", "旧分支")

SOURCE_EXTS = (".py", ".rs", ".cpp", ".h", ".hpp", ".toml", ".json",
               ".mjs", ".js", ".ts", ".tsx", ".sh", ".sql")

SKIP_DIR_PARTS = ("/.git", "node_modules", "/build", "/dist", "/target",
                  "/_digested", "/_faq_on_digested", "/.venv", "/__pycache__")


def build_index():
    """basename -> [(path, nlines)] for every source file in the tree."""
    index = collections.defaultdict(list)
    for root, dirs, files in os.walk(REPO):
        rel_root = "/" + os.path.relpath(root, REPO).replace(os.sep, "/")
        if any(part in rel_root for part in SKIP_DIR_PARTS):
            continue
        for name in files:
            if not name.endswith(SOURCE_EXTS):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, REPO)
            try:
                with open(path, "rb") as fh:
                    nlines = sum(1 for _ in fh)
            except OSError:
                nlines = 0
            index[name].append((rel, nlines))
    return index


def check(strict):
    index = build_index()
    docs = []
    for pattern in DOC_GLOBS:
        docs.extend(glob.glob(os.path.join(REPO, pattern), recursive=True))
    docs.sort()

    stats = collections.Counter()
    findings = []

    for doc in docs:
        rel_doc = os.path.relpath(doc, REPO)
        if any(rel_doc.startswith(prefix) for prefix in SKIP_DOCS):
            continue
        with open(doc, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if any(marker in line for marker in TOMBSTONE_MARKERS):
                    stats["skipped_tombstone"] += 1
                    continue
                for match in ANCHOR_RE.finditer(line):
                    cited, first, second = match.group(1), int(match.group(2)), match.group(3)
                    highest = max(first, int(second)) if second else first
                    stats["total"] += 1
                    candidates = index.get(os.path.basename(cited), [])
                    if not candidates:
                        stats["nofile"] += 1
                        findings.append((rel_doc, lineno, cited, highest, "NOFILE"))
                        continue
                    if any(n >= highest for _, n in candidates):
                        stats["ok"] += 1
                        continue
                    stats["oob"] += 1
                    longest = max(candidates, key=lambda item: item[1])
                    findings.append(
                        (rel_doc, lineno, cited, highest,
                         "OOB (longest %s has %d lines)" % (longest[0], longest[1]))
                    )

    print("scanned %d docs" % len(docs))
    for key in ("total", "ok", "oob", "nofile", "skipped_tombstone"):
        print("  %-18s %d" % (key, stats[key]))

    if findings:
        print("\nfindings:")
        for rel_doc, lineno, cited, highest, why in findings:
            print("  %s:%d  %s:%s  -> %s" % (rel_doc, lineno, cited, highest, why))
        if strict:
            return 1
    else:
        print("\nno findings")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero if any anchor is out of bounds")
    sys.exit(check(parser.parse_args().strict))
