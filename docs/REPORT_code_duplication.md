# NeoReef — Code Duplication & Reuse Report

**Generated:** 2026-04-29
**Scope:** All Python scripts, viewer HTMLs, Docker/nginx config in the repo root.
**Total source LOC analyzed:** 4,567 (Python: 2,743 — HTML/JS+CSS: 1,750 — config: ~75)

The report is structured as:
1. **Dead code & orphans** — files to delete or fix outright.
2. **Near-duplicate files** — lineage scripts that should be deleted now that the active version supersedes them.
3. **Within-file duplication** — patterns that should be helperised.
4. **Cross-file duplication** — shared logic that should be factored into common modules.
5. **Bugs found during review** — discovered while comparing implementations.
6. **Recommended action plan** — ordered by effort/impact.

---

## 1. Dead code & orphans

| File | Status | Recommendation |
|---|---|---|
| `Layer_Landuse.py` | **Empty file (0 bytes)** | Delete. CLAUDE.md already labels it a placeholder. Land-use logic actually lives in `cesium_pipeline.py:412-465` (`batch_process_landuse`) and `landuse_viewer.html`. |
| `Agisoft_test.py` | **Broken — will not run** | Either delete or fix. Bugs: (a) uses `accuracy=Metashape.HighAccuracy` which was removed in Metashape 2.x (replaced by `downscale=`); (b) filename format string `P9070{:049}.jpg` zero-pads to 49 chars (almost certainly meant `:04d}`); (c) saves to literal `r"C:\path\to\project.psx"`. The smoke test it claims to be is not exercising anything. |
| `short_scripts.txt` | Unknown role | Inspect — if it's notes, move to `docs/notes/` or delete. Not imported by any code. |
| `Batch_metashape` (no extension) | Older batch runner, superseded | Delete. See section 2. Also: the missing `.py` extension means it won't auto-execute as Python on Windows without `metashape.exe -r` — easy to mistake for a config file. |
| `NeoReef_slim` (no extension) | Path-only fork of `NeoReef.py` | Delete. See section 2. |
| `NeoReef_batch.py` | Older Ishi25-only batch runner | Delete. Superseded by `Batch_metashape.py`. |
| `NeoReef.py` | Single-survey runner | Keep as-is **only if** you use it for one-off surveys; otherwise delete and run `Batch_metashape.py` with `TARGET_FOLDER` set, which already supports single-folder mode (line 54). |

**Estimated lines removable from "delete-only" candidates: ~937 lines** (Layer_Landuse 1 + Agisoft_test 18 + Batch_metashape 390 + NeoReef_slim 168 + NeoReef_batch 381). That's ~20% of the codebase, with no behavior loss.

---

## 2. Near-duplicate files (lineage forks)

The CLAUDE.md describes the lineage `NeoReef.py → NeoReef_slim → NeoReef_batch.py → Batch_metashape → Batch_metashape.py`. All four older files are almost completely subsumed by `Batch_metashape.py`. Concrete diffs:

### 2.1 `NeoReef.py` vs `NeoReef_slim`

**Diff is 4 lines.** Identical 168-line file except:
| Line | NeoReef.py | NeoReef_slim |
|---|---|---|
| 25 | `D:\Armando\Ishi25_S008_0915_A1\…psx` | `C:\Users\Aruma\…\Ishi25_S010_0916_A1\…psx` |
| 26 | `D:\Armando\Ishi25_S008_0915_A1` | `…\Ishi25_S010_0916_A1` |
| 27 | `..._ortho.tif` (S008) | `..._ortho.tif` (S010) |
| 82 | `chunk.label = "Ishi25_S008_0915_A1"` | `chunk.label = "Ishi25_S010_0916_A1"` |

These three values are exactly the per-survey config that `Batch_metashape.py:54` (`TARGET_FOLDER`) already handles. **NeoReef_slim should be deleted; NeoReef.py is redundant once you accept Batch_metashape.py's single-folder mode.**

### 2.2 `NeoReef_batch.py` vs `Batch_metashape` (no ext) vs `Batch_metashape.py`

All three are batch processors over the same Ishi survey-folder convention. The progression:

| Feature | NeoReef_batch.py | Batch_metashape | Batch_metashape.py (active) |
|---|---|---|---|
| Folder regex | `Ishi25_…` only | `Ishi24\|25_…` | `Ishi24\|25_…` |
| `make_logger()` helper | inline `log_msg`, single file | yes | yes |
| `export_jpeg_preview()` fallback | no | inline single attempt | helper, 2-attempt fallback |
| `Complete Images` timestamped JPEG dir | no | yes | yes |
| 3D model pipeline (OBJ → glb → gltfpack → tileset.json) | no | no | yes |
| `_run_tool` subprocess wrapper | no | no | yes |
| `_compute_model_bbox` / `_make_tileset` | no | no | yes |
| `TARGET_FOLDER` single-folder mode | no | no | yes |
| `main()` function structure | no (procedural top-level) | yes | yes |
| Optional `CESIUM_PIPELINE_ENABLED` post-hook | no | yes (dead — not enabled) | no (removed) |

**`Batch_metashape.py` is a strict superset of the other two for every meaningful capability.** Delete the older two.

The `CESIUM_PIPELINE_ENABLED` block in `Batch_metashape:365-384` is interesting — it was experimental glue to chain Metashape → cesium_pipeline.py automatically. It was dropped in `Batch_metashape.py`. If chaining is desired, add it back as a CLI arg in the active script rather than a hardcoded path.

---

## 3. Within-file duplication

### 3.1 `cesium_pipeline.py`

#### 3.1.1 Three near-identical TOCHICD lookup closures (lines 389-399)

```python
def get_color(row):    return TOCHICD_MAP.get(int(row.get("TOCHICD", -1)) if … else -1, TOCHICD_DEFAULT)["color"]
def get_name_en(row):  return TOCHICD_MAP.get(int(row.get("TOCHICD", -1)) if … else -1, TOCHICD_DEFAULT)["name_en"]
def get_name_ja(row):  return TOCHICD_MAP.get(int(row.get("TOCHICD", -1)) if … else -1, TOCHICD_DEFAULT)["name_ja"]
```
Then:
```python
gdf["fill_color"]  = gdf.apply(lambda r: get_color(r),    axis=1)
gdf["land_use_en"] = gdf.apply(lambda r: get_name_en(r), axis=1)
gdf["land_use_ja"] = gdf.apply(lambda r: get_name_ja(r), axis=1)
```
**Refactor:** one helper that returns the full record, then assign columns from the result. This also halves the row iterations:
```python
def _tochicd_entry(row):
    code = int(row["TOCHICD"]) if row.get("TOCHICD") is not None else -1
    return TOCHICD_MAP.get(code, TOCHICD_DEFAULT)
entries = gdf.apply(_tochicd_entry, axis=1)
gdf["fill_color"]  = entries.map(lambda e: e["color"])
gdf["land_use_en"] = entries.map(lambda e: e["name_en"])
gdf["land_use_ja"] = entries.map(lambda e: e["name_ja"])
```

#### 3.1.2 Three near-identical `to_dict` methods (lines 77-81, 94-98, 111-115)

`OrthoRecord`, `LanduseRecord`, `Model3DRecord` each define `to_dict` that runs `asdict(self)` and then `str()`-coerces a couple of `Path` fields. **Refactor:** a single `_pathified_dict(obj, path_fields)` helper, or a `PathRecord` mixin/base dataclass.

#### 3.1.3 `ion_upload_ortho` and `ion_upload_landuse` (lines 707-748) are 90% identical

Only the `asset_type`, `source_type`, `name`, and `description` differ. **Refactor:** a single `ion_upload_record(rec, *, name_fn, asset_type, source_type, description_fn, file_attr, asset_id_setter)` — or keep both wrappers but factor out the try/except + `_ion_upload_asset` call into `_safe_ion_upload(...)`.

#### 3.1.4 "Re-scan if records empty" pattern repeated three times (lines 988-1004, 1013-1043)

The "if running this stage standalone, rebuild the records from disk" logic is duplicated for orthos, landuse, and 3d models. **Refactor:** a single `ensure_records(stage_name, ortho_records, landuse_records, model3d_records, cfg, log)` that fills in whichever lists are empty.

#### 3.1.5 `make_logger` reinvented (lines 121-136)

`cesium_pipeline.py` rolls its own logger with file+console handlers. `Batch_metashape.py:169-186` and `Batch_metashape:118-148` each have their own `make_logger` that wraps Metashape.app.console + file. Different audiences (Metashape vs CLI), so they can stay separate — but a single `neoreef_logging.py` module exposing `make_metashape_logger()` and `make_cli_logger()` would centralise the setup and let you change the format once.

### 3.2 Viewer HTMLs

#### 3.2.1 TOCHICD_LEGEND duplicated in 2 of 3 viewers — and **the data has drifted**

`cesium_viewer.html:252-272` and `landuse_viewer.html:161-181` both embed a 19-entry TOCHICD legend. They are **not** the same:

| Code | cesium_viewer label | landuse_viewer label | Match? |
|---|---|---|---|
| 12 | Park / green space | **Other natural** | No |
| 13 | Sports ground | **Parks/sports** | No |
| 14 | Industrial / warehouse | Industrial/warehouse | Yes (whitespace) |
| 15 | Public facilities | **Commercial** | No |
| 16 | School land | **Public facilities** | No |
| 17 | Vacant / other | **Mixed use** | No |

Five out of nineteen labels disagree. Depending on which viewer the user opens, the same TOCHICD code is described as a different land-use category. **This is a real consistency bug** — and the source of truth (cesium_pipeline.py:38-58, Python) doesn't fully match either viewer (it has both `name_ja` and `name_en` columns that neither viewer reads).

**Fix:** generate `tochicd_legend.json` from the Python `TOCHICD_MAP` at pipeline run time, write it next to `manifest.json`, and have both viewers `fetch()` it. Single source of truth, no drift, no JS-string-array surgery needed when codes change.

#### 3.2.2 `addLanduseLayer` is near-identical between `cesium_viewer.html:382-449` and `landuse_viewer.html:272-329`

Same `Cesium.GeoJsonDataSource.load()` + entity loop + per-polygon styling + `landuseSources/Colors/ExtH` bookkeeping. Differences: cesium_viewer uses alpha 0.55 vs landuse_viewer 0.6, and cesium_viewer also calls `buildLegend()` itself vs landuse_viewer passing `activeCodes` to its `buildLegend(activeCodes)`.

#### 3.2.3 `addOrthoLayer` near-identical between `cesium_viewer.html:333-380` and `ortho_viewer.html:185-228`

Same GroundPrimitive construction, same fallback-to-IonImageryProvider, same `orthoLayers` registry. cesium_viewer additionally tracks `_show`/`_alpha` for the separation feature.

#### 3.2.4 `toggleSeparation` duplicated

`cesium_viewer.html:478-565` (handles landuse + ortho lifting) and `landuse_viewer.html:215-251` (landuse only). The landuse-portion of the algorithm is byte-for-byte the same.

#### 3.2.5 `flyToIsland`, `bboxToRect`, status toast, manifest fetch + fallback, viewer init options

All three viewers redo this. `Cesium.Viewer` is constructed with the same 11 options (`baseLayerPicker:false, …, scene3DOnly:true`) in all three. The manifest-load `try/catch` with the hardcoded `124.205, 24.470` fallback is duplicated three times.

#### 3.2.6 CSS palette swap

The toolbar/card/legend CSS rules are functionally identical across the three viewers; the only differences are the accent colour (`#7ec8e3` cyan in cesium/ortho, `#c8b4ff` purple in landuse) and the page-background hex. Could be a single `viewer-common.css` with a CSS-variable accent: `:root { --accent: #7ec8e3; }` and a tiny per-viewer override file.

**Estimated cross-viewer extraction savings:** ~600-700 LOC if shared into `viewer-common.{css,js}` (the three HTMLs total 1,750 LOC).

---

## 4. Cross-file duplication (Python ↔ JS, scripts ↔ pipeline)

| Pattern | Locations | Recommendation |
|---|---|---|
| TOCHICD map | `cesium_pipeline.py:38-58`, `cesium_viewer.html:252-272`, `landuse_viewer.html:161-181` | Generate JSON from Python; viewers fetch. (See 3.2.1.) |
| `IMAGE_EXTENSIONS` set | `Batch_metashape.py:69-74`, `Batch_metashape:47-52`, `NeoReef_batch.py:49`, `NeoReef.py:53`, `NeoReef_slim:53` | Once the older 4 files are deleted, this becomes a non-issue (only the active file remains). |
| `get_images_from_folder` (A-Z subfolders) | `Batch_metashape.py:153-166`, `Batch_metashape:100-112`, `NeoReef_batch.py:130-142`, plus inline in `NeoReef.py:49-58`/`NeoReef_slim:49-58` | Same: lineage cleanup resolves it. |
| Metashape stdout/stderr unclose hack | `Batch_metashape.py:23-30`, `Batch_metashape:18-25`, `NeoReef_batch.py:21-27` | Same. |
| `make_logger` (Metashape variant) | `Batch_metashape.py:169-186`, `Batch_metashape:118-148` | Same. |
| Survey center coords `(124.205, 24.470)` | `cesium_pipeline.py:801-803` (manifest survey_area) and as fallbacks in all 3 viewers | Viewers should rely on the manifest exclusively. The hardcoded fallback in viewer init is only useful when the manifest is missing — at which point the viewer can't show anything anyway. Drop the fallback or move it to the manifest's static defaults. |
| Cesium.Viewer init options block | All 3 viewers | Move to `viewer-common.js`. |
| `Cesium.Ion.defaultAccessToken` set + length-check | All 3 viewers | Same. |

---

## 5. Bugs found during review

These are not part of the duplication scope but were uncovered while comparing implementations. Worth a separate ticket each.

1. **`cesium_pipeline.py:340` — broken era regex.**
   `re.match(r"^([MTSH R])(\d+)$", year_label.strip(), re.IGNORECASE)` has a **literal space** in the character class. Probably a paste error meant to be `[MTSHR]`. With the current code, a folder named `" 23"` would parse, while `R23` (Reiwa 23) does not parse case-insensitively as expected because the space is matched, not stripped.
2. **`Agisoft_test.py:14` — uses removed Metashape 1.x API** (`Metashape.HighAccuracy`). Won't run on Metashape 2.x at all.
3. **`Agisoft_test.py:10` — format string `:049` produces 49-char wide zero-padded numbers.** Almost certainly meant `:04d`.
4. **TOCHICD label divergence between viewers** (see 3.2.1) — five of nineteen labels disagree.
5. **`NeoReef.py` and `NeoReef_slim` import `Metashape` twice** (lines 14 and 20). Harmless but smells.
6. **`NeoReef_batch.py` doesn't close `log_handle` if `exit(1)` is reached early** — it does call `log_handle.close()` at line 176 before the exit, so OK, but the script-level (no `main()`) structure makes this fragile.
7. **`cesium_pipeline.py:794` uses `datetime.utcnow()`** which is deprecated in Python 3.12+. Use `datetime.now(timezone.utc)`.
8. **`Batch_metashape` (no extension)** is a Python script with no `.py` suffix. On Windows it can't be opened by file-association as Python. If kept, rename. (Recommendation: delete it.)
9. **`cesium_config.json` is committed with a live JWT** (already noted in your memory). The `.gitignore` line for it appears AFTER it was committed — `git rm --cached cesium_config.json` is needed to evict it from history going forward (history rewrite is a separate, riskier conversation).

---

## 6. Recommended action plan (ordered by effort / impact)

### Tier 1 — Pure delete, zero behavioural risk (~30 min)
- [ ] Delete `Layer_Landuse.py`
- [ ] Delete `Agisoft_test.py` (or fix bugs 2 & 3 if you actually want a smoke test)
- [ ] Delete `NeoReef_slim`
- [ ] Delete `NeoReef_batch.py`
- [ ] Delete `Batch_metashape` (the extension-less version)
- [ ] Decide on `NeoReef.py`: delete if you're happy using `Batch_metashape.py` with `TARGET_FOLDER`, otherwise keep as the documented one-survey runner
- [ ] Inspect & decide on `short_scripts.txt`

**Result:** ~20% of repo LOC removed. The only "active" Metashape script becomes `Batch_metashape.py` (or that + `NeoReef.py`). CLAUDE.md "Project structure" section should be updated to match.

### Tier 2 — Single source of truth for TOCHICD (1-2 hr)
- [ ] Have `cesium_pipeline.py` write `tochicd_legend.json` next to `manifest.json` (add `extrudeH` to the Python map; reconcile the divergent labels — pick the cesium_pipeline.py labels as canonical since they have both Japanese and English).
- [ ] Modify both viewers to `fetch("tochicd_legend.json")` and build `TOCHICD_BY_CODE` from that.
- [ ] Delete the inline `TOCHICD_LEGEND` arrays in both HTMLs.

**Result:** Bug #4 fixed forever. Adding a new land-use code in the future is a one-file change.

### Tier 3 — Within-file refactors in cesium_pipeline.py (1-2 hr)
- [ ] Collapse the three TOCHICD lookup closures (3.1.1)
- [ ] Single `to_dict` helper / mixin (3.1.2)
- [ ] Merge `ion_upload_ortho` + `ion_upload_landuse` (3.1.3)
- [ ] `ensure_records()` for the rebuild-from-disk pattern (3.1.4)
- [ ] Fix the era regex (bug #1)
- [ ] Replace `datetime.utcnow()` (bug #7)

**Result:** ~80-120 LOC removed. No external behavioural change.

### Tier 4 — Viewer extraction (4-6 hr)
- [ ] Create `viewers/common.js` with: `bboxToRect`, `flyToIsland`, status toast, manifest loader, viewer-init helper, `addOrthoLayer`, `addLanduseLayer`, `toggleSeparation` (parameterised by which layer types it should lift).
- [ ] Create `viewers/common.css` with shared toolbar / card / legend rules + `--accent` CSS variable.
- [ ] Slim each HTML down to: imports, accent-colour override, page-specific UI buttons, init call.
- [ ] Make sure `cesium_pipeline.py:870-882` still copies the CSS/JS files alongside the HTMLs into `CESIUM_OUTPUT_DIR`, and that `Dockerfile.app` and `docker-compose.yml` mount them into `/srv/neoreef`.

**Result:** ~600-700 LOC removed. The three viewers stop drifting from each other.

---

## Summary

- **Hard wins available now:** ~20% of the codebase (~937 LOC) is deletable old-version code.
- **One real consistency bug** to fix (TOCHICD labels diverge between viewers); fixing it via a generated JSON also kills the largest cross-file duplication.
- **`cesium_pipeline.py` (1,074 LOC) is the only file with significant within-file duplication** — five concrete refactors save ~80-120 LOC.
- **The three viewer HTMLs (1,750 LOC)** could collapse to roughly 1,000 LOC if shared `common.{js,css}` is extracted. This is the largest single-file-count refactor but the highest-friction (touches build/Docker/manifest copy paths).
- After Tiers 1+2, this repo would be at roughly 3,400 LOC with no functional change. After Tier 4, roughly 2,800.
