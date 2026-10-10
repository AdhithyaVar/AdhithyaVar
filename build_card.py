#!/usr/bin/env python3
"""Render the neofetch-style profile card: dark_mode.svg and light_mode.svg.

    python build_card.py            live numbers; needs ACCESS_TOKEN and USER_NAME in the environment
    python build_card.py --offline  no network: last cached numbers, or "--" where there are none yet
    python build_card.py --demo     made-up numbers, written to ./preview (the real SVGs stay untouched)

What goes on the card is edited in config.py. The portrait comes from make_ascii.py.
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import sys
from dataclasses import asdict
from datetime import date
from html import escape
from pathlib import Path

import config
from github_stats import Client, GitHubError, Stats, fetch_stats

ROOT = Path(__file__).resolve().parent
STATS_CACHE = ROOT / "cache" / "stats.json"
LOC_CACHE = ROOT / "cache" / "loc.json"

COLS = 62      # characters per line of the info panel
MIN_DOTS = 2   # a dotted leader shorter than this means the line is too long

# Layout in px. A monospace glyph advances ~0.6 em. Every line is pinned to that grid with textLength,
# so the card looks the same in Consolas (narrower) as in Menlo or DejaVu Sans Mono.
ADVANCE = 0.6
ART_FONT, ART_LINE = 10, 12
PANEL_FONT, PANEL_LINE = 14, 20
PAD, GAP = 24, 28

FONT = "Consolas,'SF Mono',Menlo,'DejaVu Sans Mono','Liberation Mono','Courier New',monospace"

# GitHub's own palette in both modes
THEMES = {
    "dark": dict(bg="#161b22", border="#30363d", text="#c9d1d9", key="#ffa657", val="#a5d6ff",
                 dim="#616e7f", add="#3fb950", rem="#f85149", art="#b1bac4"),
    "light": dict(bg="#f6f8fa", border="#d0d7de", text="#24292f", key="#953800", val="#0a3069",
                  dim="#aab4bf", add="#1a7f37", rem="#cf222e", art="#57606a"),
}

STYLE = """\
text{{font-family:{font};white-space:pre}}
.art{{font-size:{art_font}px;fill:{art}}}
.p{{font-size:{panel_font}px;fill:{text}}}
.key{{fill:{key}}}
.val{{fill:{val}}}
.dim{{fill:{dim}}}
.add{{fill:{add}}}
.rem{{fill:{rem}}}
.head{{fill:{key};font-weight:bold}}"""

DEMO = Stats(repos=48, contributed=12, stars=157, commits=2481, followers=64, loc_add=186420, loc_del=71385)

# A line is a list of (css class, text) segments. Class "txt" means plain panel text.
Line = "list[tuple[str, str]]"


class CardError(Exception):
    """The card can't be drawn the way config.py describes it."""


# ----------------------------------------------------------------------------- small helpers

def seg_len(segs) -> int:
    return sum(len(text) for _, text in segs)


def fmt(n) -> str:
    return "--" if n is None else f"{n:,}"


def compact(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.0f}K"
    return f"{n:,}"


def add_months(d: date, months: int) -> date:
    year, month = divmod(d.year * 12 + d.month - 1 + months, 12)
    month += 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def uptime_text(since: date, today: date) -> str:
    """'4 years, 2 months, 8 days' between two dates (month ends handled by clamping)."""
    if since >= today:
        return "0 days"
    months = (today.year - since.year) * 12 + today.month - since.month
    if add_months(since, months) > today:
        months -= 1
    days = (today - add_months(since, months)).days
    years, months = divmod(months, 12)
    parts = ((years, "year"), (months, "month"), (days, "day"))
    return ", ".join(f"{n} {unit}{'' if n == 1 else 's'}" for n, unit in parts)


# ----------------------------------------------------------------------------- the info panel

def leader(key: str, value, width: int, prefix: str = ". "):
    """prefix + key + ': ' + dots + ' ' + value, exactly `width` characters wide."""
    dots = width - len(prefix) - len(key) - 3 - seg_len(value)
    if dots < MIN_DOTS:
        raise CardError(f'"{key}" is too long for the {width}-character panel - shorten its value in config.py')
    head = [("dim", prefix)] if prefix else []
    return head + [("key", key), ("txt", ":"), ("dim", " " + "." * dots + " ")] + value


def title_line(title: str):
    fill = COLS - len(title) - 3
    if fill < MIN_DOTS:
        raise CardError(f'section title "{title}" is too long for the {COLS}-character panel')
    return [("dim", "- "), ("txt", title), ("dim", " " + "-" * fill)]


def loc_line(s: Stats):
    key = "Lines of Code on GitHub"
    if s.loc_net is None:
        return leader(key, [("val", "--")], COLS)
    net, add, rem = s.loc_net, s.loc_add, s.loc_del

    def detail(f):
        return [("val", fmt(net)), ("txt", " ( "), ("add", f"{f(add)}++"), ("txt", ", "),
                ("rem", f"{f(rem)}--"), ("txt", " )")]

    # full numbers, then 1.4M-style, then just the net total: first one that fits wins
    for value in (detail(fmt), detail(compact), [("val", fmt(net))]):
        try:
            return leader(key, value, COLS)
        except CardError:
            continue
    raise CardError("Lines of Code does not fit the panel")


def short(n) -> str:
    return "--" if n is None else compact(n)


def stat_items(s: Stats, f) -> dict:
    """The four counters as {key: value segments}; f formats the numbers."""
    def num(n):
        return [("val", f(n))]

    repos = num(s.repos) + [("txt", " {"), ("key", "Contributed"), ("txt", ": "),
                            ("val", f(s.contributed)), ("txt", "}")]
    return {"Repos": repos, "Stars": num(s.stars), "Commits": num(s.commits), "Followers": num(s.followers)}


def stats_lines(s: Stats):
    """Repos | Stars and Commits | Followers side by side. If big numbers don't fit, 1.2M-style numbers;
    if they still don't, one counter per line. The nightly build must never fail because a number grew."""
    sep = " | "
    for f in (fmt, short):
        it = stat_items(s, f)
        rows = [(("Repos", it["Repos"]), ("Stars", it["Stars"])),
                (("Commits", it["Commits"]), ("Followers", it["Followers"]))]
        left_need = max(2 + len(k) + 3 + seg_len(v) for (k, v), _ in rows)
        right_need = max(len(k) + 3 + seg_len(v) for _, (k, v) in rows)
        spare = COLS - len(sep) - left_need - right_need
        if spare >= 2 * MIN_DOTS:
            left_w = left_need + spare // 2
            right_w = COLS - len(sep) - left_w
            lines = [leader(lk, lv, left_w) + [("txt", sep)] + leader(rk, rv, right_w, prefix="")
                     for (lk, lv), (rk, rv) in rows]
            break
    else:
        lines = [leader(k, v, COLS) for k, v in stat_items(s, fmt).items()]
    lines.append(loc_line(s))
    return lines


def build_lines(stats: Stats, today: date):
    uptime = uptime_text(config.UPTIME_SINCE, today)
    head = config.HEADER
    if len(head) + 1 + MIN_DOTS > COLS:
        raise CardError("HEADER is too long for the info panel")
    lines = [[("head", head), ("dim", " " + "-" * (COLS - len(head) - 1))]]
    for item in config.INFO:
        if item is None:
            lines.append([])
        elif item == "@stats":
            lines.extend(stats_lines(stats))
        elif isinstance(item, str):
            lines.append(title_line(item))
        else:
            key, value = item
            lines.append(leader(key, [("val", value.replace("{uptime}", uptime))], COLS))
    for line in lines:
        if seg_len(line) > COLS:
            raise CardError(f"a line is {seg_len(line)} characters, the panel holds {COLS}")
    return lines


# ----------------------------------------------------------------------------- the portrait

def clean(row: str) -> str:
    return "".join(ch if ch.isprintable() else " " for ch in row).rstrip()


def read_art(name: str):
    try:
        text = (ROOT / name).read_text(encoding="utf-8-sig")
    except OSError:
        return None
    rows = [clean(r) for r in text.expandtabs(4).splitlines()]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    if any(ord(ch) > 126 for r in rows for ch in r):
        print(f"note: {name} has non-ASCII characters; they may not line up in every font")
    return rows or None


# ----------------------------------------------------------------------------- SVG

def markup(segs) -> str:
    out = []
    for cls, text in segs:
        safe = escape(text, quote=False)
        out.append(safe if cls == "txt" else f'<tspan class="{cls}">{safe}</tspan>')
    return "".join(out)


def render(theme: str, art, lines):
    c = THEMES[theme]
    art = art or []
    gap = GAP if art else 0
    art_w = max((len(r) for r in art), default=0) * ART_FONT * ADVANCE
    art_h = len(art) * ART_LINE
    panel_w = COLS * PANEL_FONT * ADVANCE
    panel_h = len(lines) * PANEL_LINE
    inner_h = max(art_h, panel_h)
    width = math.ceil(PAD + art_w + gap + panel_w + PAD)
    height = math.ceil(inner_h + 2 * PAD)
    art_top = PAD + (inner_h - art_h) / 2
    panel_x = PAD + art_w + gap
    panel_top = PAD + (inner_h - panel_h) / 2

    body = []
    for i, row in enumerate(art):
        if row:
            y = art_top + i * ART_LINE + ART_LINE * 0.78
            body.append(f'<text class="art" x="{PAD}" y="{y:.1f}" '
                        f'textLength="{len(row) * ART_FONT * ADVANCE:.1f}" lengthAdjust="spacing">'
                        f'{escape(row, quote=False)}</text>')
    for i, segs in enumerate(lines):
        if segs:
            y = panel_top + i * PANEL_LINE + PANEL_LINE * 0.72
            body.append(f'<text class="p" x="{panel_x:.1f}" y="{y:.1f}" '
                        f'textLength="{seg_len(segs) * PANEL_FONT * ADVANCE:.1f}" lengthAdjust="spacing">'
                        f'{markup(segs)}</text>')

    style = STYLE.format(font=FONT, art_font=ART_FONT, panel_font=PANEL_FONT, **c)
    svg = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" xml:space="preserve" role="img" aria-labelledby="card-title">',
        f'<title id="card-title">{escape(config.HEADER)} - GitHub profile card</title>',
        f"<style>\n{style}\n</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" '
        f'fill="{c["bg"]}" stroke="{c["border"]}"/>',
        *body,
        "</svg>",
        "",
    ])
    return svg, width, height


# ----------------------------------------------------------------------------- stats cache + main

def load_stats():
    try:
        return Stats(**json.loads(STATS_CACHE.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def save_stats(stats: Stats) -> None:
    STATS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    STATS_CACHE.write_text(json.dumps(asdict(stats), indent=1) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the profile card SVGs.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true",
                      help='no network: use the last cached numbers, or "--" if there are none')
    mode.add_argument("--demo", action="store_true",
                      help="made-up numbers, written to ./preview so the real SVGs are not touched")
    args = ap.parse_args(argv)

    try:
        if args.demo:
            stats, out = DEMO, ROOT / "preview"
        elif args.offline:
            stats, out = load_stats() or Stats(), ROOT
        else:
            token, user = os.environ.get("ACCESS_TOKEN"), os.environ.get("USER_NAME")
            if not (token and user):
                raise CardError("set ACCESS_TOKEN and USER_NAME for live numbers (or use --offline / --demo)")
            stats = fetch_stats(Client(token), user, affiliations=config.LOC_AFFILIATIONS,
                                include_forks=config.LOC_INCLUDE_FORKS, loc_cache=LOC_CACHE,
                                previous=load_stats())
            save_stats(stats)
            out = ROOT

        lines = build_lines(stats, date.today())
        art_light = read_art(config.ASCII_LIGHT)
        art_dark = read_art(config.ASCII_DARK) or art_light
        art_light = art_light or art_dark
        if art_dark is None:
            print("note: no portrait found in assets/, drawing the card without one (see make_ascii.py)")

        out.mkdir(parents=True, exist_ok=True)
        for theme, art in (("dark", art_dark), ("light", art_light)):
            svg, w, h = render(theme, art, lines)
            target = out / f"{theme}_mode.svg"
            target.write_text(svg, encoding="utf-8")
            print(f"wrote {os.path.relpath(target)}  ({w}x{h}px)")
    except (CardError, GitHubError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
