# 開発ドキュメント(正)

発案ノート([`../ideas/`](../ideas/README.md))を基に、開発用に確定させた内容。食い違いは本ディレクトリが優先。

- [spec-manifest-v0.md](spec-manifest-v0.md) — manifest / 座標 / グラフ / resolve / 移動ロジックの仕様(v0)
- システム仕様(現在どうなっているか。経緯は research-notes へ):
  - [system-core.md](system-core.md) — 共有コア(`knokin_core`)、本番グラフの規模、Python と TS の一致の仕組み
  - [system-capture.md](system-capture.md) — 撮影(Blender アドオン、ジョブ状態、再開、GPU)
  - [system-packer.md](system-packer.md) — パッカー(EXR→AVIF、色変換、冪等性、既定値)
  - [system-viewer.md](system-viewer.md) — ビューア(純関数コア、アプリ、URL パラメータ、計測)
- [research-notes.md](research-notes.md) — 開発の経緯、課題と選んだアプローチ、発見した注意点、誤りと教訓
- [decisions.md](decisions.md) — 開発上の決定ログ(発案ノートからの変更点を含む)
- [test-strategy.md](test-strategy.md) — 実測テストの規模の落とし方と、この環境で測れないこと
- [android-measurement.md](android-measurement.md) — Android 実機計測と操作感調整の手順書(実機は未実施)
- [measurements.md](measurements.md) — 実測の記録(撮影・パック・ビューア)。数値は測った環境つき

## システムとデータの流れ

アドオン(EXRマスター + manifest) → パッカー(AVIF連番 + 低解像度ノード画像) → ビューア

## リポジトリ構成

```
docs/ideas/        発案ノート(原文)
docs/dev/          開発ドキュメント(正)
python/knokin_core/  bpy非依存コア(標準ライブラリのみ。アドオンとパッカーが共有)
python/tests/      pytest
python/tools/      補助スクリプト(正解manifestの再生成、合成撮影データの生成)
testdata/manifests/  共通正解データ(Python/TypeScript 両側で検証)
testdata/move_cases/ move/frameAt/prefetch のテストケースJSON(Python/TS 共通の正解)
viewer/packages/core/  純関数(move/frameAt/prefetch/resolve/manifest)。DOM非依存
viewer/packages/app/  描画・入力・通信・計測のアプリ(Vite、Canvas 2D)
python/addon/      Blender層(`knokin_blender/`)と、ヘッドレス撮影の入口 `run_capture.py`
python/knokin_packer/  パッカー(EXR→AVIF、低解像度ノード画像、最終manifest)
```

## 開発の進め方

| セッション | 内容 | 状態 |
| --- | --- | --- |
| 1 | コア: 座標、グラフ、格子プリセット、検証、manifest、resolve、撮影タスク列挙、正解manifest | 完了 |
| 2 | ジョブ状態管理(JSONL、中断再開、tmp→rename)、Blender層(カメラ配置・EXR保存・ヘッドレス) | 完了(bpy 5.2.2 で実機確認) |
| 3 | ビューア純関数 `move`/`frameAt`/`prefetch` + テストケースJSON | 完了 |
| 4 | パッカー(机上検証: 合成EXRで往復・冪等性・欠落検出) | 完了 |
| 5 | ビューア描画・入力・計測(机上テスト + 合成データで Chromium 動作確認) | 完了 |
| 6 | 縮小規模での実測(bpy 実 Cycles、1080p 100枚、AVIF、Chromium)と、実機計測の入口 | 完了(GPU・Android・実作品・操作感は未実施。手順あり) |

## 開発コマンド

```
cd python && pip install pytest && python -m pytest
PYTHONPATH=. python tools/regen_golden.py   # 正解manifestを意図的に更新する時のみ
```

## パッカー

```
pip install -e "python[packer]"      # numpy, pillow>=11.3, OpenEXR
python -m knokin_packer --workdir out/ --out dist/ [--quality 60] [--speed 6] [--subsampling 4:2:0|4:4:4] [--low-width 480] [--partial]
```

再実行は冪等(変わった画像だけ作り直す)。未撮影・破損があれば拒否する(`--partial` でテスト撮影分だけ)。

## ビューアを動かす(Blender なし)

```
PYTHONPATH=python python python/tools/make_synthetic_capture.py --workdir /tmp/syn      # 色付き円盤の合成マスター
PYTHONPATH=python python -m knokin_packer --workdir /tmp/syn --out viewer/packages/app/public   # 合成データをパック
cd viewer && npm run dev                      # http://localhost:5173/?dbg=1  (m=<manifest URL> で別データ)
```

`?dbg=1` で HUD とスライダーが出る。Android 実機は同一ネットワークから `http://<PC>:5173/?dbg=1`(`vite --host` 済み)。
本番ビルドは `npm run build`(`packages/app/dist`)。manifest と `frames/` は同じ階層に置く。

## ビューア純関数のテスト

```
cd viewer && npm install && npm test        # Vitest(testdata を読む)
npm run typecheck
```

## 計測・テスト撮影の道具

```
python python/tools/make_test_scene.py scene.blend [--busy] [--shadow-catcher]   # 非対称テストシーン
python python/tools/make_test_manifest.py m.json --cell 60 --step 15 --width 1920 --height 1080
python python/tools/coord_check.py scene.blend sheet.png                         # 向きの目視確認
python python/tools/bench_capture.py --blend scene.blend --out bench/            # 時間・容量・PSNR
python python/tools/bench_seed.py scene.blend                                    # fixed / per-frame のちらつき
python python/tools/bench_pack.py --workdir w --out packbench/ --alpha straight  # AVIF 設定の掃引
node viewer/scripts/measure.mjs <baseUrl> out.json "speed=1200" ...              # ビューアのスクリプト操作(Chromium)
```

`bpy` モジュールで撮るときは `python python/addon/run_capture.py -- --blend scene.blend ...`(Blender 本体なら従来どおり `blender -b`)。

## 撮影の実行(ヘッドレス)

```
blender -b scene.blend -P python/addon/run_capture.py -- \
    --manifest manifest.json --workdir out/ [--test-shoot 100] [--samples 128] [--seed-mode fixed|per-frame]
```

同じコマンドの再実行が再開になる。Blender なしで Blender 層を試すには `pip install bpy` した環境で `pytest`
(`tests/test_blender_smoke.py` は bpy がなければスキップされる)。
