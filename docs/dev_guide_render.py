"""Lays out the guide (content comes from build_dev_guide.py) and prints docs/ProductLoop_Dev_Guide.pdf with headless Edge.
Run from the repo root: python3 docs/dev_guide_render.py   (set EDGE=/path/to/chromium-based-browser if not on macOS)"""
import runpy, subprocess, os, sys, re, json, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
g = runpy.run_path(str(HERE / "build_dev_guide.py")); PAGES = g["PAGES"]
CSS = """
@page{size:A4;margin:0}*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Helvetica Neue",Arial,sans-serif;font-size:9pt;line-height:1.38;color:#1f2937;background:#fff}
.page{width:210mm;height:296.4mm;padding:11mm 12mm 0 12mm;position:relative;overflow:hidden;break-after:page;page-break-after:always}
.page:last-child{break-after:auto;page-break-after:auto}
.foot{position:absolute;left:12mm;right:12mm;bottom:6mm;display:flex;justify-content:space-between;font-size:7.6pt;color:#9ca3af;border-top:.5pt solid #e5e7eb;padding-top:2mm}
h1{font-size:25pt;margin:6mm 0 2mm;color:#0b57d0;line-height:1.1}
h2{font-size:12.2pt;margin:3.2mm 0 1.4mm;color:#0b57d0;border-bottom:1.2px solid #dbe5fb;padding-bottom:1mm;break-after:avoid}
h2.nb{margin-top:0}h3{font-size:10pt;margin:2.5mm 0 1mm;color:#1f2937}
p{margin:1.2mm 0}.small{font-size:7.9pt;color:#6b7280}
ul,ol{margin:.8mm 0 .8mm 4.6mm;padding:0}li{margin:.5mm 0}
table{width:100%;border-collapse:collapse;margin:1.4mm 0 1.2mm;table-layout:fixed}
th{background:#eef3fd;color:#374151;text-align:left;font-size:7.6pt;text-transform:uppercase;letter-spacing:.03em;padding:1.1mm 1.6mm;border-bottom:.7pt solid #cfd8ea}
td{padding:1mm 1.6mm;border-bottom:.5pt solid #e8ebf0;vertical-align:top;font-size:8.1pt;word-wrap:break-word}
tr{break-inside:avoid}
code{font-family:Menlo,Consolas,monospace;font-size:7.6pt;background:#f1f3f6;padding:0 .8mm;border-radius:.8mm}
pre{font-family:Menlo,Consolas,monospace;font-size:6.7pt;line-height:1.32;background:#f7f8fa;border:.5pt solid #e5e7eb;border-radius:1.2mm;padding:2mm 2.4mm;margin:1.2mm 0;white-space:pre;overflow:hidden}
.cover{padding-top:16mm}.kicker{font-size:11pt;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:#6b7280}
.tagline{font-size:10pt;color:#4b5563;margin:1mm 0 5mm}.meta td{font-size:8.2pt}
.toc{width:100%;border:0}.toc td{border:0;padding:.35mm 0;font-size:9pt}.toc td:last-child{text-align:right;width:12mm;color:#6b7280}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:5mm}
.box{border-left:2.4px solid #1a73e8;background:#eff5ff;padding:1.6mm 2.4mm;margin:1.4mm 0;border-radius:0 1.2mm 1.2mm 0}
.box.warn{border-color:#f0b429;background:#fff8e6}.box.red{border-color:#dc2626;background:#fef2f2}.box.ok{border-color:#16a34a;background:#f0fdf4}
.arch{border:.6pt solid #d6deec;border-radius:2mm;padding:2.4mm;background:#fbfcfe}.lane{margin:0}.lt{font-size:7.4pt;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;margin:0 0 1mm}
.row{display:flex;gap:2mm}.b{flex:1;border:.9pt solid #9db7ee;background:#f4f8ff;border-radius:1.6mm;padding:1.6mm 2mm;font-size:7.6pt;text-align:center}
.b b{display:block;font-size:8.4pt;color:#0b57d0;margin-bottom:.4mm}.b.g{border-color:#7fd19a;background:#f1fbf4}.b.g b{color:#166534}
.b.big{text-align:left;font-size:7.7pt}.b strong{font-weight:700}.b.c3{flex:2.2}.ar{text-align:center;color:#6b7280;font-size:7.6pt;margin:1mm 0}
.tag{display:inline-block;font-size:7.2pt;font-weight:700;border-radius:2mm;padding:0 1.6mm}.t-hi{background:#fee2e2;color:#991b1b}.t-md{background:#fef3c7;color:#92400e}.t-lo{background:#dcfce7;color:#166534}
.tight th{text-transform:none;font-size:7.4pt}.sym.tight td{padding:.3mm 1.4mm;font-size:7.1pt}.sym td{font-size:7.6pt}.tight td{padding:.6mm 1.4mm;font-size:7.7pt}.mono td:first-child{font-family:Menlo,monospace;font-size:7.3pt}
"""
def toc_html():
    rows = [(lab, i + 1) for i, (lab, _) in enumerate(PAGES) if lab]
    return '<table class="toc">' + "".join(f"<tr><td>{l}</td><td>{n}</td></tr>" for l, n in rows) + "</table>"
def build(measure=False):
    n = len(PAGES); out = []
    for i, (lab, body) in enumerate(PAGES):
        body = body.replace("%%TOC%%", toc_html())
        out.append(f'<section class="page" data-p="{i+1}">{body}<div class="foot"><span>ProductLoop · Developer guide v1.0 · 8 Oct 2026 · fictional data, prototype</span><span>Page {i+1} of {n}</span></div></section>')
    js = """<script>addEventListener('load',()=>{const r=[];document.querySelectorAll('.page').forEach(p=>{const foot=p.querySelector('.foot').offsetHeight+22;
      const lim=p.clientHeight-foot;let max=0;[...p.children].forEach(c=>{if(!c.classList.contains('foot'))max=Math.max(max,c.offsetTop+c.offsetHeight)});
      r.push(p.dataset.p+':'+Math.round(max)+'/'+Math.round(lim)+(max>lim?' OVER':''))});document.title=r.join(' ')})</script>""" if measure else ""
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>x</title><style>{CSS}</style></head><body>{"".join(out)}{js}</body></html>'
EDGE = os.environ.get("EDGE", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
tmp = Path("/tmp/devguide"); tmp.mkdir(exist_ok=True)
(tmp / "m.html").write_text(build(True), encoding="utf8"); (tmp / "g.html").write_text(build(False), encoding="utf8")
dom = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--virtual-time-budget=4000", "--dump-dom", f"file://{tmp/'m.html'}"], capture_output=True, text=True).stdout
title = re.search(r"<title>([^<]*)</title>", dom); print("fit (content bottom / limit, px):", title.group(1) if title else "?")
pdf = HERE / "ProductLoop_Dev_Guide.pdf"
subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", f"file://{tmp/'g.html'}"], capture_output=True)
pages = len(re.findall(rb"/Type\s*/Page[^s]", open(pdf, "rb").read())); print("pdf pages:", pages, "expected:", len(PAGES), "->", pdf)
(tmp / "g.html").replace(HERE.parent / ".devguide_preview.html") if "--keep" in sys.argv else None
