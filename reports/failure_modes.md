# Failure Modes & Mitigation

1. **Natural COCO occlusion / crowd mismatch on clean data:**
   - Observed on `runs/clean` (50 images): `7` candidates (`{'class_swap': 1, 'missing_box': 6}`).
   - Mitigation: Human visual review marks natural occlusion/crowd as `rejected` with >= 20-char note; never auto-confirm.
2. **Hidden test (`--opaque`) encrypted filenames & altered fault profile:**
   - `img_0001` filenames carry no difficulty signal.
   - Mitigation: `qc_factory_day10.engine.difficulty` computes `difficulty_score`, `error_evidence_score`, `review_value_score` purely from box/mask geometry.
3. **`class_swap` vs `category_swap` direction ambiguity:**
   - Cross-check emits `class_swap` hypothesis; human reviewer inspects image and selects `class_swap` or `category_swap` in Review UI.
