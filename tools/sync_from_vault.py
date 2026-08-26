#!/usr/bin/env python3
"""Generate _data/cv.yml from the Obsidian vault master profile, then commit and push.

Source of truth:
    <vault>/career/documents/resume-cv/master-profile.yml

Usage:
    python3 tools/sync_from_vault.py               # generate + commit + push
    python3 tools/sync_from_vault.py --no-push     # generate + commit only
    python3 tools/sync_from_vault.py --dry-run     # print the diff, write nothing
    python3 tools/sync_from_vault.py --profile PATH
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "_data" / "cv.yml"
DEFAULT_PROFILE = (
    Path.home() / "Documents" / "Obsidian Vault"
    / "career" / "documents" / "resume-cv" / "master-profile.yml"
)
HEADER = (
    "# GENERATED FILE — do not edit by hand.\n"
    "# Source: career/documents/resume-cv/master-profile.yml (Obsidian vault)\n"
    "# Regenerate: python3 tools/sync_from_vault.py\n"
)


def find_profile(explicit):
    if explicit:
        return Path(explicit).expanduser()
    if DEFAULT_PROFILE.exists():
        return DEFAULT_PROFILE
    # vault may be mounted elsewhere (e.g. a Cowork session mount)
    for base in (Path.home() / "mnt", Path.home()):
        if base.exists():
            hits = sorted(base.glob("*/career/documents/resume-cv/master-profile.yml"))
            if hits:
                return hits[0]
    return DEFAULT_PROFILE


def build_sections(p):
    """Map master profile lists onto the rendercv section names the cv layout knows."""
    sections = {}

    if p.get("education"):
        sections["Education"] = p["education"]
    if p.get("experience"):
        sections["Experience"] = p["experience"]

    pubs = []
    for e in p.get("publications") or []:
        publisher = e.get("venue", "")
        if e.get("status"):
            publisher = f"{publisher} ({e['status']})".strip()
        entry = {"title": e.get("name", ""), "publisher": publisher}
        if e.get("year"):
            entry["date"] = str(e["year"])
        if e.get("url"):
            entry["url"] = e["url"]
        summary = " ".join(x for x in (e.get("authors"), e.get("summary")) if x)
        if summary:
            entry["summary"] = summary
        pubs.append(entry)
    if pubs:
        sections["Publications"] = pubs

    if p.get("projects"):
        sections["Projects"] = p["projects"]
    if p.get("awards"):
        sections["Awards"] = p["awards"]
    if p.get("skills"):
        sections["Skills"] = p["skills"]
    if p.get("languages"):
        sections["Languages"] = p["languages"]
    return sections


def build_cv(p):
    basics = p.get("basics") or {}
    cv = {
        "name": basics.get("name", ""),
        "label": basics.get("label", ""),
        "email": basics.get("email", ""),
        "location": basics.get("location", ""),
        "image": basics.get("image", ""),
        "summary": basics.get("summary", ""),
    }
    if p.get("socials"):
        cv["social_networks"] = p["socials"]
    cv["sections"] = build_sections(p)
    return {"cv": cv}


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    profile_path = find_profile(args.profile)
    if not profile_path.exists():
        sys.exit(f"master profile not found: {profile_path}")

    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    body = yaml.safe_dump(build_cv(data), allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=100)
    new = HEADER + body

    if args.dry_run:
        sys.stdout.write(new)
        return

    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if old == new:
        print("no change")
        return
    OUT.write_text(new, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} from {profile_path}")

    if args.no_commit:
        return
    git("add", str(OUT.relative_to(REPO)))
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        print("nothing staged")
        return
    r = git("commit", "-m", "chore(cv): sync from vault master profile", check=False)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode:
        sys.exit("commit failed (set git user.name / user.email?)")

    if args.no_push:
        print("committed; push skipped (--no-push)")
        return
    r = git("push", check=False)
    if r.returncode:
        print(r.stderr.strip())
        sys.exit("push failed — run `git push` when the network is available")
    print("pushed")


if __name__ == "__main__":
    main()
