"""Copy the already-normalized public-domain Bible JSON (WEB/KJV) from the Lumen
client tree into the CortexCloud corpus dir. The client already stores them in
the exact compact shape {"books":[{"id","name","abbr","chapters":[[v,...]]}]},
so no transformation is needed.
"""
import json
import os
import shutil

SRC = os.path.expanduser("~/bible-lux/src/assets/bible")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "data", "bible")
os.makedirs(OUT, exist_ok=True)

for name in ("WEB", "KJV"):
    src = os.path.join(SRC, f"{name.lower()}.json")
    dst = os.path.join(OUT, f"{name.lower()}.json")
    shutil.copyfile(src, dst)
    with open(dst) as f:
        n = len(json.load(f)["books"])
    print(f"{name}: {n} books -> {dst}")
