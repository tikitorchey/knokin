# 次のエージェントへの引き継ぎプロンプト

以下をそのまま次のセッションの最初のプロンプトとして渡す。

---

あなたは「Knokin Turn Table」(プリレンダリング式3Dモデルビューア)試作機の開発を引き継ぎます。対象は Chrome(PC / Android)。iOS/Safari は対象外です。
前任は、机上と合成データで、撮影→パック→ビューアの一連を実装しました。あなたの役目は、**実際に Blender で撮影し、実測して、値を決めること**です。

## 最初にやること
1. `docs/dev/README.md`(索引)、`docs/dev/spec-manifest-v0.md`(仕様)、`docs/dev/decisions.md`(DD01〜DD33)を読む。
2. `docs/ideas/` は発案時のノート(原文)。**更新しない。**食い違いは `docs/dev/` が正。
3. 動作確認: `cd python && pip install pytest numpy "pillow>=11.3" OpenEXR && python -m pytest`(bpy は `pip install bpy` があれば Blender スモークテストも走る)、`cd viewer && npm install && npm test && npm run typecheck`。
4. 作業ブランチはこのセッションの指示に従う。前任のブランチ(ccr-24134129-yza4v8、PR #1)は未マージ。main に入っているかを確認し、入っていなければそのブランチを土台にする。

## 構成(データの流れ)
Blender アドオン(`python/addon/`、EXR マスター + `capture.jsonl`)→ パッカー(`python/knokin_packer/`、AVIF 連番 + 低解像度ノード画像 + 最終 manifest)→ ビューア(`viewer/packages/core` 純関数、`viewer/packages/app` 描画・入力・計測)。三者を manifest.json が結ぶ。共有コアは `python/knokin_core/`。Python と TypeScript は `testdata/` の共通正解データで一致を保つ。

## 守る設計原則
- 骨組みはノードとエッジのグラフのみ。ビューアは `delta` と `frames` だけを使う。ファイル名は `resolve` 経由のみ(自前で組み立てない)。
- 交点(ノード)の画像は1枚を全エッジで共有。エッジは端点を保存しない。
- カメラ条件は作品ごとに固定。座標規約(Z上向き右手系、θ=0 でカメラ -Y、(90°,0°)→+X、pivot を向く)は自動テストで検算済み。変えるなら schema を上げる。
- 曖昧な点は黙って埋めず、決定として `decisions.md` に記録する(DDを連番で追加)。

## 現状(できること)
- 30°格子・φ±60°・×斜め・1°刻みのグラフ生成(ノード108、エッジ300、5,928枚)と検証。
- ヘッドレス撮影: `blender -b scene.blend -P python/addon/run_capture.py -- --manifest ... --workdir ...`(中断再開、`--test-shoot N`、`--verify`、シード/デノイズ/persistent_data 切替)。bpy 5.2.2 モジュールでのみ検証済み。**本物の Blender 本体と実シーンでは未検証。**
- パック: `python -m knokin_packer --workdir ... --out ... [--partial]`。
- ビューア: `npm run dev` → `?dbg=1` で HUD とスライダー。合成データ(`python/tools/make_synthetic_capture.py`)で Chromium 動作確認済み。手順は README の「ビューアを動かす」。

## あなたの課題(優先順)
1. **実シーンのテスト撮影(約100枚)**: Blender 本体で `--test-shoot 100`。1枚あたりの時間、EXR 容量、サンプル数・デノイズ・シード方針(fixed / per-frame)の比較、`use_persistent_data` の効果、GPU(Cycles)での動作。結果を `docs/dev/` に計測表として記録。
2. **Blender 本体での座標確認**: 実撮影の数枚で θ/φ の向きが仕様どおりか目視確認(DD04)。必要なら影キャッチャー/背景透過(D03)の方針を決める。
3. **パックの画質とサイズ**: `--partial` で上記テスト撮影をパックし、AVIF の quality / speed / 4:2:0 と 4:4:4 を比較。縁(アルファ境界)の品質、総容量の見積り(5,928枚換算)、`premultiplyAlpha` 3種の見た目の差。既定値(DD27)を決める。
4. **Android 実機計測**: `npm run build` の成果物を配信し(同一ネットワーク、または静的ホスティング)、`?dbg=1` で遅延・フェッチ/デコード時間・ヒット率・ヒープを取得。`createImageBitmap` と `ImageDecoder` の速度差、`maxItems` の上限(メモリ)、`concurrency`、`budget`/`fanFrames`/`behindFrames` を詰める。「export metrics」の JSON を記録に残す。
5. **操作感の調整**: `degPerPx`・`turnPx`・`deadZoneDeg`・`stickyDeg` の既定値は仮置き。実機で触って決め、`DEFAULT_MOVE_OPT` と `testdata/move_cases/` を更新(Python/TS の両側が通ること)。
6. 余力があれば: `diagonals: "alternate"` プリセット、重点エリア用の `span`/`stride`、manifest の `render.capture` の項目確定。

## 注意
- 実機・Blender 本体を使うために、環境に Blender / Android 端末が無い場合は、手順書と計測用の入口を整えて、その旨をユーザーに報告する(推測で数値を作らない)。
- テストが検証しているのは「決めた規則どおりに動くこと」で、操作感や画質の良し悪しは未検証。
- `viewer/packages/app/public/` は .gitignore 済み(パック成果物を置く場所)。
- コミットは小さく、テストを通してから。PR 監視は不要(ユーザー了承済み)。
