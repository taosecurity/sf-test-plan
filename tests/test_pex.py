"""Scripts are compared by meaning: made-up .pex files written by a tiny writer in the test, in two string orders."""
import io
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sftestplan import cli, pex  # noqa: E402
from test_builds import ba2  # noqa: E402


def wstr(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


class PexWriter:
    """Writes a one-object, one-state PEX 3.12 script. `order` decides the string table's order."""

    def __init__(self, order=None):
        self.order = order

    def build(self, stamp=1, code=(("assign", "::temp0", 5), ("return", "::temp0")), greeting="Hello"):
        strings = ["BeaconScript", "ScriptObject", "", "OnInit", "None", "::temp0", "Int", "Greeting", "String",
                   greeting]
        if self.order:
            strings = [strings[i] for i in self.order]
        ix = {s: i for i, s in enumerate(strings)}

        def s(v):
            return struct.pack("<H", ix[v])

        def val_ident(v):
            return b"\x01" + s(v)

        def val_int(n):
            return b"\x03" + struct.pack("<i", n)

        ops = {"assign": 0x0D, "return": 0x1A}
        instrs = b""
        for op, *args in code:
            instrs += bytes([ops[op]])
            for a in args:
                instrs += val_int(a) if isinstance(a, int) else val_ident(a)
        fn = (s("None") + s("") + struct.pack("<I", 0) + b"\x00" + struct.pack("<H", 0)
              + struct.pack("<H", 1) + s("::temp0") + s("Int") + struct.pack("<H", len(code)) + instrs)
        var = s("Greeting") + s("String") + struct.pack("<I", 0) + b"\x02" + s(greeting) + b"\x00"
        body = (s("ScriptObject") + s("") + b"\x00" + struct.pack("<I", 0) + s("")
                + struct.pack("<H", 0)                     # structs
                + struct.pack("<H", 1) + var               # variables
                + struct.pack("<H", 0)                     # guards (3.12)
                + struct.pack("<H", 0)                     # properties
                + struct.pack("<H", 1) + s("") + struct.pack("<H", 1) + s("OnInit") + fn)
        obj = s("BeaconScript") + struct.pack("<I", len(body) + 4) + body
        head = (struct.pack("<I", 0xFA57C0DE) + bytes([3, 12]) + struct.pack("<H", 4) + struct.pack("<Q", stamp)
                + wstr("BeaconScript.psc") + wstr("builder") + wstr("PC1"))
        table = struct.pack("<H", len(strings)) + b"".join(wstr(x) for x in strings)
        return head + table + b"\x00" + struct.pack("<H", 0) + struct.pack("<H", 1) + obj


REORDER = [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]


class PexListingTests(unittest.TestCase):
    def test_reordered_string_table_and_new_time_match(self):
        a = PexWriter().build(stamp=1)
        b = PexWriter(REORDER).build(stamp=99)
        self.assertNotEqual(a, b)
        self.assertEqual(pex.listing(a), pex.listing(b))

    def test_changed_code_differs(self):
        a = PexWriter().build()
        b = PexWriter(REORDER).build(code=(("assign", "::temp0", 6), ("return", "::temp0")))
        self.assertNotEqual(pex.listing(a), pex.listing(b))

    def test_changed_string_value_differs(self):
        self.assertNotEqual(pex.listing(PexWriter().build()), pex.listing(PexWriter().build(greeting="Bye")))

    def test_listing_names_the_parts(self):
        text = "\n".join(pex.listing(PexWriter().build()))
        self.assertIn("object BeaconScript extends 'ScriptObject'", text)
        self.assertIn("function OnInit", text)
        self.assertIn("assign ident:::t1, int:5", text)

    def test_cut_short_or_foreign_raises(self):
        good = PexWriter().build()
        for bad in (good[:-3], good + b"\0", b"\xfa\x57\xc0\xde" + good[4:], good[:4] + bytes([3, 2]) + good[6:]):
            with self.assertRaises(pex.PexError):
                pex.listing(bad)


class CompareByMeaningTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sf test plan ")
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def zip(self, name, script):
        p = os.path.join(self.dir, name)
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("BeaconMod.esm", b"ESM")
            z.writestr("BeaconMod - Main.ba2", ba2({"scripts/beaconscript.pex": script}))
        return p

    def compare(self, a, b):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["compare-builds", a, b])
        return code, out.getvalue()

    def test_recompile_with_new_string_order_is_same(self):
        a = self.zip("a.zip", PexWriter().build(stamp=1))
        b = self.zip("b.zip", PexWriter(REORDER).build(stamp=2))
        code, out = self.compare(a, b)
        self.assertEqual(code, 0, out)
        self.assertIn("scripts compared by meaning", out)

    def test_changed_script_differs(self):
        a = self.zip("a.zip", PexWriter().build())
        b = self.zip("b.zip", PexWriter(REORDER).build(greeting="Bye"))
        code, out = self.compare(a, b)
        self.assertEqual(code, 1, out)
        self.assertIn("1 of its files differ (scripts/beaconscript.pex)", out)


if __name__ == "__main__":
    unittest.main()
