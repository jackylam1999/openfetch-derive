#!/usr/bin/env python3
"""Photo year against council kerb year for every kerb-learn box (Jacky 30 Oct 2026: the photo and the council data may be from
different years, e.g. new estates or rebuilt streets, so a disagreement there may be a label error, not a model miss).

Usage: python3 kerbdates.py ../../../kerb-learn/dates.json
Per box: the capture dates of the NSW "best imagery" blocks over it (NSW_Imagery_Dates) and, where the council layer has dates
(Canterbury-Bankstown F_created/F_modified, Woollahra last_edited_date), the spread of kerb edit dates. A box is flagged when kerbs
were created or edited after the photo was taken (the photo may not show them yet). Northern Beaches and Parramatta publish no
dates, so their boxes are flagged "unknown" and only the scored misses can show a mismatch. Edit dates are when the record was
entered or changed (Canterbury-Bankstown audited in 2021, Woollahra re-edited in Sept 2022), not when the kerb was built, so only
edits more than two years after the photo count as a mismatch.
"""
import sys, json, datetime
import kerblearn as kl
kp = kl.kp

DATES = "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery_Dates/MapServer/0/query"
FIELDS = {"cb": "F_created,F_modified", "wo": "last_edited_date"}
day = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).strftime("%Y-%m-%d") if ms else None


def one(b):
    box = (b["x"], b["y"], b["x"] + 1000, b["y"] + 1000)
    ph = sorted({day(f["properties"]["BlockStartDate"]) for f in kp.query(DATES, box, fields="OBJECTID,BlockStartDate")} - {None})
    r = {"council": b["council"], "photo": ph}
    if b["council"] in FIELDS:
        url, _, oid = kp.COUNCILS[b["council"]]
        fs = kp.query(url, box, fields=f"{oid},{FIELDS[b['council']]}", oid=oid)
        ds = sorted(d for f in fs for k in FIELDS[b["council"]].split(",") if (d := day(f["properties"].get(k))))
        cut = ph and (datetime.date.fromisoformat(ph[-1]) + datetime.timedelta(days=730)).isoformat()
        late = [d for d in ds if cut and d > cut]
        r.update({"kerbs": len(fs), "kerb_dates": [ds[0], ds[len(ds) // 2], ds[-1]] if ds else None,
                  "edited_2y_after_photo": round(len(late) / max(len(ds), 1), 3)})
        r["flag"] = "mismatch" if r["edited_2y_after_photo"] > 0.05 else "ok"
    else:
        r["flag"] = "unknown (council publishes no dates)"
    return r


if __name__ == "__main__":
    out = {b["name"]: one(b) for b in kl.BOXES["boxes"]}
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    for n, r in out.items():
        print(n, r["council"], "photo", ",".join(r["photo"]), "kerbs", r.get("kerb_dates"), r.get("edited_2y_after_photo", ""), r["flag"])
