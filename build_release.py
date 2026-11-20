# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Richard Bejtlich
"""Build the release zip and its SHA-256 checksum file (adapted from papyrus-log-check's build_release.py).

  python -I build_release.py                 build dist/sf-test-plan-<version>.zip (+ .sha256)
  python -I build_release.py --tag v0.1.0    the same, but first check that the tag matches VERSION in
                                             sftestplan/model.py and that CHANGELOG.md has a dated entry for it

Also writes build/release-notes.md (the CHANGELOG entry), used as the GitHub release text.
The zip holds one folder, sf-test-plan-<version>/, with fixed file times, Unix "made on" system, mode 0644 and no
compression, so the same commit gives the same zip on any system. Files come from the commit (git show HEAD:<file>);
a working tree with changes to shipped files is refused (--allow-dirty builds from disk, for trying things out).
Shipped files: every tracked file except the private ones (the same list sync_public.py keeps out), the
build helpers' outputs and the repo's CI setup (.github/).
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NEVER_FILES = {"WORKPLAN.md", "NOTES.md", "sync_public.py", ".gitignore"}
NEVER_DIRS = ("tools/", ".github/")
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def git(*args):
    return subprocess.run(["git", "-C", HERE, *args], capture_output=True, check=True).stdout


def shipped():
    files = [f for f in git("ls-files", "-z").decode("utf-8").split("\0") if f]
    return sorted(f for f in files if f.rsplit("/", 1)[-1] not in NEVER_FILES and not f.startswith(NEVER_DIRS))


def dirty_files(files):
    out = git("status", "--porcelain", "--", *files).decode("utf-8", "replace")
    return [line[3:] for line in out.splitlines() if line.strip()]


def version():
    with open(os.path.join(HERE, "sftestplan", "model.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M)
    if not m:
        raise SystemExit("VERSION not found in sftestplan/model.py")
    return m.group(1)


def changelog_entry(ver):
    with open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^## {re.escape(ver)}\b([^\n]*)\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no entry for {ver}")
    return m.group(1).strip(), m.group(2).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="the git tag being released, e.g. v0.1.0")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="build from the files on disk, uncommitted changes included (never for a release)")
    args = ap.parse_args()
    if args.allow_dirty and args.tag:
        raise SystemExit("--allow-dirty can't be used with --tag: a release is built from the commit")
    files = shipped()
    if not args.allow_dirty:
        dirty = dirty_files(files)
        if dirty:
            raise SystemExit("these shipped files have uncommitted changes: " + ", ".join(dirty) +
                             ". Commit them first (or use --allow-dirty to try a build).")
    ver = version()
    heading, notes = changelog_entry(ver)
    if args.tag is not None:
        if args.tag != "v" + ver:
            raise SystemExit(f"tag {args.tag} doesn't match VERSION {ver} (expected v{ver})")
        if "not yet released" in heading.lower() or not re.search(r"\d{4}-\d\d-\d\d", heading):
            raise SystemExit(f"CHANGELOG.md entry for {ver} needs a release date, e.g. '## {ver} (2026-11-20)'")

    dist = os.path.join(HERE, "dist")
    build = os.path.join(HERE, "build")
    os.makedirs(dist, exist_ok=True)
    os.makedirs(build, exist_ok=True)
    top = f"sf-test-plan-{ver}"
    zpath = os.path.join(dist, top + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        for rel in files:
            if args.allow_dirty:
                with open(os.path.join(HERE, rel), "rb") as f:
                    data = f.read()
            else:
                data = git("show", f"HEAD:{rel}")
            info = zipfile.ZipInfo(f"{top}/{rel}", FIXED_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o100755 if rel == "sf-test-plan" else 0o100644) << 16  # the Linux launcher runs
            z.writestr(info, data)
    with open(zpath, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(zpath + ".sha256", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest}  {os.path.basename(zpath)}\n")
    with open(os.path.join(build, "release-notes.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(notes + "\n\n" + f"SHA-256 of `{os.path.basename(zpath)}`: `{digest}`\n")
    print(zpath)
    print(f"SHA-256 {digest}")
    print(f"{len(files)} files: " + ", ".join(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
