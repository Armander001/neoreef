# Developing on the mdx VM with VS Code Remote-SSH

Companion to [`DEPLOY_MDX.md`](DEPLOY_MDX.md): that document covers *deploying* NeoReef to the mdx VM; this one covers *working on it day-to-day* through VS Code. Visual overview: [`architecture/06_remote_dev.svg`](architecture/06_remote_dev.svg).

## 1. Mental model — what Remote-SSH actually does

When you connect, VS Code installs a small headless backend (**VS Code Server**, in `~/.vscode-server/` on the VM) over SSH. After that:

| Runs on your Windows laptop | Runs on the mdx VM |
|---|---|
| The VS Code window (UI, themes, keybindings) | File explorer contents, search, git operations |
| The SSH tunnel | Integrated terminal (a real bash shell on Ubuntu) |
| | Workspace extensions (Python, Docker, Claude Code) |
| | Anything you run: `docker compose`, `python`, `claude` |

So "opening a folder on mdx" means you are editing files **in place on the VM** — no syncing, no copies. Closing the window leaves everything (containers, files) running on the VM.

### Two connection routes — pick by where you are

Your `~/.ssh/config` (Windows side) defines two aliases for the same VM:

| Alias | When | How |
|---|---|---|
| `mdx` | Home / off-campus | Direct, port 22 |
| `mdx-campus` | On campus | Tunneled through `proxy.noc.titech.ac.jp:3128`, port 443 |

A VS Code `OfflineError (connection timed out)` almost always means you picked the wrong alias for your current network (campus blocks direct port 22).

## 2. Connect and open the project

1. `F1` → **Remote-SSH: Connect to Host…** → `mdx-campus` (on campus) or `mdx` (home)
2. Enter the key passphrase (or pre-load the key: `ssh-add ~/.ssh/mdx_key` in a Windows terminal once per boot)
3. **File → Open Folder** → `/home/mdx-user02/neoreef`
4. First time only: `git clone https://github.com/Armander001/neoreef.git ~/neoreef` in the integrated terminal (`` Ctrl+` ``)

The bottom-left green badge shows `SSH: mdx-campus` when you're connected.

## 3. Extensions — local vs. remote

The Extensions panel splits into **Local** and **SSH: mdx** sections. UI extensions (themes, keymaps) stay local; anything that touches code or processes must be installed **on the remote** — click *"Install in SSH: …"* on the extension page.

Recommended on the remote:

| Extension | Why |
|---|---|
| **Claude Code** (`anthropic.claude-code`) | Claude works directly on the VM's files and terminal |
| **Python** (`ms-python.python`) + Pylance | Editing `cesium_pipeline.py` with IntelliSense |
| **Container Tools / Docker** (`ms-azuretools.vscode-containers`) | Sidebar view of containers, logs, shell-in, restart |

### Claude Code on the VM

The extension needs the CLI on the VM. mdx VMs have **direct outbound internet — do not set the campus proxy there**:

```bash
# On the VM (integrated terminal)
curl -fsSL https://claude.ai/install.sh | bash
claude          # first run opens an OAuth login link — paste it into your local browser
```

Each machine authenticates separately, so logging in on the VM doesn't affect your Windows session. Claude on the VM can run `docker compose`, tail nginx logs, and edit the viewers in place.

## 4. How Docker fits the development workflow

The stack (see [`architecture/05_docker_stack.svg`](architecture/05_docker_stack.svg)) is two services:

- **`nginx`** — always-on web server. Serves `/srv/neoreef` (data volume) and the three viewer HTMLs, which are **bind-mounted straight from the repo**.
- **`pipeline`** — on-demand batch container (profile `pipeline`, never runs unless you ask).

Metashape **never** runs on the VM (license + GPU live on your Windows machine). The VM's jobs are *serve* and, optionally, *post-process*.

### The edit→see loop for viewers (the common case)

Because `cesium_viewer.html` is bind-mounted into nginx, the loop is just:

```
edit cesium_viewer.html on the VM  →  refresh http://<global-ip>/  →  done
```

No container restart, no pipeline run, no sync. Commit from the VM when happy (`git push` — set up a GitHub credential or SSH key on the VM once).

### The data-update loop

```
Windows: run Metashape + cesium_pipeline.py --stage all
Windows: rsync/scp CESIUM_OUTPUT_DIR  →  VM ~/neoreef-data/output/
```

nginx picks changes up immediately (volume is read-only to it; `manifest.json` and HTML are served with `no-cache`). See `DEPLOY_MDX.md` §4 for the bind-mount override that points nginx at the synced directory.

### Daily commands (VM terminal)

```bash
docker compose up -d nginx            # start serving (survives reboots)
docker compose logs -f nginx          # watch requests / errors live
docker compose run --rm pipeline \
  --config /app/config/cesium_config.json --stage manifest   # rebuild manifest on the VM
docker compose ps                     # what's running
docker compose down                   # stop everything
```

With the Container Tools extension you can do the same from the sidebar: right-click the container → *View Logs* / *Attach Shell* / *Restart*.

### Port forwarding for private testing

To test without exposing a port through the mdx ACL, use VS Code's **Ports** panel (next to Terminal): forward port `80` and open `http://localhost:80` on your laptop — the traffic rides the SSH tunnel. Handy for trying `NEOREEF_PORT=8080` variants before opening firewall rules.

## 5. Where things live on the VM

```
~/neoreef/                      # git clone — code, compose file, viewers
~/neoreef/cesium_config.json    # gitignored — scp'd from Windows, ion token inside
~/neoreef/docker-compose.override.yml   # VM-only nginx bind-mount (gitignored)
~/neoreef-data/output/          # synced pipeline output (COGs, GeoJSON, manifest)
~/.vscode-server/               # VS Code backend + remote extensions (auto-managed)
```

## 6. Gotchas

- **Proxy direction matters**: campus proxy on your *laptop's* SSH route — yes (that's `mdx-campus`). Campus proxy as env vars *on the VM* — never; it breaks `apt`, `docker pull`, and the Claude installer.
- **The VM is shared infrastructure**: `docker compose down` kills the public viewers. Prefer the port-forwarding loop for experiments.
- **`.vscode-server` bloat**: if the connection ever wedges mid-install, `rm -rf ~/.vscode-server` on the VM (via plain `ssh`) and reconnect — VS Code reinstalls it cleanly.
- **Don't edit the served data volume by hand** — re-run the pipeline locally and re-sync, so Windows stays the source of truth.
