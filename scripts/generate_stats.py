#!/usr/bin/env python3
"""Generate stats.svg — a self-hosted contribution summary for the profile README.

No third-party services: this asks GitHub's GraphQL API for the contribution
calendar and draws the SVG itself. Standard library only.

Design notes — the point is that this reads as the same object as ascii.svg:
  * the portrait's own grey ink, in both themes
  * a monospace face, matching the portrait's stack
  * transparent background, so it sits on GitHub's surface in either theme
  * the same left-to-right clipPath reveal, with a cursor riding the edge,
    frozen at the end (GitHub strips <script>, so motion must be SMIL)

Env:
  GITHUB_TOKEN  required
  GH_LOGIN      user to summarise (default: andriidrok1)
  OUT           output path (default: stats.svg)
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""

# Portrait ink is the data ink, so chart and portrait read as one material.
LIGHT = dict(data="#6e7681", emph="#424a53", dim="#8c959f", surface="#ffffff")
DARK = dict(data="#c9d1d9", emph="#f0f6fc", dim="#8b949e", surface="#0d1117")
MONO = ("ui-monospace,SFMono-Regular,Menlo,Consolas,"
        "&apos;Liberation Mono&apos;,monospace")

W, H = 620, 148
REVEAL = 1.30           # seconds; matches the portrait's cadence


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": f"{login}-profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    user = payload.get("data", {}).get("user")
    if not user:
        raise SystemExit(f"no such user: {login}")
    return user["contributionsCollection"]["contributionCalendar"]


def summarise(cal):
    weeks = [[d["contributionCount"] for d in w["contributionDays"]]
             for w in cal["weeks"]]
    days = [c for w in weeks for c in w]
    weekly = [sum(w) for w in weeks]
    return dict(total=cal["totalContributions"],
                active=sum(1 for c in days if c > 0),
                best=max(weekly) if weekly else 0,
                weekly=weekly)


def style():
    def block(t):
        return (f".d-f{{fill:{t['data']}}}.d-s{{stroke:{t['data']}}}"
                f".e-f{{fill:{t['emph']}}}.m-f{{fill:{t['dim']}}}"
                f".r{{stroke:{t['surface']}}}")
    return (f"<style>{block(LIGHT)}.w{{fill:{LIGHT['data']};opacity:.13}}"
            f"@media(prefers-color-scheme:dark){{{block(DARK)}"
            f".w{{fill:{DARK['data']};opacity:.16}}}}</style>")


def fade(delay, dur=0.45):
    return (f'<animate attributeName="opacity" from="0" to="1" '
            f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/>')


def render(s):
    weekly = s["weekly"] or [0]
    peak = max(weekly) or 1
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" fill="none" font-family="{MONO}">', style()]

    # the number leads
    p.append(f'<g opacity="0">{fade(0.10)}'
             f'<text x="0" y="50" class="e-f" font-size="52" font-weight="650">'
             f'{s["total"]}</text>'
             f'<text x="0" y="72" class="m-f" font-size="12">'
             f'contributions in the last year</text></g>')
    for i, (val, lab) in enumerate([(s["active"], "active days"),
                                    (s["best"], "best week")]):
        p.append(f'<g opacity="0">{fade(0.30 + i * 0.12)}'
                 f'<text x="{W}" y="{30 + i * 40}" class="e-f" font-size="19" '
                 f'font-weight="600" text-anchor="end">{val}</text>'
                 f'<text x="{W}" y="{47 + i * 40}" class="m-f" font-size="11" '
                 f'text-anchor="end">{lab}</text></g>')

    # weekly sparkline
    base, top = H - 10, H - 58
    span = base - top
    step = W / max(len(weekly) - 1, 1)
    pts = [(i * step, base - (v / peak) * span) for i, v in enumerate(weekly)]

    p.append(f'<clipPath id="rc"><rect x="0" y="{top - 6}" height="{span + 8}" '
             f'width="0"><animate attributeName="width" from="0" to="{W}" '
             f'begin="0.50s" dur="{REVEAL}s" fill="freeze"/></rect></clipPath>')
    p.append('<g clip-path="url(#rc)">')
    area = (f'M{pts[0][0]:.1f} {base:.1f}'
            + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts)
            + f'L{pts[-1][0]:.1f} {base:.1f}Z')
    p.append(f'<path d="{area}" class="w"/>')
    line = (f'M{pts[0][0]:.1f} {pts[0][1]:.1f}'
            + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts[1:]))
    p.append(f'<path d="{line}" class="d-s" stroke-width="2" '
             f'stroke-linejoin="round" stroke-linecap="round"/>')
    p.append("</g>")

    # cursor rides the wipe edge, then goes away — same trick as the portrait
    p.append(f'<rect y="{top - 6}" width="2" height="{span + 8}" class="d-f" '
             f'opacity="0"><animate attributeName="x" from="0" to="{W}" '
             f'begin="0.50s" dur="{REVEAL}s" fill="freeze"/>'
             f'<set attributeName="opacity" to="0.55" begin="0.50s"/>'
             f'<set attributeName="opacity" to="0" '
             f'begin="{0.50 + REVEAL:.2f}s"/></rect>')

    # the latest week gets the one marker, with a ring in the surface colour
    ex, ey = pts[-1]
    p.append(f'<circle cx="{ex - 2:.1f}" cy="{ey:.1f}" r="4.5" '
             f'class="e-f r" stroke-width="2" opacity="0">'
             f'{fade(0.50 + REVEAL, 0.35)}</circle>')

    p.append("</svg>")
    return "".join(p)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    login = os.environ.get("GH_LOGIN", "andriidrok1")
    out = os.environ.get("OUT", "stats.svg")

    s = summarise(fetch(login, token))
    svg = render(s)

    old = ""
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            old = f.read()
    if old == svg:
        print(f"{out} already current — {s['total']} contributions")
        return
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out} — {s['total']} contributions, "
          f"{s['active']} active days, best week {s['best']}")


if __name__ == "__main__":
    main()
