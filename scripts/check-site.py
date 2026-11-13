#!/usr/bin/env python3
"""Check the static site for broken internal links and missing assets.

The site is plain HTML. Nothing rewrites its links at build time, so a link to
a page that was renamed, or a stylesheet path that drifted, ships broken. This
checks every `href` and `src` that points inside the site, and every in-page
anchor, against the files actually present.

    python3 scripts/check-site.py site

Exit code 0 means every internal link, anchor and asset resolves. External
links are not fetched: a network check would make CI depend on the reachability
of other people's servers.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class PageScanner(HTMLParser):
    """Collects ids, outbound references and structural errors for one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.refs: list[str] = []
        self.errors: list[str] = []
        self._open: list[tuple[str, tuple[int, int]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for key in ("href", "src"):
            value = values.get(key)
            if value:
                self.refs.append(value)
        page_id = values.get("id")
        if page_id:
            self.ids.append(page_id)
        if tag not in VOID:
            self._open.append((tag, self.getpos()))

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if self._open and self._open[-1][0] == tag:
            self._open.pop()
            return
        self.errors.append(f"</{tag}> at line {self.getpos()[0]} does not match")

    def close(self) -> None:  # type: ignore[override]
        super().close()
        for tag, position in self._open:
            self.errors.append(f"<{tag}> opened at line {position[0]} is never closed")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check-site.py <site-directory>", file=sys.stderr)
        return 2

    root = Path(argv[1]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    pages = sorted(root.rglob("*.html"))
    if not pages:
        print(f"no HTML pages under {root}", file=sys.stderr)
        return 2

    scanned: dict[Path, PageScanner] = {}
    problems: list[str] = []

    for page in pages:
        scanner = PageScanner()
        scanner.feed(page.read_text(encoding="utf-8"))
        scanner.close()
        scanned[page] = scanner
        for error in scanner.errors:
            problems.append(f"{page.relative_to(root)}: {error}")

        seen: set[str] = set()
        for page_id in scanner.ids:
            if page_id in seen:
                problems.append(f"{page.relative_to(root)}: duplicate id '{page_id}'")
            seen.add(page_id)

    for page, scanner in scanned.items():
        where = page.relative_to(root)
        for ref in scanner.refs:
            parts = urlsplit(ref)
            if parts.scheme or parts.netloc or ref.startswith(("mailto:", "tel:")):
                continue
            if ref.startswith("#"):
                if parts.fragment and parts.fragment not in scanned[page].ids:
                    problems.append(f"{where}: no element with id '{parts.fragment}'")
                continue

            target = (page.parent / unquote(parts.path)).resolve()
            if not target.exists():
                problems.append(f"{where}: links to missing file '{parts.path}'")
                continue
            if parts.fragment and target.suffix == ".html":
                other = scanned.get(target)
                if other is None:
                    problems.append(f"{where}: anchor into unscanned page '{parts.path}'")
                elif parts.fragment not in other.ids:
                    problems.append(
                        f"{where}: '{parts.path}' has no element with id "
                        f"'{parts.fragment}'"
                    )

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"\n{len(problems)} problem(s) in {len(pages)} page(s)", file=sys.stderr)
        return 1

    print(f"{len(pages)} page(s) checked: all internal links, anchors and assets resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
