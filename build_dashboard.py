# -*- coding: utf-8 -*-
"""
把 4 个投放平台下所有维度的 CSV 汇总成一个自包含的离线 HTML 看板。
用法：  python build_dashboard.py
输出：  dashboard.html   （双击即可在浏览器打开，无需联网/起服务）
"""
import csv, glob, json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))

# 平台目录 -> 展示名 与 维度排序
PLATFORMS = ["买量小飞机", "微橙", "沸点投放", "麦斯"]


def dim_label(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    return re.sub(r'^\d+[_\-]?', '', name)  # 去掉数字前缀


def load_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return None
    cols = [c.strip() for c in rows[0]]
    body = rows[1:]
    total = None
    data = []
    for r in body:
        # 补齐/截断到列数
        if len(r) < len(cols):
            r = r + [''] * (len(cols) - len(r))
        elif len(r) > len(cols):
            r = r[:len(cols)]
        if r and r[0].strip() == '合计':
            total = r
        else:
            data.append(r)
    return {"name": dim_label(path), "file": os.path.basename(path),
            "columns": cols, "total": total, "rows": data}


def main():
    platforms = []
    for p in PLATFORMS:
        pdir = os.path.join(BASE, p)
        if not os.path.isdir(pdir):
            continue
        files = sorted(glob.glob(os.path.join(pdir, '*.csv')))
        dims = []
        for f in files:
            d = load_csv(f)
            if d:
                dims.append(d)
        if dims:
            platforms.append({"name": p, "dims": dims})

    data_json = json.dumps({"platforms": platforms}, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("/*__DATA__*/", "window.__DATA__ = " + data_json + ";")
    out = os.path.join(BASE, "dashboard.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)

    total_rows = sum(len(d["rows"]) for pf in platforms for d in pf["dims"])
    total_dims = sum(len(pf["dims"]) for pf in platforms)
    print(f"已生成 {out}")
    print(f"平台 {len(platforms)} 个 / 维度表 {total_dims} 张 / 数据行 {total_rows} 行")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>投放数据看板</title>
<style>
:root{
  --bg:#0f1117; --panel:#171a23; --panel2:#1d212c; --line:#2a2f3d;
  --text:#e6e9f0; --muted:#8b93a7; --accent:#5b8cff; --accent2:#27c498;
  --warn:#ffb454; --chip:#232838;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;flex-wrap:wrap;background:var(--panel)}
header h1{font-size:18px;margin:0;font-weight:600}
header .sub{color:var(--muted);font-size:12px}
.wrap{padding:18px 22px 60px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.tab{padding:7px 16px;border:1px solid var(--line);background:var(--panel);color:var(--muted);
  border-radius:20px;cursor:pointer;font-size:13px;transition:.15s;user-select:none}
.tab:hover{color:var(--text);border-color:var(--accent)}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.dimtabs .tab.active{background:var(--accent2);border-color:var(--accent2)}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 18px;min-width:130px}
.kpi .k{color:var(--muted);font-size:12px;margin-bottom:4px}
.kpi .v{font-size:20px;font-weight:650;letter-spacing:.3px}
.kpi .v.pos{color:var(--accent2)}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.controls input[type=text]{background:var(--panel2);border:1px solid var(--line);color:var(--text);
  padding:8px 12px;border-radius:8px;min-width:240px;font-size:13px}
.controls select{background:var(--panel2);border:1px solid var(--line);color:var(--text);
  padding:8px 10px;border-radius:8px;font-size:13px;max-width:220px}
.controls .lbl{color:var(--muted);font-size:12px;margin-right:-4px}
.controls .reset{cursor:pointer;color:var(--accent);font-size:12px;padding:6px 8px}
.meta{color:var(--muted);font-size:12px;margin:2px 0 8px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:10px;max-height:68vh}
table{border-collapse:collapse;width:100%;font-size:13px}
thead th{position:sticky;top:0;background:var(--panel2);color:var(--text);text-align:left;
  padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap;cursor:pointer;z-index:2}
thead th:hover{color:var(--accent)}
thead th .arrow{color:var(--accent);font-size:11px}
tbody td{padding:8px 12px;border-bottom:1px solid #20242f;white-space:nowrap;max-width:360px;
  overflow:hidden;text-overflow:ellipsis}
tbody tr:hover{background:#1b1f2b}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr.total{background:#1a2230;font-weight:600}
.pager{display:flex;gap:8px;align-items:center;margin-top:12px;color:var(--muted);font-size:13px;flex-wrap:wrap}
.pager button{background:var(--panel);border:1px solid var(--line);color:var(--text);
  padding:6px 12px;border-radius:7px;cursor:pointer}
.pager button:disabled{opacity:.4;cursor:default}
.empty{padding:40px;text-align:center;color:var(--muted)}
a.link{color:var(--accent);text-decoration:none}
</style>
</head>
<body>
<header>
  <h1>📊 投放数据看板</h1>
  <span class="sub" id="subInfo"></span>
</header>
<div class="wrap">
  <div class="tabs" id="platformTabs"></div>
  <div class="tabs dimtabs" id="dimTabs"></div>
  <div class="kpis" id="kpis"></div>
  <div class="controls" id="controls"></div>
  <div class="meta" id="meta"></div>
  <div class="tablewrap"><table><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
  <div class="pager" id="pager"></div>
</div>
<script>
/*__DATA__*/
const DATA = window.__DATA__;
const PAGE_SIZE = 50;

const RATIO_KW = ['率','ROI','CPC','CPM','成本','单价','客单价','出价','余额','版本','占比'];
const KPI_PRIORITY = ['总消费','消费','消耗','展示量','展示数','点击量','点击数','转化数',
  '订单数','总成交订单数','真实订单数','总下单量','总成交量','真实付款金额','付款金额',
  '成交金额','总成交金额','订单金额','总下单金额','总成交ROI','总ROI','ROI'];

let state = {p:0, d:0, search:'', filters:{}, sortCol:-1, sortDir:1, page:0};

const $ = id => document.getElementById(id);
const isNum = v => v!==''&&v!=null&&!isNaN(parseFloat(String(v).replace(/,/g,'')));
const toNum = v => parseFloat(String(v).replace(/,/g,''));
const fmt = v => {
  const s = String(v);
  if(/^-?\d+(\.\d+)?$/.test(s)){
    const n = parseFloat(s);
    if(Math.abs(n)>=1000) return n.toLocaleString('zh-CN',{maximumFractionDigits:2});
  }
  return s;
};

function curDim(){ return DATA.platforms[state.p].dims[state.d]; }

// 判断列是否数值列（多数值可解析为数字）
function numericCols(dim){
  const out = {};
  dim.columns.forEach((c,i)=>{
    let n=0,t=0;
    for(const r of dim.rows){ if(r[i]!==''){ t++; if(isNum(r[i])) n++; } if(t>30) break; }
    out[i] = t>0 && n/t>=0.7;
  });
  return out;
}

// 找出可作下拉筛选的分类列
function filterCols(dim){
  const res=[];
  dim.columns.forEach((c,i)=>{
    if(/ID$|链接|名称|封面|url/i.test(c)) return;
    const set=new Set();
    for(const r of dim.rows){ const v=(r[i]||'').trim(); if(v) set.add(v); if(set.size>41) break; }
    if(set.size>=2 && set.size<=40){
      // 排除纯数字列
      let allnum=true; for(const v of set){ if(!isNum(v)){allnum=false;break;} }
      if(!allnum) res.push({col:i, name:c, values:[...set].sort()});
    }
  });
  return res;
}

function buildKPIs(dim, nCols){
  const cards=[];
  const used=new Set();
  for(const kw of KPI_PRIORITY){
    const i = dim.columns.findIndex((c,idx)=>c.includes(kw) && !used.has(idx));
    if(i<0) continue;
    used.add(i);
    let val=null;
    if(dim.total && dim.total[i]!=='' && isNum(dim.total[i])) val=toNum(dim.total[i]);
    else if(nCols[i] && !RATIO_KW.some(k=>dim.columns[i].includes(k))){
      let s=0,any=false; for(const r of dim.rows){ if(isNum(r[i])){s+=toNum(r[i]);any=true;} }
      if(any) val=s;
    }
    if(val==null) continue;
    const isRoi = /ROI/.test(dim.columns[i]);
    cards.push({k:dim.columns[i], v: isRoi? val.toFixed(2): val.toLocaleString('zh-CN',{maximumFractionDigits:2}), pos:isRoi});
    if(cards.length>=8) break;
  }
  return cards;
}

function applyFilters(dim){
  let rows = dim.rows;
  const s = state.search.trim().toLowerCase();
  if(s) rows = rows.filter(r=>r.some(c=>String(c).toLowerCase().includes(s)));
  for(const [col,val] of Object.entries(state.filters)){
    if(val) rows = rows.filter(r=>(r[+col]||'').trim()===val);
  }
  if(state.sortCol>=0){
    const i=state.sortCol, dir=state.sortDir;
    rows = rows.slice().sort((a,b)=>{
      const av=a[i],bv=b[i];
      if(isNum(av)&&isNum(bv)) return (toNum(av)-toNum(bv))*dir;
      return String(av).localeCompare(String(bv),'zh')*dir;
    });
  }
  return rows;
}

function render(){
  const dim = curDim();
  const nCols = numericCols(dim);

  // 平台 tabs
  $('platformTabs').innerHTML = DATA.platforms.map((p,i)=>
    `<div class="tab ${i===state.p?'active':''}" data-p="${i}">${p.name}</div>`).join('');
  // 维度 tabs
  $('dimTabs').innerHTML = DATA.platforms[state.p].dims.map((d,i)=>
    `<div class="tab ${i===state.d?'active':''}" data-d="${i}">${d.name}</div>`).join('');

  // KPI
  const kpis = buildKPIs(dim, nCols);
  $('kpis').innerHTML = kpis.map(c=>
    `<div class="kpi"><div class="k">${c.k}</div><div class="v ${c.pos?'pos':''}">${c.v}</div></div>`).join('')
    || '<div class="kpi"><div class="k">无汇总指标</div><div class="v">—</div></div>';

  // 控件
  const fcols = filterCols(dim);
  let ctrl = `<input type="text" id="search" placeholder="🔍 全局搜索…" value="${state.search.replace(/"/g,'&quot;')}">`;
  for(const f of fcols){
    ctrl += `<span class="lbl">${f.name}</span><select data-col="${f.col}"><option value="">全部</option>`+
      f.values.map(v=>`<option ${state.filters[f.col]===v?'selected':''} value="${v.replace(/"/g,'&quot;')}">${v}</option>`).join('')+`</select>`;
  }
  ctrl += `<span class="reset" id="reset">✕ 清除筛选</span>`;
  $('controls').innerHTML = ctrl;

  // 表格
  const rows = applyFilters(dim);
  const pages = Math.max(1, Math.ceil(rows.length/PAGE_SIZE));
  if(state.page>=pages) state.page=0;
  const slice = rows.slice(state.page*PAGE_SIZE,(state.page+1)*PAGE_SIZE);

  $('thead').innerHTML = '<tr>'+dim.columns.map((c,i)=>{
    const arrow = state.sortCol===i ? (state.sortDir>0?' ▲':' ▼') : '';
    return `<th class="${nCols[i]?'num':''}" data-col="${i}">${c}<span class="arrow">${arrow}</span></th>`;
  }).join('')+'</tr>';

  let bodyHtml='';
  if(dim.total && !state.search && Object.values(state.filters).every(v=>!v)){
    bodyHtml += '<tr class="total">'+dim.columns.map((c,i)=>{
      const v=dim.total[i]||''; return `<td class="${nCols[i]?'num':''}">${i===0?'合计':fmt(v)}</td>`;
    }).join('')+'</tr>';
  }
  bodyHtml += slice.map(r=>'<tr>'+r.map((v,i)=>{
    let disp = fmt(v);
    if(/链接|url/i.test(dim.columns[i]) && /^https?:/.test(v)) disp=`<a class="link" href="${v}" target="_blank">链接</a>`;
    return `<td class="${nCols[i]?'num':''}" title="${String(v).replace(/"/g,'&quot;')}">${disp}</td>`;
  }).join('')+'</tr>').join('');
  $('tbody').innerHTML = bodyHtml || '<tr><td class="empty" colspan="99">无匹配数据</td></tr>';

  $('meta').textContent = `共 ${rows.length.toLocaleString()} 行（原始 ${dim.rows.length.toLocaleString()} 行） · 列 ${dim.columns.length} · 来源 ${dim.file}`;
  $('subInfo').textContent = `${DATA.platforms.length} 个平台 · 当前：${DATA.platforms[state.p].name} / ${dim.name}`;

  $('pager').innerHTML = `<button id="prev" ${state.page===0?'disabled':''}>← 上一页</button>`+
    `<span>第 ${state.page+1} / ${pages} 页</span>`+
    `<button id="next" ${state.page>=pages-1?'disabled':''}>下一页 →</button>`;

  bind();
}

function bind(){
  $('platformTabs').querySelectorAll('.tab').forEach(el=>el.onclick=()=>{
    state.p=+el.dataset.p; state.d=0; state.search=''; state.filters={}; state.sortCol=-1; state.page=0; render();});
  $('dimTabs').querySelectorAll('.tab').forEach(el=>el.onclick=()=>{
    state.d=+el.dataset.d; state.search=''; state.filters={}; state.sortCol=-1; state.page=0; render();});
  const se=$('search'); if(se){ se.oninput=()=>{state.search=se.value;state.page=0;render();
    const x=$('search'); x.focus(); x.setSelectionRange(x.value.length,x.value.length);};}
  $('controls').querySelectorAll('select').forEach(s=>s.onchange=()=>{
    state.filters[s.dataset.col]=s.value; state.page=0; render();});
  const rs=$('reset'); if(rs) rs.onclick=()=>{state.search='';state.filters={};state.sortCol=-1;state.page=0;render();};
  $('thead').querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const c=+th.dataset.col;
    if(state.sortCol===c) state.sortDir*=-1; else {state.sortCol=c;state.sortDir=1;}
    state.page=0; render();});
  const pv=$('prev'),nx=$('next');
  if(pv) pv.onclick=()=>{if(state.page>0){state.page--;render();}};
  if(nx) nx.onclick=()=>{state.page++;render();};
}

render();
</script>
</body>
</html>"""

if __name__ == "__main__":
    main()
