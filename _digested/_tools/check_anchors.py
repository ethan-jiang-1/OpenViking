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
    r"`([A-Za-z0-9_\-/.]+\.(?:py|rs|cpp|h|hpp|toml|json|mjs|js|ts|tsx|sh|sql))"
    r":([0-9]+)(?:[-,]\s*([0-9]+))?`"
)

# `foo.py` with NO `:line` suffix. The main check above only sees cited
# anchors, so a wrong path written without a line number was invisible --
# `skills/openviking-memory/SKILL.md` passed for weeks while the real file
# is `agent-plugins/skills/openviking-memory/SKILL.md`. Bare paths get the
# NOFILE / BADPATH treatment, just no line validation.
BARE_PATH_RE = re.compile(
    r"`([A-Za-z0-9_-][A-Za-z0-9_/.-]*\.(?:py|rs|cpp|h|hpp|toml|json|mjs|js|ts|tsx|sh|sql|md))`"
)

# A line carrying any of these is a tombstone, not a live claim.
TOMBSTONE_MARKERS = ("~~", "旧基线", "已删除", "被删", "不存在",
                     "旧锚点", "已缩到", "旧分支", "非死锚", "零命中",
                     "已随", "已腐化")

SOURCE_EXTS = (".py", ".rs", ".cpp", ".h", ".hpp", ".toml", ".json",
               ".mjs", ".js", ".ts", ".tsx", ".sh", ".sql")

SKIP_DIR_PARTS = ("/.git", "node_modules", "/build", "/dist", "/target",
                  "/.venv", "/__pycache__")
# The digest trees hold the docs themselves; they are excluded from the
# *anchor* index (a doc must not cite itself) but the bare-path check needs
# them so that `answer.md`, `research.md` and `_digested/core/...` resolve.
DOC_TREE_PARTS = ("/_digested", "/_faq_on_digested")


def build_index():
    """basename -> [(path, nlines)] for every source file in the tree."""
    index = collections.defaultdict(list)
    for root, dirs, files in os.walk(REPO):
        rel_root = "/" + os.path.relpath(root, REPO).replace(os.sep, "/")
        if any(part in rel_root for part in SKIP_DIR_PARTS):
            continue
        in_doc_tree = any(part in rel_root for part in DOC_TREE_PARTS)
        for name in files:
            if not name.endswith(SOURCE_EXTS + (".md",)):
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
                    base = os.path.basename(cited)
                    candidates = index.get(base, [])
                    if not candidates:
                        stats["nofile"] += 1
                        findings.append((rel_doc, lineno, cited, highest, "NOFILE"))
                        continue
                    # If the citation names directories, at least one real file
                    # must END with that path -- otherwise the doc points at a
                    # directory that does not exist, and basename matching would
                    # silently pass it (e.g. parse/parsers/registry.py).
                    if "/" in cited:
                        tail = cited.lstrip("./")
                        exact = [c for c in candidates
                                 if ("/" + c[0].replace(os.sep, "/").lstrip("./")).endswith("/" + tail)]
                        if not exact:
                            stats["badpath"] += 1
                            findings.append(
                                (rel_doc, lineno, cited, highest,
                                 "BADPATH (no file ends with %s; basename exists at %s)"
                                 % (tail, ", ".join(c[0] for c in candidates[:2])))
                            )
                            continue
                        candidates = exact
                    if any(n >= highest for _, n in candidates):
                        stats["ok"] += 1
                        continue
                    stats["oob"] += 1
                    longest = max(candidates, key=lambda item: item[1])
                    findings.append(
                        (rel_doc, lineno, cited, highest,
                         "OOB (longest %s has %d lines)" % (longest[0], longest[1]))
                    )

                # Bare paths: existence and directory-tail only.
                for match in BARE_PATH_RE.finditer(line):
                    cited = match.group(1)
                    # Skip only when THIS path is cited with a line number
                    # elsewhere on the line; that form is validated above.
                    if re.search(r"`" + re.escape(cited) + r":\d", line):
                        continue
                    stats["bare_total"] += 1
                    base = os.path.basename(cited)
                    candidates = index.get(base, [])
                    if not candidates:
                        stats["bare_nofile"] += 1
                        findings.append((rel_doc, lineno, cited, 0, "NOFILE (bare path)"))
                        continue
                    if "/" in cited:
                        tail = cited.lstrip("./")
                        exact = [c for c in candidates
                                 if ("/" + c[0].replace(os.sep, "/").lstrip("./")).endswith("/" + tail)]
                        if not exact:
                            stats["bare_badpath"] += 1
                            findings.append(
                                (rel_doc, lineno, cited, 0,
                                 "BADPATH (bare; no file ends with %s; basename at %s)"
                                 % (tail, ", ".join(c[0] for c in candidates[:2])))
                            )
                            continue
                    stats["bare_ok"] += 1

    print("scanned %d docs" % len(docs))
    for key in ("total", "ok", "oob", "nofile", "badpath",
                "bare_total", "bare_ok", "bare_nofile", "bare_badpath",
                "skipped_tombstone"):
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
