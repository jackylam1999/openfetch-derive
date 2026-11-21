"""joins.py prep out com-kerbs.json : run run_vic with JOINS logged, then judge each corner chord against CoM kerbs"""
import sys, os, json, runpy, warnings, numpy as np; warnings.filterwarnings("ignore")
D = "/tmp/claude-0/w/derive/openfetch/tools/derive"; sys.path.insert(0, D); sys.path.insert(0, D + "/kerbvic")
import kerblot as kl
import aerroad
aerroad.LOG = []
os.environ.setdefault("KERB_AER", "prob")
sys.argv = ["run_vic.py", sys.argv[1], sys.argv[2]] + ([sys.argv[3]] if len(sys.argv) > 3 else [])
runpy.run_path(D + "/kerbvic/run_vic.py", run_name="__main__")
json.dump(aerroad.LOG, open(sys.argv[2] + "/sides.json", "w"))
json.dump(kl.JOINS, open(sys.argv[2] + "/joins.json", "w"))
print("joins", len(kl.JOINS), "used X", sum(j[3] for j in kl.JOINS))
