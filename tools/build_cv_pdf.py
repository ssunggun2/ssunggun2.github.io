#!/usr/bin/env python3
"""Build the CV PDF from the Obsidian vault master profile.

Source of truth:
    <vault>/career/documents/resume-cv/master-profile.yml

Renders an HTML CV (Latin Modern, LaTeX-style layout) and prints it to
assets/pdf/SungGeun_AN_CV.pdf with headless Chrome. The fonts ship in
assets/fonts/lm/, so the output is identical on any machine.

Usage:
    python3 tools/build_cv_pdf.py                 # write the PDF
    python3 tools/build_cv_pdf.py --keep-html     # also keep the intermediate HTML
    python3 tools/build_cv_pdf.py --profile PATH
    python3 tools/build_cv_pdf.py --chrome PATH
"""

import argparse
import html
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
FONT_DIR = REPO / "assets" / "fonts" / "lm"
OUT_PDF = REPO / "assets" / "pdf" / "SungGeun_AN_CV.pdf"
DEFAULT_PROFILE = (
    Path.home() / "Documents" / "Obsidian Vault"
    / "career" / "documents" / "resume-cv" / "master-profile.yml"
)

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]
CHROME_NAMES = ["google-chrome", "chromium", "chromium-browser", "chrome"]

MONTHS = ["", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]


# --------------------------------------------------------------------------- helpers

def find_profile(explicit):
    if explicit:
        return Path(explicit).expanduser()
    if DEFAULT_PROFILE.exists():
        return DEFAULT_PROFILE
    for base in (Path.home() / "mnt", Path.home()):
        if base.exists():
            hits = sorted(base.glob("*/career/documents/resume-cv/master-profile.yml"))
            if hits:
                return hits[0]
    return DEFAULT_PROFILE


def find_chrome(explicit):
    if explicit:
        return explicit
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    sys.exit(
        "No Chrome/Chromium found. Install Google Chrome, or pass --chrome PATH."
    )


def fmt_date(value):
    """2024-03 -> 03/2024 ; 2021 -> 2021 ; passthrough for anything else."""
    if value is None:
        return ""
    s = str(value).strip()
    parts = s.split("-")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[1]):02d}/{parts[0]}"
    return s


def span(start, end, sep=" – "):
    a, b = fmt_date(start), fmt_date(end)
    if a and b:
        return f"{a}{sep}{b}"
    return a or b


def esc(text):
    """Escape a plain string. Values that already carry markup are passed through
    by the caller via raw()."""
    return html.escape(str(text), quote=False)


def raw(text):
    """Profile fields may contain a little inline HTML (<em>, <b>) on purpose."""
    return str(text)


# --------------------------------------------------------------------------- sections

def render_head(profile):
    basics = profile.get("basics", {}) or {}
    pdf = profile.get("pdf", {}) or {}
    name = str(basics.get("name", "")).strip()
    given, _, family = name.rpartition(" ")
    if not given:
        given, family = family, ""

    contacts = []
    for c in pdf.get("contacts") or []:
        text, url = esc(c.get("text", "")), c.get("url")
        contacts.append(f'<a href="{url}">{text}</a>' if url else text)
    if not contacts and basics.get("email"):
        contacts = [esc(basics["email"])]

    return (
        f'<h1>{esc(given)} <span class="sur">{esc(family)}</span></h1>\n'
        f'<div class="contact">{"|".join(f"<span>{c}</span>" for c in contacts)}</div>\n'
    )


def render_interests(profile):
    items = (profile.get("pdf", {}) or {}).get("research_interests") or []
    if not items:
        return ""
    lis = "\n".join(f"  <li>{raw(i)}</li>" for i in items)
    return f'<section>\n<h2>Research Interest</h2>\n<ul class="plain">\n{lis}\n</ul>\n</section>\n'


def render_education(profile):
    rows = []
    for e in profile.get("education") or []:
        when = span(e.get("start_date"), e.get("end_date"), sep="<br>– ")
        degree = " ".join(x for x in (e.get("studyType"), "in", e.get("area")) if x) \
            if e.get("area") else e.get("studyType", "")
        notes = "".join(
            f'<div class="note">{raw(h)}</div>' for h in (e.get("highlights") or [])
        )
        rows.append(
            f'  <tr><td class="when">{when}</td><td class="what">'
            f'<div class="org">{esc(e.get("institution", ""))}</div>'
            f'<div class="role">{esc(degree)}</div>{notes}</td></tr>'
        )
    if not rows:
        return ""
    body = "\n".join(rows)
    return f'<section>\n<h2>Education</h2>\n<table class="entries">\n{body}\n</table>\n</section>\n'


def render_experience(profile):
    skips = tuple((profile.get("pdf", {}) or {}).get("experience_highlight_skip") or [])
    rows = []
    for e in profile.get("experience") or []:
        highlights = [
            h for h in (e.get("highlights") or [])
            if not (skips and str(h).lstrip().startswith(skips))
        ]
        bullets = ""
        if highlights:
            lis = "".join(f"<li>{raw(h)}</li>" for h in highlights)
            bullets = f'<ul class="dash">{lis}</ul>'
        place = ", ".join(x for x in (e.get("company"), e.get("location")) if x)
        rows.append(
            f'  <tr><td class="when">{span(e.get("start_date"), e.get("end_date"))}</td>'
            f'<td class="what"><div><span class="org">{esc(e.get("position", ""))}</span></div>'
            f'<div class="role">{esc(place)}</div>{bullets}</td></tr>'
        )
    if not rows:
        return ""
    body = "\n".join(rows)
    return f'<section>\n<h2>Experience</h2>\n<table class="entries">\n{body}\n</table>\n</section>\n'


def render_publications(profile, me):
    items = []
    for p in profile.get("publications") or []:
        venue = p.get("venue", "")
        if p.get("status"):
            venue = f"{venue} ({p['status']})".strip()
        authors = str(p.get("authors", "")).rstrip(".")
        if me and me in authors:
            authors = authors.replace(me, f'<span class="me">{esc(me)}</span>')
        else:
            authors = esc(authors)
        title = esc(p.get("name", ""))
        if p.get("url"):
            title = f'<a href="{p["url"]}">{title}</a>'
        line2 = f'In <span class="venue">{esc(venue)}</span>' if venue else ""
        if p.get("year"):
            line2 = f"{line2}, {p['year']}" if line2 else str(p["year"])
        items.append(
            f'  <li><span class="pubtitle">{title}</span>.<br>'
            f'{line2}.<br>{authors}.</li>'
        )
    if not items:
        return ""
    body = "\n".join(items)
    return f'<section>\n<h2>Publications</h2>\n<ol class="pubs">\n{body}\n</ol>\n</section>\n'


def render_service(profile):
    entries = (profile.get("pdf", {}) or {}).get("service") or []
    rows = []
    for s in entries:
        note = f'<div class="note">{raw(s.get("summary", ""))}</div>' if s.get("summary") else ""
        rows.append(
            f'  <tr><td class="when">{span(s.get("start_date"), s.get("end_date"))}</td>'
            f'<td class="what"><div class="org">{esc(s.get("title", ""))}</div>{note}</td></tr>'
        )
    if not rows:
        return ""
    body = "\n".join(rows)
    return (
        f'<section>\n<h2>Service and Activities</h2>\n'
        f'<table class="entries">\n{body}\n</table>\n</section>\n'
    )


def render_skills(profile):
    rows = []
    for s in profile.get("skills") or []:
        rows.append(
            f'  <tr><td class="slabel">{esc(s.get("name", ""))}</td>'
            f'<td>{esc(s.get("keywords", ""))}</td></tr>'
        )
    langs = profile.get("languages") or []
    if langs:
        text = ", ".join(
            f'{l.get("name", "")} ({str(l.get("summary", "")).lower()})' for l in langs
        )
        rows.append(f'  <tr><td class="slabel">Languages</td><td>{esc(text)}</td></tr>')
    if not rows:
        return ""
    body = "\n".join(rows)
    return f'<section>\n<h2>Skills</h2>\n<table class="skills">\n{body}\n</table>\n</section>\n'


# --------------------------------------------------------------------------- template

def stylesheet():
    def face(filename, weight, style):
        return (
            "  @font-face { font-family: 'LM Roman'; "
            f"src: url('{(FONT_DIR / filename).as_uri()}') format('opentype'); "
            f"font-weight: {weight}; font-style: {style}; }}"
        )

    faces = "\n".join([
        face("lmroman10-regular.otf", "normal", "normal"),
        face("lmroman10-bold.otf", "bold", "normal"),
        face("lmroman10-italic.otf", "normal", "italic"),
        face("lmroman10-bolditalic.otf", "bold", "italic"),
    ])

    return f"""{faces}
  @page {{ size: A4; margin: 18mm 16mm 16mm 16mm; }}
  html {{ -webkit-print-color-adjust: exact; }}
  body {{
    font-family: 'LM Roman', 'Latin Modern Roman', 'TeX Gyre Termes', Georgia, serif;
    font-size: 10.2pt; line-height: 1.32; color: #000; margin: 0;
  }}
  a {{ color: #000; text-decoration: none; }}
  h1 {{ font-size: 24pt; font-weight: normal; text-align: center; margin: 0 0 6pt; letter-spacing: .2pt; }}
  h1 .sur {{ font-weight: bold; }}
  .contact {{ text-align: center; font-size: 9pt; margin-bottom: 16pt; }}
  .contact span {{ margin: 0 6pt; }}
  h2 {{
    font-size: 11pt; font-weight: bold; text-transform: uppercase; letter-spacing: .6pt;
    margin: 15pt 0 0; padding-bottom: 2pt; border-bottom: .8pt solid #000;
    break-after: avoid; page-break-after: avoid;
  }}
  section {{ margin-bottom: 2pt; }}
  table.entries tr, ol.pubs li, table.skills tr {{ break-inside: avoid; page-break-inside: avoid; }}
  ul.plain {{ margin: 4pt 0 0; padding-left: 12pt; }}
  ul.plain li {{ margin-bottom: 1.5pt; }}
  ul.dash {{ margin: 2pt 0 0; padding-left: 12pt; list-style: none; }}
  ul.dash li {{ margin-bottom: 1.5pt; text-indent: -9pt; }}
  ul.dash li:before {{ content: "\\2013"; padding-right: 5pt; }}
  table.entries {{ width: 100%; border-collapse: collapse; margin-top: 5pt; }}
  table.entries td {{ vertical-align: top; padding: 0 0 8pt; }}
  td.when {{ width: 24%; font-size: 9pt; padding-right: 8pt; white-space: nowrap; }}
  td.what .org {{ font-weight: bold; }}
  td.what .role {{ font-style: italic; }}
  td.what .note {{ font-size: 9.4pt; }}
  ol.pubs {{ margin: 5pt 0 0; padding-left: 16pt; }}
  ol.pubs li {{ margin-bottom: 6pt; }}
  .pubtitle {{ font-weight: bold; }}
  .venue {{ font-style: italic; }}
  .me {{ font-weight: bold; }}
  table.skills {{ width: 100%; border-collapse: collapse; margin-top: 5pt; }}
  table.skills td {{ vertical-align: top; padding: 0 0 3pt; }}
  td.slabel {{ width: 24%; font-weight: bold; padding-right: 8pt; }}
"""


def build_html(profile):
    basics = profile.get("basics", {}) or {}
    pdf = profile.get("pdf", {}) or {}
    # Name as it appears in the publications' author strings, which can differ from
    # basics.name ("Sung Geun An" vs "SungGeun AN"). Set pdf.me to control the bolding.
    me = str(pdf.get("me") or basics.get("name", "")).strip()
    body = "".join([
        render_head(profile),
        render_interests(profile),
        render_education(profile),
        render_experience(profile),
        render_publications(profile, me),
        render_service(profile),
        render_skills(profile),
    ])
    title = esc(basics.get("name", "")) + " — CV"
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n<style>\n{stylesheet()}</style>\n</head>\n<body>\n"
        f"{body}</body>\n</html>\n"
    )


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="path to master-profile.yml")
    ap.add_argument("--chrome", help="path to a Chrome/Chromium binary")
    ap.add_argument("--out", help=f"output PDF path (default: {OUT_PDF})")
    ap.add_argument("--keep-html", action="store_true",
                    help="also write the intermediate HTML next to the PDF")
    args = ap.parse_args()

    profile_path = find_profile(args.profile)
    if not profile_path.exists():
        sys.exit(f"master profile not found: {profile_path}")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    missing = [f.name for f in (
        FONT_DIR / "lmroman10-regular.otf", FONT_DIR / "lmroman10-bold.otf",
        FONT_DIR / "lmroman10-italic.otf", FONT_DIR / "lmroman10-bolditalic.otf",
    ) if not f.exists()]
    if missing:
        sys.exit(f"missing fonts in {FONT_DIR}: {', '.join(missing)}")

    out_pdf = Path(args.out).expanduser() if args.out else OUT_PDF
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    markup = build_html(profile)
    if args.keep_html:
        html_path = out_pdf.with_suffix(".html")
        html_path.write_text(markup, encoding="utf-8")
    else:
        html_path = Path(tempfile.mkdtemp(prefix="cvpdf-")) / "cv.html"
        html_path.write_text(markup, encoding="utf-8")

    chrome = find_chrome(args.chrome)
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", f"--print-to-pdf={out_pdf}", html_path.as_uri()],
        check=True, capture_output=True,
    )
    print(f"wrote {out_pdf.relative_to(REPO) if out_pdf.is_relative_to(REPO) else out_pdf}"
          f" from {profile_path}")


if __name__ == "__main__":
    main()
