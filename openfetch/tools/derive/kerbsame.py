"""One street, not one name (P-0253, 21 Nov 2026). kerblot.py lends a footpath width along "the same named street", pooled by the
NSW road name id (roadnameoid) over a block's cell and the 8 around it. One road name id is one name, not one street: ARTHUR STREET
(1766) is a street in Surry Hills and another 500 m away in Redfern, and in the 54 squares round inner Sydney 448 of 2,425 name ids
lie in two or more separate places. Surry Hills' Arthur St was given 1.25 m measured off 97 m of Redfern's Arthur St (16 measures
within 62 m), and its line sat 3-4 m short of the kerb (S16 crops f34, g04). The street key is now the name plus the connected
piece of its centrelines (pieces closer than JOIN m are one street), so a width is only lent along the street it was measured on.

    python3 kerbsame.py --selftest
"""
import sys

JOIN = 2.0   # m: centreline pieces of one name this close are one street (they meet at nodes; 2 m allows for drafting)


def street_keys(lines, names):
    """lines: shapely LineStrings; names: their road name ids (None allowed). Returns one key per line: None, or
    "<name>@<x>_<y>" with x, y the lower-left corner (whole metres) of the connected piece the line belongs to, so the key does
    not depend on which lines a run holds or their order."""
    from shapely.strtree import STRtree
    keys = [None] * len(lines)
    by = {}
    for i, n in enumerate(names):
        if n is not None:
            by.setdefault(n, []).append(i)
    for n, idx in by.items():
        G = [lines[i] for i in idx]
        T = STRtree(G)
        parent = list(range(len(G)))

        def root(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a, g in enumerate(G):
            for b in T.query(g.buffer(JOIN)):
                b = int(b)
                if b != a and G[b].distance(g) <= JOIN:
                    parent[root(a)] = root(b)
        corner = {}
        for a, g in enumerate(G):
            x, y = g.bounds[:2]
            r = root(a)
            cx, cy = corner.get(r, (x, y))
            corner[r] = (min(cx, x), min(cy, y))
        for a, i in enumerate(idx):
            x, y = corner[root(a)]
            keys[i] = f"{n}@{int(x // 1)}_{int(y // 1)}"
    return keys


def selftest():
    from shapely.geometry import LineString
    L = [LineString([(0, 0), (100, 0)]), LineString([(100, 0), (200, 5)]),       # one street in two pieces meeting at a node
         LineString([(700, 300), (800, 300)]),                                    # same name 500 m away: another street
         LineString([(0, 50), (100, 50)]), LineString([(201, 6), (300, 6)])]      # another name; a 1.4 m drafting gap
    k = street_keys(L + [LineString([(300, 6), (400, 6)])], [1766, 1766, 1766, 9, 1766, None])
    assert k[0] == k[1] == k[4], k                     # pieces of one street (node, small gap) share a key
    assert k[2] != k[0] and k[2].startswith("1766@")   # the other Arthur St does not lend its width
    assert k[3].startswith("9@") and k[5] is None
    assert street_keys(L[::-1], [1766, 1766, 1766, 9, 1766][::-1])[::-1][0] == k[0]   # order of lines does not change the key
    print("kerbsame selftest pass")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    print(__doc__)
