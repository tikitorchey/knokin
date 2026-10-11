# 撮影システム仕様(Blender アドオン + ジョブ状態)

現在の実装の記述。経緯は [research-notes.md](research-notes.md)、決定は [decisions.md](decisions.md)。manifest / 座標 / グラフは [spec.md](spec.md)。

| 場所 | 役割 |
| --- | --- |
| `python/addon/run_capture.py` | ヘッドレス撮影の入口(コマンドライン) |
| `python/addon/knokin_blender/scene.py` | Blender 層(`bpy` に依存する唯一のモジュール)。カメラ・レンダー設定の適用、カメラ配置、レンダー |
| `python/knokin_core/jobs.py` | 撮影タスクの列挙(`bpy` 非依存) |
| `python/knokin_core/jobstate.py` | 作業ディレクトリ、JSONL ログ、原子書き込み、再開(`bpy` 非依存) |
| `python/tools/make_test_scene.py` ほか | テストシーン、縮小 manifest、座標確認、ベンチ(§7) |

## 1. 入力と出力

- 入力: `manifest.json`(グラフ + カメラ + 画像条件)と、撮影する `.blend`(被写体・ライト・ワールドを含む)。
- 出力: 作業ディレクトリ(`spec.md` §7)
  - `manifest.json`(撮影開始時の写し)、`capture.jsonl`、`render_meta.json`
  - `masters/n/{node}.exr`、`masters/e/{edge}/{i:04d}.exr`
- **ライティングはワールド固定**(カメラに追従しない)。カメラ条件は作品ごとに固定で、全フレーム共通。

## 2. 実行方法

```
# Blender 本体
blender -b scene.blend -P python/addon/run_capture.py -- --manifest manifest.json --workdir out/ [options]
# bpy モジュール(pip install bpy==5.2.2)。--blend が要る
python python/addon/run_capture.py -- --blend scene.blend --manifest manifest.json --workdir out/ [options]
```

| オプション | 既定 | 内容 |
| --- | --- | --- |
| `--test-shoot N` | — | 全タスクから均等に N 枚だけ撮る(`sample_jobs`。決定的) |
| `--limit N` | — | この実行で N 枚撮ったら止める |
| `--verify` | off | 既存マスターの SHA-256 も照合してから飛ばす |
| `--samples` | 128 | Cycles のサンプル数 |
| `--seed` / `--seed-mode` | 0 / `fixed` | `fixed`: 全フレーム同一シード。`per-frame`: `seed + タスク番号`(DD12, DD38) |
| `--no-denoise` | デノイズ ON | デノイザーは OpenImageDenoise |
| `--device` | `CPU` | `GPU` は §4 |
| `--no-persistent-data` | persistent ON | `render.use_persistent_data` |
| `--blend` | — | `bpy` モジュールで実行するときに開く `.blend` |

**同じコマンドを再実行すれば再開**になる(§5)。manifest が検証(`validate_graph`)に通らなければ撮影を始めない。

## 3. Blender 層(`scene.py`)

### `apply_manifest(scene, manifest, settings)`

| 設定 | 値 |
| --- | --- |
| カメラ | `PERSP`、`lens`=`camera.focalMm`、`sensor_width`=`camera.sensorWidthMm`、`sensor_fit=HORIZONTAL`、`clip_end = max(100, distance×10)`。シーンにカメラが無ければ `knokin_cam` を作る |
| 解像度 | `image.width × image.height`、100% |
| エンジン | Cycles |
| 背景 | `film_transparent = True`(背景は透明、D03)。影キャッチャーは使わない(DD36) |
| 出力 | OpenEXR、RGBA、**16bit half**、ZIP(可逆)。`use_file_extension=False`(一時名 `*.part.exr` を厳密に書くため、DD14) |
| サンプル・デノイズ・シード | `samples` / `use_denoising` / `use_animated_seed=False` / `seed` |

EXR は**シーン線形・アルファ乗算済み(associated)**で出る。Blender のビュー変換(Standard / AgX など)は EXR の中身に影響しない。パッカーが色変換を自分で行う(`system-packer.md` §3)ので、**Blender 上のプレビューとパック後の見た目は一致しない場合がある**(AgX などでプレビューした場合)。

### `place_camera(scene, manifest, θ, φ)`

位置 = `pivot + distance × direction(θ, φ)`、**pivot を向く**、ロール 0(上は +Z)。座標規約は `spec.md` §2。実描画で向きを目視確認済み(`measurements/coord-check.png`、DD40)。

### `render_to(scene, path)` / `render_metadata(...)`

`render.filepath` に指定して `bpy.ops.render.render(write_still=True)`。`render_metadata` は §5 の `render_meta.json` の中身(Blender バージョン、エンジン、`RenderSettings`、サンプル数、デノイザー、シード、`.blend` の SHA-256)を返す。

## 4. デバイス(CPU / GPU)

`--device GPU` は `enable_gpu()` が Cycles の環境設定で、`OPTIX → CUDA → HIP → ONEAPI → METAL` の順に GPU があるバックエンドを探し、見つかった GPU だけを有効にする。**GPU が無ければ `DeviceError` で止まる**(CPU に黙って落ちない、DD37)。有効にしたデバイス名は `render_meta.json` の `settings.gpu_devices` に残る。

**実 GPU では未検証**(開発環境に GPU が無い。エラー経路のみ自動テスト済み)。

## 5. ジョブ状態と再開(`jobstate.py`、DD10, DD11)

- **タスク**: `enumerate_jobs(graph)` は「ノード全部 → 各エッジの内部フレーム」を1画像1タスクで列挙する(端点はノード側で撮る)。ID は `n000`、`e0001/0007`。
- **ログ** `capture.jsonl`: 1行目が header(`manifest_sha256`)、以降 1画像1行 `{id, theta, phi, path, seconds, bytes, sha256, ts}`。末尾の途中切れ行は無視。途中行が壊れていればエラー。
- **完了の判定**: ログ行がある **かつ** ファイルが存在し **サイズが一致**(`--verify` でハッシュも照合)。ファイルが消えた/変わったものは `corrupt` として撮り直す。
- **原子書き込み**: `*.part.exr` に書く → fsync → rename → ログ追記。途中で落ちても最終名の不完全ファイルは残らず、rename 後・ログ前に落ちた画像は撮り直される。再開時に残った `*.part.*` は削除する。
- **manifest の同一性**: 作業ディレクトリは manifest の SHA-256 に結びつく。別の manifest で再開しようとすると拒否する(新しい作業ディレクトリを使う)。撮影中は manifest を書き換えず、撮影条件は `render_meta.json` に保存する(DD11)。
- **進捗**: 1枚ごとに `[done/total] id 秒 バイト eta` を表示(`summarize`)。

## 6. 既知の制約・注意

- `bpy` モジュールで撮るときは `--blend` が必須。Cycles 起動時の `CUEW initialization failed` は CUDA ライブラリが無いという表示で、CPU 撮影では無害。
- シーン側の準備(被写体の配置、pivot=(0,0,0.9) 付近、ライト)は撮影システムの責務ではない。**被写体が全視点で枠に収まるか**は manifest の `focalMm` / `distance` で決まるので、撮影前に `coord_check.py` で確認する。
- 重いシーンの撮影時間・サンプル数は実作品で再測定が必要(`measurements.md`)。
- 影キャッチャーは φ<0 で被写体を隠すため使えない(DD36)。接地影が要る作品は別途検討。

## 7. 補助ツール(`python/tools/`)

| ツール | 内容 |
| --- | --- |
| `make_test_scene.py out.blend [--busy] [--busy-scale] [--shadow-catcher]` | 非対称テストシーン(赤 +X、緑 +Y、青 +Z、黄の鼻 -Y)。`--busy` は高周波テクスチャの大きな本体(コーデックのストレス用) |
| `make_test_manifest.py out.json [--cell --step --phi --diagonals --width --height --alpha]` | 縮小/本番の格子 manifest。既定は焦点距離 50mm・距離 5.5・alpha=`straight` |
| `coord_check.py scene.blend out.png` | 8視点を実カメラ経路で描いたコンタクトシート |
| `bench_capture.py` | サンプル数・デノイズ・persistent・シードの組み合わせで時間/容量/PSNR を測る |
| `bench_seed.py` | シード方式ごとの隣接フレームのちらつき |
| `make_synthetic_capture.py` | Blender なしで、色付き円盤の合成マスターを作る(パッカー/ビューアの机上検証用) |
