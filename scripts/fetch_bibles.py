"""Fetch + normalize WEB and KJV into compact per-book arrays for the
CortexCloud research/ask corpus. Public domain (WEB, KJV). Run once on
staging; commit the JSON under app/data/bible/.

Output shape: {"books":[{"id","name","abbr","chapters":[[v1,v2,...]]}]}
"""
import json
import os
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "data", "bible")
os.makedirs(OUT, exist_ok=True)


def fetch(name: str) -> dict:
    url = f"https://api.getbible.net/v2/{name.lower()}.json"
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310
        return json.load(r)


def normalize(data: dict) -> dict:
    books = []
    for b in data.get("books", []):
        chapters = []
        for ch in b.get("chapters", []):
            chapters.append([v.get("text", "") for v in ch.get("verses", [])])
        books.append({"id": b.get("book", b.get("abbr", "")).upper(),
                      "name": b.get("name", ""), "abbr": b.get("abbr", ""), "chapters": chapters})
    return {"books": books}


for name in ("WEB", "KJV"):
    data = fetch(name)
    out = normalize(data)
    path = os.path.join(OUT, f"{name.lower()}.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{name}: {len(out['books'])} books -> {path}")
