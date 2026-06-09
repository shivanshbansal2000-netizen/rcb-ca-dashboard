"""
Daily news and events aggregator for RCB holdings impact monitoring.
Outputs news_data.json which generate_dashboard.py embeds into index.html.

Sources:
  1. BSE exchange announcements (non-CA) -- filtered to held ISINs
  2. RBI + SEBI RSS -- macro events
  3. Google News RSS -- top sectors by holding count

Run: python fetch_news.py
"""
import json, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import requests

HERE            = Path(__file__).parent
ISIN_FILE       = HERE / "rcb_isins.json"
SECTOR_MAP_FILE = HERE / "sector_map.json"
OUT_FILE        = HERE / "news_data.json"

# Categories to INCLUDE from BSE (non-CA actionable filings)
BSE_INCLUDE_KW = [
    "board meeting", "outcome of board meeting", "financial results", "results",
    "insider trading", "sast", "pledge", "encumbrance",
    "creation of pledge", "revocation of pledge", "invocation of pledge",
    "takeover", "open offer",
    "agm", "egm", "court convened meeting",
    "analyst", "investor meet", "concall",
    "press release", "media release",
    "restructuring", "merger", "amalgamation", "demerger", "acquisition",
    "change in management", "key managerial",
    "sebi order", "regulatory",
]

# CA categories already shown in the CA tab -- skip these
BSE_EXCLUDE_KW = [
    "interim dividend", "final dividend", "dividend",
    "buyback", "buy back",
    "rights issue",
    "record date",
    "delisting",
    "sub-division", "subdivision", "stock split",
    "bonus",
]

# Keywords that push a BSE filing to HIGH impact
HIGH_KW = [
    "insider trading", "sast", "pledge", "encumbrance",
    "takeover", "acquisition", "open offer",
    "board meeting", "financial results", "outcome",
    "merger", "amalgamation", "demerger",
    "sebi order", "regulatory",
    "change in management",
]

# Fallback sectors when sector_map.json is absent
FALLBACK_SECTORS = [
    ("Pharmaceuticals", 0),
    ("Finance", 0),
    ("FMCG", 0),
    ("Information Technology", 0),
    ("Capital Goods", 0),
    ("Chemicals", 0),
]

IST = timezone(timedelta(hours=5, minutes=30))


# ── helpers ──

def load_isins():
    env_isins = os.environ.get("RCB_ISINS")
    if env_isins:
        return json.loads(env_isins.lstrip("﻿"))
    if ISIN_FILE.exists():
        return json.loads(ISIN_FILE.read_text())
    return {}


def load_sector_map():
    if SECTOR_MAP_FILE.exists():
        try:
            return json.loads(SECTOR_MAP_FILE.read_text())
        except Exception:
            pass
    return {}


def top_sectors(sector_map, our_isins, n=6):
    if not sector_map:
        return FALLBACK_SECTORS[:n]
    counts = {}
    for isin in our_isins:
        s = sector_map.get(isin, {}).get("sector", "Other")
        if s and s != "Other":
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return FALLBACK_SECTORS[:n]
    return sorted(counts.items(), key=lambda x: -x[1])[:n]


def impact_for_count(count):
    if count > 100:
        return "HIGH"
    if count >= 20:
        return "MEDIUM"
    return "LOW"


def is_ca_category(text):
    t = text.lower()
    return any(kw in t for kw in BSE_EXCLUDE_KW)


def is_includeable(text):
    t = text.lower()
    return any(kw in t for kw in BSE_INCLUDE_KW)


def announcement_impact(text):
    t = text.lower()
    return "HIGH" if any(kw in t for kw in HIGH_KW) else "MEDIUM"


def parse_rss_date(date_str):
    if not date_str:
        return None
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%d %b %Y %H:%M:%S %z",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(IST)
        except ValueError:
            continue
    return None


# ── data fetchers ──

def fetch_bse_announcements(our_isins, days_back=2):
    today   = datetime.now(IST).date()
    from_dt = today - timedelta(days=days_back)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer":    "https://www.bseindia.com/",
        "Origin":     "https://www.bseindia.com",
    }
    params = {
        "strCat":      "-1",
        "strPrevDate": from_dt.strftime("%d/%m/%Y"),
        "strScrip":    "",
        "strSearch":   "P",
        "strtoDate":   today.strftime("%d/%m/%Y"),
        "strType":     "C",
        "subcategory": "-1",
    }
    print("  Fetching BSE announcements...")
    try:
        r = requests.get(
            "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
            params=params, headers=headers, timeout=20
        )
        r.raise_for_status()
        data = r.json()
        raw  = data if isinstance(data, list) else data.get("Table", data.get("data", []))
    except Exception as e:
        print(f"  BSE error: {e}")
        return []

    items = []
    for rec in raw:
        isin = (rec.get("ISIN") or rec.get("isin") or "").strip()
        if isin not in our_isins:
            continue

        headline  = (rec.get("HEADLINE") or "").strip()
        category  = (rec.get("CATEGORYNAME") or rec.get("SUBCATNAME") or "").strip()
        dt_str    = rec.get("DT_TM") or rec.get("NEWS_DT") or ""
        company   = our_isins.get(isin, rec.get("LONG_NAME", isin))
        scrip_cd  = rec.get("SCRIP_CD") or ""
        attach    = rec.get("ATTACHMENTNAME") or ""

        combined = f"{category} {headline}".strip()

        if is_ca_category(combined) and not is_includeable(combined):
            continue
        if not is_includeable(combined):
            continue

        if attach:
            url_link = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{attach}"
        elif scrip_cd:
            url_link = f"https://www.bseindia.com/corporates/ann.html?scripcd={scrip_cd}"
        else:
            url_link = ""

        items.append({
            "date":          (dt_str[:16] if dt_str else today.strftime("%d/%m/%Y")),
            "headline":      headline or category,
            "url":           url_link,
            "category":      "Exchange Filing",
            "sector":        company,
            "affected_count": 1,
            "impact":        announcement_impact(combined),
        })

    print(f"  BSE: {len(items)} matched announcements")
    return items


def fetch_rss_items(url, label, max_age_hours=48, max_items=8):
    items   = []
    cutoff  = datetime.now(IST) - timedelta(hours=max_age_hours)
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root    = ET.fromstring(r.content)
        channel = root.find("channel") or root
        for item in channel.findall("item"):
            title   = (item.findtext("title") or "").strip()
            link    = (item.findtext("link") or "").strip()
            pub_dt  = parse_rss_date(item.findtext("pubDate") or "")
            if pub_dt and pub_dt < cutoff:
                continue
            date_str = pub_dt.strftime("%d/%m/%Y %H:%M") if pub_dt else ""
            items.append({"date": date_str, "headline": title, "url": link})
            if len(items) >= max_items:
                break
    except Exception as e:
        print(f"  RSS {label}: {e}")
    return items


def fetch_macro_news():
    items = []
    sources = [
        ("https://www.rbi.org.in/scripts/RSS.aspx", "RBI"),
        ("https://www.sebi.gov.in/sebi_data/cms_feed/LatestNew.rss", "SEBI"),
    ]
    for url, label in sources:
        raw = fetch_rss_items(url, label)
        for r in raw:
            items.append({
                "date":          r["date"],
                "headline":      r["headline"],
                "url":           r["url"],
                "category":      f"Macro - {label}",
                "sector":        "Macro",
                "affected_count": -1,   # -1 = all holdings
                "impact":        "MEDIUM",
            })
        print(f"  {label}: {len(raw)} items")
    return items


def fetch_sector_news(sector_counts, total_isins):
    items = []
    for sector, count in sector_counts:
        query  = quote_plus(f"{sector} India NSE stock market")
        url    = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        raw    = fetch_rss_items(url, f"Google/{sector}", max_items=5)
        impact = impact_for_count(count) if count > 0 else "MEDIUM"
        for r in raw:
            items.append({
                "date":          r["date"],
                "headline":      r["headline"],
                "url":           r["url"],
                "category":      "Sector News",
                "sector":        sector,
                "affected_count": count if count > 0 else total_isins,
                "impact":        impact,
            })
        print(f"  Sector '{sector}' ({count} holdings): {len(raw)} items")
        time.sleep(0.4)
    return items


# ── main ──

def main():
    print(f"\n{'='*60}")
    print(f"MARVIN News Fetcher -- {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}")
    print(f"{'='*60}")

    our_isins  = load_isins()
    sector_map = load_sector_map()
    print(f"ISINs: {len(our_isins)}  |  Sector map: {len(sector_map)} entries")

    sectors = top_sectors(sector_map, our_isins, n=6)
    print(f"Top sectors: {[s for s, _ in sectors]}")

    all_items = []

    print("\n[1/3] BSE Exchange Announcements")
    all_items += fetch_bse_announcements(our_isins, days_back=2)

    print("\n[2/3] Macro (RBI / SEBI)")
    all_items += fetch_macro_news()

    print("\n[3/3] Sector News (Google News)")
    all_items += fetch_sector_news(sectors, len(our_isins))

    # Sort: HIGH first, then MEDIUM, then LOW
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_items.sort(key=lambda x: order.get(x["impact"], 3))

    OUT_FILE.write_text(json.dumps(all_items, indent=2, ensure_ascii=False))

    high = sum(1 for i in all_items if i["impact"] == "HIGH")
    med  = sum(1 for i in all_items if i["impact"] == "MEDIUM")
    low  = sum(1 for i in all_items if i["impact"] == "LOW")
    print(f"\nTotal: {len(all_items)} items  --  HIGH:{high}  MEDIUM:{med}  LOW:{low}")
    print(f"Saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
