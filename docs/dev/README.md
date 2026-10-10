# 開発ドキュメント(正)

発案ノート([`../ideas/`](../ideas/README.md))を基に、開発用に確定させた内容。食い違いは本ディレクトリが優先。

- [spec-manifest-v0.md](spec-manifest-v0.md) — manifest / 座標 / グラフ / resolve の仕様(v0)
- [decisions.md](decisions.md) — 開発上の決定ログ(発案ノートからの変更点を含む)

## システムとデータの流れ

アドオン(EXRマスター + manifest) → パッカー(AVIF連番 + 低解像度ノード画像) → ビューア

## リポジトリ構成

```
docs/ideas/        発案ノート(原文)
docs/dev/          開発ドキュメント(正)
python/knokin_core/  bpy非依存コア(標準ライブラリのみ。アドオンとパッカーが共有)
python/tests/      pytest
python/tools/      補助スクリプト(正解manifestの再生成など)
testdata/manifests/  共通正解データ(Python/TypeScript 両側で検証)
testdata/move_cases/ move/frameAt/prefetch のテストケースJSON(Python/TS 共通の正解)
viewer/packages/core/  純関数(move/frameAt/prefetch/resolve/manifest)。DOM非依存
viewer/            (予定) 描画・入力・通信・計測のアプリ(Vite)
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
| 5 | ビューア描画・入力・計測 | 未 |

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

## ビューア純関数のテスト

```
cd viewer && npm install && npm test        # Vitest(testdata を読む)
npm run typecheck
```

## 撮影の実行(ヘッドレス)

```
blender -b scene.blend -P python/addon/run_capture.py -- \
    --manifest manifest.json --workdir out/ [--test-shoot 100] [--samples 128] [--seed-mode fixed|per-frame]
```

同じコマンドの再実行が再開になる。Blender なしで Blender 層を試すには `pip install bpy` した環境で `pytest`
(`tests/test_blender_smoke.py` は bpy がなければスキップされる)。
