# Exporting from Metashape for CesiumJS: 3D Tiles & Orthomosaic

This guide covers exporting two types of output from an Agisoft Metashape project for visualization in CesiumJS:

1. **3D Tiles** — a textured 3D model (shows the full three-dimensional structure)
2. **Orthomosaic** — a 2D top-down georeferenced image (a flat map-like image)

Both can be displayed together in CesiumJS and serve complementary purposes.

---

## Prerequisites

- **Agisoft Metashape Professional 2.0 or later**
- A completed photogrammetry project with:
  - Aligned cameras
  - A built, textured mesh
  - A defined coordinate reference system (CRS), preferably **EPSG:4326 (WGS 84)**

### Verify the Coordinate Reference System

Before exporting either output, confirm the CRS is correctly set:

- Open the **Reference** panel
- Confirm the chunk's coordinate system is defined
- For CesiumJS, **EPSG:4326 (WGS 84)** is strongly recommended
- To change it: **Reference** panel → **Settings** → set Coordinate System to `WGS 84 (EPSG::4326)`

---

## Part 1: Export 3D Tiles (Textured 3D Model)

### 1.1 Build a Tiled Model

1. Menu: **Workflow → Build Tiled Model**
2. Settings:
   - **Source data**: Mesh (recommended) or Dense Cloud
   - **Pixel size**: default (or specify for a target resolution)
   - **Tile size**: 256 (default)
   - **Face count**: High or Medium depending on desired detail
3. Click **OK** and wait for completion

> Large models (millions of polygons) may take several hours to build.

### 1.2 Export as 3D Tiles

1. Menu: **File → Export → Export Tiled Model**
2. In the Save dialog:
   - **File type**: **`Cesium 3D Tiles 1.1 (*.3tz)`**
   - Filename example: `shiraho_reef_site1.3tz`
3. In the export options dialog:
   - **Texture format**: **KTX 2.0** (recommended — better compression and faster loading than JPEG)
   - **Embed textures**: ✓ checked
   - Leave other settings at default
4. Click **OK**

### 1.3 Unpack the .3tz Archive

The `.3tz` file is a ZIP archive. Extract it:

- Windows: right-click → Extract All (or 7-Zip)
- macOS/Linux: `unzip shiraho_reef_site1.3tz -d shiraho_reef_site1/`

After extraction:

```
shiraho_reef_site1/
├── App/             ← DELETE this folder (standalone viewer, not needed)
├── Data/            ← contains all .b3dm tile files (KEEP)
└── tileset.json     ← root tileset descriptor (KEEP)
```

The `Data/` folder and `tileset.json` are what will be deployed to the server.

---

## Part 2: Export Orthomosaic (2D Georeferenced Image)

### 2.1 Build the Orthomosaic

If not already built:

1. Menu: **Workflow → Build Orthomosaic**
2. Settings:
   - **Projection**: Geographic, CRS = **WGS 84 (EPSG:4326)**
   - **Surface**: Mesh (reflects the reef's relief) or DEM
   - **Blending mode**: Mosaic (default)
   - **Enable hole filling**: ✓ checked
3. Click **OK** and wait for completion

### 2.2 Export as GeoTIFF

1. Menu: **File → Export → Export Orthomosaic → Export JPEG/TIFF/PNG**
2. Settings:
   - **File format**: TIFF/GeoTIFF
   - **Coordinate System**: WGS 84 (EPSG:4326)
   - **Pixel size**: default (original resolution); increase the value to reduce file size if needed
   - **Write BigTIFF**: ✓ check if the file may exceed 4 GB
   - **Write KML / World file**: not required (GeoTIFF embeds the georeferencing)
3. Filename example: `coral_ortho_site1.tif`
4. Click **Export**

> High-resolution orthomosaics can be several GB to tens of GB. If the file is too large, increase the pixel size (coarser resolution) or crop the export region using the bounding box in the export dialog.

---

## Output Summary

After completing both parts, you will have:

```
# 3D Tiles (textured 3D model)
shiraho_reef_site1/
├── Data/
└── tileset.json

# Orthomosaic (2D georeferenced image)
coral_ortho_site1.tif
```

| Output | Format | Purpose in CesiumJS |
|--------|--------|---------------------|
| 3D Tiles | `tileset.json` + `Data/` | Full 3D structure, viewable from any angle |
| Orthomosaic | GeoTIFF | Flat top-down image draped on the terrain surface |

---

## Notes on the Two Outputs

- **3D Tiles** preserve the three-dimensional shape of the reef (relief, overhangs, vertical structures). Best for detailed inspection from multiple viewpoints.
- **Orthomosaic** is a single flat image projected from above. Best for mapping, area measurement, and as a base image overlay. It does not contain 3D shape information.
- The two can be shown simultaneously or toggled in the CesiumJS interface, depending on the use case.

---

## Troubleshooting

### Missing or incorrect georeferencing
- Confirm the chunk's CRS is set to EPSG:4326 **before** building outputs
- Re-export after correcting

### Orthomosaic file too large
- Increase Pixel size in the export dialog (coarser resolution)
- Crop the export region using the bounding box
- Enable BigTIFF for files over 4 GB

### Black/missing textures on the 3D model
- Increase texture resolution in Build Texture settings (4096 or 8192)
- Verify UV mapping on the mesh

### Out of memory during tiled model build
- Decimate the mesh: **Tools → Mesh → Decimate Mesh**
- Lower the texture size before tiling

---

## Next Steps

Once exported, these files will be transferred to the MDX server:

- **3D Tiles** → served via Nginx as static files, loaded with `Cesium.Cesium3DTileset.fromUrl()`
- **Orthomosaic** → converted to Cloud Optimized GeoTIFF (COG), then served via GeoServer (WMS) or pre-tiled with gdal2tiles
