"""Read a compiled Papyrus script (.pex) as a plain listing, so two builds can be compared by meaning.

The Papyrus compiler stores every name and string once in a string table, and the code refers to table entries by
number. Two compiles of the same source can order that table differently, so their bytes differ while the scripts
are the same. listing() swaps every table number for the text it stands for and writes the header, objects,
variables, properties, states, functions, instructions and debug info as lines. Two scripts are the same when
their listings match.

Never compared: the compile time, the source-file modification time and the string-table order. Sections whose
order means nothing (user flags, struct members, variables, guards, properties, states' functions, locals, debug
entries) are sorted, and temporary variables (::tempN) are renamed by first use, because the compiler writes them
in a build-dependent order. Instruction order inside a function is compared as written, and so is a struct's
declared member order (through its debug "structorder" entry).

Reads PEX 3.9 (Fallout 4) and 3.12 (Starfield) little-endian scripts. Anything else raises PexError, and the
caller then compares the bytes instead.
"""
from __future__ import annotations

import struct

# opcode: (name, fixed argument count, variadic). Variadic ops are followed by an int count and that many args.
OPCODES = {
    0x00: ("nop", 0, False), 0x01: ("iadd", 3, False), 0x02: ("fadd", 3, False), 0x03: ("isub", 3, False),
    0x04: ("fsub", 3, False), 0x05: ("imul", 3, False), 0x06: ("fmul", 3, False), 0x07: ("idiv", 3, False),
    0x08: ("fdiv", 3, False), 0x09: ("imod", 3, False), 0x0A: ("not", 2, False), 0x0B: ("ineg", 2, False),
    0x0C: ("fneg", 2, False), 0x0D: ("assign", 2, False), 0x0E: ("cast", 2, False), 0x0F: ("cmp_eq", 3, False),
    0x10: ("cmp_lt", 3, False), 0x11: ("cmp_le", 3, False), 0x12: ("cmp_gt", 3, False), 0x13: ("cmp_ge", 3, False),
    0x14: ("jmp", 1, False), 0x15: ("jmpt", 2, False), 0x16: ("jmpf", 2, False), 0x17: ("callmethod", 3, True),
    0x18: ("callparent", 2, True), 0x19: ("callstatic", 3, True), 0x1A: ("return", 1, False),
    0x1B: ("strcat", 3, False), 0x1C: ("propget", 3, False), 0x1D: ("propset", 3, False),
    0x1E: ("array_create", 2, False), 0x1F: ("array_length", 2, False), 0x20: ("array_getelement", 3, False),
    0x21: ("array_setelement", 3, False), 0x22: ("array_findelement", 4, False),
    0x23: ("array_rfindelement", 4, False), 0x24: ("is", 3, False), 0x25: ("struct_create", 1, False),
    0x26: ("struct_get", 3, False), 0x27: ("struct_set", 3, False), 0x28: ("array_findstruct", 5, False),
    0x29: ("array_rfindstruct", 5, False), 0x2A: ("array_add", 3, False), 0x2B: ("array_insert", 3, False),
    0x2C: ("array_removelast", 1, False), 0x2D: ("array_remove", 3, False), 0x2E: ("array_clear", 1, False),
    # PEX 3.12 additions
    0x2F: ("array_getallmatchingstructs", 6, False), 0x30: ("lock_guards", 0, True),
    0x31: ("unlock_guards", 0, True), 0x32: ("try_lock_guards", 1, True),
}


class PexError(Exception):
    pass


class _Reader:
    def __init__(self, data: bytes):
        self.b, self.p = data, 0
        self.strings: list[str] = []

    def need(self, n: int) -> None:
        if self.p + n > len(self.b):
            raise PexError(f"the script ends early at byte {self.p}")

    def _unpack(self, fmt: str, n: int):
        self.need(n)
        v = struct.unpack_from(fmt, self.b, self.p)[0]
        self.p += n
        return v

    def u8(self) -> int:
        return self._unpack("<B", 1)

    def u16(self) -> int:
        return self._unpack("<H", 2)

    def u32(self) -> int:
        return self._unpack("<I", 4)

    def s32(self) -> int:
        return self._unpack("<i", 4)

    def u64(self) -> int:
        return self._unpack("<Q", 8)

    def f32(self) -> float:
        return self._unpack("<f", 4)

    def wstr(self) -> str:
        n = self.u16()
        self.need(n)
        s = self.b[self.p:self.p + n].decode("utf-8", "replace")
        self.p += n
        return s

    def sref(self) -> str:
        i = self.u16()
        if i >= len(self.strings):
            raise PexError(f"string number {i} is out of range at byte {self.p - 2}")
        return self.strings[i]

    def value(self) -> str:
        t = self.u8()
        if t == 0:
            return "None"
        if t == 1:
            return "ident:" + self.sref()
        if t == 2:
            return "str:" + repr(self.sref())
        if t == 3:
            return "int:" + str(self.s32())
        if t == 4:
            return "float:" + repr(self.f32())
        if t == 5:
            return "bool:" + ("True" if self.u8() else "False")
        raise PexError(f"unknown value type {t} at byte {self.p - 1}")


def _function(r: _Reader, indent: str) -> list[str]:
    head = f"{indent}returns {r.sref()}  doc {r.sref()!r}  userflags {r.u32():#x}  flags {r.u8():#x}"
    params = [f"{indent}param {r.sref()} : {r.sref()}" for _ in range(r.u16())]
    local_list = [(r.sref(), r.sref()) for _ in range(r.u16())]
    code = []
    for _ in range(r.u16()):
        op = r.u8()
        if op not in OPCODES:
            raise PexError(f"unknown opcode {op:#x} at byte {r.p - 1}")
        name, fixed, variadic = OPCODES[op]
        args = [r.value() for _ in range(fixed)]
        if variadic:
            count = r.value()
            if not count.startswith("int:"):
                raise PexError(f"a variadic count is {count} at byte {r.p}")
            args += [r.value() for _ in range(int(count[4:]))]
        code.append((name, args))
    rename: dict[str, str] = {}
    for _, args in code:
        for a in args:
            if a.startswith("ident:::temp") and a[6:] not in rename:
                rename[a[6:]] = f"::t{len(rename) + 1}"
    for lname, _ in sorted(local_list, key=lambda x: (x[1], x[0])):
        if lname.startswith("::temp") and lname not in rename:
            rename[lname] = f"::t{len(rename) + 1}"
    lines = [head] + params
    lines += sorted(f"{indent}local {rename.get(n, n)} : {ty}" for n, ty in local_list)
    for i, (name, args) in enumerate(code):
        args = ["ident:" + rename.get(a[6:], a[6:]) if a.startswith("ident:") else a for a in args]
        lines.append(f"{indent}{i:4d} {name} " + ", ".join(args))
    return lines


def listing(data: bytes) -> list[str]:
    """The script's listing (see the module text). Raises PexError for anything it can't read in full."""
    r = _Reader(data)
    if r.u32() != 0xFA57C0DE:
        raise PexError("not a little-endian PEX script")
    major, minor, game = r.u8(), r.u8(), r.u16()
    if (major, minor) not in ((3, 9), (3, 12)):
        raise PexError(f"PEX version {major}.{minor} isn't supported")
    with_guards = (major, minor) >= (3, 12)
    r.u64()  # compile time: never compared
    out = [f"pex {major}.{minor} game {game}", f"source {r.wstr()}  user {r.wstr()}  machine {r.wstr()}"]
    r.strings = [r.wstr() for _ in range(r.u16())]

    debug = []
    if r.u8():
        r.u64()  # source modification time: never compared
        for _ in range(r.u16()):
            obj, state, fn, ftype = r.sref(), r.sref(), r.sref(), r.u8()
            lines = [r.u16() for _ in range(r.u16())]
            debug.append(f"debug function {obj}.{state}.{fn} type {ftype} lines {lines}")
        for _ in range(r.u16()):
            obj, grp, doc, flags = r.sref(), r.sref(), r.sref(), r.u32()
            names = sorted(r.sref() for _ in range(r.u16()))
            debug.append(f"debug propertygroup {obj}.{grp!r} doc {doc!r} flags {flags:#x} {names}")
        for _ in range(r.u16()):
            obj, order = r.sref(), r.sref()
            names = [r.sref() for _ in range(r.u16())]  # declared member order: kept as written
            debug.append(f"debug structorder {obj}.{order} {names}")
    debug.sort()

    out += sorted(f"userflag {r.sref()} = bit {r.u8()}" for _ in range(r.u16()))

    for _ in range(r.u16()):
        oname = r.sref()
        size = r.u32()
        start = r.p
        out.append(f"object {oname} extends {r.sref()!r}")
        out.append(f"  doc {r.sref()!r}  const {r.u8()}  userflags {r.u32():#x}  autostate {r.sref()!r}")
        structs = []
        for _ in range(r.u16()):
            block = [f"  struct {r.sref()}"]
            for _ in range(r.u16()):
                mname, mtype, mflags = r.sref(), r.sref(), r.u32()
                mval, mconst, mdoc = r.value(), r.u8(), r.sref()
                block.append(f"    member {mname} : {mtype}  flags {mflags:#x} = {mval}  const {mconst}  doc {mdoc!r}")
            structs.append(block[:1] + sorted(block[1:]))
        variables = []
        for _ in range(r.u16()):
            vname, vtype, vflags = r.sref(), r.sref(), r.u32()
            vval, vconst = r.value(), r.u8()
            variables.append(f"  variable {vname} : {vtype}  flags {vflags:#x} = {vval}  const {vconst}")
        guards = [f"  guard {r.sref()}" for _ in range(r.u16())] if with_guards else []
        properties = []
        for _ in range(r.u16()):
            pname, ptype, pdoc, pflags, pfl = r.sref(), r.sref(), r.sref(), r.u32(), r.u8()
            block = [f"  property {pname} : {ptype}  doc {pdoc!r}  userflags {pflags:#x}  flags {pfl:#x}"]
            if pfl & 4:
                block.append(f"    autovar {r.sref()}")
            else:
                if pfl & 1:
                    block += ["    get"] + _function(r, "      ")
                if pfl & 2:
                    block += ["    set"] + _function(r, "      ")
            properties.append(block)
        states = []
        for _ in range(r.u16()):
            block = [f"  state {r.sref()!r}"]
            funcs = [[f"    function {r.sref()}"] + _function(r, "      ") for _ in range(r.u16())]
            for f in sorted(funcs):
                block += f
            states.append(block)
        for block in sorted(structs):
            out += block
        out += sorted(variables) + sorted(guards)
        for block in sorted(properties) + sorted(states):
            out += block
        if r.p - start not in (size - 4, size):
            raise PexError(f"object {oname} read {r.p - start} bytes but its size field says {size}")
    if r.p != len(data):
        raise PexError(f"{len(data) - r.p} unread bytes at the end")
    return out + debug
