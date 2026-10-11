# Knokin オンボーディング

プロジェクトに初めて入る人向け。まずこの文書を読み、細部は [spec.md](spec.md)(仕様)と [decisions.md](decisions.md)(決定ログ)を見る。

## 1. これは何か

**プリレンダー式の3Dモデルビューア**(ターンテーブル型)。パーティクル・半透明・複雑なGIなど、リアルタイム描画では品質が出にくい表現を、劣化なく閲覧できるようにする。

方式の要点:

- Blender(Cycles)で、視点(θ方位角・φ仰角)ごとの**通常画像だけ**をレンダリングしておく。深度や再投影による**補間はしない**。
- 全角度を撮ると約13万枚(約90日)かかるので、カメラが動ける場所を**骨組み(ノードとエッジのグラフ)の線上だけ**に絞る。試作は 30° 格子・φ±60°・×斜め・1°刻みで **5,928枚**(約99時間 @1分/枚の見積り)。
- ビューアは、ドラッグに応じて骨組み上を動き、最寄りの画像を表示する。ノード(交点)では曲がれる。
- ライティングはワールド固定。対象は Chrome(PC / Android)。iOS/Safari は対象外。

## 2. システムとデータの流れ

```
Blender アドオン ──▶ パッカー ──▶ ビューア
 EXR マスター        AVIF 連番 + 低解像度     Chrome で閲覧
 + capture.jsonl     ノード画像 + 最終 manifest
```

三者を結ぶ契約が `manifest.json`([spec.md](spec.md))。計測・検証は独立させず、各システムに同梱している。

| システム | 場所 | 言語 | 役割 |
| --- | --- | --- | --- |
| 共有コア | `python/knokin_core/` | Python(標準ライブラリのみ) | 座標、グラフ生成、検証、manifest、resolve、ジョブ状態。bpy 非依存 |
| 撮影アドオン | `python/addon/` | Python(bpy) | カメラ配置、EXR 保存、ヘッドレス撮影、中断再開 |
| パッカー | `python/knokin_packer/` | Python | EXR → AVIF、低解像度化、最終 manifest、冪等 |
| ビューア | `viewer/packages/core`(純関数)、`viewer/packages/app`(描画・入力・計測) | TypeScript | `move` / `frameAt` / `prefetch`、キャッシュ、Canvas 2D 描画、デバッグHUD |
| 共通正解データ | `testdata/` | JSON | Python と TS が同じファイルで検証し、仕様の解釈を一致させる |

## 3. 守る設計原則

1. 骨組みは**ノードとエッジのグラフのみ**。ビューアが使うのは `delta` と `frames` だけで、格子を前提にしない。
2. ファイル名は `resolve` 経由でのみ得る。自前で組み立てない。
3. 交点(ノード)の画像は**1枚を全エッジで共有**。エッジは端点を保存しない。エッジはノードでのみ交わる。
4. カメラ条件は作品ごとに固定。座標規約(Z上向き右手系、θ=0 でカメラ -Y、pivot を向く)を変えるなら `schema` を上げる。
5. 撮影中は manifest を書き換えない。撮影条件は `render_meta.json` に残し、パッカーが取り込む。
6. 曖昧な点は黙って埋めず、`decisions.md` に DD として記録する。

## 4. 動かしてみる(Blender なし)

```
# Python: テスト
cd python && pip install pytest numpy "pillow>=11.3" OpenEXR && python -m pytest

# TypeScript: テスト・型検査
cd viewer && npm install && npm test && npm run typecheck

# 合成データでビューアを動かす(色付き円盤のマスター → パック → 配信)
PYTHONPATH=python python python/tools/make_synthetic_capture.py --workdir /tmp/syn
PYTHONPATH=python python -m knokin_packer --workdir /tmp/syn --out viewer/packages/app/public
cd viewer && npm run dev      # http://localhost:5173/?dbg=1
```

- `?dbg=1` で HUD(遅延・取得/デコード時間・ヒット率・ヒープ)とパラメータのスライダー、メトリクスJSONの書き出しが出る。Android 実機は同一ネットワークから `http://<PC>:5173/?dbg=1`。
- 本番ビルドは `npm run build`(`packages/app/dist`)。manifest と `frames/` は同じ階層に置く。
- 正解 manifest の意図的な再生成: `PYTHONPATH=python python python/tools/regen_golden.py`。

実撮影(Blender 本体):

```
blender -b scene.blend -P python/addon/run_capture.py -- \
    --manifest manifest.json --workdir out/ [--test-shoot 100] [--samples 128] [--seed-mode fixed|per-frame] [--verify]
python -m knokin_packer --workdir out/ --out dist/ [--quality 60] [--speed 6] [--subsampling 4:2:0|4:4:4] [--partial]
```

どちらも再実行が再開(冪等)。`--partial` は撮影済みだけをパックする(テスト撮影用)。

## 5. 現状

試作の4システムは、机上テストと合成データでの動作確認まで完了。Blender 本体・実シーン・Android 実機での確認は**まだ行っていない**。

**未了(実機・実シーンが必要)**

1. 実シーンのテスト撮影(約100枚): 1枚の時間、EXR容量、サンプル数、**デノイズ/シード方針(D10)**、`use_persistent_data` の効果、GPU動作。
2. Blender 本体で θ/φ の向きを目視確認(DD04)。影キャッチャー(D03)の要否。
3. AVIF の既定値(DD27)の確定: quality / speed / 4:2:0 と 4:4:4、縁の品質、`premultiplyAlpha`、5,928枚換算の総容量。
4. Android 実機計測: メモリ上限(`maxItems`)、`createImageBitmap` と `ImageDecoder` の速度、`concurrency`、先読みパラメータ。
5. 操作感の調整: `degPerPx` `turnPx` `deadZoneDeg` `stickyDeg` は仮置き。決めたら `DEFAULT_MOVE_OPT` と `testdata/move_cases/` を更新(Python/TS 両側が通ること)。

テストが保証するのは「決めた規則どおりに動くこと」で、操作感や画質の良し悪しではない。Blender / 実機が無い環境では、数値を推測で作らず、手順と計測の入口を整えて報告する。

**未実装(試作の外)**

- `diagonals: "alternate"` プリセット(DD05)、`render.capture` の項目確定。
- Day2: 圧縮方式の探索(動画コーデック、アルファ分離)。
- 後続: 重点エリア(`span`/`stride`、密度展開、T字接続)、配布(ストレージ・共有・埋め込み)、WebGL・クロスフェード・Worker化(実測で必要になった場合)。

## 6. 読む順番

1. この文書
2. [spec.md](spec.md) — manifest、座標、グラフ、撮影ディレクトリ、移動ロジック
3. [decisions.md](decisions.md) — D01〜D11(基本方針)と DD01〜DD33(開発上の決定)
4. コード: `python/knokin_core/` → `viewer/packages/core/src/` → 各システム

## 7. 圧縮方式の探索(Day2、進行中)

`python/tools/codec_bench.py` が、AVIF 連番(現行)と動画コーデック(AV1 aom/SVT、HEVC、VP9)+**カラー/アルファ分離**を、同じ8bit基準画像に対して比較する(容量、アルファ/合成PSNR、デコード時間、ランダムアクセスで必要なデコード枚数)。

```
PYTHONPATH=python python python/tools/codec_bench.py --frames <エッジ1本分のEXR/PNG連番ディレクトリ> --out report [--quick]
```

- 入力は**実レンダーのエッジ1本分**(ノード→途中フレーム→ノード、30°なら31枚)。`--synthetic` は動作確認用で、数値は参考にならない。
- 結果の表は `report.md` / `report.csv`。再実行は続きから再開する(`--fresh` でやり直し)。AVIF の比較基準はストレートアルファ(DD34)。
- 予備調査の結果と結論は [research-compression.md](research-compression.md)。方針の決定は未検証項目の実測後に DD として行う。
- 未着手: WebCodecs `VideoDecoder` でのブラウザ側デコード、キーフレーム(ノード)設計、逆再生コスト。
