"""Fetch real scans into the data folder (outside the repo) as raw responses and ScanPlan fixtures.

    python3 server/scripts/fetch_fixtures.py SID [SID ...]

Reads keys from $THRESHOLD_DATA_DIR/.env (default ../hackprinceton26-data). Nothing it writes may enter git.
"""
import base64, csv, json, os, pathlib, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from threshold.scanplan import QUERY, normalize  # noqa: E402

DATA = pathlib.Path(os.environ.get("THRESHOLD_DATA_DIR", "~/Code/hackathons/hackprinceton26-data"))
ENV = dict(l.strip().split("=", 1) for l in (DATA / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))


def graph(query: str, **variables) -> dict:
    auth = base64.b64encode(f"{ENV['MATTERPORT_API_KEY']}:{ENV['MATTERPORT_API_TOKEN']}".encode()).decode()
    req = urllib.request.Request("https://api.matterport.com/api/models/graph",
                                 data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Basic " + auth})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


if __name__ == "__main__":
    index = {r["sid"]: r for r in csv.DictReader(open(DATA / "models_index.csv"))}
    for sid in sys.argv[1:]:
        raw = graph(QUERY, id=sid)
        if raw.get("errors") and not (raw.get("data") or {}).get("model"):
            print(sid, "ERROR", raw["errors"][0].get("message"))
            continue
        (DATA / "raw" / f"{sid}.json").write_text(json.dumps(raw))
        plan = normalize(raw["data"]["model"], index.get(sid))
        (DATA / "fixtures" / "scanplan" / f"{sid}.json").write_text(json.dumps(plan))
        closed = sum(1 for r in plan["rooms"] if r["polygon"])
        kinds = {}
        for o in plan["openings"]:
            kinds[o["type"]] = kinds.get(o["type"], 0) + 1
        print(f"{sid} | {str(plan['name'])[:34]:34} | rooms {len(plan['rooms']):3} ({closed} with a polygon) | walls {len(plan['walls']):3} "
              f"| openings {kinds} | panos {len(plan['panos']):3} | yaw {plan['geo'] and plan['geo']['yaw_deg']}")
        time.sleep(0.4)
