# 共有コア仕様(`python/knokin_core`)とテストデータ

現在の実装の記述。manifest・座標・グラフの**規則そのもの**は [spec.md](spec.md)。ここは実装の地図と、Python と TypeScript を一致させる仕組み。

## 1. モジュール(標準ライブラリのみ。Blender 同梱 Python に追加導入なしで動く、DD09)

| モジュール | 内容 |
| --- | --- |
| `coords.py` | 座標規約: `direction(θ,φ)`、`camera_position`、`look_direction`、`norm_theta`、`angular_diff`。検算(90,0)→+X、(0,0)→-Y、(0,90)→+Z は自動テスト |
| `graph.py` | `Node` / `Edge` / `Graph`。`angle_at(edge, i)`、`canonical`(端点を持たない正規形) |
| `presets.py` | `UniformGrid`(均一格子プリセット)。`diagonals` は `none` / `cross`(`alternate` は未実装でエラー、DD05)。中心ノードを追加して斜めを2エッジに分割(DD02) |
| `validate.py` | 検証: id 重複、ノード位置重複、θ 範囲、|φ| 上限、端点到達、交点規則(全フレーム位置の突き合わせ)、連結性 |
| `manifest.py` | `Manifest` の読み書き(決定的な書式)、`build_grid_manifest`、`default_frames()`、開始ノード = (0,0) に最も近いノード |
| `resolve.py` | 論理参照 → パス、`frame_id`、`master_relpath`(撮影側の配置)。**ファイル名を作る唯一の場所**(Python 側) |
| `jobs.py` / `jobstate.py` | 撮影タスクの列挙 / 作業ディレクトリと再開(`system-capture.md`) |

## 2. 本番グラフの規模(30°格子・φ±60°・× 斜め・1°刻み)

ノード 108、エッジ 300、**総画像数 5,928**(ノード 108 + 緯線 1,740 + 経線 1,392 + 斜め 2,688)。× なしは 3,192。縮小グラフ(60°・15°刻み・×)は 30 ノード・78 エッジ・168 枚。

## 3. Python と TypeScript の一致を保つ仕組み

| データ | 内容 | 検証する側 |
| --- | --- | --- |
| `testdata/manifests/minimal.json` | 3 ノード・3 エッジ(手書き) | 両側 |
| `testdata/manifests/grid30_cross.json` | プリセットから生成した正解 | Python は再生成して一致を確認、TS は同じファイルを読みノード数・エッジ数・総画像数・resolve 結果を検証 |
| `testdata/move_cases/*.json` | `move` / `frameAt` / `prefetch` の入出力(規則から手計算) | **TS のみ**(Python に `move` の実装は無い) |

意図して正解を更新するときだけ `PYTHONPATH=python python python/tools/regen_golden.py`。

## 4. テスト

```
cd python && python -m pytest          # 57 件(bpy があれば Blender スモークテストも走る)
cd viewer && npm test                  # Vitest(core 36 件 + app 21 件)
cd viewer && npm run typecheck
```

テストが検証しているのは**決めた規則どおりに動くこと**であり、操作感・画質・性能の良し悪しは含まない(それらは実測、`measurements.md`)。
