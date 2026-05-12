# NeoReef — Architecture Diagrams

Hand-authored SVGs describing each logical subsystem. Edit them directly; they
are not generated. Open in any browser, Inkscape, or VS Code's SVG preview.

| File | Subsystem | Source files described |
|---|---|---|
| `01_system_overview.svg` | End-to-end data flow from photos to browser | All |
| `02_metashape_pipeline.svg` | Photogrammetry batch — `Batch_metashape.py` | `Batch_metashape.py` |
| `03_cesium_pipeline.svg` | Geospatial post-processing — `cesium_pipeline.py` | `cesium_pipeline.py` |
| `04_viewers.svg` | Three browser viewers + manifest.json contract | `cesium_viewer.html`, `ortho_viewer.html`, `landuse_viewer.html` |
| `05_docker_stack.svg` | nginx + pipeline containers + volumes | `Dockerfile.app`, `docker-compose.yml`, `nginx/default.conf` |

## Visual vocabulary

Used consistently across all five diagrams so they read as a family:

| Shape / Colour | Meaning |
|---|---|
| **Rounded blue box** (`#1e3a5f` outline, `#cfe1f2` fill) | Python module / function / pipeline stage |
| **Rounded purple box** (`#3a1e5f` outline, `#e1cff2` fill) | Browser viewer / JavaScript |
| **Rounded green box** (`#1e5f3a` outline, `#cff2e1` fill) | Data artefact (file on disk) |
| **Rounded orange box** (`#5f3a1e` outline, `#f2e1cf` fill) | External service (Cesium ion, OSM, CDN) |
| **Rounded grey box** (`#3a3a3a` outline, `#e0e0e0` fill) | Container / infrastructure |
| **Solid arrow** | Synchronous call or data flow |
| **Dashed arrow** | Configuration or optional path |
| **Bold label** | Public name (file, function, container, URL) |
| **Italic sub-label** | Implementation note or condition |

## Editing

Each SVG starts with a `<!-- LAYOUT GUIDE -->` comment block explaining the
column/row grid used, so future edits stay aligned. To add a new component:

1. Pick the colour from the vocabulary table that matches its role.
2. Reuse the existing `<defs>` arrow markers (`arrow-end`).
3. Snap the box's `x`/`y` to the grid noted in the layout guide.
4. Update the corresponding section of `REPORT_code_duplication.md` if the
   change affects coupling or duplication.

If a subsystem grows large enough to deserve its own file, add a new
`NN_subsystem.svg` here and a row to the table above.
