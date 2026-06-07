"""
Daily CA monitor for RCB family holdings.
Fetches upcoming corporate actions from NSE for the next 30 days,
filters for our ISINs, and sends an email digest.

Run: python ca_monitor.py
"""
import json, sys, time, os
from pathlib import Path
from datetime import datetime, timedelta
import requests

from generate_dashboard import generate as generate_dashboard

# ── Config ──
HERE       = Path(__file__).parent
ISIN_FILE  = HERE / "rcb_isins.json"
STATE_FILE = HERE / "state.json"
GMAIL_TOOL = r"C:\Users\mlbca\Desktop\marvin\tools\gmail_sender\send.py"
FROM_EMAIL = "info@nextgenregistry.com"
TO_EMAIL   = "info@nextgenregistry.com"
WINDOW_DAYS = 30

CA_TYPES_WATCH = {
    "buy back":     "Buyback",
    "buyback":      "Buyback",
    "open offer":   "Open Offer",
    "rights":       "Rights Issue",
    "delisting":    "Delisting",
    "interim":      "Interim Dividend",
    "final":        "Final Dividend",
    "dividend":     "Dividend",
    "record":       "Record Date",
}

URGENT_DAYS  = 10   # flag as URGENT if deadline within this many days
LOOKBACK_DAYS = 14  # also surface recently missed past actions


# ── Load ISINs ──
def load_isins():
    # In CI: read from environment variable (GitHub Secret)
    env_isins = os.environ.get("RCB_ISINS")
    if env_isins:
        return json.loads(env_isins)
    # Local: read from file
    if not ISIN_FILE.exists():
        print("ERROR: rcb_isins.json not found and RCB_ISINS env var not set.")
        sys.exit(1)
    return json.loads(ISIN_FILE.read_text())


# ── Load / Save state ──
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_run": None, "alerted": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── NSE Session ──
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
        print(f"  Warning: NSE session prime failed — {e}")
    return s


# ── NSE: ISIN → Symbol map ──
def build_isin_symbol_map():
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    print("  Downloading NSE equity master...")
    try:
        r = requests.get(url, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        isin_map = {}
        for line in r.text.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) >= 7:
                symbol = parts[0].strip().strip('"')
                isin   = parts[6].strip().strip('"')
                name   = parts[1].strip().strip('"')
                if isin:
                    isin_map[isin] = {"symbol": symbol, "name": name}
        print(f"  NSE master loaded — {len(isin_map)} entries")
        return isin_map
    except Exception as e:
        print(f"  ERROR loading NSE master: {e}")
        return {}


# ── NSE: Fetch corporate actions ──
def fetch_nse_ca(session, from_dt, to_dt):
    from_str = from_dt.strftime("%d-%m-%Y")
    to_str   = to_dt.strftime("%d-%m-%Y")
    url = (f"https://www.nseindia.com/api/corporates-corporateActions"
           f"?index=equities&from_date={from_str}&to_date={to_str}")
    print(f"  Fetching NSE CAs: {from_str} to {to_str}")
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return []
    except Exception as e:
        print(f"  ERROR fetching NSE CA: {e}")
        return []


# ── BSE fallback: fetch corporate actions ──
def fetch_bse_ca(from_dt, to_dt):
    from_str = from_dt.strftime("%d/%m/%Y")
    to_str   = to_dt.strftime("%d/%m/%Y")
    url = "https://api.bseindia.com/BseIndiaAPI/api/CorporateAction/w"
    params = {
        "scripcode": "", "strtype": "",
        "strd1": from_str, "strd2": to_str,
        "Flag": "", "segment": "D"
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer":    "https://www.bseindia.com/",
        "Origin":     "https://www.bseindia.com",
    }
    print(f"  Fetching BSE CAs (fallback): {from_str} → {to_str}")
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("Table", "data", "Data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
    except Exception as e:
        print(f"  ERROR fetching BSE CA: {e}")
        return []


# ── Filter CAs for our ISINs ──
def filter_ca(ca_list, our_isins, isin_symbol_map):
    """
    Normalise NSE/BSE CA records and match against our ISIN set.
    Returns list of dicts: {isin, name, symbol, subject, ex_date, record_date, source}
    """
    today   = datetime.today().date()
    matches = []

    for item in ca_list:
        # --- NSE record fields ---
        symbol  = (item.get("symbol") or item.get("Symbol") or "").strip().upper()
        subject = (item.get("subject") or item.get("purpose") or item.get("Remarks") or "").strip()
        ex_raw  = item.get("exDate") or item.get("ExDate") or item.get("ex_date") or ""
        rec_raw = item.get("recordDate") or item.get("RecordDate") or item.get("record_date") or ""
        isin    = (item.get("isin") or item.get("ISIN") or "").strip()

        # Try to get ISIN from symbol map if not in record
        if not isin and symbol:
            for k, v in isin_symbol_map.items():
                if v.get("symbol") == symbol:
                    isin = k
                    break

        if isin not in our_isins:
            continue

        # Filter by CA type
        subject_lower = subject.lower()
        ca_type = None
        for keyword, label in CA_TYPES_WATCH.items():
            if keyword in subject_lower:
                ca_type = label
                break
        if not ca_type:
            continue

        # Parse date
        def parse_date(s):
            for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%b %d, %Y"):
                try:
                    return datetime.strptime(s.strip(), fmt).date()
                except:
                    pass
            return None

        key_date = parse_date(rec_raw) or parse_date(ex_raw)
        if not key_date:
            continue

        days_left = (key_date - today).days
        if days_left < -LOOKBACK_DAYS or days_left > WINDOW_DAYS:
            continue

        name = our_isins.get(isin, isin_symbol_map.get(isin, {}).get("name", "Unknown"))

        matches.append({
            "isin":      isin,
            "name":      name,
            "symbol":    symbol or isin_symbol_map.get(isin, {}).get("symbol", "-"),
            "ca_type":   ca_type,
            "subject":   subject,
            "key_date":  key_date.strftime("%d %b %Y"),
            "days_left": days_left,
            "urgent":    0 <= days_left <= URGENT_DAYS,
            "missed":    days_left < 0,
        })

    matches.sort(key=lambda x: x["days_left"])
    return matches


# ── Build HTML email ──
def build_html(matches, today):
    urgent  = [m for m in matches if m["urgent"]]
    upcoming = [m for m in matches if not m["urgent"]]

    def rows(items, bg_urgent=False):
        out = ""
        for i, m in enumerate(items):
            bg = "#FFF3CD" if m["urgent"] else ("#F9F9F9" if i % 2 else "#FFFFFF")
            badge_color = "#DC3545" if m["urgent"] else "#0D6EFD"
            badge = f'<span style="background:{badge_color};color:white;padding:2px 8px;border-radius:10px;font-size:11px;">{m["ca_type"]}</span>'
            out += f"""
            <tr style="background:{bg}">
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;">{i+1}</td>
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;font-weight:bold;">{m['name']}</td>
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;">{m['isin']}</td>
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;">{badge}</td>
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;">{m['key_date']}</td>
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;{'color:#DC3545;font-weight:bold' if m['urgent'] else ''}">{m['days_left']} days</td>
              <td style="padding:8px;border:1px solid #ddd;font-size:12px;color:#555;">{m['subject'][:80]}</td>
            </tr>"""
        return out

    table_hdr = """
    <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;">
      <thead>
        <tr style="background:#1F3864;color:white;">
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">#</th>
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">Stock</th>
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">ISIN</th>
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">Action</th>
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">Key Date</th>
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">Days Left</th>
          <th style="padding:10px;border:1px solid #ddd;text-align:left;">Details</th>
        </tr>
      </thead>
      <tbody>"""

    urgent_section = ""
    if urgent:
        urgent_section = f"""
        <h3 style="color:#DC3545;margin-top:24px;">
          URGENT - Act within {URGENT_DAYS} days ({len(urgent)} action{'s' if len(urgent)>1 else ''})
        </h3>
        {table_hdr}{rows(urgent)}</tbody></table>"""

    upcoming_section = ""
    if upcoming:
        upcoming_section = f"""
        <h3 style="color:#1F3864;margin-top:24px;">
          Upcoming - Next 30 Days ({len(upcoming)} action{'s' if len(upcoming)>1 else ''})
        </h3>
        {table_hdr}{rows(upcoming)}</tbody></table>"""

    no_action = ""
    if not matches:
        no_action = """
        <div style="padding:20px;background:#E8F5E9;border-radius:6px;color:#2E7D32;font-family:Arial;">
          No corporate actions due in the next 30 days for RCB holdings.
        </div>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:1000px;margin:0 auto;padding:20px;">
      <div style="background:#1F3864;color:white;padding:16px 20px;border-radius:6px 6px 0 0;">
        <h2 style="margin:0;">MARVIN — Corporate Action Alert</h2>
        <p style="margin:4px 0 0;font-size:13px;">RCB Family Holdings &nbsp;|&nbsp; {today.strftime('%d %B %Y')} &nbsp;|&nbsp; 671 ISINs monitored</p>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:16px;border-radius:0 0 6px 6px;">
        {urgent_section}
        {upcoming_section}
        {no_action}
        <p style="font-size:11px;color:#999;margin-top:24px;">
          Monitored actions: Rights Issues, Buybacks, Open Offers, Dividends<br>
          Source: NSE / BSE &nbsp;|&nbsp; Sent by MARVIN
        </p>
      </div>
    </body></html>"""
    return html


# ── Send email ──
def send_email(subject, html):
    try:
        gmail.send_email(
            to=[TO_EMAIL],
            subject=subject,
            body="",
            html=html,
            attachments=[],
            cc=[],
            thread_id="",
            sender=FROM_EMAIL,
            forward_thread_id="",
        )
        print("  Email sent.")
    except Exception as e:
        print(f"  Email FAILED: {e}")


# ── Main ──
def main():
    today = datetime.today()
    print(f"\n{'='*60}")
    print(f"MARVIN CA Monitor — {today.strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}")

    our_isins = load_isins()
    print(f"Loaded {len(our_isins)} RCB equity ISINs")

    # Build ISIN → NSE symbol map
    isin_symbol_map = build_isin_symbol_map()

    # Date window — look back for missed actions too
    from_dt = today - timedelta(days=LOOKBACK_DAYS)
    to_dt   = today + timedelta(days=WINDOW_DAYS)

    # Fetch CAs — NSE first, BSE fallback
    session = nse_session()
    ca_list = fetch_nse_ca(session, from_dt, to_dt)

    if not ca_list:
        print("  NSE returned no data, trying BSE fallback...")
        ca_list = fetch_bse_ca(from_dt, to_dt)

    print(f"  Total CA records fetched: {len(ca_list)}")

    # Filter for our ISINs
    matches = filter_ca(ca_list, our_isins, isin_symbol_map)
    print(f"  Matched to RCB holdings: {len(matches)}")

    # Generate HTML dashboard
    dash = generate_dashboard(matches, len(our_isins), today.strftime("%d %b %Y %H:%M"))
    print(f"  Dashboard: {dash}")

    # Email disabled — NEXTGEN company email must not be used for personal/family projects
    urgent_count = sum(1 for m in matches if m["urgent"])

    # Save state
    state = load_state()
    state["last_run"] = today.isoformat()
    save_state(state)

    print(f"\nDone. {len(matches)} actions found ({urgent_count} urgent).")


if __name__ == "__main__":
    main()
