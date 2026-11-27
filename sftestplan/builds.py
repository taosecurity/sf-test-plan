"""Compare a tested mod zip with a new build (compare-builds, check-build).

Read only. Plugin entries (.esm, .esp, .esl, .ba2) are compared by CRC-32 and size first. A .ba2 that differs is
copied, one at a time, to a temporary file and opened: each file inside is compared by its unpacked content, and a
.pex script is compared by meaning (pex.listing: compile time and string-table order ignored), so a recompile of the
same source still matches. A loose .pex is compared the same way. A script that listing() can't read is compared by its bytes with the compile time zeroed. Every other file entry (an SFSE DLL, an .ini, an interface file) is compared by CRC-32, size and sha256, except, in a zip that has a plugin, documents (.txt, .md, .pdf and the like), pictures (.png, .jpg), a fomod
folder, extensionless readme and license files and OS junk (__MACOSX, Thumbs.db).
"""
from __future__ import annotations

import hashlib
import json
import logging
import lzma
import os
import re
import shutil
import struct
import tempfile
import zipfile
import zlib

from . import pex
from .model import SetupError

log = logging.getLogger("sf-test-plan")

PLUGIN_EXTS = (".esm", ".esp", ".esl", ".ba2")
# Beside a plugin these may change between builds without changing the mod: documents, pictures, a fomod
# installer folder, extensionless readme and license files, and the junk files macOS and Windows add.
DOC_EXTS = (".txt", ".md", ".rtf", ".pdf", ".url", ".html", ".htm", ".docx",
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
_DOC_NAMES = {"readme", "license", "licence", "changelog", "changes", "credits", "copying", "authors",
              "thumbs.db", "desktop.ini", ".ds_store"}
PINS_FORMAT = "sf-test-plan-pins/1"
COMPARE_FORMAT = "sf-test-plan-compare/1"
_SHA16 = re.compile(r"[0-9a-f]{16}")
_CHUNK = 1 << 20
_PEX_MAGIC = (b"\xde\xc0\x57\xfa", b"\xfa\x57\xc0\xde")
_PEX_MAX = 16 << 20   # a script larger than this is compared by bytes, without reading it whole


class BA2Unreadable(Exception):
    """The archive can't be opened by this reader; it is then compared as a whole file."""


# ---------------------------------------------------------------- zips
def _open_zip(path: str, which: str) -> zipfile.ZipFile:
    if not os.path.isfile(path):
        raise SetupError(f"the {which} zip {path} doesn't exist. Give the path to a mod zip.")
    try:
        return zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise SetupError(f"can't read the {which} zip {path}: {e}. Give the path to a mod zip.")


def zip_entries(zf: zipfile.ZipFile, every_file: bool = False) -> dict:
    """{name (lower case, forward slashes): ZipInfo} for the plugin entries and loose .pex scripts (every file
    entry with every_file, which compare-builds always passes)."""
    out = {}
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir() or name.endswith("/") or not (every_file or name.lower().endswith(PLUGIN_EXTS + (".pex",))):
            continue
        out[name.lower()] = info
    return out


def _is_packaging(key: str) -> bool:
    """A document, picture, fomod or OS junk entry (key: lower case, forward slashes), ignored beside a plugin."""
    parts = key.split("/")
    return (key.endswith(DOC_EXTS) or parts[-1] in _DOC_NAMES or "fomod" in parts[:-1]
            or parts[0] == "__macosx")


def _has_plugin(entries: dict) -> bool:
    return any(k.endswith(PLUGIN_EXTS) for k in entries)


def _pex_digest(h, data: bytes, name: str) -> str:
    """Add a script to the hash by meaning (pex.listing), or by its bytes with the compile time zeroed."""
    try:
        h.update("\n".join(pex.listing(data)).encode("utf-8"))   # by meaning: string-table order ignored
        return h.hexdigest()[:16]
    except pex.PexError as err:
        log.debug("%s: compared by bytes (compile time zeroed) because %s", name, err)
    if len(data) >= 16 and data[:4] in _PEX_MAGIC:
        data = data[:8] + b"\0" * 8 + data[16:]   # zero the compile time
    h.update(data)
    return h.hexdigest()[:16]


def _loose_pex_digest(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str | None:
    """A loose script's digest by meaning, or None when it is too large to read whole."""
    if info.file_size > _PEX_MAX:
        return None
    return _pex_digest(hashlib.sha256(), zf.read(info), info.filename)


def _sha16(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    h = hashlib.sha256()
    with zf.open(info) as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- BA2
def _read(f, n: int) -> bytes:
    raw = f.read(n)
    if len(raw) != n:
        raise BA2Unreadable("it ends early")
    return raw


def _ba2_entries(f, size: int):
    """(method, entries) for a BTDX archive. Entry: dict with name, chunks [(offset, packed, size)], tex (DX10 fields or None)."""
    magic, version, kind, count, names_at = struct.unpack("<4sI4sIQ", _read(f, 24))
    if magic != b"BTDX":
        raise BA2Unreadable("it is not a BA2 archive (no BTDX header)")
    if version not in (1, 2, 3, 7, 8):
        raise BA2Unreadable(f"it is BA2 version {version}, which this tool doesn't know")
    method = 0
    if version in (2, 3):
        _read(f, 8)
        if version == 3:
            (method,) = struct.unpack("<I", _read(f, 4))
    if kind not in (b"GNRL", b"DX10"):
        raise BA2Unreadable(f"its type {kind!r} is not GNRL or DX10")
    if count * 24 > size or names_at > size:
        raise BA2Unreadable("its header gives more files than it can hold")
    entries = []
    for _ in range(count):
        if kind == b"GNRL":
            _h, _ext, _d, _fl, off, packed, usize, _a = struct.unpack("<I4sIIQIII", _read(f, 36))
            entries.append({"chunks": [(off, packed, usize)], "tex": None})
        else:
            _h, _ext, _d, _u, n_chunks, chunk_hdr, height, width, mips, fmt, cube, _t = struct.unpack(
                "<I4sIBBHHHBBBB", _read(f, 24))
            chunks = []
            for _ in range(n_chunks):
                off, packed, usize, _s, _e, _a = struct.unpack_from("<QIIHHI", _read(f, max(chunk_hdr, 24)))
                chunks.append((off, packed, usize))
            entries.append({"chunks": chunks, "tex": (height, width, mips, fmt, cube)})
    f.seek(names_at)
    for e in entries:
        (n,) = struct.unpack("<H", _read(f, 2))
        e["name"] = pex.text(_read(f, n)).replace("\\", "/").lower()   # bytes kept; case folded as the game does
    return method, entries


def _unpacked_chunks(f, method: int, chunks, size: int):
    """Yield each chunk's unpacked bytes (zlib); raise BA2Unreadable for LZ4 or a bad block."""
    for off, packed, usize in chunks:
        stored = packed or usize
        if off + stored > size:
            raise BA2Unreadable("a file inside points past its end")
        f.seek(off)
        if not packed:
            remaining = usize
            while remaining:
                part = _read(f, min(_CHUNK, remaining))
                remaining -= len(part)
                yield part
            continue
        if method == 3:
            raise BA2Unreadable("it is LZ4-packed, which this tool can't unpack")
        d = zlib.decompressobj()
        out = 0
        try:
            remaining = packed
            while remaining:
                raw = _read(f, min(_CHUNK, remaining))
                remaining -= len(raw)
                data = d.decompress(raw, usize - out + 1)
                while True:
                    out += len(data)
                    if out > usize:
                        raise BA2Unreadable("a packed file inside unpacks to more than its stated size")
                    if data:
                        yield data
                    if not d.unconsumed_tail:
                        break
                    data = d.decompress(d.unconsumed_tail, usize - out + 1)
            data = d.flush()
            out += len(data)
            if data:
                yield data
        except zlib.error as e:
            raise BA2Unreadable(f"a packed file inside can't be unpacked ({e})")
        if out != usize:
            raise BA2Unreadable("a packed file inside unpacks to a size other than its stated size")


def _entry_digest(f, method: int, e, size: int) -> str:
    h = hashlib.sha256()
    if e["tex"] is not None:
        h.update(repr(e["tex"]).encode("ascii"))
    stated = sum(c[2] for c in e["chunks"])
    if e["name"].endswith(".pex") and stated <= _PEX_MAX:
        return _pex_digest(h, b"".join(_unpacked_chunks(f, method, e["chunks"], size)), e["name"])
    for data in _unpacked_chunks(f, method, e["chunks"], size):
        h.update(data)
    return h.hexdigest()[:16]


def ba2_digests(path: str) -> dict:
    """{file inside (lower case): digest} for a BA2 file on disk. Raises BA2Unreadable."""
    size = os.path.getsize(path)
    try:
        with open(path, "rb") as f:
            method, entries = _ba2_entries(f, size)
            return {e["name"]: _entry_digest(f, method, e, size) for e in entries}
    except struct.error:
        raise BA2Unreadable("its header is cut short")


def _ba2_digests_in_zip(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict:
    tmp = tempfile.mkdtemp(prefix="sf-test-plan-ba2-")
    try:
        arc = os.path.join(tmp, "a.ba2")
        with zf.open(info) as src, open(arc, "wb") as dst:
            shutil.copyfileobj(src, dst, _CHUNK)
        return ba2_digests(arc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- pins
def load_pins(path: str | None) -> dict:
    """{file name without its folder (lower case): (tested sha16, built sha16, why)} from a --pins file."""
    if not path:
        return {}
    fix = f'Give a JSON file like {{"format": "{PINS_FORMAT}", "pins": {{"mymod.esm": {{"tested": "<16 hex>", ' \
          '"built": "<16 hex>", "why": "<text>"}}}.'
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise SetupError(f"can't read the --pins file {path}: {e.strerror}. {fix}")
    except (ValueError, UnicodeDecodeError) as e:
        raise SetupError(f"the --pins file {path} is not valid JSON ({e}). {fix}")
    if not isinstance(data, dict) or data.get("format") != PINS_FORMAT:
        raise SetupError(f"the --pins file {path} has no \"format\": \"{PINS_FORMAT}\". {fix}")
    pins = data.get("pins")
    if not isinstance(pins, dict):
        raise SetupError(f"the --pins file {path} has no \"pins\" object. {fix}")
    out = {}
    for name, pin in pins.items():
        ok = isinstance(pin, dict) and all(isinstance(pin.get(k), str) for k in ("tested", "built", "why"))
        if not ok or not _SHA16.fullmatch(pin["tested"].lower()) or not _SHA16.fullmatch(pin["built"].lower()):
            raise SetupError(f"the --pins file {path} has a bad pin for {name!r}: it needs \"tested\" and \"built\" "
                             f"(16 hex digits each, the start of the file's sha256) and \"why\" (text). {fix}")
        key = name.replace("\\", "/").rsplit("/", 1)[-1].lower()   # a key copied with its folder works too
        out[key] = (pin["tested"].lower(), pin["built"].lower(), pin["why"])
    return out


# ---------------------------------------------------------------- compare
def compare(tested: str, built: str, pins: dict | None = None) -> dict:
    """The compare-builds result (the --json shape): same, problems, warnings, entries."""
    try:
        return _compare(tested, built, pins or {})
    except (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError, NotImplementedError, RuntimeError) as e:
        raise SetupError(f"can't read a file inside {tested} or {built}: {e}. Check that both are whole, "
                         "unencrypted mod zips.")
    except OSError as e:
        raise SetupError(f"can't read {tested} or {built}, or write a temporary file: {e.strerror or e}.")


def _compare(tested: str, built: str, pins: dict) -> dict:
    problems, warnings, entries = [], [], []
    with _open_zip(tested, "tested") as za, _open_zip(built, "built") as zb:
        a, b = zip_entries(za, True), zip_entries(zb, True)   # every file: plugins, scripts, DLLs and the rest
        every_file = not _has_plugin(a) and not _has_plugin(b)
        if every_file:
            log.debug("no plugin files in either zip: comparing every file")
            if not a and not b:
                problems.append("Both zips are empty, so there is nothing to compare.")
        else:   # a zip with a plugin: documents, pictures and a fomod folder may change between builds, the rest may not
            a = {k: v for k, v in a.items() if not _is_packaging(k)}
            b = {k: v for k, v in b.items() if not _is_packaging(k)}
            log.debug("comparing %d and %d files (documents, pictures and fomod files left out)", len(a), len(b))

        def add(name, status, detail=""):
            entries.append({"name": name, "status": status, "detail": detail})

        for key in sorted(set(a) | set(b)):
            name = (a.get(key) or b.get(key)).filename.replace("\\", "/")
            base = key.rsplit("/", 1)[-1]
            if key not in b:
                add(name, "only in tested")
                problems.append(f"The tested zip has {name}, but the built zip does not.")
                continue
            if key not in a:
                add(name, "only in built")
                problems.append(f"The built zip has {name}, but the tested zip does not.")
                continue
            ia, ib = a[key], b[key]
            if (ia.CRC, ia.file_size) == (ib.CRC, ib.file_size):
                add(name, "same")
                continue
            sa, sb = _sha16(za, ia), _sha16(zb, ib)
            if sa == sb:
                add(name, "same")
                continue
            detail = f"the tested zip's copy has sha256 {sa}, and the built zip's copy has {sb}"
            if key.endswith(".pex"):
                pa, pb = _loose_pex_digest(za, ia), _loose_pex_digest(zb, ib)
                if pa is not None and pa == pb:
                    add(name, "same", "the script does the same (compared by meaning)")
                    continue
            elif key.endswith(".ba2"):
                try:
                    da, db = _ba2_digests_in_zip(za, ia), _ba2_digests_in_zip(zb, ib)
                except BA2Unreadable as e:
                    log.debug("%s: compared as a whole file: %s", name, e)
                    detail = f"the archive was compared as a whole file because {e}; {detail}"
                else:
                    diff = sorted(k for k in set(da) | set(db) if da.get(k) != db.get(k))
                    if not diff:
                        add(name, "same", "the files inside match (scripts compared by meaning)")
                        continue
                    shown = ", ".join(diff[:5]) + (f" and {len(diff) - 5} more" if len(diff) > 5 else "")
                    detail = f"{len(diff)} of its files differ ({shown}); {detail}"
            pin = pins.get(base)
            if pin and pin[0] == sa and pin[1] == sb:
                add(name, "pinned", pin[2])
                warnings.append(f"{name} differs, but the --pins file allows this exact pair: {pin[2]}")
                continue
            add(name, "differs", detail)
            problems.append(f"{name} differs: {detail}.")
    n_diff = sum(1 for e in entries if e["status"] in ("differs", "only in tested", "only in built"))
    return {"format": COMPARE_FORMAT, "same": not problems, "problems": problems, "warnings": warnings,
            "entries": entries, "differ": n_diff, "total": len(entries), "every_file": every_file}


def ok_line(result: dict) -> str:
    what = "files" if result.get("every_file") else "plugins, scripts and other files"
    return f"OK: the built zip has the same {what} as the tested zip."


def print_report(result: dict) -> None:
    for e in result["entries"]:
        detail = f": {e['detail']}" if e["detail"] else ""
        print(f"{e['name']}: {e['status']}{detail}")
    for w in result["warnings"]:
        print(f"WARNING: {w}")
    if result["same"]:
        print(ok_line(result))
    elif not result["entries"]:
        print(f"DIFFERENT: {result['problems'][0]}")
    else:
        print(f"DIFFERENT: {result['differ']} of {result['total']} files differ.")


def as_json(result: dict) -> str:
    keep = ("format", "same", "problems", "warnings", "entries")
    return json.dumps({k: result[k] for k in keep}, indent=2, ensure_ascii=False)


def tested_zip_from_plan(plan_path: str, zip_value: str) -> str:
    """The plan's zip: value, resolved against the plan's own folder unless it is absolute. The plan's folder is
    kept as the user gave it, so a report names examples\\Mod-0.1.0.zip, not a long absolute path."""
    if not zip_value:
        raise SetupError(f"the plan {plan_path} has no zip: line, so there is no tested zip. Add zip: to the "
                         "plan's header or give --tested.")
    if os.path.isabs(zip_value):
        return zip_value
    return os.path.join(os.path.dirname(plan_path), zip_value)
