"""Scene split consistency and guideline checks against the owning job."""


def check(ctx):
    errors, scenes = [], {}
    for name in ctx["manifest"]:
        meta = ctx["meta"][name]
        scenes.setdefault(meta["scene_id"], set()).add(meta["split"])
        if meta["guideline_version"] != ctx["jobs"][meta["job_id"]]["guideline"]:
            errors.append({"type": "guideline_mismatch", "target": name})
    errors.extend({"type": "scene_leak", "target": scene}
                  for scene, splits in scenes.items() if len(splits) > 1)
    return errors
