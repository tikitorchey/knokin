# ビューア仕様(純関数コア + アプリ)

現在の実装の記述。経緯は [research-notes.md](research-notes.md)。移動ロジックの規則(`move` / `frameAt` / `prefetch`)の本文は [spec.md](spec.md) §8。対象は Chrome(PC / Android)。iOS/Safari は対象外。

```
viewer/                     npm workspaces(DD20)
  packages/core/            純関数。DOM 非依存、Vitest。manifest 読込み、resolve、graph、move、frameAt、prefetch
  packages/app/             Vite + 素の TypeScript + Canvas 2D。入力・通信・デコード・描画・計測
  scripts/                  Playwright による計測スクリプト(Node)
```

## 1. コア(`packages/core`)

| モジュール | 内容 |
| --- | --- |
| `manifest.ts` | `parseManifest(text)` → `{manifest, graph}`。`schema` と `coords` 宣言が一致しなければ拒否(DD08) |
| `resolve.ts` | 論理参照 → パス(`{name}` / `{name:0Nd}` のみ。Python と同一仕様、DD06)。**ファイル名を作るのはここだけ** |
| `graph.ts` | `delta` と `frames` からグラフ構造(ノード・エッジ・接続)を作る。ビューアが使うのは `delta` と `frames` だけ |
| `move.ts` | `move(graph, state, drag, opt)` → 新しい `State`。`State = {pos, heading, acc}`(DD15)。規則は spec §8 |
| `frameAt.ts` | `frameAt(graph, pos)` → `FrameRef`(`round(t)`、端点はノード参照。クロスフェードなし) |
| `prefetch.ts` | `prefetch(graph, state, budget, opt)` → 優先度順の `FrameRef[]`(DD19) |

既定値(`types.ts`): `DEFAULT_MOVE_OPT = {degPerPx 0.25, turnPx 12, deadZoneDeg 45, stickyDeg 15}`、`DEFAULT_PREFETCH_OPT = {fanFrames 3, behindFrames 2}`。**`MoveOpt` の4値は仮置き**で、実機で触って決める(`android-measurement.md` §4)。

正解データ: `testdata/move_cases/{move,frame_at,prefetch}.json`(規則から手計算。ケースごとに `opt` を明示)。Vitest が読む。**Python 側に `move` の実装は無い**(manifest/resolve/graph の一致だけを `testdata/manifests/` で Python と TS の両側で検証している)。

## 2. アプリ(`packages/app/src`)

### 起動順(`main.ts`)

1. URL の `m` で manifest を決める(既定 `./manifest.json`)。取得して `parseManifest`。
2. `Metrics`、`LoaderOpt`、`CanvasView` を作る。低解像度ありなら(`frames.nodeLow` と `image.low`)、全ノードを `lowCache` に先読みする。
3. `FrameCache`(フル)を作る(`maxItems` 48、`concurrency` 6 が既定)。
4. `Controller` を作り、ポインタ入力を結ぶ。`?dbg` ならデバッグ UI(§6)。
5. 描画は `requestAnimationFrame` で**最新の1枚だけ**描く(DD31)。

### `Controller`(`controller.ts`、DD28)

入力 → `move` → `frameAt` → 表示の接着。DOM 非依存・時計注入でテストできる。

- `drag(dx, dy, at)`: `move` で状態を更新し、`prefetch`(`budget` 既定 16)で want-list を作って `cache.want([現在, ...先読み])`。
- 現在のフレームが**デコード済み**なら表示(`hit`)。未到着なら**直前のフレームを保持**し、**ノードの上なら低解像度画像を代役に出す**(DD30)。ミスは1表示につき1回数える。
- `onReady(key)`: 待っていたフレームが届いたら表示。
- 遅延 = ポインタイベントの `timeStamp` → 描画直後(`performance.now()`)。`latency` に記録。

### `FrameCache`(`cache.ts`、DD29)

優先順の want-list を毎回**置き換える**。待機中で外れたものは破棄、通信中で外れたものは `abort`。デコード済みが `maxItems` を超えたら、(want 外 → 最近使っていない順)→(want 内の優先度が低い順)に `close()` して解放。失敗したキーは `failed` に入り再要求されない(`retry failed` で解除)。`maxItems` と `concurrency` は実行中に変更できる。

### `loader.ts`

`fetch` → `blob` → デコード。デコード方式は `createImageBitmap`(既定)または `ImageDecoder`(`decode=` で切替、DD32/DD42)。`premultiplyAlpha` は `premultiply`(既定)/`none`/`default`。**URL は `urls.ts` が `resolve` 経由で作る**(キー `n:n000` / `e:e0001/7`)。取得時間、デコード時間、バイト数を `Metrics` に記録。

### `render.ts`

Canvas 2D(`alpha:false`)。画像を contain で収め、バッキングストアは `devicePixelRatio` に追従。背景は暗色(`checker` でチェッカー表示に切替可)。**フレームは常に最後に表示したものを保持**し、リサイズで再描画する。

### 入力(`bindPointer`)

ポインタイベントのみ(マウス/タッチ共通)。**単一ポインタのみ**(2本目は無視)。`getCoalescedEvents()` があれば細かい移動をすべて `drag` に渡す。ピンチ・ホイールは未対応。`touch-action: none`。

### 計測(`metrics.ts`、DD33)

`latency`、`fetchMs`、`decodeMs`、`frameBytes`(直近 1,000 サンプルの p50/p95/max)と、カウンタ(`hit` `miss` `fail` `abort` `lowShown`)、`hitRate`。`reset()` で全消去。

## 3. URL パラメータ(DD43)

| パラメータ | 内容 | 既定 |
| --- | --- | --- |
| `m` | manifest の URL | `./manifest.json` |
| `dbg` | HUD とデバッグパネルを出す | off |
| `bench` | (`dbg` と併用)起動 1.5 秒後にスクリプト操作を自動実行 | off |
| `tag` | 計測 JSON に入る任意の識別子 | 空 |
| `speed` | スクリプト操作の指の速度 px/s | 400 |
| `decode` | `createImageBitmap` / `imageDecoder` | `createImageBitmap` |
| `pm` | `premultiply` / `none` / `default` | `premultiply` |
| `cache` / `conc` / `budget` | キャッシュ上限(枚)/ 同時取得数 / 先読み数 | 48 / 6 / 16 |
| `dpp` / `turn` / `dead` / `sticky` | `degPerPx` / `turnPx` / `deadZoneDeg` / `stickyDeg` | 0.25 / 12 / 45 / 15 |

## 4. 通信とデータ配置

`<配信ルート>/manifest.json` と `frames/`(`frames.base` 以下)を同じ階層に置く。ビューアは manifest の URL を基準に相対 URL を解決する。パッカーの出力ディレクトリをそのまま配信すればよい。開発時は `viewer/packages/app/public/` に置く(`.gitignore` 済み)。**計測は必ず `npm run build` して配信したもので行う**(開発サーバは未バンドルで遅い)。

## 5. メモリ

デコード済みフレームは `幅×高さ×4` バイト(1080p で約 7.9 MB/枚)。`cacheMax` 48 で約 380 MB。**この分は JS ヒープに現れない**(HUD の `heap` は 3〜4 MB のまま)ので、HUD の `decoded`(推定 MB)を見る。Android での上限はここで決まる見込み(実機未計測)。

## 6. デバッグ UI(`?dbg=1`)

- HUD(左上): 遅延 / 取得 / デコードの p50・p95、フレーム KB、ヒット率、`miss`/`fail`/`abort`、現在位置、デコード済み枚数と推定 MB、取得中の数、低解像度の先読み数、JS ヒープ。500 ms ごとに更新。
- パネル(右): `degPerPx` `turnPx` `deadZone` `stickyDeg` `budget` `fanFrames` `behind` `cacheMax` `concurrency`、`decode` `premultiply`、`checker bg`、`reset`、`run scripted drag`、`export metrics`、`retry failed`、JSON のテキスト欄。
- **`run scripted drag`**(`bench.ts`): 決まった道(右 4 秒 → 下 2 秒 → 右下 2 秒 → 左 4 秒 → 上 3 秒 → 左上 2 秒 → 右 3 秒)を一定速度で再生する。メトリクスを消してから開始し、終了後に JSON を作る(`window.__knokinBench` とテキスト欄)。止まったタブで巨大なドラッグにならないよう、1フレームの経過時間は 100 ms で頭打ち。
- **JSON の中身**: `tag`、`ua`、`dpr`、`screen`、`image`、`cores`、`deviceMemoryGB`、`opt`、`cache`、`loader`、`heapMB`、`peakHeapMB`、`decodedMB`、`peakDecodedMB`、`scripted`、各メトリクス。`export metrics` はダウンロードも試みる(スマホではテキスト欄からのコピーが確実)。

## 7. 計測スクリプト(`viewer/scripts/`)

| スクリプト | 内容 |
| --- | --- |
| `measure.mjs <baseUrl> <out.json> [variant…]` | headless Chromium でスクリプト操作を variant(URL パラメータ)ごとに回す。`CPU_SLOWDOWN`、`NET="kbps,rttMs"` で**エミュレーション**(実機の代わりではない)。`PLAYWRIGHT_MODULE` で Playwright の場所を指定 |
| `premult.mjs <baseUrl> <truthDir> <out.json>` | `premultiplyAlpha` 3種と ImageDecoder を、意図した合成結果(`make_premult_truth.py` が作る)と PSNR で比較 |
| `decode-bench.mjs <baseUrl> <dir> [reps]` | デコード時間のみを `createImageBitmap` / `ImageDecoder` で測る |

## 8. 既知の制約・未対応

- Android 実機は未計測。デスクトップ headless Chromium の遅延 p50 17.5 ms は 1 vsync 分で、**実機の遅延ではない**。
- 単一ポインタのみ、ピンチ・ホイール・キーボード操作なし。
- クロスフェードなし(`frameAt` は最寄りのフレームを返すだけ)。
- フル画像が未到着のとき、**エッジの途中では代役が無い**(直前のフレームを保持するだけ。低解像度はノードのみ)。
- 画面サイズ変更時は再描画のみ(画像の再取得はしない)。
- 操作感の4値は仮置き。
