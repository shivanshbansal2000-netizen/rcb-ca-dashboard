"""
Builds ISIN -> sector mapping for RCB holdings using NSE index constituent CSVs.
Each CSV already includes Industry column -- no per-stock API calls needed.
Runs in ~10 seconds. Outputs sector_map.json -- commit to repo, refresh quarterly.

Usage:
  python build_sector_map.py
"""
import json, os, sys
from pathlib import Path
import requests

HERE      = Path(__file__).parent
ISIN_FILE = HERE / "rcb_isins.json"
OUT_FILE  = HERE / "sector_map.json"

# NSE publishes index constituent CSVs with Company Name, Industry, Symbol, ISIN
# Ordered broadest-first so wider coverage files take priority
INDEX_CSVS = [
    "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftylargemidcap250_list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftymidcap150_list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftysmallcap250_list.csv",
    "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}


def load_isins():
    env_isins = os.environ.get("RCB_ISINS")
    if env_isins:
        return json.loads(env_isins.lstrip("﻿"))
    if not ISIN_FILE.exists():
        print("ERROR: rcb_isins.json not found and RCB_ISINS env var not set.")
        sys.exit(1)
    return json.loads(ISIN_FILE.read_text())


def fetch_index_csv(url):
    """Download one index CSV and return {isin: {company, sector, symbol}}."""
    try:
        r = requests.get(url, timeout=20, headers=HEADERS)
        r.raise_for_status()
        entries = {}
        for line in r.text.splitlines()[1:]:
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) < 5:
                continue
            # CSV columns: Company Name, Industry, Symbol, Series, ISIN Code
            company = parts[0]
            sector  = parts[1]
            symbol  = parts[2]
            isin    = parts[4]
            if isin and sector:
                entries[isin] = {"company": company, "sector": sector, "symbol": symbol}
        label = url.split("/")[-1]
        print(f"  {label}: {len(entries)} entries")
        return entries
    except Exception as e:
        print(f"  WARN: {url.split('/')[-1]} failed -- {e}")
        return {}


def build_master_map():
    """Merge all index CSVs into one ISIN -> sector map."""
    master = {}
    for url in INDEX_CSVS:
        entries = fetch_index_csv(url)
        for isin, data in entries.items():
            if isin not in master:  # first match wins (broadest index first)
                master[isin] = data
    return master


def main():
    print("Building sector map from NSE index CSVs...")
    our_isins  = load_isins()
    print(f"Loaded {len(our_isins)} RCB ISINs\n")

    print("Downloading NSE index files:")
    master = build_master_map()
    print(f"\nTotal unique ISINs across all indices: {len(master)}")

    # Match our holdings against the master
    result = {}
    matched = 0
    for isin, company_name in our_isins.items():
        if isin in master:
            result[isin] = master[isin]
            matched += 1
        else:
            result[isin] = {"company": company_name, "sector": "Other", "symbol": ""}

    print(f"Matched: {matched}/{len(our_isins)} ISINs  |  Unmatched (sector=Other): {len(our_isins)-matched}")

    OUT_FILE.write_text(json.dumps(result, indent=2))

    # Sector breakdown
    sectors = {}
    for v in result.values():
        s = v.get("sector", "Other")
        sectors[s] = sectors.get(s, 0) + 1

    print(f"\nSector breakdown ({len(sectors)} sectors):")
    for s, c in sorted(sectors.items(), key=lambda x: -x[1]):
        bar = "█" * (c // 3)
        print(f"  {c:3d}  {s:40s} {bar}")

    print(f"\nSaved {len(result)} entries to {OUT_FILE}")


if __name__ == "__main__":
    main()
