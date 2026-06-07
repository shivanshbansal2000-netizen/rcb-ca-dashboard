"""
Generates a self-contained HTML dashboard from CA match data.
Called by ca_monitor.py after each fetch. Output: ca_dashboard.html
"""
from pathlib import Path
from datetime import datetime

OUT = Path(__file__).parent / "ca_dashboard.html"


def generate(matches, total_isins, last_updated):
    urgent   = [m for m in matches if m["urgent"]]
    missed   = [m for m in matches if m.get("missed")]
    upcoming = [m for m in matches if not m["urgent"] and not m.get("missed")]

    # Embed data as JS
    import json
    data_js = json.dumps(matches)

    # CA type badge colours
    type_colors = {
        "Dividend":         ("#0D6EFD", "#E7F1FF"),
        "Interim Dividend": ("#0D6EFD", "#E7F1FF"),
        "Final Dividend":   ("#0D6EFD", "#E7F1FF"),
        "Record Date":      ("#6F42C1", "#F3EFFF"),
        "Rights Issue":     ("#198754", "#D1E7DD"),
        "Buyback":          ("#FD7E14", "#FFF3CD"),
        "Open Offer":       ("#DC3545", "#F8D7DA"),
        "Delisting":        ("#212529", "#E2E3E5"),
    }

    def badge(ca_type):
        bg, light = type_colors.get(ca_type, ("#6C757D", "#F8F9FA"))
        return (f'<span style="background:{light};color:{bg};border:1px solid {bg};'
                f'padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">'
                f'{ca_type}</span>')

    def rows(items):
        out = ""
        for i, m in enumerate(items):
            is_missed = m.get("missed")
            urgbg  = "#FFE8E8" if is_missed else ("#FFF8E1" if m["urgent"] else ("#F9F9F9" if i % 2 else "#FFFFFF"))
            days_c = "#888" if is_missed else ("#DC3545" if m["urgent"] else ("#E67E00" if m["days_left"] <= 20 else "#198754"))
            days_label = f"{abs(m['days_left'])}d ago" if is_missed else f"{m['days_left']}d"
            out += f"""
            <tr style="background:{urgbg}">
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;color:#888;">{i+1}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;font-weight:600;">{m['name']}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#555;font-family:monospace;">{m['isin']}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;">{badge(m['ca_type'])}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;">{m['key_date']}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;font-weight:700;color:{days_c};">{days_label}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#666;">{m['subject'][:90]}</td>
            </tr>"""
        return out

    all_rows = rows(missed) + rows(urgent) + rows(upcoming)

    ca_types = sorted(set(m["ca_type"] for m in matches))
    filter_btns = "".join(
        f'<button onclick="filterType(\'{t}\')" style="margin:3px;padding:5px 12px;border:1px solid #ddd;'
        f'border-radius:20px;background:#fff;cursor:pointer;font-size:12px;">{t}</button>'
        for t in ca_types
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARVIN - CA Dashboard | RCB Holdings</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #F4F6F9; color: #212529; }}
  .header {{ background: linear-gradient(135deg, #1F3864, #2E5090); color: white; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }}
  .header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: 0.5px; }}
  .header p {{ font-size: 12px; opacity: 0.8; margin-top: 4px; }}
  .header .updated {{ font-size: 11px; opacity: 0.7; text-align: right; }}
  .stats {{ display: flex; gap: 16px; padding: 20px 32px; }}
  .stat-card {{ background: white; border-radius: 10px; padding: 16px 24px; flex: 1; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px solid #ddd; }}
  .stat-card.urgent {{ border-left-color: #DC3545; }}
  .stat-card.total  {{ border-left-color: #0D6EFD; }}
  .stat-card.watch  {{ border-left-color: #198754; }}
  .stat-card .val {{ font-size: 28px; font-weight: 700; }}
  .stat-card .lbl {{ font-size: 12px; color: #888; margin-top: 2px; }}
  .section {{ margin: 0 32px 24px; background: white; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; }}
  .section-header {{ padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; }}
  .section-header h2 {{ font-size: 14px; font-weight: 700; }}
  .section-header.urgent {{ background: #FFF5F5; }}
  .section-header.upcoming {{ background: #F0F7FF; }}
  .filters {{ padding: 12px 20px; border-bottom: 1px solid #eee; background: #FAFAFA; }}
  .filters span {{ font-size: 12px; color: #888; margin-right: 8px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ padding: 10px 12px; text-align: left; font-size: 11px; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid #eee; background: #FAFAFA; }}
  .search-bar {{ padding: 12px 20px; border-bottom: 1px solid #eee; }}
  .search-bar input {{ width: 100%; padding: 8px 14px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; outline: none; }}
  .search-bar input:focus {{ border-color: #1F3864; }}
  .no-data {{ padding: 40px; text-align: center; color: #888; font-size: 14px; }}
  .refresh-btn {{ background: white; border: 1px solid #ddd; border-radius: 6px; padding: 6px 14px; font-size: 12px; cursor: pointer; color: #555; }}
  .refresh-btn:hover {{ background: #F4F6F9; }}
  .footer {{ text-align: center; padding: 16px; font-size: 11px; color: #aaa; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>MARVIN - Corporate Action Dashboard</h1>
    <p>RCB Family Holdings &nbsp;|&nbsp; {total_isins} ISINs monitored &nbsp;|&nbsp; Next 30 days</p>
  </div>
  <div class="updated">
    Last updated<br><strong>{last_updated}</strong><br><br>
    <button class="refresh-btn" onclick="location.reload()">Refresh</button>
  </div>
</div>

<div class="stats">
  <div class="stat-card urgent">
    <div class="val">{len(urgent)}</div>
    <div class="lbl">Urgent (within 10 days)</div>
  </div>
  <div class="stat-card" style="border-left-color:#DC3545;background:#FFF5F5;">
    <div class="val" style="color:#DC3545;">{len(missed)}</div>
    <div class="lbl">Recently Missed (last 14 days)</div>
  </div>
  <div class="stat-card total">
    <div class="val">{len(matches)}</div>
    <div class="lbl">Total Actions</div>
  </div>
  <div class="stat-card watch">
    <div class="val">{total_isins}</div>
    <div class="lbl">ISINs Monitored</div>
  </div>
  <div class="stat-card" style="border-left-color:#6F42C1;">
    <div class="val">{len(set(m['ca_type'] for m in matches))}</div>
    <div class="lbl">Action Types</div>
  </div>
</div>

<div class="section">
  <div class="section-header">
    <h2>All Corporate Actions</h2>
    <span style="font-size:12px;color:#888;">{len(matches)} records</span>
  </div>
  <div class="search-bar">
    <input type="text" id="searchBox" placeholder="Search by stock name, ISIN, or action type..." onkeyup="filterTable()">
  </div>
  <div class="filters">
    <span>Filter:</span>
    <button onclick="filterType('ALL')" style="margin:3px;padding:5px 12px;border:1px solid #1F3864;border-radius:20px;background:#1F3864;color:white;cursor:pointer;font-size:12px;">All</button>
    {filter_btns}
  </div>
  {'<table><thead><tr><th>#</th><th>Stock Name</th><th>ISIN</th><th>Action</th><th>Key Date</th><th>Days Left</th><th>Details</th></tr></thead><tbody id="caTableBody">' + all_rows + '</tbody></table>' if matches else '<div class="no-data">No corporate actions due in the next 30 days.</div>'}
</div>

<div class="footer">
  MARVIN &nbsp;|&nbsp; Source: NSE / BSE &nbsp;|&nbsp; RCB Holdings only &nbsp;|&nbsp; Run ca_monitor.py to refresh
</div>

<script>
const allData = {data_js};

function filterTable() {{
  const q = document.getElementById('searchBox').value.toLowerCase();
  const rows = document.querySelectorAll('#caTableBody tr');
  rows.forEach(r => {{
    const txt = r.innerText.toLowerCase();
    r.style.display = txt.includes(q) ? '' : 'none';
  }});
}}

function filterType(type) {{
  const rows = document.querySelectorAll('#caTableBody tr');
  rows.forEach(r => {{
    if (type === 'ALL') {{ r.style.display = ''; return; }}
    r.style.display = r.innerText.toLowerCase().includes(type.toLowerCase()) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    return OUT
