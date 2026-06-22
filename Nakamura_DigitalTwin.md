# Ocean Digital Twin — CesiumJS on MDX

海洋研究データ（ROMS海洋モデル出力、海底地形、観測サイト等）を3D地球儀上で可視化・公開するWebアプリケーション。MDX学術クラウド上に完全自前でホスティングする。

## 環境概要

- **OS**: Ubuntu 24.04 LTS on MDX (10_Ubuntu 24.04 LTS Vendor template)
- **VM**: CPU 12パック（12コア / 18GB RAM）、仮想ディスク150GB
- **ストレージ**:
  - `/` (149GB): OS、Docker、CesiumJSアプリ
  - `/fast` (1TB): アクティブデータ（CTOD が読む地形 COG、CTOD キャッシュ）— **Lustre ネットワークFS**（`lustre_client.service` がマウント）
  - `/large` (10TB): ROMS NC ファイル、ncWMS/THREDDS 設定、アーカイブ等 — **Lustre ネットワークFS**（同上）

### 再起動時の落とし穴: Docker は Lustre マウント完了を待つ必要がある

`/fast` `/large` は Lustre で、boot 時に `lustre_client.service`（oneshot, ~15-25 秒かかる）が
マウントする。Docker デーモンが先に起動するとコンテナの bind-mount が**マウント前の空 inode**
を掴んだままになり、ホスト側に Lustre がマウントされても**コンテナ内は空ディレクトリのまま**
になる（CTOD で terrain 404/500、ncWMS で ROMS データセット消失、ローカル nginx 配信の
`.sigmesh` だけ動作する症状）。

対策として `/etc/systemd/system/docker.service.d/wait-for-lustre.conf` で
docker.service に `After=lustre_client.service` / `Requires=lustre_client.service` を入れている。
**この override を消すと再起動のたびに問題が再発する**。

復旧手順（万一発生した場合）:
```bash
# Lustre がマウント済みなのを確認してから 3 コンテナを再起動
ls /fast/terrain/common/merged_global.vrt && ls /large/ncwms_config/config.xml
docker restart ctod ncwms thredds
```

## 技術方針（重要）

- ベースマップは **ESRI World Imagery（デフォルト）**、国土地理院タイル（`https://cyberjapandata.gsi.go.jp/xyz/` の seamlessphoto / std）の 3 種から選択
- Cesium Ion は使用しない（依存を持たないため `Cesium.Ion.defaultAccessToken` も未設定）
- 地形タイルは CTOD（Docker）で **`merged_global.vrt`**（GEBCO 広域 + サイト別高解像度を VRT で統合）から生成。広域ズームでは GEBCO、各サイトに寄ると自動的に高解像度ローカル COG が反映される（σ面 terrain ではない）
- σ層は **`.sigmesh` バイナリメッシュ** を CesiumJS `Primitive` として描画
- すべてのバックエンドサービスは Docker コンテナで運用（個別 `docker run`、docker-compose 未使用）
- Nginx がリバースプロキシとして全サービスを束ねる

## アーキテクチャ

```
Nginx :80
  ├── /            → /var/www/cesium-app（静的ファイル）
  ├── /ctod/       → localhost:5000（CTOD: bathymetry terrain）
  ├── /ncwms/      → localhost:8070（ncWMS: ROMS WMS）
  ├── /thredds/    → localhost:8080（THREDDS: ROMS OPeNDAP/カタログ）
  └── /geoserver/  → localhost:8600（GeoServer: Shapefile等）※未起動
```

## Docker コンテナのバインドマウント

| コンテナ | ホスト → コンテナ |
|---|---|
| `ncwms` | `/large/roms → /data/roms`、`/large/ncwms → /data/ncwms`、`/large/ncwms_config → /usr/local/tomcat/.ncWMS2` |
| `thredds` | `/large/roms → /data/roms` |
| `ctod` | `/fast/terrain → /terrain`、`/fast/ctod_cache → /cache` |

**重要**:
- ncWMS の **実行時 config.xml は `/usr/local/tomcat/.ncWMS2/config.xml`** → ホスト側は `/large/ncwms_config/config.xml`（バインドマウント経由で永続化）。コンテナ再作成しても保持される
- ncWMS の NcML 内 `location` 属性は **コンテナ内パス**（`/data/roms/<Site>/<Project>/<file>.nc`）を指定する（ホストパス `/large/roms/...` ではない）

## ディレクトリ構成

```
/var/www/cesium-app/          CesiumJS アプリ本体（HTML/JS）
  ├── index.html
  ├── scripts/                Python スクリプト（uv プロジェクト）
  └── data/
       ├── datasets.json          データセットインデックス（git管理）
       ├── variable_registry.json 変数メタデータの一元辞書（git管理）
       ├── overlays/              静的 GeoJSON オーバーレイ（git管理外）
       │   ├── overlays.json
       │   └── <name>_{lines,polygons}.geojson
       ├── Yaeyama/
       │   └── Yaeyama3/
       │       ├── roms_grid.json                   プロジェクト共通
       │       ├── sigma_mesh_k0..14.sigmesh        プロジェクト共通（15個）
       │       └── <datasetId>_config.json          NCファイル毎
       ├── ShizugawaBay/
       │   ├── Shizugawa1/  Shizugawa2/  Shizugawa3/
       └── TokyoBay/
           ├── TokyoBay1/   TokyoBay2/   TokyoBay3/

/fast/terrain/                地形 COG（CTOD が配信）
  ├── common/                 全サイト共通の広域地形 + マージ VRT
  │   ├── gebco_2025_*_cog.tif       Float32 COG（CTOD 配信用、Int16 原本も併存）
  │   └── merged_global.vrt          全サイト統合 VRT（CTOD URL: /terrain/common/merged_global.vrt）
  ├── Yaeyama/
  │   ├── yaeyama_cog.tif     高解像度ローカル海底地形（Float32 COG）
  │   ├── Yaeyama_topo_merged_10m.tif
  │   └── merged_terrain.vrt  (旧 Yaeyama-only VRT、参照されていない)
  ├── ShizugawaBay/
  │   ├── Shizugawa3_bath_10m_grd_final.tif   原本（UTM 54N, Float64）
  │   └── shizugawabay_cog.tif                高解像度ローカル海底地形（Float32 COG）
  └── TokyoBay/               (今後追加)
/fast/ctod_cache/             CTOD タイルキャッシュ

/large/roms/                  ROMS NetCDF（ncWMS/THREDDS 配信元）
  ├── Yaeyama/
  │   ├── Yaeyama1/  Yaeyama2/  Yaeyama3/    例: Y3_his_*.nc, Yaeyama3_his_*.nc
  ├── ShizugawaBay/  TokyoBay/
/large/ncwms/                 NcML 設定 + add-dataset.sh
/large/ncwms_config/          ncWMS の実行時 config（config.xml, godiva3.properties, logs）
/large/thredds/config/        THREDDS catalog.xml（今後）
/large/geospatial/            GeoServer用データ + 静的GeoJSON（今後）
/large/drone_raw/             ドローン写真原本
/large/archive/, /large/jma_gpv/  各種アーカイブ
```

## Git 管理

- リポジトリ: `/var/www/cesium-app/`（ローカルのみ、リモートなし）
- `.gitignore` で除外: `node_modules/`, `Cesium/`, `.claude/`, `data/`, `scripts/.venv/`
- CesiumJS ライブラリの復元: `npm install && cp -r node_modules/cesium/Build/Cesium ./Cesium`

## Python 環境（uv）

- パッケージ管理: [uv](https://docs.astral.sh/uv/)（`~/.local/bin/uv`）
- プロジェクト: `scripts/`（`pyproject.toml` + `uv.lock`）
- 依存: `netcdf4`, `numpy`, `rasterio`, `scipy`
- 実行: `uv run --project scripts python scripts/<script>.py`

### スクリプト一覧

すべてのスクリプトは NC ファイルの親ディレクトリから `<Site>/<Project>` を自動推定する
（`--site` / `--project` で上書き可能）。

- **`setup_dataset.py`** — データセット準備の1コマンドパイプライン
  - 実行内容: グリッドJSON抽出 → バイナリメッシュ生成 → ncWMS登録 → 設定JSON生成
  - **σ-COG ステップは廃止**（mesh が NC を直接読むため不要）
  - **流速抽出ステップも廃止**（ブラウザが ncWMS から u/v WMS PNG を直接 fetch するため。後述「ROMS σ面表示 / 流速ベクトル表示」参照）
  - 使い方:
    ```bash
    # 基本（全ステップ、site/project は NC 親ディレクトリから推定）
    uv run --project scripts python scripts/setup_dataset.py \
        /large/roms/Yaeyama/Yaeyama3/<file>.nc \
        /fast/terrain/Yaeyama/yaeyama_cog.tif

    # オプション
    #   --site <name>            サイト名（推定の上書き）
    #   --project <name>         プロジェクト名（推定の上書き）
    #   --dataset-id <ID>        データセットID（省略時: NCファイル名のstem）
    #   --ncwms-id <ID>          ncWMS ID（省略時: roms_<nc_stem>）
    #   --label <text>           表示ラベル
    #   --subsample <N>          グリッドJSONサブサンプル（デフォルト: 2)
    #   --resolution <m>         メッシュ解像度（デフォルト: 自動 = ½ ROMS ρ-cell。
    #                            下記「メッシュ解像度プロトコル」参照）
    #   --skip-grid              グリッドJSON生成をスキップ（同一プロジェクト2つ目以降）
    #   --skip-mesh              メッシュ生成をスキップ（同一プロジェクト2つ目以降）
    #   --skip-ncwms             ncWMS登録をスキップ
    ```
  - 出力:
    - `data/<Site>/<Project>/<dataset_id>_config.json` — ブラウザ用データセット設定
    - `data/datasets.json` — データセットインデックス（自動更新、キーは `<Project>_<datasetId>`）
    - 各サブスクリプトの出力（下記）

- **`extract_roms_grid.py`** — ROMS格子データをJSONに抽出
  ```bash
  uv run --project scripts python scripts/extract_roms_grid.py \
      /large/roms/<Site>/<Project>/<file>.nc --subsample 2 \
      --terrain-cog /fast/terrain/<Site>/<terrain_cog>.tif
  ```
  - 出力: `data/<Site>/<Project>/roms_grid.json`（**プロジェクト共通**、同プロジェクト内 NC は同一格子を共有）

- **`generate_sigma_mesh.py`** — NC + bathymetry COG/VRT から **直接** σ層バイナリメッシュ生成
  - `LinearNDInterpolator` で ROMS 曲線格子を bathymetry ピクセル格子に補間し、メッシュ化
  - **σ-COG を介さない**（旧パイプラインから変更）
  - **terrain ソースは `merged_global.vrt` を渡すのが基本**（local COG だけだと外側ドメインで σレイヤーが欠ける）。VRT 内で GEBCO ↔ サイト別高解像度 COG が自動切替
  - メッシュ解像度は **`--resolution` 省略時に自動 = ½ ROMS ρ-cell**（下記プロトコル参照）。COG 読み込みもこの解像度までダウンサンプル（`rasterio` の `out_shape` + `Resampling.average` + VRT オーバービュー）
  - **海岸線バッファ**: 海洋マスクを `binary_dilation` で ~½ ρ-cell ぶん外側に拡張し、ncWMS のセル四角形塗り（底層ドレープ）と footprint を一致させる。`--coast-buffer-m 0` で無効化可
  ```bash
  # 全層生成（推奨）
  uv run --project scripts python scripts/generate_sigma_mesh.py \
      /large/roms/<Site>/<Project>/<file>.nc \
      /fast/terrain/common/merged_global.vrt --all

  # オプション
  #   --layers k0 k1 ...   特定の層のみ
  #   --resolution <m>     メッシュ解像度（デフォルト: 自動 = ½ ROMS ρ-cell）
  #   --coast-buffer-m <m> 海洋マスク外側膨張量（デフォルト: 自動 = ½ ρ-cell、0 で無効）
  #   --offset <m>         地形クランプオフセット（デフォルト: 1.0m）
  ```
  - 出力: `data/<Site>/<Project>/sigma_mesh_k<N>.sigmesh`（**プロジェクト共通**、層あたり数 MB〜十数 MB）
  - バイナリ形式（.sigmesh）:
    - ヘッダ 32バイト: magic(u32)=0x53494D45, version(u32)=1, nVertices(u32), nIndices(u32), lonMin(f64), latMin(f64)
    - 頂点データ: lon(f64), lat(f64), elevation(f32) × nVertices（20バイト/頂点）
    - インデックスデータ: u32 × nIndices（三角形リスト）

- **流速抽出スクリプトは廃止**（旧 `extract_velocity.py` / `.velgrid` ファイル）
  - 流速ベクトルは ncWMS から u/v WMS PNG として直接 fetch し、ブラウザで decode する方式に移行
  - 後述「ROMS σ面表示 / 流速ベクトル表示」を参照

- **`generate_sigma_geotiff.py`** — `[DEPRECATED]` σ層 COG 生成（旧パイプラインの中間ファイル）
  - 現在のパイプラインからは除外されており、`setup_dataset.py` からは呼ばれない
  - QGIS等で σ-surface を可視化したいデバッグ用途のみ残置

## 長時間処理の実行ルール

**mdx I では無操作 10 分程度で SSH セッションが切られる**。フォアグラウンドで走らせている
ジョブは Claude セッションごと巻き込まれて止まる可能性があるため、**長時間処理（数分以上
かかる見込みのコマンド）は必ず `run_in_background: true` で起動する**こと。

- `run_in_background` で起動したプロセスは Claude セッションが切断されても **OS 上で生存し
  続ける**（実証済み: `setup_dataset.py` の 40 分ジョブがセッションドロップ後も完走した）
- 再接続後は `ps -ef | grep <キーワード>` で生存確認、出力ファイル（`/tmp/claude-*/tasks/<id>.output`）
  または成果物（生成された JSON / バイナリ）から進捗を判定する
- 完了監視はメインプロセスの終了を待つ until-loop を `run_in_background` で投げる:
  ```bash
  until ! kill -0 <pid> 2>/dev/null; do sleep 5; done; echo "exited"
  ```
- 対象になる典型処理: `setup_dataset.py`, `generate_sigma_mesh.py`,
  `gdalbuildvrt` / `gdal_translate` の大規模ファイル変換、`docker restart ncwms`（数十秒）
- 数秒で終わる軽い処理（`ls`, `cat`, `ncdump -h`, `docker ps` 等）は通常実行で OK

## コマンド

```bash
# Docker コンテナのログ確認
docker logs -f ncwms          # ncWMS ログ
docker logs -f thredds        # THREDDS ログ
docker logs -f ctod           # CTOD ログ

# Nginx 設定の確認・リロード
sudo nginx -t && sudo systemctl reload nginx

# GeoTIFF → COG 変換（EPSGが4326でない場合は先にgdalwarp）
gdal_translate -of COG -co COMPRESS=DEFLATE input.tif /fast/terrain/<Site>/<file>_cog.tif

# SSL証明書の更新
sudo certbot renew

# ncWMS / THREDDS コンテナ再作成（バインドマウント変更時など）
docker rm -f ncwms thredds
docker run -d --name ncwms --restart unless-stopped -p 8070:8080 \
  -v /large/roms:/data/roms -v /large/ncwms:/data/ncwms \
  -v /large/ncwms_config:/usr/local/tomcat/.ncWMS2 \
  axiom/ncwms:latest
docker run -d --name thredds --restart unless-stopped -p 8080:8080 \
  -v /large/roms:/data/roms \
  unidata/thredds-docker:5.8
```

## CesiumJS コーディング規約

- 画像レイヤは `UrlTemplateImageryProvider`（地理院タイル）または `WebMapServiceImageryProvider`（ncWMS/GeoServer WMS）を使う
- `WebMapServiceImageryProvider` は `new` コンストラクタで生成する（`fromUrl()` は CesiumJS 1.140 に存在しない）
- 地形は `CesiumTerrainProvider.fromUrl("/ctod/tiles/dynamic/?cog=/terrain/...")` で読み込む（cog パラメータは CTOD コンテナ内パス）
- すべての外部データURLは相対パス（`/ncwms/`, `/thredds/`, `/geoserver/`, `/ctod/`, `/data/`, `/terrain/`）で Nginx 経由にする

## UIコントロールパネル

- **構造**: 左上の ☰ ボタン（`#menuToggleBtn`、fixed, top:10px, left:10px）でパネル開閉
- **パネル** (`#controlPanel`): fixed, top:44px, left:10px, width:268px、スクロール可能
- セクション構成: Base Map / Terrain / ROMS Data / Display の4セクション
- **データセット依存コントロール**: `vectorControls`（`ncVariables` に `u` と `v` の両方が含まれるとき表示。Vectors ON/OFF + Spacing + Scale）
- **断面カットボタン**: ☰ の隣の `✂`（`#cutToggleBtn`、left:52px）で鉛直断面カットの ON/OFF。ピッキング中は緑の `✓` ボタン（`#cutFinishBtn`、left:94px）が出現。詳細は「ROMS σ面表示 / 鉛直断面カット」参照
- **UI 文字列は英語**: コントロールパネルラベル・tooltip・操作説明オーバーレイなど画面に出るテキストは全て英語で統一（CLAUDE.md などドキュメントは日本語のまま）

## CSS注意点

- **`<select>` 要素のスタイリング**: `color: white; background: #3a3a3a` を直接指定すると、Linux の GTK ライトテーマ環境でドロップダウンのオプション文字が白背景に白文字で不可視になる。代わりに `color-scheme: dark` を使用することで OS ネイティブのダークモード描画を適用できる
  ```css
  #controlPanel select {
    color-scheme: dark;  /* background/color は指定しない */
  }
  ```

## Nginx 設定時の注意

- 各 location ブロックに `add_header Access-Control-Allow-Origin *;` を必ず付ける
- THREDDS・ncWMS・GeoServer は `proxy_read_timeout 300;` を設定する（大きなデータのリクエストがタイムアウトするため）

## ROMS WMS（ncWMS）

- **THREDDS WMS は ROMS の曲線座標グリッドに非対応**。EDAL ライブラリの `Domain2DMapper.forGrid` で NullPointerException が発生する
- ROMS WMS には ncWMS（`axiom/ncwms:latest`, ポート 8070）を使用する
- **ncWMS 実行時 config**: コンテナ内 `/usr/local/tomcat/.ncWMS2/config.xml`（ホスト `/large/ncwms_config/config.xml` にバインド）
- レイヤー名: `<ncwmsId>/<変数名>` 形式（例: `roms_Y3_20160701/temp`）
- NcML で `ocean_time` の `calendar` 属性を `gregorian` に上書きして使用する
- NcML 内 `location` 属性は **コンテナ内パス**（`/data/roms/...`）を指定する
- THREDDS は OPeNDAP・カタログ用途のみに使用
- WMS パラメータ: `COLORSCALERANGE`, `STYLES`（例: `default-scalar/x-Sst`）, `NUMCOLORBANDS` が必要
- σ層指定: `ELEVATION` パラメータに `s_rho` の実値を指定（例: `ELEVATION=-0.03333`）。インデックス番号ではない

### NcML `<aggregation>` は GetMap で「spi is null」を起こす — 使用禁止

NetCDF-Java/CDM 5.0-beta6 + EDAL 1.4.2 (`axiom/ncwms:latest`) では `<aggregation type="union">`
の NcML を ncWMS で使うと、GetCapabilities や dataset load は通るが **GetMap で必ず**
`Could not read underlying data / Cause: spi is null, perhaps file has been closed` で失敗する。
キャッシュされた `NetcdfDataset` がファイルハンドルを閉じた後に再アクセスする際の bug。
`updateInterval` を変えても直らない。

**回避策**: 単一ファイル NcML（aggregation 不使用）にする。追加変数が必要な場合は
`<variable name="X" shape="..." type="..."><values>...</values></variable>` で **inline values**
として埋め込む（NcML が数 MB になっても問題なし）。

### Cartesian ROMS NC (spherical=0) の特殊扱い — Shiraho_reef

ほとんどの ROMS は `spherical=1` で `lon_rho`/`lat_rho` を NC にネイティブに持つが、
**Shiraho_reef は `spherical=0`** で `x_rho`/`y_rho`（投影メートル単位、grid file の CRS は
EPSG:32651 = UTM zone 51N）しか持たない。ncWMS/EDAL の staggered grid factory は 2D の
`lon_*`/`lat_*` 軸を要求するため、そのままでは load 不能。

対策スクリプト: **`scripts/regenerate_cartesian_ncml.py`** が以下を含む NcML を生成:
1. 元 NC は手付かず、location 属性で単一ファイル参照（aggregation を使わない）
2. `<remove>` で `x_*`/`y_*` 8 変数を削除
3. grid NC から読んだ `lon_rho/lat_rho/lon_u/lat_u/lon_v/lat_v/lon_psi/lat_psi` を
   `<variable><values>` で inline 埋め込み（NcML 約 1.2 MB）
4. `<variable name="spherical">` で値を 1 に override（CDM の ROMSConvention が見る）
5. `<variable name="ocean_time">` の calendar を `gregorian` に上書き
   （元 NC の `gregorian_proleptic` だと EDAL が `cannot be handled` で拒否）
6. **`f`, `h`, `pm`, `pn`, `mask_rho`, `mask_u`, `mask_v`, `mask_psi`, `grid` (node/face/edge1/edge2_coordinates),
   全データ変数の `coordinates` 属性に残った `x_*`/`y_*` 参照を `lon_*`/`lat_*` に書き換え**（**最重要**）
   — 削除した変数への stale ref を残すと、EDAL の `CdmGridDatasetFactory.getGridFromCoords`
   が null axisType の軸を sort しようとして NPE で必ず落ちる。Shiraho では his で 161 個の
   coordinates 属性に置換が必要。
7. **sed_eco_layer 次元と sediment_* 変数の修正**（下記「ROMS qck NC の sediment 問題」と共通）

実行例（his + qck + dia 3 つ同時生成）:
```bash
uv run --project scripts python scripts/regenerate_cartesian_ncml.py \
    /large/roms/Yaeyama/Shiraho_reef/SR_veg_eco2_sg_his_20231007_v5.nc \
    /large/roms/Yaeyama/Shiraho_reef/SR_veg_eco2_sg_qck_20231007_v5.nc \
    /large/roms/Yaeyama/Shiraho_reef/SR_veg_eco2_sg_dia_20231007_v5.nc \
    --grid-nc /large/roms/Yaeyama/Shiraho_reef/shiraho_roms_grd_JCOPET_v18.1.nc
```
生成された NcML を `add-dataset.sh` 経由で（または config.xml 直接編集で）ncWMS に登録。
スクリプトは config.xml は触らず NcML だけ吐く（再生成しやすいため）。

### ROMS qck NC の sediment_* 問題（Cartesian/spherical 共通）

ROMS qck output の `sediment_*` 変数は dim が `(ocean_time, sed_eco_layer, eta_rho, xi_rho)`
だが、変数属性に `location: edge2` という誤ラベルを持っている。EDAL は size マッチングで
grid type を判定するため `edge2 = (eta_v, xi_v)` で照合に行き、`eta_v=eta_rho-1` のサイズ差
で size mismatch エラーになり、変数が `not be made available` で reject される。

**修正方法**（Shizugawa3 用 NcML を参照）:
- `<variable name="sed_eco_layer"><attribute name="axis" value="Z"/><attribute name="_CoordinateAxisType" value="Height"/></variable>`
  で sed_eco_layer を vertical axis として宣言
- 各 `sediment_*` 変数に `<attribute name="location" value="face"/>` と
  `<attribute name="coordinates" value="lon_rho lat_rho sed_eco_layer ocean_time"/>` を override

これらは spherical=0 でも spherical=1 でも qck NC 全般に必要。
`scripts/regenerate_cartesian_ncml.py` の `collect_sediment_overrides()` が自動生成する。
**spherical=1 の qck (Shizugawa3 等)** は trivial NcML の代わりに手書きで対応してきたが、
将来このスクリプトを spherical 問わず使えるよう拡張するのが望ましい。

### dia/qck データセットの ncWMS 登録（companion 設計）

ROMS run は通常 his（履歴）+ qck（高頻度サブセット）+ dia（診断）の 3 NC に分かれて出力される。
それぞれを別の ncWMS データセットとして登録し、ブラウザ側で `ncSources` map を使って
「どの ncwmsId のどのレイヤーが各変数を持つか」を解決する設計（[`setup_dataset.py`](scripts/setup_dataset.py)
の `--companions` オプションが対応）。

- qck source には `sedLayerElev` (cm) を設定。SedimentBed カテゴリの変数（`location: face`,
  vertical axis = `sed_eco_layer`）はブラウザの terrainOnly モードで描画され、`ELEVATION`
  パラメータをこの値に pin して **海底地形にドレープ**として表示される（σ層 mesh は描画しない）。
  ROMS の sed_eco_layer は表層 = 0.1 cm なのでデフォルト `--sed-layer-elev 0.1`。

config json の `ncSources.<kind>` には `ncFile / ncwmsId / timeRange / nTimes / variables` と、
qck の場合は `sedLayerElev` も入る。`variableSource` map で変数 → kind を引き、ブラウザは
正しい ncwmsId の WMS レイヤーを構成する。3 NC のうち lat/lon を NC に持たない（Cartesian）
場合は **3 つすべて** `regenerate_cartesian_ncml.py` で NcML を作る必要がある（dia/qck も独立して
EDAL がロードするため）。

## ROMS NetCDF データ

### 共通仕様

- CF-Conventions 準拠。変数名は ROMS の出力設定に依存する
- σ座標系: 鉛直方向は `s_rho` 次元で表現（k=1=底層, k=N=表層）
- 水平格子: 曲線座標グリッド（curvilinear grid, 2D の `lon_rho`/`lat_rho`）
- σ深度計算（Vtransform=2）: `z = ζ + (ζ + h) × (hc×s + h×Cs) / (hc + h)`
  - パラメータ: `Vtransform`, `Vstretching`, `theta_s`, `theta_b`, `hc`, `s_rho`, `Cs_r` — すべて NC ファイル内に格納
- **NetCDF ファイルを ncatted 等で直接編集しない**（同一ファイルへの上書きで破損した実績あり）
- メタデータ修正は NcML（`.ncml`）経由で行う

### 命名規則（サイト/プロジェクト別）

**基本原則**: プロジェクトフォルダ（例: `Yaeyama/Yaeyama3/`）内の NC ファイルは
**同一の格子と σ 層構造を共有する**前提で運用する。共通化できるものはプロジェクト
共通名（`sigma_mesh_k<N>.sigmesh`, `roms_grid.json`）、NC ファイル毎の固有 config は
dataset_id プレフィックス付き名（`<dataset_id>_config.json`）とする。

- **NC ファイル配置先**: `/large/roms/<Site>/<Project>/<file>.nc`
  - サイト: `Yaeyama` / `ShizugawaBay` / `TokyoBay` / `Palau` / `Kikai` / `FORP_Kuroshio`
  - プロジェクト: `Yaeyama1〜3` + `Shiraho_reef`, `Shizugawa1〜3`, `TokyoBay1〜3`, `Palau1〜2`, ...
- **データセットID**（NCファイル単位）: NCファイル名の stem（例: `Y3_his_20160701`）
- **ncWMS ID**: `roms_<dataset_id>`（例: `roms_Y3_20160701`）
- **datasets.json のキー**: `<Project>_<dataset_id>`（例: `Yaeyama3_Y3_his_20160701`）— プロジェクト横断で一意
- **広域共通地形**: `/fast/terrain/common/gebco_2025_*_cog.tif`（Float32 COG、全サイト参照のベース）
- **統合 VRT**: `/fast/terrain/common/merged_global.vrt` — GEBCO + 各サイト COG をマージ（CTOD はこれを配信）
  - CTOD URL: `/terrain/common/merged_global.vrt`
  - データセット config の `terrainCogUrl` は全て **このマージ VRT** を指す
- **サイトベースマップ COG**（サイト共通）: `/fast/terrain/<Site>/<site>_cog.tif`（例: `Yaeyama/yaeyama_cog.tif`, `ShizugawaBay/shizugawabay_cog.tif`, `Palau/palau_cog.tif`, `Kikai/kikai_cog.tif`）
  - 全て **Float32, EPSG:4326, NoData=-3.4028235e+38** で統一（マージ VRT の整合性のため）
  - 新サイト追加時は CRS/型を統一して `merged_global.vrt` を再生成すること:
    ```bash
    # 重要: 必ず container 絶対パス /terrain/... で渡す（CTOD は VRT XML を文字列で
    # rasterio に渡すため、相対パスは CWD=/app/ で解決され失敗する）
    cd /fast/terrain/common && gdalbuildvrt -overwrite -resolution highest \
      merged_global.vrt \
      /terrain/common/gebco_2025_n90.0_s0.0_w90.0_e180.0_cog.tif \
      /terrain/Yaeyama/yaeyama_cog.tif \
      /terrain/ShizugawaBay/shizugawabay_cog.tif \
      /terrain/Palau/palau_cog.tif \
      /terrain/Kikai/kikai_cog.tif
    # OverviewList を追加（仮想 overview で CTOD の safe_level チェックを満たす）
    sed -i 's|</VRTRasterBand>|</VRTRasterBand>\n  <OverviewList resampling="average">2 4 8 16 32 64 128 256 512 1024</OverviewList>|' merged_global.vrt
    # キャッシュをクリアして CTOD 再起動
    sudo rm -rf /fast/ctod_cache/2f7465727261696e2f636f6d6d6f6e2f6d65726765645f676c6f62616c2e767274 \
      /fast/ctod_cache/factory_cache.db
    docker restart ctod
    ```
  - **ホスト側 symlink**: `/terrain → /fast/terrain` を作成しておくことで、VRT の絶対コンテナパスがホスト上でも解決可能になる:
    ```bash
    sudo ln -s /fast/terrain /terrain
    ```

### 変数表示の仕組み（registry 駆動）

ブラウザの Variable セレクタに何を出すかは、**`data/variable_registry.json` というレジストリ**と
**各データセット config の `ncVariables` リスト**を実行時に join して決まる。

- `ncVariables`: NC ファイルに実在する time-varying 空間変数の生のリスト（`setup_dataset.py` が自動生成）
- `variable_registry.json`: 表示用メタデータ（label / category / min / max / palette など）の一元辞書

**新変数を追加する手順**: `variable_registry.json` を編集してエントリを足し、ブラウザをリロード
するだけ。Python 修正も config 再生成も不要。

`data/variable_registry.json` の構造:

```json
{
  "categoryOrder": ["Physical", "Oxygen/Carbon", "Nutrients", "DOM", ...],
  "variables": {
    "temp":   { "label": "Temperature (°C)", "category": "Physical",
                "min": 15, "max": 30, "palette": "x-Sst" },
    "zeta":   { "label": "SSH (m)", "category": "Physical",
                "min": -0.5, "max": 1.5, "palette": "div-RdBu", "is2d": true },
    "_velocity": {
      "label": "Current Speed (m/s)", "category": "Physical",
      "min": 0, "max": 1.5, "palette": "seq-Heat",
      "wmsSuffix": "u:face:v:face-mag",
      "requires": ["u", "v"]
    },
    "DO":     { "label": "Dissolved O₂ (μmol/L)", "category": "Oxygen/Carbon",
                "min": 0, "max": 350, "palette": "psu-viridis" }
  }
}
```

書き方ルール:
- **キー = NC 変数名**: ncWMS レイヤー名は `<ncwmsId>/<key>` で組み立てられる
- **アンダースコア接頭辞は仮想キー**: `_velocity` のような合成変数。`wmsSuffix` で実際のレイヤー名、
  `requires` で必須 NC 変数（u, v 等）を列挙
- **要件チェック**: `requires` の全変数が dataset の `ncVariables` に揃っている場合のみ表示候補に
  入る。未指定なら `requires: [key]` がデフォルト

### データセット config JSON スキーマ

`data/<Site>/<Project>/<dataset_id>_config.json`:

```json
{
  "label": "ROMS Yaeyama3 — Y3_his_20160701",
  "datasetId": "Y3_his_20160701",
  "ncwmsId": "roms_Y3_20160701",
  "ncFile": "Y3_his_20160701.nc",
  "site": "Yaeyama",
  "project": "Yaeyama3",
  "terrainCogUrl": "/terrain/common/merged_global.vrt",
  "gridJson": "Yaeyama/Yaeyama3/roms_grid.json",
  "sigmaMeshUrlTemplate": "/data/Yaeyama/Yaeyama3/sigma_mesh_k{k}.sigmesh",
  "timeRange": ["2016-07-01T00:00:00Z", "2016-07-23T15:00:00Z"],
  "nTimes": 544,
  "nLayers": 15,
  "bbox": { "lonMin": ..., "lonMax": ..., "latMin": ..., "latMax": ... },
  "camera": { "lon": ..., "lat": ..., "height": 200000 },
  "ncVariables": ["temp", "salt", "zeta", "u", "v", "DO", "NO3_01", ...]
}
```

流速ベクトル表示の可否は `ncVariables` に `u` と `v` の両方が含まれるかで実行時判定する（旧 `hasVelocity` フラグは廃止）。

`ncVariables` は NC に実在する変数の生リスト。表示メタデータは持たず、レジストリと join される。

`data/datasets.json`:
```json
{
  "datasets": {
    "Yaeyama3_Y3_his_20160701": {
      "label": "ROMS Yaeyama3 — Y3_his_20160701",
      "site": "Yaeyama",
      "project": "Yaeyama3",
      "config": "Yaeyama/Yaeyama3/Y3_his_20160701_config.json"
    }
  },
  "default": "Yaeyama3_Y3_his_20160701"
}
```

### データセット一覧

| データセットID | サイト/プロジェクト | NC ファイル | ncWMS ID | NcML |
|---|---|---|---|---|
| `Y3_his_20160701` | Yaeyama/Yaeyama3 | `Y3_his_20160701.nc` (23 GB) | `roms_Y3_20160701` | `/large/ncwms/Y3_his_20160701.ncml` |
| `Yaeyama3_his_20160501` | Yaeyama/Yaeyama3 | `Yaeyama3_his_20160501.nc` (154 GB) | `roms_Yaeyama3_his_20160501` | `/large/ncwms/Yaeyama3_his_20160501.ncml` |
| `P1_his_20230102` | Palau/Palau1 | `P1_his_20230102.nc` (371 GB) | `roms_P1_his_20230102` | `/large/ncwms/P1_his_20230102.ncml` |
| `P2_his_20230309` | Palau/Palau2 | `P2_his_20230309.nc` (86 GB) | `roms_P2_his_20230309` | `/large/ncwms/P2_his_20230309.ncml` |

> **データセット追加手順（1コマンド）:**
> 1. NC ファイルを `/large/roms/<Site>/<Project>/` に配置
> 2. パイプライン実行:
>    ```bash
>    uv run --project scripts python scripts/setup_dataset.py \
>        /large/roms/<Site>/<Project>/<file>.nc \
>        /fast/terrain/<Site>/<site>_cog.tif
>    ```
> 3. **同じプロジェクト内 2 つ目以降の NC ファイル**は格子・mesh が共通なので skip 推奨:
>    ```bash
>    uv run --project scripts python scripts/setup_dataset.py \
>        /large/roms/<Site>/<Project>/<file>.nc \
>        /fast/terrain/<Site>/<site>_cog.tif \
>        --skip-grid --skip-mesh
>    ```
> 4. `data/datasets.json` が自動更新され、ブラウザのデータセットセレクタに新データセットが表示される
> 5. **index.html の編集は不要**

> **手動で個別実行する場合:**
> - ncWMS のみ登録: `/large/ncwms/add-dataset.sh <Site>/<Project>/<file>.nc [ncwmsId] [タイトル]`
> - 個別ステップは各スクリプトの `--help` を参照

## ROMS σ面表示

### バイナリメッシュ Primitive 方式

σ座標面を事前生成したバイナリメッシュ（`.sigmesh`）から CesiumJS `Primitive` API で
独立したポリゴンレイヤーとして描画する。**CTOD terrain は bathymetry のみで、σ面表示は
terrain を切り替えない**（旧仕様の σ-COG terrain は廃止）。

#### データ生成パイプライン

1. `generate_sigma_mesh.py` が NC + bathymetry（**`merged_global.vrt`**）から **直接** バイナリメッシュを生成
   - メッシュ解像度は **½ ROMS ρ-cell** で自動算出（下記プロトコル）
   - terrain COG は `out_shape` + `Resampling.average` でメッシュ解像度までダウンサンプル読み込み（VRT のオーバービュー使用）。これにより外側ドメイン（Yaeyama1 など）の数百〜数千 km 範囲でも数百 MB に収まる
   - 海洋マスクを `binary_dilation` で ~½ ρ-cell 外側に拡張（底層ドレープと footprint を合わせるため。詳細は下記「海岸線バッファ」）
2. メッシュは `data/<Site>/<Project>/sigma_mesh_k<N>.sigmesh` に配置（プロジェクト共通）

#### メッシュ解像度プロトコル

**基本ルール: メッシュ解像度 = ½ ROMS ρ-cell**（domain 中央で `lon_rho`/`lat_rho` の隣接間距離から算出）。

- 2 mesh sample / ρ-cell = ROMS 場に対する Nyquist 相当の刻み。これ以上細かくしても ROMS の情報量を超えない
- terrain COG も同じ解像度までダウンサンプル → メッシュ位置とピクセル中心が ~1:1 で揃い、補間アーチファクトと不要なデータ量を同時に抑える
- フロアは設けない（Shiraho_reef なら 25m、Shizugawa3 なら 30m まで自動で細かくなる）
- 既定値は **`--resolution` 省略**で発動。意図的に固定したい場合のみ `--resolution <m>` を渡す
- **新規データセット（プロジェクト）追加時もこのプロトコルに従う**こと（`setup_dataset.py` も同様に自動）

参考: 既存プロジェクトのメッシュ解像度

| プロジェクト | ρ-cell | メッシュ解像度 |
|---|---|---|
| Yaeyama1 / Shizugawa1 / Palau1 | ~1500 m | 750 m |
| Yaeyama2 / Shizugawa2 / Palau2 | ~300 m | 150 m |
| Yaeyama3 | ~100 m | 50 m |
| Shizugawa3 | ~60 m | 30 m |
| Shiraho_reef | ~50 m | 25 m |

#### 海岸線バッファ

ncWMS の WMS 底層ドレープは ρ-cell を四角形（隣接 4 ρ-points の重心が四隅）として塗るため、`mask=0.5` 等値線より ~½ ρ-cell 外側まで広がる。σ-mesh 側でこれを合わせないと、海岸沿いで底層ドレープが σレイヤーの外にはみ出して見える。

- `compute_grid` 内で `mask>0.5` 海洋画素を `scipy.ndimage.binary_dilation`（3×3 structure）で **~½ ρ-cell ぶん拡張**してから quad gating
- 拡張領域の `h` は `NearestNDInterpolator`（ocean ρ-cell のみ）で補完済みなので、`z_sigma = max(z_sigma, terrain+offset)` のクランプで自然に海岸へ寄せられる
- 既定値は自動（½ ρ-cell）。`--coast-buffer-m <m>` で個別指定、`--coast-buffer-m 0` で無効化

#### ブラウザ側の仕組み（`index.html`）

1. **データセット切替時**: `datasetConfig.terrainCogUrl`（全データセット共通の `merged_global.vrt`）を `setBathymetryTerrain()` に渡す。URL が前回と同じ場合は no-op（`currentTerrainUrl` でガード）
2. **σ層選択時**: `datasetConfig.sigmaMeshUrlTemplate.replace("{k}", layerIndex)` から `.sigmesh` を fetch、`Primitive` を構築して `viewer.scene.primitives` に追加
3. **スカラーテクスチャ**: ncWMS から `GetMap` した PNG を Primitive のテクスチャとして適用
   - `ELEVATION` パラメータは `romsGrid.s_rho[k]` の実値（インデックスではない）
4. **時刻変更時**: `viewer.clock.onTick` で `lastTimeString` と比較、300ms デバウンス後にテクスチャ再生成
5. **2D 変数（zeta 等）**: `cfg.is2d` の場合 `sigmaLayerSelect` を `disabled`、`ELEVATION` パラメータを送信しない
6. **All Layers モード**: 全層のメッシュを同時表示
7. **Bottom-layer drape**: バリ erased エリアを埋めるため、`updateBaseLayer()` で底層 WMS イメージを terrain にドレープ

#### 流速ベクトル表示

ncWMS から u/v を WMS PNG として **オンデマンド fetch** し、ブラウザで decode して Canvas
矢印を合成する方式。`.velgrid` 事前抽出は廃止（データセット追加時の前処理ボトルネックを解消、
かつ動的な wet/dry も per-timestep で正しく反映されるようになった）。

- **取得 PNG**: 時刻 t / σ層 k ごとに 3 枚を並列 fetch（`STYLES=raster/seq-Greys`,
  `COLORSCALERANGE=-2,2`, `NUMCOLORBANDS=250`）
  - `<ncwmsId>/u` — grayscale R が u を encode（`ELEVATION=s_rho[k]`）
  - `<ncwmsId>/v` — 同上で v
  - `<ncwmsId>/wetdry_mask_rho` — `STYLES=default-categorical`、wet=`(0,0,143)`, dry=`(140,0,0)`,
    alpha=0=ドメイン外
- **R → m/s LUT**: `seq-Greys` パレットは **sRGB ガンマで非線形** なので、データセット読み込み時に
  1×256 px の `GetLegendGraphic` を取って 256 エントリの Float32 LUT を 1 回だけ構築
- **キャッシュ**: snapshot は `(layer, timeString)` をキーに LRU で 60 件保持（~135 MB worst case）。
  時刻スクラブ・σ層切替で再 fetch、データセット切替でクリア
- **矢印描画**: `drawVectorsOnCanvas()` が `romsGrid` の ρ-point を Spacing 倍で走査し、各点の
  lon/lat を snapshot の WMS pixel に map、`mask_rho`（静的）と `wetdry_mask_rho`（動的）の両方
  wet な点のみ u/v を読んで矢印を描画。スカラー WMS PNG の Canvas に上書きして Primitive
  テクスチャに焼き込む流れは旧実装と同じ
- **UI**: Vectors（ON/OFF）+ Spacing + Scale
- **検証精度**: GetFeatureInfo との突き合わせで decode 誤差 ±0.02 m/s（4 m/s レンジを 8bit
  量子化した分）。矢印表示には十分

### 設計上の注意

- **σ面は浮遊ジオメトリ**: terrain（bathymetry）とは別の Primitive として浮遊表示。terrain は切り替わらない
- **メッシュサイズ**: ½ ρ-cell 解像度で 1 プロジェクトあたり 数 MB〜250 MB（ρ-cell サイズと領域広さ依存。Shiraho_reef ~4 MB / Yaeyama3 ~250 MB）
- **2D 変数**: σ層に依存しないので `s_rho[k]` の `ELEVATION` を送信しない
- **Terrain Exaggeration**: `viewer.scene.verticalExaggeration` で bathymetry の誇張は効くが、σ面 Primitive 側は別途 `currentExaggeration` を適用して再構築する
- **OIT は Viewer 構築時に無効化（`orderIndependentTranslucency: false`）**: Layer All + Opacity<1 で OIT の weighted-average 合成だと「上層が支配的・下層が (1-α) 分だけ透ける」自然な積層表示にならないため。OIT を切ると Cesium が translucent コマンドをカメラ距離で奥→手前にソートして標準 α blend で描画するので、σ-mesh が k=0→k=14 の順に重なる。`Scene.orderIndependentTranslucency` は **readonly getter** なので Viewer 構築後の代入は無視される — 必ず構築時オプションで渡すこと。OIT を再有効化すると Layer All の見た目が壊れる
- **σ-Primitive は常に translucent パスで描画**: 上記 OIT 無効化を前提に、`Material.translucent` / `Appearance.translucent` を常に `true` に固定。opacity=1 でも back-to-front の α=1 blend で「topmost σ-mesh wins」となり opaque パスと視覚的に等価。opacity 変更時は uniform 更新のみで primitive 再構築は不要
- **σ-mesh の描画順は boundingVolume proxy で固定**: Cesium の translucent ソートは `BoundingSphere.distanceSquaredTo` を使うが、σ-mesh の境界球は水平半径数 km と巨大で全層ほぼ同心配置のため、カメラが内側に入ると一斉に距離 0 を返し、安定ソートでも「内側組がまとめて最前面扱い」になって前面 σ-layer が下層に隠れる現象（複雑地形で顕著）が出る。対策として `viewer.scene.postUpdate` で各 σ-Primitive の **`primitive._boundingSphereWC[i]` 配列要素を proxy sphere に置き換える**。proxy は real BV の center/radius をスナップショットで保持しつつ `distanceSquaredTo` だけを per-instance に override して layer 順位ぶん合成した値を返す。`computePlaneDistances` は別途保持した real BV にdelegateするため frustum bin 割り当ては実ジオメトリで正しく計算される（差し替え先を間違えると σ-mesh が wrong near/far で far-plane クリップされ地形が前面に出る）。`command.boundingVolume` を直接書き換えても `Primitive.update()` が render パス中で毎フレーム `colorCommand.boundingVolume = _boundingSphereWC[i]` を実行して上書きするため無効。`_boundingSphereWC` 自体は σ-mesh のような identity modelMatrix の Primitive では `_updateBoundingVolumes` の modelMatrix-changed ガード（`Primitive.js:1953`）で初回以降再計算されないので proxy が生き残る。`primitive.cull = false` も同じく `Primitive.update` 経由で毎フレーム colorCommand.cull に反映される。順位の符号は `dot(camera.directionWC, ellipsoidNormal) < 0`（見下ろし）で `k=0` を最遠、見上げで反転。`_boundingSphereWC` / `_colorCommands` は Cesium internal なので、Cesium アップグレード時は要再検証

### 鉛直断面カット（polyline-shaped half-space clip）

σ-mesh を **任意の折れ線に沿った鉛直「壁」で半空間クリップ**して断面を観察する機能。地形・bottom-layer drape はクリップ対象外（カット下の海底地形は見えたまま）。

**UI フロー**: ☰ 隣の `✂` ボタンで picking mode → カーソル crosshair + 説明文表示 + 緑の `✓` Finish ボタン出現 → 左クリックで点を順次追加（マーカー + プレビュー折れ線が表示）→ **右クリック / Enter / `✓` の 3 経路いずれかで finalize**（クロスプラットフォーム対応: 右クリックはタッチ不可、Enter はキーボード必要、`✓` は全環境）。点数 0〜1 で finalize すると silent cancel、Escape または `✂` 再押下で cancel。完了後は赤い polyline だけが残る。Dataset 切替で自動リセット（`switchDataset` 冒頭で `clearCut()`）。最大 16 セグメント = 17 点（`MAX_CUT_SEGMENTS`）。

**実装方式**: Cesium の `Cesium3DTileset.clippingPlanes` が使えない（σ-mesh は素の `Primitive`）ため、**Material fabric の `source` 内で world-space discard** する。各セグメントは鉛直平面を 1 枚定義し、**各 fragment の最寄りセグメント (Voronoi 領域) の half-space で discard 判定**する → 折れ線に沿った曲がる壁になる。

- fabric uniforms: `clipEnabled` (float 0/1), `clipSegCount` (float, アクティブセグメント数), およびセグメントごとに 3 つの vec3 (`clipSegN_A`, `clipSegN_B`, `clipSegN_N`)。i ∈ [0, MAX_CUT_SEGMENTS=16)
- shader: `czm_inverseView * vec4(-materialInput.positionToEyeEC, 1.0)` から world position を再構成。各セグメントについて perpendicular foot を求めて最小距離のものを Voronoi 勝者とし、勝者の `dot(P - midpoint, N) > 0` で `material.alpha = 0` → 既存の `if (material.alpha < 0.01) discard;` が depth write も止める。`if (clipSegCount > i + 0.5)` の if-ladder で未使用スロットを skip
- fabric `type` は **`RomsSigmaOverlayPolyV2`**（旧 `RomsSigmaOverlay` → `RomsSigmaOverlayClip` → 改名。下記 mat3 罠で V2 にバンプ）

**セグメント構築** (`buildSegmentsFromPolyline`):
1. クリック N 点を sea-level 投影（`height = 0`）→ N-1 セグメント
2. 各セグメントについて midpoint, ellipsoid normal `up`, edge `B - A`、`n = normalize(up × edge)`（鉛直平面）
3. **discard 側の決定は始点→終点の chord に対して 1 回だけ算出**:
   - `cameraSide = dot(cameraPos - mid, chord_normal)`、`angSin = |cameraSide| / |camRel|`
   - `angSin > 0.1`（~5.7°以上）: カメラ側を discard
   - それ以下（plan view 等）: `dot(chord_normal, camera.rightWC)` の符号で「画面左側」を discard
4. 各セグメント法線を chord の discard 方向に sign 揃え（全セグメントが同じ側を discard）— C 字や急な折れ線では直感に反する側になり得る
5. 結果は ECEF で固定 → カメラを回しても断面の向きは変わらない

**State 永続化**: `cutState = { segments: [{a, b, n}, ...], lineEntity }` をモジュール変数で保持。`createSigmaPrimitive` 内で `buildClipSegUniforms()` を呼んで uniform に焼き込むため、変数切替・σ層切替・All Layers モード・時刻スクラブを跨いでカットが維持される。既存 Primitive への切替反映は `applyCutToAllPrimitives()` が uniform 値だけ書き換え（Primitive 再構築不要）。

**カット線エンティティ**: picking 中は薄赤 (α=0.7) の `cutPreviewLineEntity`、適用後は赤 (α=0.9) の `cutState.lineEntity`。どちらも `arcType: NONE` で測地線曲線化を防止。マーカー (赤点) は picking 中だけ表示、finalize 時に除去。

### Cesium Material 罠: mat3 uniform は cache 再構築で壊れる

最初実装時、各セグメントを `mat3` (column-major length-9 array) 1 個で渡したが、**1 回目の Primitive 構築は通るのに 2 回目以降で σ-mesh が描画されなくなる**現象が出た（exaggeration 変更・層切替・任意の Primitive 再構築のたびに発生）。

原因は Cesium `Material` の cache 機構:
- 同じ fabric `type` を 2 回目以降に構築するとキャッシュ済みテンプレートと `combine(newTemplate, cachedTemplate, deep=true)` でマージされる (`Material.js` 720 行付近)
- **`combine` deep は `for (property in array)` でインデックスを enumerate し、結果を `{}` リテラルに格納する** → length-9 Array が `{0: ..., 1: ..., ..., 8: ...}` の plain object に潰される
- 結果 `Array.isArray(uniformValue) === false` になり `getUniformType` が `mat3` を返せず、uniform binding が silent failure。shader は壊れたまま compile される

**回避策**: mat3 を使わず、`{x, y, z}` named-property オブジェクト (= vec3) で渡す。`combine` deep は `{x, y, z}` を `{x, y, z}` のまま保つ（インデックスでなく named property だから）ので `getUniformType` が numAttributes=3 → vec3 として正しく認識する。各セグメントを `clipSegN_A / clipSegN_B / clipSegN_N` の 3 つの vec3 に分割する設計に変更（合計 16 × 3 = 48 vec3 uniforms。WebGL2 の minimum max-fragment-uniforms 224 vec4 components に十分収まる）。

**教訓**: Cesium fabric uniform で `Array` 系（mat3/mat4）は cache 経由で壊れる。安全なのは `float / bool / 2〜4 named-property の vec / Cartesian3 / Color`。同じ `type` で Material を作り直すパスがあるなら **mat 系は使わない**。Cesium 側を pin する場合は `Material.js` の `combine(_template, cachedTemplate, true)` を頭に置く。

## 参照ドキュメント

- 構築手順書: @docs/cesiumjs-mdx-implementation-guide.md
- 国土地理院タイル仕様: https://maps.gsi.go.jp/development/siyou.html
- CTOD: https://github.com/sogelink-research/ctod
- CesiumJS Offline Guide: https://github.com/CesiumGS/cesium/blob/main/Documentation/OfflineGuide/README.md
