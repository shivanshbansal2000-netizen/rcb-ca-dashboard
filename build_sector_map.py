"""
One-time script to build ISIN -> sector mapping for RCB holdings.
Reads ISINs from rcb_isins.json (or RCB_ISINS env var).
Queries NSE quote API for each symbol's industry classification.
Outputs sector_map.json -- commit to repo after running, refresh quarterly.

Usage:
  python build_sector_map.py
  python build_sector_map.py --reset   # start fresh, ignore existing cache
"""
import json, time, os, sys
from pathlib import Path
import requests

HERE       = Path(__file__).parent
ISIN_FILE  = HERE / "rcb_isins.json"
OUT_FILE   = HERE / "sector_map.json"


def load_isins():
    env_isins = os.environ.get("RCB_ISINS")
    if env_isins:
        return json.loads(env_isins.lstrip("﻿"))
    if not ISIN_FILE.exists():
        print("ERROR: rcb_isins.json not found and RCB_ISINS env var not set.")
        sys.exit(1)
    return json.loads(ISIN_FILE.read_text())


def nse_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    })
    try:
        s.get("https://www.nseindia.com", timeout=15)
        time.sleep(2)
    except Exception as e:
        print(f"  Warning: NSE session prime failed -- {e}")
    return s


def get_nse_master():
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    print("  Downloading NSE equity master...")
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    isin_map = {}
    for line in r.text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 7:
            symbol = parts[0].strip().strip('"')
            name   = parts[1].strip().strip('"')
            isin   = parts[6].strip().strip('"')
            if isin:
                isin_map[isin] = {"symbol": symbol, "name": name}
    print(f"  NSE master loaded -- {len(isin_map)} entries")
    return isin_map


def get_sector(session, symbol):
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        return (
            data.get("metadata", {}).get("industry")
            or data.get("industryInfo", {}).get("basicIndustry")
        )
    except Exception:
        return None


def main():
    reset = "--reset" in sys.argv
    print("Building sector map for RCB holdings...")
    our_isins = load_isins()
    print(f"Loaded {len(our_isins)} ISINs")

    existing = {}
    if OUT_FILE.exists() and not reset:
        existing = json.loads(OUT_FILE.read_text())
        print(f"Resuming -- {len(existing)} entries already cached")

    nse_master = get_nse_master()
    session    = nse_session()

    result = dict(existing)
    todo   = [isin for isin in our_isins if isin not in result]
    print(f"Need to fetch sector for {len(todo)} ISINs\n")

    for i, isin in enumerate(todo):
        company_name = our_isins.get(isin, "Unknown")
        if isin not in nse_master:
            result[isin] = {"company": company_name, "sector": "Other", "symbol": ""}
            continue

        entry  = nse_master[isin]
        symbol = entry["symbol"]
        sector = get_sector(session, symbol)
        result[isin] = {
            "company": entry["name"] or company_name,
            "sector":  sector or "Other",
            "symbol":  symbol,
        }
        print(f"  [{i+1}/{len(todo)}] {symbol}: {sector or 'unknown'}")
        time.sleep(1.5)

        if (i + 1) % 50 == 0:
            OUT_FILE.write_text(json.dumps(result, indent=2))
            print(f"  Progress saved ({len(result)} entries)")

    OUT_FILE.write_text(json.dumps(result, indent=2))

    sectors = {}
    for v in result.values():
        s = v.get("sector", "Other")
        sectors[s] = sectors.get(s, 0) + 1

    print(f"\nTop sectors in portfolio:")
    for s, c in sorted(sectors.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:3d}  {s}")
    print(f"\nSaved {len(result)} entries to {OUT_FILE}")
    print("Next step: git add sector_map.json && git commit -m 'data: sector map'")


if __name__ == "__main__":
    main()
