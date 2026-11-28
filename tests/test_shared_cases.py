"""The PMT shared test sets (PMTW6 D1) as sf-test-plan runs them (0.5.1).

The cases live in tests/shared (a byte-for-byte copy of the house sets; never edited here). Each case is one
subTest named by its id. Cases that sf-test-plan can't have are listed under "not_applicable" in
tests/shared/ADOPTION.json; cases it fails on purpose are under "known_limits" and are skipped with their reason.
The tool is run as a child process (python -I sf_test_plan.py ...), the way a user runs it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(HERE, "shared")
EXE = os.path.join(ROOT, "sf_test_plan.py")
sys.path.insert(0, ROOT)

from sftestplan import cli  # noqa: E402

WINDOWS = os.name == "nt"
PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: x\n"
MARKS = {"format": "sf-test-plan-marks/2", "run": "a", "title": "T", "exported": "2026-11-19T21:04:00Z",
         "checks": [{"id": "1.1", "r": "pass", "n": "ok", "t": "one", "g": 1, "at": "2026-11-19T20:58:10Z",
                     "src": "page"}]}
REPORT = {"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}
PINS = {"format": "sf-test-plan-pins/1",
        "pins": {"mymod.esm": {"tested": "0123456789abcdef", "built": "fedcba9876543210", "why": "made-up"}}}


def load(*parts):
    with open(os.path.join(SHARED, *parts), encoding="utf-8") as f:
        return json.load(f)


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


ADOPTION = load("ADOPTION.json")
EXIT = ADOPTION["exit_codes"]
CODES = set(EXIT["ok"]) | set(EXIT["finding"]) | set(EXIT["refuse"])


def case_insensitive_fs():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.txt"), "w").close()
        return os.path.exists(os.path.join(d, "A.TXT"))


def run(args, cwd=None, timeout=60):
    p = subprocess.run([sys.executable, "-I", EXE] + list(args), capture_output=True, cwd=cwd, timeout=timeout,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return (p.returncode, p.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
            p.stderr.decode("utf-8", "replace").replace("\r\n", "\n"))


class Shared(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="stp shared ")
        self.t = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def known(self, cid):
        """True (and the reason printed) when the case is a recorded known limit of this tool."""
        why = ADOPTION["known_limits"].get(cid)
        if why:
            print(f"known limit {cid}: {why}")
        return bool(why)

    def never(self, code, out, err, what):
        text = out + err
        self.assertNotIn("Traceback", text, f"{what}: a traceback\n{text[-600:]}")
        self.assertTrue(0 <= code < 128, f"{what}: exit code {code}")
        self.assertIn(code, CODES, f"{what}: exit code {code} is not in ADOPTION.json's exit_codes")


# ------------------------------------------------------------------------------------------------ set 1
class OutPaths(Shared):
    def make(self, case):
        t = self.t
        for d in case.get("dirs", []):
            os.makedirs(os.path.join(t, d), exist_ok=True)
        for f in case.get("files", []):
            with open(os.path.join(t, f), "w", encoding="utf-8", newline="\n") as fh:
                fh.write("input")
        for ln in case.get("links", []):
            src, dst = os.path.join(t, ln["from"]), os.path.join(t, ln["to"])
            try:
                (os.symlink if ln["kind"] == "symlink" else os.link)(dst, src)
            except (OSError, NotImplementedError, AttributeError):
                return False
        return True

    def test_cases(self):
        data = load("out-paths.json")
        ci = case_insensitive_fs()
        for case in data["cases"]:
            cid = case["id"]
            with self.subTest(case=cid):
                if cid in ADOPTION["not_applicable"] or self.known(cid):
                    continue
                if case.get("only_if") == "windows" and not WINDOWS:
                    continue
                # sf-test-plan refuses a colon in an output's file name only on Windows (a file stream there);
                # Linux and macOS allow colons, so this shared case is skipped off Windows.
                if cid == "out-stream-colon" and sys.platform != "win32":
                    print(f"skipped {cid}: the colon refusal is Windows-only")
                    continue
                if case.get("only_if") == "case_insensitive_fs" and not ci:
                    continue
                if not self.make(case):
                    print(f"skipped {cid}: this system can't make the {case.get('needs')}")
                    continue
                inp = case.get("input")
                if inp:       # the input is a real plan (hard links share its bytes)
                    with open(os.path.join(self.t, inp), "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(PLAN)
                    before = _read_bytes(os.path.join(self.t, inp))
                else:
                    inp = "plan.testplan.md"
                    with open(os.path.join(self.t, inp), "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(PLAN)
                    before = _read_bytes(os.path.join(self.t, inp))
                out = self.t.replace("\\", "/") + "/" + case["out"]
                plan = os.path.join(self.t, inp)
                for opt, argv in (("--out", ["build", plan, "--out", out]),
                                  ("--log", ["check", plan, "--log", out])):
                    started = set(os.listdir(self.t))
                    code, so, se = run(argv, cwd=self.t)
                    self.never(code, so, se, f"{cid} {opt}")
                    after = _read_bytes(plan)
                    if case["expect"] == "refuse":
                        self.assertIn(code, EXIT["refuse"], f"{cid} {opt}: exit {code}\n{so}{se}")
                        self.assertEqual(before, after, f"{cid} {opt}: the input changed")
                        self.assertIn(opt, so + se, f"{cid} {opt}: the message doesn't name the option")
                        self.assertEqual(started, set(os.listdir(self.t)), f"{cid} {opt}: something was written")
                    else:
                        self.assertIn(code, EXIT["ok"], f"{cid} {opt}: exit {code}\n{so}{se}")
                        self.assertTrue(os.path.isfile(out), f"{cid} {opt}: no file")
                        os.remove(out)


# ------------------------------------------------------------------------------------------------ set 2
class DamagedInputs(Shared):
    def zips(self):
        a, b = os.path.join(self.t, "a.zip"), os.path.join(self.t, "b.zip")
        for p in (a, b):
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("MyMod.esm", "x")
        return a, b

    def plan(self):
        p = os.path.join(self.t, "plan.testplan.md")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(PLAN)
        return p

    def commands(self, damaged):
        """(name, argv) for each place sf-test-plan reads JSON, given the damaged file."""
        a, b = self.zips()
        plan = self.plan()
        return [("import marks", ["import", damaged, "--plan", plan]),
                ("logs report", ["logs", damaged, "--plan", plan, "--out", os.path.join(self.t, "m.json")]),
                ("--pins", ["compare-builds", a, b, "--pins", damaged]),
                ("build --rules", ["build", plan, "--rules", damaged, "--out", os.path.join(self.t, "p.html")]),
                ("build --style", ["build", plan, "--style", damaged, "--out", os.path.join(self.t, "p.html")]),
                ("rules --from", ["rules", plan, "--from", damaged, "--out", os.path.join(self.t, "r.json")])]

    def test_files(self):
        manifest = load("damaged-inputs", "manifest.json")
        for case in manifest["files"]:
            name = case["file"]
            with self.subTest(case=name):
                if name in ADOPTION["not_applicable"] or self.known(name):
                    continue
                src = os.path.join(SHARED, "damaged-inputs", name)
                for what, argv in self.commands(src):
                    t0 = time.time()
                    code, so, se = run(argv, cwd=self.t)
                    self.never(code, so, se, f"{name} in {what}")
                    self.assertLess(time.time() - t0, manifest["time_limit_s"] + 20, f"{name} in {what}: too slow")
                    if case["answer"] == "refuse":
                        self.assertIn(code, EXIT["refuse"], f"{name} in {what}: exit {code}\n{so}{se}")
                        self.assertIn(name, so + se, f"{name} in {what}: the message doesn't name the file")
                    # read_or_refuse: any non-crashing answer is right

    def mutate(self, doc):
        """(label, mutated copy) for each key at depth 1 and 2 and each mutation."""
        out = []

        def paths(node, prefix, depth):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield prefix + [k]
                    if depth < 2:
                        yield from paths(v, prefix + [k], depth + 1)
            elif isinstance(node, list) and depth < 2:
                for i, v in enumerate(node[:1]):
                    yield prefix + [i]
                    yield from paths(v, prefix + [i], depth + 1)

        for p in paths(doc, [], 1):
            for mid in ("m-null-value", "m-empty-object", "m-wrong-type-string", "m-drop-key"):
                new = json.loads(json.dumps(doc))
                node = new
                for k in p[:-1]:
                    node = node[k]
                last = p[-1]
                if mid == "m-null-value":
                    node[last] = None
                elif mid == "m-empty-object":
                    node[last] = {}
                elif mid == "m-wrong-type-string":
                    node[last] = "false" if isinstance(node[last], bool) else "12"
                elif isinstance(node, dict):
                    del node[last]
                else:
                    continue
                out.append((mid, "/".join(str(x) for x in p), new))
        return out

    def test_mutations(self):
        a, b = self.zips()
        plan = self.plan()
        ids = {m["id"] for m in load("damaged-inputs", "manifest.json")["mutations"]["list"]}
        samples = (("marks", MARKS, lambda f: ["import", f, "--plan", plan]),
                   ("pins", PINS, lambda f: ["compare-builds", a, b, "--pins", f]),
                   ("report", REPORT, lambda f: ["logs", f, "--plan", plan, "--out", os.path.join(self.t, "m.json")]))
        for label, doc, argv in samples:
            for mid, path, new in self.mutate(doc):
                self.assertIn(mid, ids)
                with self.subTest(case=mid, sample=label, key=path):
                    if mid in ADOPTION["not_applicable"] or self.known(mid):
                        continue
                    f = os.path.join(self.t, "mutated.json")
                    with open(f, "w", encoding="utf-8", newline="\n") as fh:
                        json.dump(new, fh)
                    if os.path.exists(os.path.join(self.t, "m.json")):
                        os.remove(os.path.join(self.t, "m.json"))
                    code, so, se = run(argv(f), cwd=self.t)
                    self.never(code, so, se, f"{label} {mid} {path}")
                    if code in EXIT["refuse"]:
                        self.assertIn("mutated.json", so + se, f"{label} {mid} {path}: the message doesn't name the file")


# ------------------------------------------------------------------------------------------------ set 4
def bad_chars(s):
    return [c for c in s if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") and c != "\n"]


class TerminalText(Shared):
    """Zip entry names are what sf-test-plan prints from outside (compare-builds names the differing files)."""

    def report(self, name):
        a, b = os.path.join(self.t, "a.zip"), os.path.join(self.t, "b.zip")
        for p, body in ((a, "one"), (b, "two")):
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("Data/MyMod.esm", "x")
                z.writestr(zipfile.ZipInfo(name), body)
        return run(["compare-builds", a, b], cwd=self.t)

    def test_cases(self):
        data = load("terminal-text.json")
        base = None
        for case in data["cases"]:
            cid = case["id"]
            with self.subTest(case=cid):
                if cid in ADOPTION["not_applicable"] or self.known(cid):
                    continue
                text = case["text"] if "text" in case else case["repeat"]["text"] * case["repeat"]["count"]
                if len(text) > 20000:
                    text = text[:20000]    # a zip entry name holds at most 65,535 bytes: the long cases are cut to fit
                name = "Data/Scripts/" + text.replace("/", "_") + ".pex"
                code, so, se = self.report(name)
                self.never(code, so, se, cid)
                full = so + se
                if base is None:
                    bc, bo, be = self.report("Data/Scripts/plain.pex")
                    base = len((bo + be).splitlines())
                rules = case["rules"]
                if "no_raw" in rules:
                    self.assertEqual([], bad_chars(full.replace("\t", "")), f"{cid}: raw control or format characters")
                if "one_line" in rules:
                    self.assertEqual(base, len(full.splitlines()), f"{cid}: the text added lines\n{full}")
                if "unchanged" in rules:
                    self.assertIn(text.replace("\\", "/"), full,     # the zip layer turns a \\ in a name into /
 f"{cid}: the text was changed")


# ------------------------------------------------------------------------------------------------ set 5
class PathsAndPrograms(Shared):
    def test_spellings(self):
        data = load("paths-and-programs.json")
        for case in data["spellings"]:
            cid = case["id"]
            with self.subTest(case=cid):
                if cid in ADOPTION["not_applicable"] or self.known(cid):
                    continue
                if case["flavor"] == "windows" and not WINDOWS:
                    continue
                if case["flavor"] == "posix" and WINDOWS:
                    continue
                self.assertEqual(case["expect"], cli._same_file(case["a"], case["b"]), cid)

    def test_policy(self):
        """A UNC path read from a plan's zip: line is refused or skipped, naming the plan, and never opened."""
        for case in load("paths-and-programs.json")["policy"]:
            cid = case["id"]
            with self.subTest(case=cid):
                if cid in ADOPTION["not_applicable"] or self.known(cid):
                    continue
                if case["expect"] == "use_as_given":
                    continue      # a typed path is opened as given; nothing to prove with no network
                plan = os.path.join(self.t, "plan.testplan.md")
                with open(plan, "w", encoding="utf-8", newline="\n") as f:
                    f.write("# T\nrun: a\nzip: " + case["path"] + "\n\n## 1 G\n- [ ] one\n")
                built = os.path.join(self.t, "b.zip")
                with zipfile.ZipFile(built, "w") as z:
                    z.writestr("MyMod.esm", "x")
                t0 = time.time()
                code, so, se = run(["check-build", plan, "--built", built], cwd=self.t, timeout=30)
                self.never(code, so, se, cid)
                self.assertLess(time.time() - t0, 10, f"{cid}: slow (did it try the network?)")
                text = so + se
                self.assertIn(code, EXIT["refuse"], f"{cid}: {code}\n{text}")
                self.assertIn("network path", text, f"{cid}: the refusal doesn't say why\n{text}")
                self.assertIn(plan, text, f"{cid}: the refusal doesn't name the plan\n{text}")
                self.assertIn("--tested", text, f"{cid}: the refusal doesn't give the fix\n{text}")


if __name__ == "__main__":
    unittest.main()
