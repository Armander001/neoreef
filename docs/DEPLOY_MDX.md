# Deploying NeoReef to mdx

How to move NeoReef from a local prototype to the [mdx research cloud](https://mdx.jp) (the data-empowered platform operated jointly by Japanese universities, including Science Tokyo). The Docker stack in this repo was designed for this target; this document covers the steps around it. For day-to-day development *on* the VM through VS Code Remote-SSH, see [`REMOTE_DEV_MDX.md`](REMOTE_DEV_MDX.md).

**Division of labor:** Metashape photogrammetry stays on the local Windows machine (license + GPU). The mdx VM only *serves* results — and optionally runs the post-processing pipeline. The recommended split:

```
Local Windows machine                     mdx VM (Ubuntu)
─────────────────────                     ────────────────
Batch_metashape.py (Metashape)            nginx container (docker compose)
cesium_pipeline.py --stage all     ───►   serves CESIUM_OUTPUT_DIR contents
        rsync/scp output                  (COGs, GeoJSON, models, manifest, viewers)
```

---

## 1. Get a VM (mdx user portal)

Done once, through the mdx user portal (`https://oprpl.mdx.jp`). You need to be added to the lab's mdx project by its project manager — check whether Nakamura Lab already has an allocation before applying for a new one (the `163.220.179.199` address used as `SERVER_BASE_URL` example in the config suggests a lab VM may already exist).

Checklist in the portal:

- [ ] Deploy a VM from the **Ubuntu 22.04/24.04 template** (3–4 vCPU / 8 GB RAM is plenty for nginx; add more if running the pipeline on the VM)
- [ ] **Storage**: orthomosaic COGs are multi-GB each. Size the virtual disk for your survey count × ~2–5 GB, plus headroom. Request additional storage if needed.
- [ ] Register your **SSH public key** at deploy time (mdx VMs are key-only; no password login)
- [ ] Assign a **global IP (DNAT)** so the viewers are reachable from outside
- [ ] Open **ACL / firewall rules** in the portal: inbound TCP 22 (SSH, restrict to campus ranges if possible) and TCP 80 (HTTP). Everything else closed.

Then verify access:

```bash
ssh mdxuser@<global-ip>
```

> mdx VMs have direct outbound internet — do **not** set the campus proxy (`proxy.noc.titech.ac.jp`) on the VM. That proxy is for machines on the campus LAN, and setting it on mdx will break `apt`, `docker pull`, and CDN access.

## 2. Install Docker on the VM

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER   # log out/in afterwards
```

## 3. Put the code and config on the VM

```bash
# On the VM
git clone https://github.com/Armander001/neoreef.git ~/neoreef
```

`cesium_config.json` is gitignored (it holds the Cesium ion token) — copy it over by hand and **adjust its paths** for the VM:

```bash
# From the local machine
scp cesium_config.json mdxuser@<global-ip>:~/neoreef/
```

Config values that change for the VM:

| Key | Local value | mdx value |
|---|---|---|
| `CESIUM_OUTPUT_DIR` | Windows path | `/home/mdxuser/neoreef-data/output` (or wherever you sync to) |
| `SERVER_BASE_URL` | `""` | keep `""` — viewers and data are co-hosted on the same nginx, so relative URLs work |
| `USE_ION` | either | `false` to serve everything from the VM; `true` if layers should stream from Cesium ion instead |

## 4. Get the data onto the VM

**Recommended: process locally, sync only the pipeline output.** `--stage manifest` already copies the viewer HTMLs into `CESIUM_OUTPUT_DIR`, so that one directory is the complete deployable site.

```powershell
# On the local machine, after a pipeline run
scp -r <CESIUM_OUTPUT_DIR>/* mdxuser@<global-ip>:~/neoreef-data/output/
```

(`rsync -avz --progress` via WSL or Git Bash is much better for multi-GB re-syncs — it skips unchanged COGs.)

The stock `docker-compose.yml` serves a *named volume* that only the pipeline container writes to. When output is synced from outside, bind-mount the synced directory instead, using a `docker-compose.override.yml` on the VM (already gitignored, so it never touches the repo):

```yaml
# ~/neoreef/docker-compose.override.yml  (VM only)
services:
  nginx:
    volumes:
      - /home/mdxuser/neoreef-data/output:/srv/neoreef:ro
```

**Alternative: run the pipeline on the VM.** Transfer the raw `*_ortho.tif` + shapefiles instead, set `DATA_SOURCE_DIR` to that directory, and run `docker compose run --rm pipeline --config /app/config/cesium_config.json --stage all`. Only worth it if local→VM transfer of raw inputs is cheaper than transfer of outputs (it usually isn't — raw and processed are similar sizes, and the pipeline needs RAM for windowed COG conversion).

## 5. Start serving

```bash
cd ~/neoreef
docker compose up -d nginx
docker compose logs -f nginx        # watch for startup errors
```

Verify from the local machine:

```bash
curl -I http://<global-ip>/manifest.json          # expect 200, Cache-Control: no-cache
curl -I http://<global-ip>/                        # expect 200 (cesium_viewer.html is the index)
curl -s -H "Range: bytes=0-1023" -o /dev/null -w "%{http_code}" http://<global-ip>/<some>.tif   # expect 206
```

That last check matters: CesiumJS streams COGs via HTTP range requests, and a `200` instead of `206` means the proxy/firewall in between is buffering whole multi-GB files.

Then open `http://<global-ip>/` in a browser. The viewers load CesiumJS from a CDN and (if `USE_ION=true`) tiles from Cesium ion, so the *browser* needs internet too — on campus, that's the usual proxy-configured browser.

## 6. Operations

- **Update data**: re-run the pipeline locally, re-sync `CESIUM_OUTPUT_DIR`. nginx serves the volume read-only and picks changes up immediately (`manifest.json` and `*.html` are sent with `no-cache`).
- **Update viewers/code**: `git pull` on the VM, then `docker compose up -d nginx` (viewer HTMLs come from the synced output dir, so a local pipeline `--stage manifest` re-run + sync also works).
- **Change port**: `NEOREEF_PORT=8080 docker compose up -d nginx` (and open that port in the mdx ACL).
- **Restart policy**: nginx runs with `restart: unless-stopped`, so it survives VM reboots once Docker is enabled (`sudo systemctl enable docker`).

## 7. Security notes

- The ion token lives only in `cesium_config.json` on the VM (and embedded in viewer config where applicable). Keep VM SSH key-only; never commit the config.
- nginx sends `Access-Control-Allow-Origin: *`. This is intentional for read-only public survey data; revisit if anything sensitive is ever added to the output directory.
- HTTP only for now. If the deployment gets a DNS name, add HTTPS (Caddy or certbot in front of nginx) before sharing the URL broadly.

## Open items (decide before/with the first deployment)

1. **Does the lab already have an mdx project/VM?** If `163.220.179.199` is live, steps 1–2 may already be done — confirm with the project manager and get an account on the existing VM.
2. **ion vs. local serving** (`USE_ION`): local-only keeps everything on mdx (no per-asset ion quota usage); ion offloads tile streaming but ties the deployment to the token and quota.
3. **Transfer path for multi-GB syncs**: campus network → mdx is fast; from home, expect long first syncs. `rsync` makes subsequent syncs incremental.
