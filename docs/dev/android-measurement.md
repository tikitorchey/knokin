# Android 実機計測と操作感の調整(手順書)

この環境には Android 端末が無く、**実機の数値は未取得**。ここは、実機で同じ測定を再現するための手順。デスクトップ Chromium とエミュレーションで取った参考値は [measurements.md](measurements.md) §4。

## 1. 用意するデータ

実作品のテスト撮影(または縮小グラフの全撮影)をパックして、ビューアの `public/` に置く。

```
# 1080p・縮小グラフ(60°・15°刻み・×、168枚)の例。Blender 本体なら blender -b scene.blend -P ... に読み替える
python python/tools/make_test_manifest.py m_view.json --cell 60 --step 15 --width 1920 --height 1080
python python/addon/run_capture.py -- --blend scene.blend --manifest m_view.json --workdir w_view --samples 16
python -m knokin_packer --workdir w_view --out viewer/packages/app/public       # 既定: q60 / s6 / 4:2:0
```

辺をたどる操作の計測には、グラフが閉じていること(全枚撮影した縮小グラフ)が必要。`--partial` の100枚抽出では辺の途中が欠けるので、ビューア計測には使えない。

## 2. 配信

```
cd viewer && npm install && npm run build
cd packages/app && npx vite preview --host 0.0.0.0 --port 4173      # dist をそのまま配信
```

- 端末と PC が同じ Wi-Fi: 端末の Chrome で `http://<PCのIP>:4173/?dbg=1&tag=<端末名>`。
- USB で繋ぐ場合: PC 側 `chrome://inspect` で端末を認識させ、`adb reverse tcp:4173 tcp:4173` のあと端末で `http://localhost:4173/...`。
- 開発サーバ(`npm run dev`)は計測に使わない(未バンドル・HMR のオーバーヘッドが乗る)。必ず build して配信する。
- 通信条件は結果に効く。Wi-Fi の場合は `tag` に回線(`wifi5GHz` など)も入れる。

## 3. 計測(1回 約 20 秒)

`?dbg=1` で HUD(遅延・取得・デコードの p50/p95、ヒット率、デコード済み枚数と推定 MB、ヒープ)とパネルが出る。

1. 画面を縦横どちらで測るか決めて固定する(`tag` に入れる)。
2. パネルの **run scripted drag** を押す。同じ操作(赤道→経線→斜め→反転)が自動で再生される。速度は URL の `speed=<px/s>`(既定 400)。
3. 終わると **JSON がパネル下のテキスト欄に出る**(`export metrics` でも同じ。ダウンロードも試みるが、スマホでは欄から全選択コピーのほうが確実)。これを保存して `docs/dev/measurements/android-<端末>-<条件>.json` に置く。

URL だけで条件を指定できる(スライダー操作は不要):

| 目的 | URL に足す |
| --- | --- |
| 速度を変える | `speed=400`(既定)、`speed=1200`、`speed=2400` |
| デコード方式 | `decode=createImageBitmap`(既定)/ `decode=imageDecoder` |
| premultiplyAlpha | `pm=premultiply`(既定)/ `none` / `default` |
| キャッシュ上限(メモリ) | `cache=24` など(既定 48。デコード済み 1080p は約 7.9 MB/枚) |
| 同時取得数 | `conc=2` など(既定 6) |
| 先読みの数 | `budget=16`(既定) |
| タグ | `tag=Pixel8-wifi` |
| 自動実行 | `bench=1` |

見るもの(JSON のキー): `latency`(入力→表示、ms)、`fetchMs`、`decodeMs`、`hitRate`/`counters`(`miss` `fail` `abort` `lowShown`)、`peakDecodedMB`(デコード済みの推定ピーク)、`peakHeapMB`(JS ヒープ。**デコード済み画像は入らない**)、`ua`/`dpr`/`cores`/`deviceMemoryGB`。

### 優先して取る順

1. 既定のまま `speed=400` / `1200` / `2400`。ヒット率が 95% を割る速度が「実用の上限」の目安。
2. `decode=imageDecoder` と `pm=none` / `default`(デスクトップでは `ImageDecoder` が 4倍遅く、`pm` は差なし)。
3. `cache=12` / `24` / `48` / `96`: **メモリ**。ブラウザのタブが落ちる(リロードされる)境目を探す。Chrome のタスクマネージャ(端末のメニュー)や `chrome://inspect` のメモリ表示も併用。
4. `conc=2` / `4` / `6` / `12`: デスクトップの CPU 4倍遅エミュレーションでは 2〜4 が良かった(measurements.md §4.2)。実機で同じ向きか。
5. `budget` / `fanFrames` / `behind`(パネルのスライダー)。
6. 4:4:4 のパックに差し替えて、デコード時間とヒット率(既定は 4:2:0。ハードウェアデコーダ非対応ならソフトウェア復号で遅くなる可能性)。

結果から決めた値は DD に追記し、`DEFAULT_CONTROLLER_OPT` / キャッシュ既定(`packages/app/src/main.ts` の `cache` `conc`)/ `DEFAULT_LOADER_OPT` を更新する。

## 4. 操作感の調整(`degPerPx` `turnPx` `deadZoneDeg` `stickyDeg`)

これらは**指で触って決める**値で、自動テストでは良し悪しが決まらない。URL かスライダーで変えて触る。

```
?dbg=1&dpp=0.35&turn=16&dead=45&sticky=15
```

| 値 | 意味 | 触りながら見る点 |
| --- | --- | --- |
| `degPerPx`(0.25) | 1 px のドラッグで何度回るか | 画面を横切る1回のスワイプで何度回るか(1 px = 0.25° なら 400 px で 100°) |
| `turnPx`(12) | ノードで別の辺へ曲がるのに必要なドラッグ量 | 小さすぎると意図せず曲がる、大きすぎると曲がれない |
| `deadZoneDeg`(45) | 選んだ辺とのずれがこれを超えたら動かない | φ 端など行き止まりでの挙動 |
| `stickyDeg`(15) | 直進を優先する角度 | 赤道を回し続けるとき、ノードで引っかからないか |

決まったら:

1. `viewer/packages/core/src/types.ts` の `DEFAULT_MOVE_OPT` を更新する。
2. `testdata/move_cases/move.json` の各ケースは **`opt` を明示して手計算した正解**なので、既定値を変えても既存ケースはそのまま通る(既定値を参照していない)。ただし新しい値で挙動が変わる点(曲がり始め・不感帯の境目)を、新しい `opt` を持つケースとして足す。期待値は規則から手で導く(実装の出力を写さない)。
3. `cd viewer && npm test && npm run typecheck`。Python 側には `move` の実装が無い(`testdata/move_cases/` を読むのは Vitest のみ)ので、Python のテストは影響を受けない。
4. DD に値と根拠(端末、触った感想)を追記する。

## 5. 記録の置き方

- JSON: `docs/dev/measurements/android-<端末>-<条件>.json`
- 結果の表と所感: [measurements.md](measurements.md) に「§6 Android 実機」として追記し、端末名・Chrome のバージョン・回線・画面の向きを必ず書く。
- 数値を推測で埋めない。測っていない欄は「未測定」と書く。
