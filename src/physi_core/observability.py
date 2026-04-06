"""Trace-based observability — groups events per logical operation.

Every logical operation (qq_message / perception_segment / session_extract / …)
opens a Trace via start_trace(). All emit() calls within the same asyncio task
are automatically attached to that trace via ContextVar propagation.

HTTP monitor at :8765 shows:
- Traces tab: traces grouped, newest first, collapsible with full JSON detail
- LLM Log tab: raw full I/O from llm_calls.jsonl with search
- Runtime Log tab: tail of runtime.log
"""

from __future__ import annotations

import contextvars
import json
import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# ── Context propagation ───────────────────────────────────────────────────────

_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "physi_trace_id", default=None
)


def _local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


# ── Data model ────────────────────────────────────────────────────────────────

class TraceEvent:
    __slots__ = ("ts", "type", "data", "offset_ms")

    def __init__(self, event_type: str, data: dict[str, Any], trace_t0: float) -> None:
        self.ts = _local_now()
        self.type = event_type
        self.data = data
        self.offset_ms = int((time.perf_counter() - trace_t0) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "type": self.type, "offset_ms": self.offset_ms, "data": self.data}


class Trace:
    def __init__(self, trace_id: str, trigger: str, meta: dict[str, Any]) -> None:
        self.id = trace_id
        self.trigger = trigger
        self.started_at = _local_now()
        self.ended_at: str | None = None
        self.status = "running"
        self.events: list[TraceEvent] = []
        self.meta = meta
        self.summary: dict[str, Any] = {}
        self._t0 = time.perf_counter()
        self.duration_ms = 0

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append(TraceEvent(event_type, data, self._t0))

    def end(self, status: str = "ok", **summary: Any) -> None:
        self.status = status
        self.ended_at = _local_now()
        self.duration_ms = int((time.perf_counter() - self._t0) * 1000)
        self.summary = summary

    def total_tokens(self) -> tuple[int, int]:
        inp = sum(e.data.get("input_tokens", 0) for e in self.events if e.type == "llm_call")
        out = sum(e.data.get("output_tokens", 0) for e in self.events if e.type == "llm_call")
        return inp, out

    def to_dict(self) -> dict[str, Any]:
        inp, out = self.total_tokens()
        return {
            "id": self.id,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "meta": self.meta,
            "summary": self.summary,
            "input_tokens": inp,
            "output_tokens": out,
            "events": [e.to_dict() for e in self.events],
        }


# ── HTML monitor (full-featured) ──────────────────────────────────────────────

_HTML = r"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>PhysiBot Monitor</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:"Segoe UI",ui-sans-serif,Arial,sans-serif;background:#0d1117;color:#c9d1d9;font-size:14px}
    /* ── Layout ── */
    .topbar{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid #21262d;background:#0d1117;position:sticky;top:0;z-index:100}
    h1{font-size:17px;font-weight:600;color:#e6edf3;display:flex;align-items:center;gap:8px}
    .dot{width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block;animation:pulse 2s infinite;flex-shrink:0}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    .tabs{display:flex;gap:4px;margin-left:auto}
    .tab{background:none;border:1px solid #30363d;border-radius:6px;color:#8b949e;padding:4px 14px;cursor:pointer;font-size:13px;transition:all .15s}
    .tab.active{background:#1f6feb;border-color:#1f6feb;color:#fff}
    .content{padding:14px 16px}
    .panel{display:none}.panel.active{display:block}
    /* ── Stats ── */
    .stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
    .stat{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 16px;min-width:130px}
    .stat-label{color:#8b949e;font-size:11px;margin-bottom:3px}
    .stat-value{font-size:20px;font-weight:600;color:#e6edf3}
    .stat-value.tok{font-size:15px}
    /* ── Toolbar ── */
    .toolbar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
    .btn{background:#21262d;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;padding:4px 12px;cursor:pointer;font-size:13px}
    .btn.active{background:#1f6feb;border-color:#1f6feb;color:#fff}
    .search-box{background:#161b22;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;padding:4px 10px;font-size:13px;width:220px;outline:none}
    .search-box:focus{border-color:#58a6ff}
    /* ── Trace list ── */
    .traces{border:1px solid #30363d;border-radius:8px;overflow:hidden}
    .trace-row{border-bottom:1px solid #21262d}
    .trace-row:last-child{border-bottom:none}
    .trace-header{display:flex;align-items:center;gap:10px;padding:8px 12px;transition:background .15s;cursor:pointer;user-select:none;min-width:0}
    .trace-header:hover{background:#161b22}
    .toggle{width:16px;color:#8b949e;font-size:11px;flex-shrink:0}
    .ts{color:#8b949e;font-size:12px;font-variant-numeric:tabular-nums;flex-shrink:0;width:95px}
    .trigger{flex-shrink:0;width:140px}
    .pill{border-radius:999px;padding:1px 8px;font-size:11px;font-weight:500}
    .pill.qq_message{background:#0d2137;color:#58a6ff;border:1px solid #1f4a6e}
    .pill.perception{background:#0d2117;color:#3fb950;border:1px solid #1e4a2a}
    .pill.session_extract{background:#1e1530;color:#bc8cff;border:1px solid #3d2464}
    .pill.daily_merge,.pill.weekly_review{background:#1e1a08;color:#d29922;border:1px solid #4a3b0e}
    .pill.system,.pill.other{background:#21262d;color:#8b949e;border:1px solid #30363d}
    .status{flex-shrink:0;font-size:13px}
    .ok{color:#3fb950}.err{color:#f85149}.running{color:#d29922}
    .dur{color:#8b949e;font-size:12px;flex-shrink:0;width:55px;text-align:right}
    .tokens{color:#8b949e;font-size:12px;flex-shrink:0;width:110px;text-align:right}
    .tok-in{color:#58a6ff}.tok-out{color:#3fb950}
    .summary-text{color:#e6edf3;font-size:12px;flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:100%}
    /* ── Event detail ── */
    .events-wrap{padding:0 12px 10px 36px;border-top:1px solid #21262d;background:#0a0f14}
    .ev{border-left:2px solid #21262d;margin-left:4px;padding:4px 0 4px 10px}
    .ev+.ev{border-top:1px solid #161b22}
    .ev-header{display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer;min-width:0}
    .ev-header:hover .ev-type{text-decoration:underline}
    .ev-off{color:#555;width:55px;flex-shrink:0;font-variant-numeric:tabular-nums}
    .ev-type{flex-shrink:0;min-width:100px}
    .ev-llm{color:#58a6ff}.ev-tool{color:#3fb950}.ev-err{color:#f85149}
    .ev-consolidator{color:#d29922}.ev-info{color:#8b949e}
    .ev-summary{color:#c9d1d9;flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px;max-width:100%}
    .ev-detail{display:none;background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;margin-top:6px;font-size:12px}
    .ev-detail.open{display:block}
    .ev-detail pre{white-space:pre-wrap;word-break:break-all;line-height:1.5;font-family:"Cascadia Code","Fira Code",monospace;font-size:11px}
    /* JSON syntax highlight */
    .jk{color:#79c0ff}.jv{color:#a5d6ff}.jn{color:#ff7b72}.jb{color:#d2a8ff}.js{color:#a5d6ff}
    /* ── LLM log panel ── */
    .llm-log-toolbar{display:flex;gap:8px;margin-bottom:10px;align-items:center}
    .llm-entry{border:1px solid #21262d;border-radius:8px;margin-bottom:8px;overflow:hidden}
    .llm-entry-header{padding:8px 12px;display:flex;gap:10px;align-items:center;cursor:pointer;background:#161b22}
    .llm-entry-header:hover{background:#1c2128}
    .llm-dir{font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;flex-shrink:0}
    .llm-dir.req{background:#0d2137;color:#58a6ff;border:1px solid #1f4a6e}
    .llm-dir.resp{background:#0d2117;color:#3fb950;border:1px solid #1e4a2a}
    .llm-ts{color:#8b949e;font-size:12px;flex-shrink:0}
    .llm-preview{color:#c9d1d9;font-size:12px;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
    .llm-body{display:none;padding:10px 12px;background:#0d1117;font-size:12px}
    .llm-body.open{display:block}
    .llm-body pre{white-space:pre-wrap;word-break:break-all;font-family:"Cascadia Code","Fira Code",monospace;font-size:11px;line-height:1.5}
    .llm-section{margin-bottom:10px}
    .llm-section-title{color:#8b949e;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
    .llm-section-content{background:#161b22;border-radius:4px;padding:8px;overflow-x:auto;max-height:300px;overflow-y:auto}
    /* ── Runtime log panel ── */
    .log-wrap{background:#0a0f14;border:1px solid #21262d;border-radius:8px;padding:12px;font-family:"Cascadia Code","Fira Code",monospace;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-all;max-height:70vh;overflow-y:auto}
    .log-err{color:#f85149}.log-warn{color:#d29922}.log-info{color:#c9d1d9}.log-debug{color:#8b949e}
    /* ── Tools summary ── */
    .tools-wrap{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px 14px;margin-bottom:12px;font-size:12px;color:#8b949e}
    .tools-wrap b{color:#c9d1d9}
    .tool-name{display:inline-block;background:#21262d;border-radius:4px;padding:1px 6px;margin:2px;color:#c9d1d9;font-size:11px}
    .empty{padding:32px;text-align:center;color:#484f58}
    a{color:#58a6ff;text-decoration:none}
    /* ── Copy button ── */
    .copy-btn{background:#21262d;border:1px solid #30363d;border-radius:4px;color:#8b949e;padding:2px 8px;cursor:pointer;font-size:11px;margin-left:8px}
    .copy-btn:hover{color:#c9d1d9}
  </style>
</head>
<body>
<div class="topbar">
  <h1><span class="dot"></span>PhysiBot Monitor</h1>
  <div class="tabs">
    <button class="tab active" onclick="showPanel('traces',this)">Traces</button>
    <button class="tab" onclick="showPanel('llmlog',this)">LLM Log</button>
    <button class="tab" onclick="showPanel('runtimelog',this)">Runtime Log</button>
  </div>
</div>

<!-- ══ TRACES PANEL ══ -->
<div class="content panel active" id="panel-traces">
  <div class="stats">
    <div class="stat"><div class="stat-label">今日 Traces</div><div class="stat-value" id="sTotal">-</div></div>
    <div class="stat"><div class="stat-label">运行中</div><div class="stat-value" id="sActive">-</div></div>
    <div class="stat"><div class="stat-label">今日 Token</div><div class="stat-value tok" id="sTokens">-</div></div>
    <div class="stat"><div class="stat-label">工具</div><div class="stat-value" id="sTools">-</div></div>
  </div>
  <div class="tools-wrap" id="toolsWrap"></div>
  <div class="toolbar" id="filterBar">
    <button class="btn active" onclick="setFilter('',this)">全部</button>
    <button class="btn" onclick="setFilter('qq_message',this)">💬 消息</button>
    <button class="btn" onclick="setFilter('perception',this)">👁 感知</button>
    <button class="btn" onclick="setFilter('session_extract',this)">🧠 记忆</button>
    <button class="btn" onclick="setFilter('error',this)">✗ 错误</button>
    <input class="search-box" id="traceSearch" placeholder="搜索 Trace…" oninput="renderTraces()"/>
  </div>
  <div class="traces" id="traceList"><div class="empty">加载中…</div></div>
</div>

<!-- ══ LLM LOG PANEL ══ -->
<div class="content panel" id="panel-llmlog">
  <div class="llm-log-toolbar">
    <input class="search-box" id="llmSearch" placeholder="搜索 system / messages / response…" oninput="renderLlmLog()" style="width:300px"/>
    <button class="btn" onclick="loadLlmLog()">刷新</button>
    <span style="color:#8b949e;font-size:12px" id="llmCount"></span>
  </div>
  <div id="llmList"><div class="empty">点击刷新加载 LLM 完整日志</div></div>
</div>

<!-- ══ RUNTIME LOG PANEL ══ -->
<div class="content panel" id="panel-runtimelog">
  <div class="toolbar">
    <button class="btn" onclick="loadRuntimeLog()">刷新</button>
    <select class="search-box" id="logLines" style="width:120px" onchange="loadRuntimeLog()">
      <option value="100">最近100行</option>
      <option value="300">最近300行</option>
      <option value="500">最近500行</option>
    </select>
  </div>
  <div class="log-wrap" id="logWrap"><span style="color:#8b949e">点击刷新加载</span></div>
</div>

<script>
// ════════════════════════ Global state ════════════════════════
const expanded = new Set();      // trace IDs
const evExpanded = new Set();    // "traceId:evIdx" strings
let currentFilter = '';
let allTraces = [];
let allLlmEntries = [];

// ════════════════════════ Panel switching ════════════════════════
function showPanel(name, btn) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'runtimelog') loadRuntimeLog();
  if (name === 'llmlog') loadLlmLog();
}

// ════════════════════════ Helpers ════════════════════════
function esc(x){ return String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmtDur(ms){ if(ms<1000) return ms+'ms'; return (ms/1000).toFixed(1)+'s'; }
function fmtNum(n){ if(n>=1000000) return (n/1000000).toFixed(1)+'M'; if(n>=1000) return (n/1000).toFixed(1)+'K'; return String(n); }

function copyTraceJson(id){
  const t=allTraces.find(x=>x.id===id);
  if(t) copyText(JSON.stringify(t,null,2));
}

// LLM 日志条目：绝不能把 JSON.stringify(req) 塞进 HTML 属性，否则 " 会截断 onclick，整段 JSON 会泄漏到页面上
let allLlmPairs = [];
function copyLlmPair(i){
  const p=allLlmPairs[i];
  if(p) copyText(JSON.stringify({req:p.req||{},resp:p.resp||{}},null,2));
}

function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {
    const el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  });
}

// ════════════════════════ JSON syntax highlighting ════════════════════════
function hlJson(obj) {
  let s;
  try { s = JSON.stringify(obj, null, 2); } catch { s = String(obj); }
  return s.replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="jk">$1</span>:')
          .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="js">$1</span>')
          .replace(/:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, ': <span class="jn">$1</span>')
          .replace(/:\s*(true|false)/g, ': <span class="jb">$1</span>')
          .replace(/:\s*(null)/g, ': <span class="jb">$1</span>');
}

// ════════════════════════ Trace rendering ════════════════════════
function triggerClass(t){
  if(t==='qq_message') return 'qq_message';
  if(t.startsWith('perception')) return 'perception';
  if(t==='session_extract') return 'session_extract';
  if(t==='daily_merge'||t==='weekly_review') return 'daily_merge';
  return 'other';
}
function triggerLabel(t){
  const map={qq_message:'💬 QQ消息',perception_segment:'👁 感知片段',perception_daily:'📋 日合并',
             perception_weekly:'📊 周回顾',session_extract:'🧠 记忆提取',cli_message:'⌨ CLI'};
  return map[t]||('⚙ '+t);
}
function statusIcon(s){
  if(s==='ok') return '<span class="ok">✓</span>';
  if(s==='error') return '<span class="err">✗</span>';
  return '<span class="running">⟳</span>';
}

function shortStr(s,max){if(s==null)return'';const t=String(s);return t.length<=max?t:t.slice(0,max)+'…';}

function buildSummaryText(trace){
  const s=trace.summary||{};const m=trace.meta||{};
  if(trace.trigger==='qq_message'){
    return esc(shortStr(m.text_preview,120))+' → '+esc(shortStr(s.reply_preview,120));
  }
  if(trace.trigger==='cli_message'){
    return esc(shortStr(m.text_preview,120))+' → '+esc(shortStr(s.reply_preview,120));
  }
  if(trace.trigger==='perception_segment'){
    return s.notify?'⚠️ 已通知':esc(shortStr(s.projects||'',120));
  }
  if(trace.trigger==='session_extract'){
    return s.writes?`写入 ${s.writes} 条记忆`:'无新信息';
  }
  if(s.error) return '<span class="err">'+esc(shortStr(s.error,200))+'</span>';
  return esc(shortStr(JSON.stringify(s),120));
}

function evTypeClass(t){
  if(t==='llm_call') return 'ev-llm';
  if(t==='tool_call'||t.startsWith('agent.tool')) return 'ev-tool';
  if(t==='error'||t.includes('error')) return 'ev-err';
  if(t.startsWith('consolidator')) return 'ev-consolidator';
  return 'ev-info';
}

function evSummary(ev){
  const d=ev.data||{};
  if(ev.type==='llm.context.built'){
    const roles=(d.conversation_tail_roles||[]).join('→')||'?';
    return `ctx sys=${fmtNum(d.system_prompt_len||0)}ch · ${d.conversation_messages||0}条 · tail ${esc(shortStr(roles,40))}`;
  }
  if(ev.type==='message.received'||ev.type==='message.responded'){
    return esc(shortStr(d.text_preview||d.response_preview||'',100));
  }
  if(ev.type==='qq.message.in'||ev.type==='qq.message.out'){
    return esc(shortStr(d.text_preview||'',100));
  }
  if(ev.type==='llm_call'){
    const tc=d.tool_calls||[];
    const tools=Array.isArray(tc)?tc.map(function(x){return typeof x==='string'?x:(x&&x.name)||'?';}).join(', '):String(tc);
    return `<span class="tok-in">↑${fmtNum(d.input_tokens||0)}</span> <span class="tok-out">↓${fmtNum(d.output_tokens||0)}</span> [${esc(shortStr(tools,40))}] ${fmtDur(d.latency_ms||0)} <span style="color:#8b949e">${esc(shortStr(d.text_preview||'',50))}</span>`;
  }
  if(ev.type==='tool_call'||ev.type==='agent.tool.result'){
    const ok=d.success!==false;
    return `<b>${esc(d.tool||d.tool_name||'')}</b> ${ok?'<span class="ok">ok</span>':'<span class="err">err</span>'} ${fmtDur(d.latency_ms||0)}`;
  }
  if(ev.type==='agent.tool.requested'){
    let ap='';
    try{ap=JSON.stringify(d.arguments);}catch(e){ap=String(d.arguments||'');}
    return `<b>${esc(d.tool||'')}</b> ${esc(shortStr(ap,72))}`;
  }
  if(ev.type==='agent.round.start'||ev.type==='agent.round.final'||ev.type==='agent.round.max_reached'){
    return esc(shortStr(JSON.stringify(d),100));
  }
  if(ev.type==='perception.snapshot'){
    return `ocr ${d.ocr_frame_count||0}/${d.ocr_after_dedup||0} · parts ${d.parts_count||0}`;
  }
  if(ev.type.startsWith('consolidator')){
    return esc(shortStr(JSON.stringify(d),100));
  }
  return esc(shortStr(JSON.stringify(d),100));
}

function buildEventsHtml(trace){
  if(!trace.events||trace.events.length===0) return '<div style="color:#555;padding:6px">无内部事件</div>';
  return trace.events.map((ev,i)=>{
    const key=trace.id+':'+i;
    const isOpen=evExpanded.has(key);
    const cls=evTypeClass(ev.type);
    const detailJson=hlJson(ev.data||{});
    const copyId='copy-'+key.replace(':','-');
    return `<div class="ev">
      <div class="ev-header" onclick="toggleEv('${key}')">
        <span class="ev-off">+${ev.offset_ms}ms</span>
        <span class="ev-type ${cls}">${esc(ev.type)}</span>
        <span class="ev-summary">${evSummary(ev)}</span>
      </div>
      <div class="ev-detail ${isOpen?'open':''}" id="evd-${key.replace(':','-')}">
        <button class="copy-btn" onclick="copyText(document.getElementById('evpre-${key.replace(':','-')}').textContent)">复制</button>
        <pre id="evpre-${key.replace(':','-')}">${detailJson}</pre>
      </div>
    </div>`;
  }).join('');
}

function setFilter(f, btn){
  currentFilter=f;
  document.querySelectorAll('#filterBar .btn').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  renderTraces();
}

function renderTraces(){
  const container=document.getElementById('traceList');
  const q=(document.getElementById('traceSearch').value||'').toLowerCase();
  let traces=allTraces;
  if(currentFilter==='error') traces=traces.filter(t=>t.status==='error');
  else if(currentFilter) traces=traces.filter(t=>t.trigger===currentFilter||t.trigger.startsWith(currentFilter));
  if(q) traces=traces.filter(t=>JSON.stringify(t).toLowerCase().includes(q));
  if(traces.length===0){container.innerHTML='<div class="empty">暂无 Trace</div>';return;}
  container.innerHTML=traces.map(trace=>{
    const tc=triggerClass(trace.trigger);
    const inp=trace.input_tokens||0,out=trace.output_tokens||0;
    const tokStr=inp||out?`<span class="tok-in">↑${fmtNum(inp)}</span> <span class="tok-out">↓${fmtNum(out)}</span>`:'';
    const isExp=expanded.has(trace.id);
    const evHtml=isExp?`<div class="events-wrap">${buildEventsHtml(trace)}</div>`:'';
    return `<div class="trace-row">
      <div class="trace-header" onclick="toggle('${trace.id}')">
        <span class="toggle">${isExp?'▼':'▶'}</span>
        <span class="ts">${(trace.started_at||'').slice(11,23)}</span>
        <span class="trigger"><span class="pill ${tc}">${triggerLabel(trace.trigger)}</span></span>
        <span class="status">${statusIcon(trace.status)}</span>
        <span class="dur">${fmtDur(trace.duration_ms||0)}</span>
        <span class="tokens">${tokStr}</span>
        <span class="summary-text">${buildSummaryText(trace)}</span>
        <button class="copy-btn" onclick="event.stopPropagation();copyTraceJson('${esc(trace.id)}')">复制JSON</button>
      </div>
      ${evHtml}
    </div>`;
  }).join('');
}

function toggle(id){
  if(expanded.has(id)) expanded.delete(id); else expanded.add(id);
  renderTraces();
}
function toggleEv(key){
  if(evExpanded.has(key)) evExpanded.delete(key); else evExpanded.add(key);
  const el=document.getElementById('evd-'+key.replace(':','-'));
  if(el) el.classList.toggle('open',evExpanded.has(key));
}

// ════════════════════════ Stats refresh ════════════════════════
async function refresh(){
  try{
    const [stats,data]=await Promise.all([
      fetch('/api/stats').then(r=>r.json()),
      fetch('/api/traces?limit=200').then(r=>r.json()),
    ]);
    allTraces=data.traces||[];
    document.getElementById('sTotal').textContent=stats.trace_count||0;
    document.getElementById('sActive').textContent=stats.active_count||0;
    document.getElementById('sTokens').textContent=`↑${fmtNum(stats.total_input_tokens||0)} ↓${fmtNum(stats.total_output_tokens||0)}`;
    document.getElementById('sTools').textContent=`${(stats.tools_exposed||[]).length}/${(stats.tools_all||[]).length}`;
    const te=stats.tools_exposed||[];
    document.getElementById('toolsWrap').innerHTML=
      `<b>注入工具 (${te.length})</b>: `+(te.length?te.map(t=>`<span class="tool-name">${esc(t)}</span>`).join(''):'无');
    renderTraces();
  }catch(e){console.warn('refresh error',e);}
}

// ════════════════════════ LLM Log panel ════════════════════════
async function loadLlmLog(){
  document.getElementById('llmList').innerHTML='<div class="empty">加载中…</div>';
  try{
    const data=await fetch('/api/llm_log?limit=80').then(r=>r.json());
    allLlmEntries=data.entries||[];
    document.getElementById('llmCount').textContent=`共 ${allLlmEntries.length} 条`;
    renderLlmLog();
  }catch(e){
    document.getElementById('llmList').innerHTML=`<div class="empty">加载失败: ${esc(String(e))}</div>`;
  }
}

// Build paired request+response groups from flat entries list
function pairLlmEntries(entries){
  const byId={};
  const order=[];
  for(const e of entries){
    const rid=e.request_id||('_'+Math.random());
    if(!byId[rid]){byId[rid]={req:null,resp:null};order.push(rid);}
    if(e.direction==='request') byId[rid].req=e;
    else byId[rid].resp=e;
  }
  return order.map(rid=>byId[rid]);
}

function renderLlmLog(){
  const q=(document.getElementById('llmSearch').value||'').toLowerCase();
  let entries=allLlmEntries;
  if(q) entries=entries.filter(e=>JSON.stringify(e).toLowerCase().includes(q));
  if(!entries.length){document.getElementById('llmList').innerHTML='<div class="empty">无匹配记录</div>';return;}
  const pairs=pairLlmEntries(entries);
  allLlmPairs=pairs;
  document.getElementById('llmCount').textContent=`共 ${pairs.length} 次调用`;
  document.getElementById('llmList').innerHTML=pairs.map((p,i)=>{
    const req=p.req||{};
    const resp=p.resp||{};
    const ts=esc((req.ts||resp.ts||'').slice(11,19));
    const sysLen=(req.system||'').length;
    const msgCount=(req.messages||[]).length;
    // Last user message preview
    const lastMsg=(req.messages||[]).filter(m=>m.role==='user').pop();
    const userPreview=typeof lastMsg?.content==='string'?lastMsg.content.slice(0,80):
                      (Array.isArray(lastMsg?.content)?lastMsg.content.find(b=>b.type==='text')?.text?.slice(0,80)||'':'');
    const respPreview=resp.text?resp.text.slice(0,80):
                      (resp.tool_calls?.length?'⚙ '+resp.tool_calls.map(t=>t.name).join(', '):'');
    const latency=resp.latency_ms?` ${fmtDur(resp.latency_ms)}`:'';
    const tokens=resp.usage?` ${fmtNum((resp.usage.input_tokens||0)+(resp.usage.output_tokens||0))}tok`:'';
    const traceId=esc(req.trace_id||resp.trace_id||'');
    const reqId=esc(req.request_id||'');
    const hasSys=sysLen>0;
    return `<div class="llm-entry">
      <div class="llm-entry-header" onclick="toggleLlmEntry(${i})">
        <span class="llm-ts">${ts}</span>
        <span class="llm-dir ${hasSys?'req':'resp'}" style="font-size:10px">${esc(req.model||req.provider_sdk||'?')}</span>
        <span class="llm-preview" style="flex:1;min-width:0">
          <span style="color:#79c0ff">${esc(userPreview||'(no user msg)')}</span>
          ${respPreview?`<span style="color:#8b949e"> → </span><span style="color:#a5d6ff">${esc(respPreview)}</span>`:''}
        </span>
        <span style="color:#8b949e;font-size:11px;flex-shrink:0">${tokens}${latency} sys:${sysLen} msg:${msgCount} tr:${traceId}</span>
        <button class="copy-btn" onclick="event.stopPropagation();copyLlmPair(${i})">复制</button>
      </div>
      <div class="llm-body" id="llmb-${i}">
        ${buildPairBody(req,resp)}
      </div>
    </div>`;
  }).join('');
}

function buildPairBody(req,resp){
  let html='';
  // ── REQUEST side ──
  if(req.system!==undefined){
    html+=`<div class="llm-section"><div class="llm-section-title">▶ System Prompt (${(req.system||'').length} chars)</div>
      <div class="llm-section-content"><pre>${esc(req.system||'(empty)')}</pre></div></div>`;
  }
  if(req.messages&&req.messages.length){
    // Show only the last user message inline, full history collapsible
    const msgs=req.messages;
    const newMsgs=msgs.filter(m=>m.role==='user'||m.role==='tool');
    const histMsgs=msgs.filter(m=>m.role==='assistant');
    html+=`<div class="llm-section"><div class="llm-section-title">▶ User Input (${msgs.length} msgs total, ${histMsgs.length} assistant turns in history)</div>
      <div class="llm-section-content"><pre>${hlJson(msgs)}</pre></div></div>`;
  }
  if(req.tools&&req.tools.length){
    const names=req.tools.map(t=>t.function?.name||t.name).join(', ');
    html+=`<div class="llm-section"><div class="llm-section-title">▶ Tools (${req.tools.length}): ${esc(names)}</div>
      <div class="llm-section-content" style="display:none"><pre>${hlJson(req.tools)}</pre></div></div>`;
    // Make tools header clickable to expand
    html=html.replace('style="display:none"','id="tools-detail-hidden"');
  }
  // ── RESPONSE side ──
  if(resp.text){
    html+=`<div class="llm-section" style="border-left-color:#3fb950"><div class="llm-section-title">◀ Response Text</div>
      <div class="llm-section-content"><pre>${esc(resp.text)}</pre></div></div>`;
  }
  if(resp.thinking){
    html+=`<div class="llm-section" style="border-left-color:#d2a8ff"><div class="llm-section-title">◀ Thinking</div>
      <div class="llm-section-content"><pre>${esc(resp.thinking)}</pre></div></div>`;
  }
  if(resp.tool_calls&&resp.tool_calls.length){
    html+=`<div class="llm-section" style="border-left-color:#ffa657"><div class="llm-section-title">◀ Tool Calls (${resp.tool_calls.length})</div>
      <div class="llm-section-content"><pre>${hlJson(resp.tool_calls)}</pre></div></div>`;
  }
  if(resp.usage||resp.latency_ms){
    html+=`<div class="llm-section" style="border-left-color:#8b949e"><div class="llm-section-title">◀ Usage / Latency</div>
      <div class="llm-section-content"><pre>${hlJson({usage:resp.usage,latency_ms:resp.latency_ms})}</pre></div></div>`;
  }
  return html||'(no data)';
}

function toggleLlmEntry(i){
  const el=document.getElementById('llmb-'+i);
  if(el) el.classList.toggle('open');
}

// ════════════════════════ Runtime log panel ════════════════════════
async function loadRuntimeLog(){
  const lines=document.getElementById('logLines').value||'100';
  document.getElementById('logWrap').textContent='加载中…';
  try{
    const data=await fetch('/api/logs?lines='+lines).then(r=>r.json());
    const content=(data.content||'(empty)');
    // Colorize by log level
    const html=content.split('\n').map(line=>{
      if(line.includes(' ERROR ')) return `<span class="log-err">${esc(line)}</span>`;
      if(line.includes(' WARNING ')) return `<span class="log-warn">${esc(line)}</span>`;
      if(line.includes(' DEBUG ')) return `<span class="log-debug">${esc(line)}</span>`;
      return `<span class="log-info">${esc(line)}</span>`;
    }).join('\n');
    document.getElementById('logWrap').innerHTML=html;
    // Auto-scroll to bottom
    const w=document.getElementById('logWrap');
    w.scrollTop=w.scrollHeight;
  }catch(e){
    document.getElementById('logWrap').textContent='加载失败: '+e;
  }
}

// ════════════════════════ Boot ════════════════════════
refresh();
setInterval(refresh,4000);
</script>
</body>
</html>"""


# ── Observability class ───────────────────────────────────────────────────────

class Observability:
    def __init__(self, data_dir: Path, max_traces: int = 500) -> None:
        self._lock = threading.Lock()
        self._traces: deque[Trace] = deque(maxlen=max_traces)
        self._active: dict[str, Trace] = {}  # trace_id → Trace
        self._tools_all: list[str] = []
        self._tools_exposed: list[str] = []
        self._started_at = time.time()
        self._data_dir = data_dir

        logs_dir = data_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self._traces_path = logs_dir / "traces.jsonl"
        self._runtime_log_path = logs_dir / "runtime.log"
        self._llm_calls_path = logs_dir / "llm_calls.jsonl"
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ── Trace lifecycle ───────────────────────────────────────────────────────

    def start_trace(self, trigger: str, **meta: Any) -> str:
        """Open a new trace for a logical operation. Sets ContextVar for current task."""
        trace_id = _short_id()
        trace = Trace(trace_id, trigger, meta)
        with self._lock:
            self._active[trace_id] = trace
            self._traces.append(trace)
        _current_trace_id.set(trace_id)
        return trace_id

    def end_trace(self, trace_id: str, status: str = "ok", **summary: Any) -> None:
        """Close the trace and persist it."""
        with self._lock:
            trace = self._active.pop(trace_id, None)
        if trace is None:
            return
        trace.end(status, **summary)
        line = json.dumps(trace.to_dict(), ensure_ascii=False)
        try:
            with self._traces_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            logger.warning("Failed to write trace to JSONL")

    # ── Event emission ────────────────────────────────────────────────────────

    def emit(self, event_type: str, **data: Any) -> None:
        """Emit an event into the current trace (determined by ContextVar)."""
        trace_id = _current_trace_id.get()
        if trace_id is None:
            return
        with self._lock:
            trace = self._active.get(trace_id)
        if trace is not None:
            trace.add_event(event_type, {k: _json_safe(v) for k, v in data.items()})

    # ── Tool registry snapshot ────────────────────────────────────────────────

    def set_tools(self, all_tools: list[str], exposed: list[str]) -> None:
        with self._lock:
            self._tools_all = all_tools
            self._tools_exposed = exposed

    # ── API data ──────────────────────────────────────────────────────────────

    def get_traces(self, limit: int = 200, trigger: str = "") -> list[dict[str, Any]]:
        with self._lock:
            traces = list(self._traces)
        if trigger:
            traces = [t for t in traces if t.trigger == trigger or t.trigger.startswith(trigger)]
        traces = traces[-limit:]
        traces.reverse()
        return [t.to_dict() for t in traces]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            traces = list(self._traces)
            active_count = len(self._active)
            tools_all = list(self._tools_all)
            tools_exposed = list(self._tools_exposed)
        total_in = sum(t.total_tokens()[0] for t in traces)
        total_out = sum(t.total_tokens()[1] for t in traces)
        return {
            "trace_count": len(traces),
            "active_count": active_count,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "tools_all": tools_all,
            "tools_exposed": tools_exposed,
            "uptime_seconds": int(time.time() - self._started_at),
        }

    def get_llm_log(self, limit: int = 80) -> list[dict[str, Any]]:
        """Read the most recent entries from llm_calls.jsonl (newest last)."""
        if not self._llm_calls_path.exists():
            return []
        try:
            lines = self._llm_calls_path.read_text(encoding="utf-8").splitlines()
            entries: list[dict[str, Any]] = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            # Newest first
            entries.reverse()
            return entries[:limit]
        except Exception as e:
            logger.warning("Failed to read llm_calls.jsonl: %s", e)
            return []

    def get_runtime_log(self, lines: int = 100) -> str:
        """Return the last N lines of runtime.log."""
        if not self._runtime_log_path.exists():
            return "(runtime.log not found)"
        try:
            all_lines = self._runtime_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(all_lines[-lines:])
        except Exception as e:
            return f"(read error: {e})"

    # ── HTTP server ───────────────────────────────────────────────────────────

    def start_server(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        if self._httpd is not None:
            return
        obs = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._send_text(_HTML, "text/html; charset=utf-8")
                elif parsed.path == "/api/stats":
                    self._send_json(obs.get_stats())
                elif parsed.path == "/api/traces":
                    qs = parse_qs(parsed.query)
                    limit = int((qs.get("limit") or ["200"])[0])
                    trigger = (qs.get("trigger") or [""])[0]
                    self._send_json({"traces": obs.get_traces(limit=limit, trigger=trigger)})
                elif parsed.path == "/api/llm_log":
                    qs = parse_qs(parsed.query)
                    limit = int((qs.get("limit") or ["80"])[0])
                    self._send_json({"entries": obs.get_llm_log(limit=limit)})
                elif parsed.path == "/api/logs":
                    qs = parse_qs(parsed.query)
                    lines = int((qs.get("lines") or ["100"])[0])
                    self._send_json({"content": obs.get_runtime_log(lines=lines)})
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *_args: Any) -> None:
                return

            def _send_json(self, payload: Any) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def _send_text(self, text: str, content_type: str) -> None:
                data = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Monitor UI started: http://%s:%d/", host, port)

    def stop_server(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None


# ── Module-level singleton ────────────────────────────────────────────────────

_OBS: Observability | None = None


def initialize_observability(data_dir: Path) -> Observability:
    global _OBS
    if _OBS is None:
        _OBS = Observability(data_dir)
    return _OBS


def get_observability() -> Observability | None:
    return _OBS


def start_trace(trigger: str, **meta: Any) -> str:
    if _OBS is None:
        return ""
    return _OBS.start_trace(trigger, **meta)


def end_trace(trace_id: str, status: str = "ok", **summary: Any) -> None:
    if _OBS is not None and trace_id:
        _OBS.end_trace(trace_id, status, **summary)


def emit_event(event_type: str, **data: Any) -> None:
    """Emit an event into the current active trace."""
    if _OBS is not None:
        _OBS.emit(event_type, **data)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return repr(value)
