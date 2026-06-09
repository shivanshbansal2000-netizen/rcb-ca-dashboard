"""
Generates a self-contained HTML dashboard from CA match data + news/events data.
Called by ca_monitor.py after each fetch. Output: index.html

Reads news_data.json (if present) to populate the News & Events tab.
"""
import json
from pathlib import Path
from datetime import datetime

OUT       = Path(__file__).parent / "index.html"
NEWS_FILE = Path(__file__).parent / "news_data.json"


def _load_news():
    if NEWS_FILE.exists():
        try:
            return json.loads(NEWS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def generate(matches, total_isins, last_updated):
    urgent   = [m for m in matches if m["urgent"]]
    missed   = [m for m in matches if m.get("missed")]
    upcoming = [m for m in matches if not m["urgent"] and not m.get("missed")]
    news     = _load_news()

    n_high = sum(1 for n in news if n["impact"] == "HIGH")
    n_med  = sum(1 for n in news if n["impact"] == "MEDIUM")
    n_low  = sum(1 for n in news if n["impact"] == "LOW")

    # ── CA badge colours ──
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

    def ca_badge(ca_type):
        bg, light = type_colors.get(ca_type, ("#6C757D", "#F8F9FA"))
        return (f'<span style="background:{light};color:{bg};border:1px solid {bg};'
                f'padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">'
                f'{ca_type}</span>')

    def impact_badge(impact):
        cfg = {
            "HIGH":   ("#DC3545", "#FFF0F0"),
            "MEDIUM": ("#E67E00", "#FFF8E1"),
            "LOW":    ("#0D6EFD", "#E7F1FF"),
        }
        bg, light = cfg.get(impact, ("#6C757D", "#F8F9FA"))
        return (f'<span style="background:{light};color:{bg};border:1px solid {bg};'
                f'padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;">'
                f'{impact}</span>')

    def ca_rows(items):
        out = ""
        for i, m in enumerate(items):
            is_missed = m.get("missed")
            urgbg    = "#FFE8E8" if is_missed else ("#FFF8E1" if m["urgent"] else ("#F9F9F9" if i % 2 else "#FFFFFF"))
            days_c   = "#888" if is_missed else ("#DC3545" if m["urgent"] else ("#E67E00" if m["days_left"] <= 20 else "#198754"))
            days_lbl = f"{abs(m['days_left'])}d ago" if is_missed else f"{m['days_left']}d"
            out += f"""
            <tr style="background:{urgbg}">
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;color:#888;">{i+1}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;font-weight:600;">{m['name']}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#555;font-family:monospace;">{m['isin']}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;">{ca_badge(m['ca_type'])}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;">{m['key_date']}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;font-weight:700;color:{days_c};">{days_lbl}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#666;">{m['subject'][:90]}</td>
            </tr>"""
        return out

    def news_rows(items):
        out = ""
        for i, n in enumerate(items):
            rowbg = "#F9F9F9" if i % 2 else "#FFFFFF"
            cnt   = n.get("affected_count", 0)
            if cnt == -1:
                affected = f"All ({total_isins})"
            elif cnt == 1:
                affected = "1 holding"
            elif cnt > 1:
                affected = f"{cnt} holdings"
            else:
                affected = "-"
            headline = n.get("headline", "")
            url      = n.get("url", "")
            hl_html  = (f'<a href="{url}" target="_blank" rel="noopener" style="color:#1F3864;text-decoration:none;">'
                        f'{headline[:110]}</a>' if url else headline[:110])
            out += f"""
            <tr class="news-row" data-impact="{n['impact']}" data-category="{n.get('category','')}" style="background:{rowbg}">
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;color:#888;">{i+1}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#555;white-space:nowrap;">{n.get('date','')[:16]}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:12px;">{hl_html}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#555;">{n.get('category','')}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#444;">{n.get('sector','')[:40]}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;font-size:11px;color:#555;">{affected}</td>
              <td style="padding:9px 12px;border-bottom:1px solid #eee;">{impact_badge(n['impact'])}</td>
            </tr>"""
        return out

    ca_types      = sorted(set(m["ca_type"] for m in matches))
    ca_filter_btns = "".join(
        f'<button onclick="filterCa(\'{t}\')" style="margin:3px;padding:5px 12px;border:1px solid #ddd;'
        f'border-radius:20px;background:#fff;cursor:pointer;font-size:12px;">{t}</button>'
        for t in ca_types
    )

    all_ca_rows   = ca_rows(missed + urgent + upcoming)
    all_news_rows = news_rows(news)

    news_tab_badge = (f'<span style="background:#DC3545;color:white;border-radius:10px;'
                      f'padding:1px 7px;font-size:10px;margin-left:6px;">{n_high}</span>'
                      if n_high > 0 else "")

    news_empty = ('' if news else
                  '<div style="padding:40px;text-align:center;color:#888;font-size:14px;">'
                  'No news data yet. Run <code>fetch_news.py</code> to populate.</div>')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARVIN - RCB Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #F4F6F9; color: #212529; }}
  .header {{ background: linear-gradient(135deg, #1F3864, #2E5090); color: white; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }}
  .header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: 0.5px; }}
  .header p {{ font-size: 12px; opacity: 0.8; margin-top: 4px; }}
  .header .updated {{ font-size: 11px; opacity: 0.7; text-align: right; }}
  .tab-nav {{ background: #1a3070; padding: 0 32px; display: flex; gap: 4px; }}
  .tab-btn {{ background: transparent; border: none; color: rgba(255,255,255,0.65); padding: 12px 20px; cursor: pointer; font-size: 13px; font-weight: 600; border-bottom: 3px solid transparent; transition: all 0.15s; }}
  .tab-btn:hover {{ color: white; }}
  .tab-btn.active {{ color: white; border-bottom-color: #FFC107; }}
  .stats {{ display: flex; gap: 16px; padding: 20px 32px; }}
  .stat-card {{ background: white; border-radius: 10px; padding: 16px 24px; flex: 1; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px solid #ddd; }}
  .stat-card .val {{ font-size: 28px; font-weight: 700; }}
  .stat-card .lbl {{ font-size: 12px; color: #888; margin-top: 2px; }}
  .section {{ margin: 0 32px 24px; background: white; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; }}
  .section-header {{ padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; }}
  .section-header h2 {{ font-size: 14px; font-weight: 700; }}
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
  .impact-meter {{ display: flex; gap: 16px; padding: 20px 32px 8px; }}
  .impact-card {{ background: white; border-radius: 10px; padding: 16px 28px; flex: 0 0 auto; box-shadow: 0 1px 4px rgba(0,0,0,0.08); text-align: center; cursor: pointer; transition: transform 0.1s; }}
  .impact-card:hover {{ transform: translateY(-2px); }}
  .impact-card .count {{ font-size: 32px; font-weight: 700; }}
  .impact-card .label {{ font-size: 12px; color: #888; margin-top: 2px; }}
  .impact-card.high {{ border-left: 4px solid #DC3545; }}
  .impact-card.medium {{ border-left: 4px solid #E67E00; }}
  .impact-card.low {{ border-left: 4px solid #0D6EFD; }}
  .footer {{ text-align: center; padding: 16px; font-size: 11px; color: #aaa; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>MARVIN - RCB Holdings Dashboard</h1>
    <p>{total_isins} ISINs monitored &nbsp;|&nbsp; Corporate Actions + News & Events</p>
  </div>
  <div class="updated">
    Last updated<br><strong>{last_updated}</strong><br><br>
    <button class="refresh-btn" onclick="location.reload()">Refresh</button>
  </div>
</div>

<div class="tab-nav">
  <button class="tab-btn active" id="btn-ca" onclick="switchTab('ca', this)">
    Corporate Actions &nbsp;<span style="background:rgba(255,255,255,0.25);border-radius:10px;padding:1px 7px;font-size:10px;">{len(matches)}</span>
  </button>
  <button class="tab-btn" id="btn-news" onclick="switchTab('news', this)">
    News &amp; Events{news_tab_badge}
  </button>
</div>

<!-- ══ CA TAB ══ -->
<div id="tab-ca">

<div class="stats">
  <div class="stat-card" style="border-left-color:#DC3545;">
    <div class="val" style="color:#DC3545;">{len(urgent)}</div>
    <div class="lbl">Urgent (within 10 days)</div>
  </div>
  <div class="stat-card" style="border-left-color:#DC3545;background:#FFF5F5;">
    <div class="val" style="color:#DC3545;">{len(missed)}</div>
    <div class="lbl">Recently Missed (last 14 days)</div>
  </div>
  <div class="stat-card" style="border-left-color:#0D6EFD;">
    <div class="val">{len(matches)}</div>
    <div class="lbl">Total Actions</div>
  </div>
  <div class="stat-card" style="border-left-color:#198754;">
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
    <input type="text" id="caSearch" placeholder="Search by stock name, ISIN, or action type..." onkeyup="filterCaTable()">
  </div>
  <div class="filters">
    <span>Filter:</span>
    <button onclick="filterCa('ALL')" style="margin:3px;padding:5px 12px;border:1px solid #1F3864;border-radius:20px;background:#1F3864;color:white;cursor:pointer;font-size:12px;">All</button>
    {ca_filter_btns}
  </div>
  {'<table><thead><tr><th>#</th><th>Stock Name</th><th>ISIN</th><th>Action</th><th>Key Date</th><th>Days Left</th><th>Details</th></tr></thead><tbody id="caTableBody">' + all_ca_rows + '</tbody></table>' if matches else '<div class="no-data">No corporate actions due in the next 30 days.</div>'}
</div>

</div><!-- /tab-ca -->

<!-- ══ NEWS TAB ══ -->
<div id="tab-news" style="display:none;">

<div class="impact-meter">
  <div class="impact-card high" onclick="filterNews('HIGH')">
    <div class="count" style="color:#DC3545;">{n_high}</div>
    <div class="label">HIGH Impact</div>
  </div>
  <div class="impact-card medium" onclick="filterNews('MEDIUM')">
    <div class="count" style="color:#E67E00;">{n_med}</div>
    <div class="label">MEDIUM Impact</div>
  </div>
  <div class="impact-card low" onclick="filterNews('LOW')">
    <div class="count" style="color:#0D6EFD;">{n_low}</div>
    <div class="label">LOW Impact</div>
  </div>
  <div class="impact-card" style="border-left:4px solid #198754;cursor:default;">
    <div class="count" style="color:#198754;">{len(news)}</div>
    <div class="label">Total Items</div>
  </div>
</div>

<div class="section" style="margin-top:8px;">
  <div class="section-header">
    <h2>News &amp; Events</h2>
    <span style="font-size:12px;color:#888;">Last 48 hours &nbsp;|&nbsp; {len(news)} items</span>
  </div>
  <div class="search-bar">
    <input type="text" id="newsSearch" placeholder="Search headlines, sectors, categories..." onkeyup="filterNewsTable()">
  </div>
  <div class="filters">
    <span>Impact:</span>
    <button onclick="filterNews('ALL')" style="margin:3px;padding:5px 12px;border:1px solid #1F3864;border-radius:20px;background:#1F3864;color:white;cursor:pointer;font-size:12px;">All</button>
    <button onclick="filterNews('HIGH')"   style="margin:3px;padding:5px 12px;border:1px solid #DC3545;border-radius:20px;background:#fff;color:#DC3545;cursor:pointer;font-size:12px;font-weight:700;">HIGH</button>
    <button onclick="filterNews('MEDIUM')" style="margin:3px;padding:5px 12px;border:1px solid #E67E00;border-radius:20px;background:#fff;color:#E67E00;cursor:pointer;font-size:12px;font-weight:700;">MEDIUM</button>
    <button onclick="filterNews('LOW')"    style="margin:3px;padding:5px 12px;border:1px solid #0D6EFD;border-radius:20px;background:#fff;color:#0D6EFD;cursor:pointer;font-size:12px;font-weight:700;">LOW</button>
    &nbsp;<span>Category:</span>
    <button onclick="filterNewsCat('Exchange Filing')"  style="margin:3px;padding:5px 12px;border:1px solid #ddd;border-radius:20px;background:#fff;cursor:pointer;font-size:12px;">Exchange Filings</button>
    <button onclick="filterNewsCat('Sector News')"      style="margin:3px;padding:5px 12px;border:1px solid #ddd;border-radius:20px;background:#fff;cursor:pointer;font-size:12px;">Sector News</button>
    <button onclick="filterNewsCat('Macro')"            style="margin:3px;padding:5px 12px;border:1px solid #ddd;border-radius:20px;background:#fff;cursor:pointer;font-size:12px;">Macro</button>
  </div>
  {('<table><thead><tr><th>#</th><th>Date</th><th>Headline</th><th>Category</th><th>Company / Sector</th><th>Holdings Affected</th><th>Impact</th></tr></thead><tbody id="newsTableBody">' + all_news_rows + '</tbody></table>') if news else news_empty}
</div>

</div><!-- /tab-news -->

<div class="footer">
  MARVIN &nbsp;|&nbsp; Sources: NSE / BSE / RBI / SEBI / Google News &nbsp;|&nbsp; RCB Holdings only
</div>

<script>
function switchTab(name, btn) {{
  document.getElementById('tab-ca').style.display    = (name === 'ca')   ? '' : 'none';
  document.getElementById('tab-news').style.display  = (name === 'news') ? '' : 'none';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}

function filterCaTable() {{
  const q = document.getElementById('caSearch').value.toLowerCase();
  document.querySelectorAll('#caTableBody tr').forEach(r => {{
    r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none';
  }});
}}

function filterCa(type) {{
  document.querySelectorAll('#caTableBody tr').forEach(r => {{
    if (type === 'ALL') {{ r.style.display = ''; return; }}
    r.style.display = r.innerText.toLowerCase().includes(type.toLowerCase()) ? '' : 'none';
  }});
}}

function filterNewsTable() {{
  const q = document.getElementById('newsSearch').value.toLowerCase();
  document.querySelectorAll('#newsTableBody .news-row').forEach(r => {{
    r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none';
  }});
}}

function filterNews(impact) {{
  document.querySelectorAll('#newsTableBody .news-row').forEach(r => {{
    if (impact === 'ALL') {{ r.style.display = ''; return; }}
    r.style.display = r.dataset.impact === impact ? '' : 'none';
  }});
}}

function filterNewsCat(cat) {{
  document.querySelectorAll('#newsTableBody .news-row').forEach(r => {{
    r.style.display = r.dataset.category.includes(cat) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    return OUT
