# Factory Reuse Matrix (`cvat` → `qc_factory_day10`)

Audit root: `D:\06-Learning\AIA-VINGROUP\learning\cvat` (read-only audit, 2026-11-19).

| Module | Path (`cvat/...`) | Inputs / Outputs | Dependencies | Tests | Reusable? | Required Changes | Risk | Reuse Decision |
|---|---|---|---|---|---|---|---|---|
| Content-addressed Cache | `src/cvat_tools/core/cache.py` | file/params → SHA256 key + JSON cache | Python stdlib (`hashlib`, `json`) | `tests/` | Yes | Decouple `cvat_tools.core.paths` to accept Day10 run cache dir | Low | **REUSE (Adapt)** in `qc_factory_day10/engine/mask_statistics.py` |
| Transactions / Backup | `src/cvat_tools/core/transactions.py` | state paths → backup & rollback | Python stdlib | `tests/` | Yes | Pattern reused for safe SQLite/export backup | Low | **REUSE (Pattern)** in `qc_factory_day10/review/review_store.py` |
| ShapeStore (SQLite) | `src/cvat_tools/core/shapestore.py` | shape/review revisions ↔ SQLite | `sqlite3` (stdlib) | `tests/` | Yes | Simplify schema to Day10 candidate verdicts (`confirmed`/`rejected`/`skip`) | Low | **REUSE (Adapt)** in `qc_factory_day10/review/review_store.py` |
| HTML Review Queue | `src/cvat_tools/quality/review.py` | ranked queue + images → interactive HTML | `cv2`, `numpy` (optional) | `tests/` | Yes | Replace `cv2` base64 encoding with direct local file/HTTP serving + SVG overlay + Fluid Light UI | Low | **REUSE (Adapt)** in `qc_factory_day10/review/server.py` |
| Quality Metrics Eval | `src/cvat_tools/quality/metrics_eval.py` | bbox / masks → IoU, invalid geom | `numpy` | `tests/` | Partial | Pure-Python stdlib port for `validator/validate.py` & `engine/geometry.py` | Low | **REUSE (Stdlib Port)** in `qc_factory_day10/engine/geometry.py` |
| Stuff/Thing Overlap | `src/cvat_tools/segmentation/stuff_things.py` | masks + classes → overlap metrics | `numpy` | `tests/` | Partial | Adapt overlap/containment logic to COCO panoptic RGB IDs | Low | **REUSE (Pattern)** in `qc_factory_day10/engine/matching.py` |
| Frame Profiler / Router | `harness/frame_profiler.py` | image stats → complexity cues | `numpy`, `cv2` | `tests/` | Partial | Port complexity cues (object count, small-obj ratio, crowding) to stdlib Day10 triage | Medium | **REUSE (Adapt)** in `qc_factory_day10/engine/difficulty.py` |
| CVAT REST Client / Sync | `src/cvat_tools/core/client.py`, `autolabel/sync.py` | CVAT server API | `requests`, CVAT server | `tests/` | No | Not needed: Day10 is offline `delivery/` folder | None | **DO NOT REUSE** (incompatible / forbidden network) |
| Heavyweight Models (YOLO/SAM/VLM) | `src/cvat_tools/detection/`, `segmentation/sam_refine.py` | RGB images → predictions | `torch`, `ultralytics`, `onnxruntime` | `tests/` | No (challenge) | Forbidden inside `validator/validate.py` (stdlib only); disabled in default challenge mode | High | **DISABLED BY DEFAULT** (optional practice-only) |

---

## Audit bổ sung: `D:\06-Learning\AIA-VINGROUP\learning\day10\projects` (`CVAT Factory X`)

| Module | Path (`day10/projects/...`) | Purpose | Dependencies | Reuse Decision |
|---|---|---|---|---|
| Showcase Review & Session | `release_control/showcase/` | Interactive review flow, security & session state | `fastapi`, `uvicorn`, `pydantic` | **REUSE (Architecture Pattern)** — ported to zero-dependency stdlib `http.server` + `sqlite3` in `qc_factory_day10/review/` so it runs on any team laptop without `pip install` |
| Fault Lab & Validators | `release_control/fault_lab/`, `validators/` | Controlled fault injection & rule checks | `pydantic`, `pyyaml` | **REFERENCE ONLY** — Day10 official lab already provides `scripts/inject_release.py` and requires stdlib-only `validator/validate.py` |
| Lineage & Release Control | `release_control/lineage/`, `release/` | Release state machine (`HOLD` / `RELEASE`) & OpenLineage | `pydantic`, `mlflow` | **REFERENCE ONLY** — Day10 official lab uses `scripts/lineage.py`, `scripts/pack_release.py`, `scripts/check_handover.py` |
