"""Interactive local HTTP Review UI server (stdlib http.server + sqlite3, Fluid Light Mode)."""
from __future__ import annotations

import html
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from qc_factory_day10.adapters.delivery_reader import DeliveryContext, safe_rel_path
from qc_factory_day10.engine.geometry import yolo_to_pixels
from qc_factory_day10.review.review_store import ReviewStore


def _build_image_overlays(ctx: DeliveryContext) -> dict[str, dict[str, Any]]:
    """Preload detection boxes and panoptic segment bboxes per image for fast UI rendering."""
    items = ctx.manifest.get("items", {})
    pan_imgs = {Path(im["file_name"]).stem: im for im in ctx.panoptic.get("images", []) if "file_name" in im}
    pan_anns = {Path(a["file_name"]).stem: a for a in ctx.panoptic.get("annotations", []) if "file_name" in a}
    cat_names = {c["id"]: c["name"] for c in ctx.panoptic.get("categories", []) if c.get("isthing", 1)}

    overlays: dict[str, dict[str, Any]] = {}
    for name, entry in items.items():
        im = pan_imgs.get(name, {})
        w = int(im.get("width", 640) or 640)
        h = int(im.get("height", 480) or 480)
        det_boxes = []
        lbl_rel = entry.get("label", "")
        if lbl_rel:
            lbl_path = safe_rel_path(ctx.root, lbl_rel)
            if lbl_path and lbl_path.is_file():
                for line in lbl_path.read_text(encoding="utf-8").splitlines():
                    parts = line.split()
                    if len(parts) == 5:
                        try:
                            cls_id = int(parts[0])
                            vals = [float(x) for x in parts[1:]]
                            x1, y1, x2, y2 = yolo_to_pixels(vals, w, h)
                            det_boxes.append({
                                "label": ctx.classes.get(cls_id, str(cls_id)),
                                "x1": round(x1, 1), "y1": round(y1, 1),
                                "x2": round(x2, 1), "y2": round(y2, 1),
                            })
                        except ValueError:
                            pass
        pan_boxes = []
        ann = pan_anns.get(name, {})
        for seg in ann.get("segments_info", []):
            cname = cat_names.get(seg.get("category_id"))
            if not cname:
                continue
            bx, by, bw, bh = seg.get("bbox", [0, 0, 0, 0])
            pan_boxes.append({
                "label": cname,
                "iscrowd": bool(seg.get("iscrowd", 0)),
                "x1": round(bx, 1), "y1": round(by, 1),
                "x2": round(bx + bw, 1), "y2": round(by + bh, 1),
            })
        overlays[name] = {
            "width": w,
            "height": h,
            "image_rel": entry.get("image", f"images/{name}.jpg"),
            "det_boxes": det_boxes,
            "pan_boxes": pan_boxes,
        }
    return overlays


def render_review_html(run_name: str, reviewers: list[str]) -> str:
    """Render Fluid Light-Mode interactive review SPA."""
    rev_opts = "".join(f'<option value="{html.escape(r)}">{html.escape(r)}</option>' for r in reviewers)
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QC Intelligence Review — {html.escape(run_name)}</title>
<style>
  :root {{
    --bg: #f8fafc; --surface: #ffffff; --border: #cbd5e1;
    --text: #0f172a; --muted: #475569; --primary: #0f4c81;
    --green: #15803d; --red: #b91c1c; --amber: #b45309;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); font-size: 14px; }}
  header {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px;
            padding: 12px 24px; background: var(--surface); border-bottom: 1px solid var(--border); }}
  .title {{ font-size: 20px; font-weight: 800; letter-spacing: -0.02em; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
  .pill {{ padding: 6px 12px; border-radius: 6px; background: #f1f5f9; border: 1px solid var(--border); font-weight: 600; }}
  main {{ width: 100%; padding: 16px 24px; display: grid; grid-template-columns: 320px 1fr 380px; gap: 16px; min-height: calc(100vh - 70px); }}
  @media (max-width: 1100px) {{ main {{ grid-template-columns: 1fr; }} }}
  .panel {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }}
  .queue-list {{ overflow-y: auto; max-height: calc(100vh - 220px); display: flex; flex-direction: column; gap: 8px; }}
  .q-item {{ padding: 10px; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; background: #fff; text-align: left; }}
  .q-item.active {{ border-color: var(--primary); background: #eff6ff; }}
  .q-item.confirmed {{ border-left: 4px solid var(--green); }}
  .q-item.rejected {{ border-left: 4px solid var(--red); }}
  .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  .badge.HARD {{ background: #fee2e2; color: #991b1b; }}
  .badge.MEDIUM {{ background: #fef3c7; color: #92400e; }}
  .viewport {{ position: relative; overflow: auto; background: #e2e8f0; border-radius: 6px; min-height: 460px; display: flex; align-items: center; justify-content: center; }}
  .stage {{ position: relative; transform-origin: top left; display: inline-block; }}
  .stage img {{ display: block; max-width: none; }}
  .stage svg {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
  button, select, input, textarea {{ font-family: inherit; font-size: 14px; border-radius: 6px; border: 1px solid var(--border); }}
  button, select, input {{ height: 40px; padding: 0 12px; background: #fff; color: var(--text); }}
  button {{ cursor: pointer; font-weight: 600; }}
  button.primary {{ background: var(--primary); color: #fff; border-color: var(--primary); }}
  button.confirm {{ background: var(--green); color: #fff; border-color: var(--green); }}
  button.reject {{ background: var(--red); color: #fff; border-color: var(--red); }}
  textarea {{ padding: 10px; width: 100%; min-height: 96px; resize: vertical; }}
  .hint {{ font-size: 12px; color: var(--muted); }}
  .err {{ color: var(--red); font-weight: 600; }}
</style>
</head>
<body>
<header>
  <div class="title">QC Intelligence Review — {html.escape(run_name)}</div>
  <div class="stats" id="statsBar">Loading...</div>
  <div class="controls">
    <label>Reviewer: <select id="reviewerSel">{rev_opts}</select></label>
    <button class="primary" onclick="exportOfficial()">Export review_log.csv &amp; errors.json</button>
  </div>
</header>
<main>
  <section class="panel">
    <div class="controls">
      <select id="filterVerdict" onchange="renderQueue()">
        <option value="pending">Pending / Skip</option>
        <option value="all">Tất cả</option>
        <option value="confirmed">Confirmed</option>
        <option value="rejected">Rejected</option>
      </select>
      <select id="filterTier" onchange="renderQueue()">
        <option value="ALL">Mọi tier</option>
        <option value="MEDIUM">MEDIUM</option>
        <option value="HARD">HARD</option>
      </select>
    </div>
    <div class="queue-list" id="queueList"></div>
  </section>

  <section class="panel">
    <div class="controls">
      <button onclick="prevItem()">&larr; Trước</button>
      <button onclick="nextItem()">Sau &rarr;</button>
      <label><input type="checkbox" id="chkDet" checked onchange="renderCanvas()"> Detection (đỏ)</label>
      <label><input type="checkbox" id="chkPan" checked onchange="renderCanvas()"> Panoptic (xanh)</label>
      <button onclick="setZoom(zoom * 1.25)">Zoom +</button>
      <button onclick="setZoom(Math.max(0.4, zoom / 1.25))">Zoom -</button>
      <button onclick="setZoom(1.0)">100%</button>
    </div>
    <div class="viewport" id="viewport">
      <div class="stage" id="stage">
        <img id="imgEl" alt="candidate"/>
        <svg id="svgEl"></svg>
      </div>
    </div>
  </section>

  <section class="panel">
    <div id="detailMeta"></div>
    <label>Loại lỗi chốt (nếu là lỗi):
      <select id="resolvedType" style="width:100%;margin-top:4px">
        <option value="class_swap">class_swap (box detection sai)</option>
        <option value="category_swap">category_swap (segment panoptic sai)</option>
        <option value="bbox_drift">bbox_drift (box lệch khỏi vật)</option>
        <option value="missing_box">missing_box (thiếu box detection)</option>
        <option value="instance_merge">instance_merge (2 vật bị gộp)</option>
      </select>
    </label>
    <label>Ghi chú bằng chứng (bắt buộc &ge; 20 ký tự mô tả thấy gì trong ảnh):
      <textarea id="noteInput" placeholder="VD: Trong ảnh là xe buýt màu đỏ nhưng box detection gán nhầm thành truck..."></textarea>
    </label>
    <div class="hint">Độ dài hiện tại: <span id="noteLen">0</span>/20 ký tự | Phím tắt: C=Confirm, R=Reject, S=Skip</div>
    <div class="controls">
      <button class="confirm" onclick="submitDecision('confirmed')">Confirm (C)</button>
      <button class="reject" onclick="submitDecision('rejected')">Reject (R)</button>
      <button onclick="submitDecision('skip')">Skip (S)</button>
    </div>
    <div id="statusMsg" class="hint"></div>
  </section>
</main>
<script>
let STATE = {{ candidates: [], overlays: {{}}, stats: {{}} }};
let FILTERED = [];
let CUR_ID = null;
let zoom = 1.0;

async function loadState() {{
  const res = await fetch('/api/state');
  STATE = await res.json();
  renderStats();
  renderQueue();
  if (!CUR_ID && FILTERED.length) selectCandidate(FILTERED[0].candidate_id);
  else if (CUR_ID) renderDetail();
}}

function renderStats() {{
  const s = STATE.stats;
  document.getElementById('statsBar').innerHTML =
    `<span class="pill">Tổng: ${{s.total || 0}}</span>` +
    `<span class="pill">Đã duyệt: ${{s.reviewed || 0}}</span>` +
    `<span class="pill">Còn lại: ${{s.pending || 0}}</span>` +
    `<span class="pill">MEDIUM: ${{(s.by_tier||{{}}).MEDIUM || 0}} | HARD: ${{(s.by_tier||{{}}).HARD || 0}}</span>`;
}}

function renderQueue() {{
  const fv = document.getElementById('filterVerdict').value;
  const ft = document.getElementById('filterTier').value;
  FILTERED = STATE.candidates.filter(c => {{
    if (fv === 'pending' && !['pending', 'skip'].includes(c.verdict)) return false;
    if (fv !== 'all' && fv !== 'pending' && c.verdict !== fv) return false;
    if (ft !== 'ALL' && c.difficulty_tier !== ft) return false;
    return true;
  }});
  const el = document.getElementById('queueList');
  el.innerHTML = FILTERED.map(c =>
    `<button class="q-item ${{c.verdict}} ${{c.candidate_id === CUR_ID ? 'active' : ''}}" onclick="selectCandidate('${{c.candidate_id}}')">
      <div><b>${{c.image_id}}</b> <span class="badge ${{c.difficulty_tier}}">${{c.difficulty_tier}}</span></div>
      <div class="hint">${{c.candidate_type}} | P=${{c.priority}} | ${{c.verdict}}</div>
    </button>`
  ).join('');
}}

function selectCandidate(cid) {{
  CUR_ID = cid;
  renderQueue();
  renderDetail();
}}

function renderDetail() {{
  const c = STATE.candidates.find(x => x.candidate_id === CUR_ID);
  if (!c) return;
  document.getElementById('detailMeta').innerHTML =
    `<div><b>Ảnh:</b> ${{c.image_id}} <span class="badge ${{c.difficulty_tier}}">${{c.difficulty_tier}}</span></div>` +
    `<div><b>Giả thuyết:</b> ${{c.candidate_type}} (P=${{c.priority}})</div>` +
    `<div><b>Bằng chứng máy đo:</b> ${{c.evidence}}</div>` +
    `<div><b>Người được phân:</b> ${{c.assigned_reviewer || 'Chưa phân'}}</div>`;
  document.getElementById('resolvedType').value = c.resolved_type || c.candidate_type;
  document.getElementById('noteInput').value = c.note || '';
  updateNoteLen();
  renderCanvas();
}}

function renderCanvas() {{
  const c = STATE.candidates.find(x => x.candidate_id === CUR_ID);
  if (!c) return;
  const ov = STATE.overlays[c.image_id];
  if (!ov) return;
  const img = document.getElementById('imgEl');
  img.src = '/delivery/' + ov.image_rel;
  const svg = document.getElementById('svgEl');
  svg.setAttribute('viewBox', `0 0 ${{ov.width}} ${{ov.height}}`);
  let shapes = '';
  if (document.getElementById('chkDet').checked) {{
    for (const b of ov.det_boxes) {{
      shapes += `<rect x="${{b.x1}}" y="${{b.y1}}" width="${{b.x2-b.x1}}" height="${{b.y2-b.y1}}" fill="none" stroke="#dc2626" stroke-width="2.5"/>`;
      shapes += `<text x="${{b.x1}}" y="${{Math.max(14, b.y1-3)}}" fill="#dc2626" font-size="13" font-weight="bold">${{b.label}}</text>`;
    }}
  }}
  if (document.getElementById('chkPan').checked) {{
    for (const b of ov.pan_boxes) {{
      shapes += `<rect x="${{b.x1}}" y="${{b.y1}}" width="${{b.x2-b.x1}}" height="${{b.y2-b.y1}}" fill="none" stroke="#2563eb" stroke-width="2" stroke-dasharray="5,3"/>`;
      shapes += `<text x="${{b.x1}}" y="${{Math.min(ov.height-4, b.y2+13)}}" fill="#2563eb" font-size="12" font-weight="bold">${{b.label}}</text>`;
    }}
  }}
  svg.innerHTML = shapes;
  setZoom(zoom);
}}

function setZoom(z) {{
  zoom = z;
  document.getElementById('stage').style.transform = `scale(${{zoom}})`;
}}

function updateNoteLen() {{
  document.getElementById('noteLen').textContent = document.getElementById('noteInput').value.trim().length;
}}
document.getElementById('noteInput').addEventListener('input', updateNoteLen);

async function submitDecision(verdict) {{
  if (!CUR_ID) return;
  const note = document.getElementById('noteInput').value.trim();
  const resolved_type = document.getElementById('resolvedType').value;
  const reviewer = document.getElementById('reviewerSel').value;
  const msg = document.getElementById('statusMsg');
  const res = await fetch('/api/decide', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ candidate_id: CUR_ID, verdict, resolved_type, note, reviewer }})
  }});
  const data = await res.json();
  if (!res.ok) {{
    msg.className = 'err';
    msg.textContent = data.error || 'Lỗi lưu quyết định';
    return;
  }}
  msg.className = 'hint';
  msg.textContent = `Đã lưu: ${{verdict}} (${{resolved_type}})`;
  await loadState();
  nextItem();
}}

function nextItem() {{
  const i = FILTERED.findIndex(x => x.candidate_id === CUR_ID);
  if (i >= 0 && i + 1 < FILTERED.length) selectCandidate(FILTERED[i + 1].candidate_id);
  else if (FILTERED.length) selectCandidate(FILTERED[0].candidate_id);
}}

function prevItem() {{
  const i = FILTERED.findIndex(x => x.candidate_id === CUR_ID);
  if (i > 0) selectCandidate(FILTERED[i - 1].candidate_id);
}}

async function exportOfficial() {{
  const res = await fetch('/api/export', {{ method: 'POST' }});
  const data = await res.json();
  document.getElementById('statusMsg').textContent =
    `Đã xuất ${{data.review_rows}} dòng vào review_log.csv và ${{data.total_errors}} lỗi vào errors.json`;
}}

document.addEventListener('keydown', e => {{
  if (['TEXTAREA', 'INPUT', 'SELECT'].includes(document.activeElement.tagName)) return;
  if (e.key === 'c' || e.key === 'C') submitDecision('confirmed');
  else if (e.key === 'r' || e.key === 'R') submitDecision('rejected');
  else if (e.key === 's' || e.key === 'S') submitDecision('skip');
  else if (e.key === 'ArrowRight') nextItem();
  else if (e.key === 'ArrowLeft') prevItem();
}});

loadState();
</script>
</body>
</html>"""


def create_review_server(
    ctx: DeliveryContext,
    store: ReviewStore,
    out_dir: Path,
    reviewers: list[str],
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Create a local ThreadingHTTPServer for interactive human visual review."""
    overlays = _build_image_overlays(ctx)
    html_page = render_review_html(out_dir.name, reviewers).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, code: int, payload: Any) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            path = unquote(urlparse(self.path).path)
            if path == "/" or path == "/index.html":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_page)))
                self.end_headers()
                self.wfile.write(html_page)
                return
            if path == "/api/state":
                self._send_json(HTTPStatus.OK, {
                    "candidates": store.list_candidates(),
                    "stats": store.stats(),
                    "overlays": overlays,
                })
                return
            if path.startswith("/delivery/"):
                rel = path[len("/delivery/"):]
                file_path = safe_rel_path(ctx.root, rel)
                if file_path and file_path.is_file():
                    ctype, _ = mimetypes.guess_type(str(file_path))
                    data = file_path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", ctype or "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = unquote(urlparse(self.path).path)
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8"))
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
                return

            if path == "/api/decide":
                try:
                    updated = store.record_decision(
                        candidate_id=str(payload["candidate_id"]),
                        verdict=str(payload["verdict"]),
                        resolved_type=str(payload["resolved_type"]),
                        note=str(payload.get("note", "")),
                        reviewer=str(payload.get("reviewer", "")),
                    )
                    self._send_json(HTTPStatus.OK, {"ok": True, "candidate": updated})
                except (KeyError, ValueError) as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if path == "/api/export":
                rows = store.export_review_log(out_dir / "review_log.csv")
                base_errs = out_dir / "rules_errors.json"
                if not base_errs.is_file():
                    base_errs = out_dir / "errors.json"
                total = store.merge_confirmed_into_errors(base_errs, out_dir / "errors.json")
                self._send_json(HTTPStatus.OK, {"ok": True, "review_rows": rows, "total_errors": total})
                return

            self.send_error(HTTPStatus.NOT_FOUND)

    return ThreadingHTTPServer((host, port), Handler)


def serve_blocking(
    ctx: DeliveryContext,
    store: ReviewStore,
    out_dir: Path,
    reviewers: list[str],
    port: int = 8765,
) -> None:
    srv = create_review_server(ctx, store, out_dir, reviewers, port=port)
    print(f"Review UI running at http://127.0.0.1:{srv.server_address[1]}/ (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
