"""Do two identical kerblot runs give identical rings? (KN14, 20 Nov 2026, P-0231.)
Runs kerblot.py twice on the same inputs, once with the cells reversed and a different hash seed, and compares the rings
(drawn file and why file) byte for byte. Any difference fails.

    python3 kerbrepeat.py <kerblot arguments, as for kerblot.py>     e.g. lots roads raw drawn bld cells.txt out.json --ground g --road r
    python3 kerbrepeat.py --selftest
The out file (argument 7) and --why file are written next to it with .a / .b suffixes and left for inspection.
"""
import hashlib, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, cells_rev, seed, tag):
    a = list(args)
    out = a[6] + "." + tag
    a[6] = out
    if cells_rev:
        rev = out + ".cells"
        open(rev, "w").write("".join(reversed(open(a[5]).readlines())))
        a[5] = rev
    if "--why" in a:
        a[a.index("--why") + 1] += "." + tag
    subprocess.run([sys.executable, os.path.join(HERE, "kerblot.py")] + a, check=True, env={**os.environ, "PYTHONHASHSEED": str(seed)},
                   stdout=subprocess.DEVNULL)
    files = [out] + ([a[a.index("--why") + 1]] if "--why" in a else [])
    return [hashlib.md5(open(f, "rb").read()).hexdigest() for f in files]


def compare(args):
    ha, hb = run(args, False, 1, "a"), run(args, True, 2, "b")
    ok = ha == hb
    print("kerbrepeat", "pass: identical" if ok else f"FAIL: {ha} vs {hb}")
    return 0 if ok else 1


def selftest():
    import kerblot as kl
    from shapely.geometry import box
    a, b = set(), set()
    blocks = [(318, 6251, box(318100, 6251100, 318150, 6251140)), (318, 6251, box(318500, 6251500, 318560, 6251530)), (319, 6253, box(319200, 6253300, 319230, 6253360))]
    ida = [kl.block_id(x, y, c, a) for x, y, c in blocks]
    idb = [kl.block_id(x, y, c, b) for x, y, c in reversed(blocks)][::-1]
    assert ida == idb, (ida, idb)
    assert len(set(ida)) == 3
    assert kl.block_id(318, 6251, blocks[0][2], a) not in ida, "a clash must get its own id"
    print("kerbrepeat selftest pass")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else compare(sys.argv[1:]))
