"""app.py — DSS prototype frontend (drill-down + dark mode + reason lookup).
Run: streamlit run app.py
Python side runs loader -> normalize -> scoring -> mcda, then injects the result
as JSON into a self-contained HTML/JS drill-down component. Other five modules untouched.
"""
import json
import pandas as pd
import yaml
import streamlit as st
import streamlit.components.v1 as components

from modules.loader import load_batteries
from modules.normalize import normalize
from modules.scoring import score_dimensions
from modules.mcda import recommend

st.set_page_config(page_title="EV Battery End-of-Life Decision Support", layout="wide")

# ---- Global style polish: larger base font, tighter headings, more breathing room ----
st.markdown("""
<style>
  html, body, [class*="css"] { font-size: 16px; }
  .block-container { padding-top: 2.5rem; max-width: 1100px; }
  h1 { font-size: 2rem !important; font-weight: 650 !important; letter-spacing: -0.02em; }
  h2 { font-size: 1.45rem !important; font-weight: 600 !important; }
  h3 { font-size: 1.2rem !important; font-weight: 600 !important; }
  .stCaption, [data-testid="stCaptionContainer"] { font-size: 0.95rem !important; }
  section[data-testid="stSidebar"] { font-size: 1rem; }
  .streamlit-expanderHeader, [data-testid="stExpander"] summary {
    font-size: 1.15rem !important; font-weight: 600 !important;
  }
  [data-testid="stExpander"] summary p { font-size: 1.15rem !important; font-weight: 600 !important; }
  .stSlider label { font-size: 0.95rem !important; }
  div[data-testid="stMarkdownContainer"] p { font-size: 1rem; line-height: 1.65; }
</style>
""", unsafe_allow_html=True)

PATH_COLORS = {
    "reuse": "#1baf7a",
    "remanufacture": "#2a78d6",
    "resell": "#4a3aa7",
    "recycle": "#898781",
}


@st.cache_data
def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


cfg = load_config()

with st.sidebar:
    st.header("Input & parameters")
    uploaded = st.file_uploader("Upload battery data CSV", type="csv")
    st.subheader("Dimension weights (live)")
    w_value = st.slider("Residual value", 0.0, 1.0, float(cfg["dimension_weights"]["value"]), 0.05)
    w_risk = st.slider("Safety & compliance", 0.0, 1.0, float(cfg["dimension_weights"]["risk"]), 0.05)
    w_liq = st.slider("Market liquidity", 0.0, 1.0, float(cfg["dimension_weights"]["liquidity"]), 0.05)
    w_time = st.slider("Time window", 0.0, 1.0, float(cfg["dimension_weights"]["time_window"]), 0.05)

cfg["dimension_weights"] = {"value": w_value, "risk": w_risk, "liquidity": w_liq, "time_window": w_time}

csv_path = uploaded if uploaded else "data/batteries.csv"
df = load_batteries(csv_path)
df = normalize(df, cfg)
df = score_dimensions(df, cfg)
result = recommend(df, cfg)

path_order = list(cfg["pathways"].keys())
paths_payload = []
batteries_payload = {}
for key in path_order:
    grp = result[result["top_key"] == key]
    label = cfg["pathways"][key]["label"]
    paths_payload.append({
        "name": label, "key": key,
        "color": PATH_COLORS.get(key, "#888780"), "count": int(len(grp)),
    })
    batteries_payload[key] = [
        {
            "id": r["battery_id"],
            "soh": r["soh_pct"], "age": r["age_years"], "faults": r["fault_count"],
            "conf": r["confidence"],
            "v": r["value_score"], "r": r["risk_score"],
            "l": r["liquidity_score"], "t": r["time_window_score"],
        }
        for _, r in grp.iterrows()
    ]

total_recoverable = float(result["book_value_usd"].sum())
total_count = int(len(result))

payload = {
    "paths": [p for p in paths_payload if p["count"] > 0],
    "batteries": batteries_payload,
    "totalRecoverable": total_recoverable,
    "totalCount": total_count,
}

st.title("EV Battery Second-life Decision Support")
st.caption("Click a pie slice to see batteries on that pathway, then click a battery to expand its scores")

HTML = """
<style>
  :root {
    --c-text: #2c2c2a; --c-text-mut: #888780; --c-text-faint: #b4b2a9;
    --c-text-sub: #5f5e5a; --c-surface: #ffffff; --c-panel: #f6f5f0;
    --c-border: #e3e1d8; --c-border-soft: #ecebe4; --c-pie-border: #ffffff;
    --c-hover: #f1efe8; --c-card: #ffffff;
    --c-warn-fg: #854f0b; --c-warn-bg: #faeeda;
    --c-ok-fg: #27500a; --c-ok-bg: #eaf3de;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --c-text: #e8e6dd; --c-text-mut: #9c9a92; --c-text-faint: #73726c;
      --c-text-sub: #b4b2a9; --c-surface: #201f1e; --c-panel: #2c2c2a;
      --c-border: #3c3c39; --c-border-soft: #333331; --c-pie-border: #14100f;
      --c-hover: #2c2c2a; --c-card: #1a1a19;
      --c-warn-fg: #fac775; --c-warn-bg: #412402;
      --c-ok-fg: #c0dd97; --c-ok-bg: #173404;
    }
  }
  body { background: transparent; margin: 0; }
  * { box-sizing: border-box; }
</style>
<div id="app" style="font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color: var(--c-text);">
  <div style="display:flex; gap:32px; align-items:center; flex-wrap:wrap;
       background:var(--c-card); border:1px solid var(--c-border); border-radius:16px; padding:24px 28px;">
    <div style="position:relative; width:250px; height:250px; flex-shrink:0;">
      <canvas id="pie"></canvas>
      <div id="center" style="position:absolute; inset:0; display:flex; flex-direction:column;
           align-items:center; justify-content:center; pointer-events:none;">
        <div style="font-size:13px; color:var(--c-text-mut); margin-bottom:2px;">Est. recoverable value</div>
        <div id="centerVal" style="font-size:32px; font-weight:650; color:var(--c-text); line-height:1.1;"></div>
        <div style="font-size:12px; color:var(--c-text-faint); margin-top:2px;" id="centerSub"></div>
      </div>
    </div>
    <div id="legend" style="flex:1; min-width:220px;"></div>
  </div>
  <div id="detail" style="margin-top:24px;"></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const DATA = __PAYLOAD__;
const dims = [['v','Residual value'],['r','Safety & compliance'],['l','Liquidity'],['t','Time window']];
const fmtMoney = (n) => '$' + (n>=1000 ? (n/1000).toFixed(1)+'k' : Math.round(n));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
let activeIdx = 0;

document.getElementById('centerVal').textContent = fmtMoney(DATA.totalRecoverable);
document.getElementById('centerSub').textContent = DATA.totalCount + ' batteries';

const legendEl = document.getElementById('legend');
function renderLegend() {
  legendEl.innerHTML = '';
  DATA.paths.forEach((p,i) => {
    const active = i === activeIdx;
    const row = document.createElement('div');
    row.style.cssText = 'display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; cursor:pointer; margin-bottom:6px; transition:background .12s; border:1px solid '+(active?'var(--c-border)':'transparent')+'; background:'+(active?'var(--c-hover)':'transparent')+';';
    row.onmouseenter = ()=> { if(i!==activeIdx) row.style.background='var(--c-hover)'; };
    row.onmouseleave = ()=> { if(i!==activeIdx) row.style.background='transparent'; };
    row.onclick = ()=> selectPath(i);
    row.innerHTML =
      '<span style="width:12px; height:12px; border-radius:3px; background:'+p.color+'; flex-shrink:0;"></span>'+
      '<span style="flex:1; font-size:15px; color:var(--c-text);">'+p.name+'</span>'+
      '<span style="font-size:16px; font-weight:650; color:var(--c-text);">'+p.count+'</span>'+
      '<span style="font-size:17px; color:var(--c-text-faint);">&rsaquo;</span>';
    legendEl.appendChild(row);
  });
}

const detailEl = document.getElementById('detail');
function selectPath(i) {
  activeIdx = i;
  renderLegend();
  const p = DATA.paths[i];
  const list = DATA.batteries[p.key] || [];
  let html = '<div style="background:var(--c-card); border:1px solid var(--c-border); border-radius:16px; padding:20px 24px;">'+
    '<div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">'+
      '<span style="width:12px; height:12px; border-radius:3px; background:'+p.color+';"></span>'+
      '<span style="font-size:17px; font-weight:650; color:var(--c-text);">'+p.name+'</span>'+
      '<span style="font-size:14px; color:var(--c-text-faint);">&middot; '+p.count+' batteries</span>'+
    '</div>';
  list.forEach(b => {
    const lowConf = b.conf < 0.4;
    const badge = lowConf
      ? '<span style="font-size:13px; color:var(--c-warn-fg); background:var(--c-warn-bg); padding:3px 10px; border-radius:8px; white-space:nowrap;">&#9888; Needs review</span>'
      : '<span style="font-size:13px; color:var(--c-ok-fg); background:var(--c-ok-bg); padding:3px 10px; border-radius:8px; white-space:nowrap;">Confidence '+Math.round(b.conf*100)+'%</span>';
    let bars = '';
    dims.forEach(([k,label])=>{
      bars += '<div style="display:flex; align-items:center; gap:12px; margin-bottom:10px;">'+
        '<div style="width:150px; font-size:13px; color:var(--c-text-sub); text-align:right;">'+label+'</div>'+
        '<div style="flex:1; background:var(--c-surface); border:1px solid var(--c-border-soft); border-radius:5px; height:16px;">'+
          '<div style="width:'+Math.round(b[k]*100)+'%; height:100%; border-radius:5px; background:'+p.color+'; opacity:0.8;"></div>'+
        '</div>'+
        '<div style="width:42px; font-size:13px; font-family:monospace; color:var(--c-text);">'+b[k].toFixed(2)+'</div>'+
      '</div>';
    });
    html += '<div style="border:1px solid var(--c-border); border-radius:10px; margin-bottom:10px; overflow:hidden;">'+
      '<div class="bhead" style="display:flex; align-items:center; gap:14px; padding:14px 16px; cursor:pointer;">'+
        '<span style="font-family:monospace; font-size:14px; color:var(--c-text-sub); width:88px;">'+b.id+'</span>'+
        '<span style="flex:1; font-size:14px; color:var(--c-text-mut);">SOH '+b.soh+'% &middot; '+b.age+'y &middot; '+b.faults+' faults</span>'+
        badge+
        '<span class="chev" style="font-size:15px; color:var(--c-text-faint); transition:transform .15s;">&#9662;</span>'+
      '</div>'+
      '<div class="bbody" style="max-height:0; overflow:hidden; transition:max-height .22s ease; background:var(--c-panel);">'+
        '<div style="padding:16px 18px;">'+bars+'</div>'+
      '</div>'+
    '</div>';
  });
  html += '</div>';
  detailEl.innerHTML = html;
  detailEl.querySelectorAll('.bhead').forEach(h=>{
    h.onclick = ()=>{
      const body = h.nextElementSibling;
      const open = body.style.maxHeight && body.style.maxHeight!=='0px';
      body.style.maxHeight = open ? '0' : '230px';
      h.querySelector('.chev').style.transform = open ? '' : 'rotate(180deg)';
    };
  });
}

new Chart(document.getElementById('pie'), {
  type:'doughnut',
  data:{ labels:DATA.paths.map(p=>p.name),
    datasets:[{ data:DATA.paths.map(p=>p.count),
      backgroundColor:DATA.paths.map(p=>p.color), borderColor:css('--c-pie-border'), borderWidth:4 }] },
  options:{ responsive:true, maintainAspectRatio:false, cutout:'66%',
    plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label:(c)=>c.label+': '+c.raw+' batteries' } } },
    onClick:(e,els)=>{ if(els.length) selectPath(els[0].index); } }
});

renderLegend();
selectPath(0);
</script>
"""

html_filled = HTML.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
components.html(html_filled, height=640, scrolling=True)

# ---- Batch optimization (collapsible, native Streamlit) ----
with st.expander("Batch optimization  ·  allocate under capacity limits", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    cap_reuse = c1.number_input("Reuse capacity", 0, 100, 3)
    cap_reman = c2.number_input("Remanufacture capacity", 0, 100, 2)
    cap_resell = c3.number_input("Resell capacity", 0, 100, 3)
    cap_recycle = c4.number_input("Recycle capacity", 0, 100, 10)
    if st.button("Run batch optimization"):
        from modules.optimize import optimize_allocation
        capacity = {"reuse": cap_reuse, "remanufacture": cap_reman,
                    "resell": cap_resell, "recycle": cap_recycle}
        alloc = optimize_allocation(df, cfg, capacity)

        # Distribution after optimization, keyed for consistent coloring
        opt_paths = []
        for key in path_order:
            n = int((alloc["path_key"] == key).sum())
            if n > 0:
                opt_paths.append({
                    "name": cfg["pathways"][key]["label"],
                    "color": PATH_COLORS.get(key, "#888780"),
                    "count": n,
                })
        opt_payload = {"paths": opt_paths, "total": int(len(alloc))}

        DONUT = """
<style>
  :root { --c-text:#2c2c2a; --c-text-mut:#888780; --c-text-faint:#b4b2a9;
          --c-pie-border:#ffffff; --c-card:#ffffff; --c-border:#e3e1d8; }
  @media (prefers-color-scheme: dark) {
    :root { --c-text:#e8e6dd; --c-text-mut:#9c9a92; --c-text-faint:#73726c;
            --c-pie-border:#14100f; --c-card:#1a1a19; --c-border:#3c3c39; }
  }
  body { background: transparent; margin: 0; }
</style>
<div style="font-family:-apple-system,'Segoe UI',Roboto,sans-serif; color:var(--c-text);
     background:var(--c-card); border:1px solid var(--c-border); border-radius:16px; padding:20px 24px;">
  <div style="font-size:15px; font-weight:600; margin-bottom:14px;">Distribution after optimization</div>
  <div style="display:flex; gap:28px; align-items:center; flex-wrap:wrap;">
    <div style="position:relative; width:190px; height:190px; flex-shrink:0;">
      <canvas id="optpie"></canvas>
      <div style="position:absolute; inset:0; display:flex; flex-direction:column;
           align-items:center; justify-content:center; pointer-events:none;">
        <div id="optval" style="font-size:26px; font-weight:650; line-height:1;"></div>
        <div style="font-size:11px; color:var(--c-text-faint); margin-top:2px;">allocated</div>
      </div>
    </div>
    <div id="optlegend" style="flex:1; min-width:200px;"></div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const OD = __OPTPAYLOAD__;
const css = (v)=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
document.getElementById('optval').textContent = OD.total;
const leg = document.getElementById('optlegend');
OD.paths.forEach(p=>{
  const row=document.createElement('div');
  row.style.cssText='display:flex; align-items:center; gap:12px; padding:8px 4px; font-size:14px;';
  row.innerHTML='<span style="width:11px;height:11px;border-radius:3px;background:'+p.color+';"></span>'+
    '<span style="flex:1; color:var(--c-text);">'+p.name+'</span>'+
    '<span style="font-weight:650; color:var(--c-text);">'+p.count+'</span>';
  leg.appendChild(row);
});
new Chart(document.getElementById('optpie'), {
  type:'doughnut',
  data:{ labels:OD.paths.map(p=>p.name),
    datasets:[{ data:OD.paths.map(p=>p.count), backgroundColor:OD.paths.map(p=>p.color),
      borderColor:css('--c-pie-border'), borderWidth:4 }] },
  options:{ responsive:true, maintainAspectRatio:false, cutout:'66%',
    plugins:{ legend:{display:false}, tooltip:{callbacks:{label:(c)=>c.label+': '+c.raw+' batteries'}} } }
});
</script>
"""
        donut_filled = DONUT.replace("__OPTPAYLOAD__", json.dumps(opt_payload, ensure_ascii=False))
        components.html(donut_filled, height=270, scrolling=False)

        st.dataframe(alloc.drop(columns=["path_key"]), use_container_width=True, hide_index=True)

# ---- Ask about a recommendation (collapsible, native Streamlit) ----
with st.expander("Ask about a recommendation", expanded=False):
    sel = st.selectbox("Select a battery", result["battery_id"].tolist())
    row = result[result["battery_id"] == sel].iloc[0]

    low_conf = row["confidence"] < 0.4
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown(f"**Recommended pathway:** {row['top_choice']}")
        st.markdown(f"**Runner-up:** {row['second_choice']}")
        st.markdown(f"**Rationale:** {row['reason']}")
    with c2:
        if low_conf:
            st.warning(f"Needs review — confidence {int(row['confidence']*100)}%")
        else:
            st.success(f"Confidence {int(row['confidence']*100)}%")

    st.caption("Four-dimension scores")
    score_df = pd.DataFrame({
        "Dimension": ["Residual value", "Safety & compliance", "Market liquidity", "Time window"],
        "Score": [row["value_score"], row["risk_score"], row["liquidity_score"], row["time_window_score"]],
    })
    st.dataframe(score_df, use_container_width=True, hide_index=True,
                 column_config={"Score": st.column_config.ProgressColumn(
                     "Score", min_value=0.0, max_value=1.0, format="%.2f")})