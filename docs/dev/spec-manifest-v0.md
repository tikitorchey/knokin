# manifest 仕様 v0

`schema` は `knokin-turntable/0`。リーダーは完全一致のみ受理し、それ以外は読み込みを拒否する。
実装: `python/knokin_core/`。サンプル: `testdata/manifests/`。

## 1. 原則

- 骨組みはノードとエッジのグラフのみ。格子は「グラフを生成するプリセット」で、リーダーは `delta` と `frames` だけを使う。
- ファイル名はリーダーが組み立てず、論理参照を `resolve` に渡して得る。
- 交点(ノード)の画像は1枚で全エッジが共有する。エッジは端点を保存しない。
- カメラ条件は作品ごとに宣言し、全フレームで固定。ライティングはワールド固定。

## 2. 座標規約

Blender 世界座標(Z上向き・右手系)。角度は度。

- θ(方位角): カメラが -Y 側のとき 0。+Z から見て反時計回りが正。ノード・フレームの値は [0, 360)。
- φ(仰角): 水平 0、上が正。使用範囲は |φ| ≤ 75°(×構成の試作は ±60°)。極は含めない。
- 方向ベクトル `d = (cosφ·sinθ, −cosφ·cosθ, sinφ)`。カメラ位置 = `pivot + distance·d`。
- 姿勢: **pivot を向く**。ロール 0(上は +Z)。
- 検算: (θ,φ)=(90,0) → +X、(0,0) → -Y、(0,90) → +Z。自動テスト済み。

ビューアの入力向き(右ドラッグで θ 減少、下ドラッグで φ 増加)は manifest に含めない。

## 3. グラフ

| 要素 | 内容 |
| --- | --- |
| ノード | `id`, `theta`, `phi`。画像1枚 |
| エッジ | `id`, `kind`, `from`, `to`, `delta`=[Δθ,Δφ](from→to の全体量), `frames`(両端点を含む枚数) |

規則:
- フレーム i の角度 = `from + delta · i/(frames−1)`。θ は [0,360) に正規化。
- i=0 は node(from)、i=frames−1 は node(to)。エッジ側には保存しない(`Graph.canonical`)。
- エッジは双方向。逆向きは逆順に読む。
- **エッジはノードでのみ交わる。** 交差・T字・重なりはノードで分割する。バリデータは全フレームの位置を突き合わせて検出する。
- `kind` は自由ラベル(`lat` `lon` `diag`)。ビューアの挙動に影響しない。
- 検証項目: id重複、ノード位置重複、θ範囲、|φ|上限、端点到達(from+delta=to)、交点規則、連結性。

### 均一格子プリセット(`render.graphPreset`)

```json
{ "type": "uniform-grid", "cellDeg": 30, "phiRange": [-60, 60], "stepDeg": 1, "diagonals": "cross" }
```

- `diagonals`: `none` | `cross`(×)。`alternate` は未実装(指定するとエラー)。
- 制約: 360 が cellDeg の倍数、phiRange の幅が cellDeg の倍数、cellDeg(×では cellDeg/2)が stepDeg の倍数。
- 生成: 緯線(閉ループ、セル幅ごとに分割)、経線、`cross` ではセル中心に追加ノードを置き、4隅から中心へ4本の斜めエッジ(`delta`=±cellDeg/2, `frames`=cellDeg/2/stepDeg+1)。
- ID: ノードは `n000`…(格子点を φ→θ 順、続いてセル中心)、エッジは `e0001`…(lat、lon、diag の順)。
- 30°・φ±60°・cross・1°: ノード108、エッジ300、**総画像数 5,928**(ノード108 + 緯線1,740 + 経線1,392 + 斜め2,688)。cross なしは 3,192。

## 4. 論理参照と配置

| 参照 | 意味 | 解決先(Day1) |
| --- | --- | --- |
| `node(n)` | ノード画像 | `base + frames.node` |
| `node(n)`(low) | 低解像度ノード画像 | `base + frames.nodeLow`(任意) |
| `edge(e, i)` | 途中フレーム(1 ≤ i ≤ frames−2) | `base + frames.edge` |

端点を `edge()` で指定するとエラー。ジョブ/ログ用の安定ID: `n000`、`e0001/0007`(`frame_id`)。

テンプレート構文は `{name}` と `{name:0Nd}` のみ(Python/TS 共通。他はエラー)。プレースホルダは `{node}` `{edge}` `{i}`。

## 5. manifest 構造

```
schema, meta?, coords, camera, image, frames, nodes, edges, start, render?
```

| キー | 内容 |
| --- | --- |
| `coords` | 規約の宣言。リーダーが実装する規約と完全一致しなければ拒否 |
| `camera` | `projection`, `focalMm`, `sensorWidthMm`, `distance`, `pivot` |
| `image` | `width`, `height`, `alpha`(`premultiplied`\|`straight`), `colorSpace`(`sRGB`), `low?`(`{width,height}`: 低解像度ノード画像) |
| `frames` | `codec`(`image-seq`), `format`, `base`, `node`, `nodeLow?`, `edge` |
| `start` | `{ "node": id }`。生成時は (0,0) に最も近いノード |
| `render` | 撮影条件の記録(`graphPreset`、Blender版・サンプル数・シード・ハッシュ等)。ビューアは参照しない |

書き出しは決定的(キー順固定、インデント2、末尾改行、整数値は整数表記)。

## 6. 共通正解データ

- `testdata/manifests/minimal.json`: 3ノード・3エッジ(手書き)。
- `testdata/manifests/grid30_cross.json`: プリセットから生成した正解。Python のテストが再生成して一致を確認する。TypeScript 側も同じファイルを読み、ノード数・エッジ数・総画像数・resolve 結果を検証する。
- `testdata/move_cases/`(予定): 「この位置から、このドラッグで、この位置」を JSON で持つ。

## 7. 撮影作業ディレクトリ(capture work dir)

manifest の外にある撮影側の規約。パッカーはこれを入力にする。

```
manifest.json         撮影開始時の manifest(再開時は同一内容でなければ拒否)
capture.jsonl         1行目 header(manifest の SHA-256)、以降 1画像1行
render_meta.json      撮影条件(Blender版、サンプル数、デノイザー、シード、.blend の SHA-256)
masters/n/{node}.exr
masters/e/{edge}/{i:04d}.exr
```

- `capture.jsonl` の frame 行: `id, theta, phi, path, seconds, bytes, sha256, ts`。
- 完了の判定: ログ行がある **かつ** ファイルが存在し、サイズが一致(`--verify` でハッシュも照合)。
- 書き込みは `*.part.exr` に行い、fsync して rename、最後にログを追記。途中で落ちても最終名の不完全ファイルは残らず、rename 後・ログ前に落ちた画像は撮り直される。
- ログ末尾の途中切れ行は無視する。作業ディレクトリの再開時に残った `*.part.*` は削除する。
- `render_meta.json` の内容は、パッカーが最終 manifest の `render` に取り込む(撮影中は manifest を書き換えない)。

## 8. 移動ロジック(ビューアの純関数)

実装: `viewer/packages/core/src/`(`move.ts` `frameAt.ts` `prefetch.ts`)。正解データ: `testdata/move_cases/*.json`(規則から手計算で作成)。

### 状態

```ts
State   = { pos: Pos, heading: [x,y], acc: [x,y] }
Pos     = { at:'node', node } | { at:'edge', edge, t }   // t は 0..frames-1 の実数(辺の内部は 0<t<frames-1)
heading = 直前に動いた画面方向(単位ベクトル。不明なら [0,0])
acc     = ノードの上で溜めたドラッグ量(px)。辺の上では常に [0,0]
```

### 画面方向

画面は x 右・y 下。右ドラッグで θ 減少、下ドラッグで φ 増加。角度差 (Δθ, Δφ) の画面ベクトルは `(−Δθ·cosφ, Δφ)`。

- 辺の接線 T(t 増加方向)と 1 フレームあたりの角度 L は、**その時点の φ**(辺上では現在の t の φ)で計算する。
- ノードから出る方向は、ノードの φ で計算する(辺の `to` 側から出るときは delta の符号を反転)。

### move(graph, state, drag{dx,dy}, opt) → State

`MoveOpt` 初期値: `degPerPx=0.25`(感度)、`turnPx=12`(曲がりに要るドラッグ量)、`deadZoneDeg=45`、`stickyDeg=15`。

1. **辺の上**: ドラッグを T に射影した s(px)だけを使う(垂直成分は捨てる)。`t += s·degPerPx / L`。端点を超えたら端点のノードで止め、使い切れなかった分(px)を `acc` に持ち越す。
2. **ノードの上**: ドラッグを `acc` に加える。接続辺それぞれの出る方向 u との角度を `acc` から測る。
   - 最小角の辺を best とする。
   - `heading` と `stickyDeg` 以内で揃う辺があれば straight(直進辺)。`acc` との角度が best より `stickyDeg` 以内に収まるなら、best の代わりに straight を選ぶ(ヒステリシス)。
   - 選んだ辺が straight で `acc` との角度が `stickyDeg` 以内なら、そのまま進む(ノードで止まらない)。それ以外は `|acc| ≥ turnPx` が必要(粘り)。
   - 選んだ辺との角度が `deadZoneDeg` を超えるなら動かない(行き止まり。`|acc|` は `turnPx` に切り詰めて、逆向きに戻しやすくする)。
   - 進むときは、その辺の端(`from` なら t=0、`to` なら t=frames−1)に入り、`acc` を辺の上のドラッグとして消費する。
3. 1 回の呼び出しで複数の辺をまたいでよい(上限 64 ホップ)。

×構成の内部ノードは 8 方向なので、最寄りの辺との差は最大 22.5° となり、不感帯は φ 端などの行き止まりでだけ働く。高緯度(φ=60° で cosφ=0.5)では、画面上の 8 方向は均等でなくなる。

### frameAt(graph, pos) → FrameRef

`round(t)`(.5 は切り上げ)を 0..frames−1 に収める。端点ならノード参照、途中なら辺参照。クロスフェードはしない。

### prefetch(graph, state, budget, opt) → FrameRef[]

優先度順で最大 `budget` 件。現在のフレームと重複は含めない。`PrefetchOpt`: `fanFrames=3`、`behindFrames=2`。

- **辺の上**: 進行方向(`heading` と T の内積の符号。`heading` が不明なら t 増加方向)に最大 `ceil(budget/2)` 枚。端点に届けばそのノードまで。続いて、そのノードの他の接続辺の先頭 `fanFrames` 枚を、ランク順に巡回して取る(辺は `heading` に近い順、同角度は辺 ID 順)。最後に後方 `behindFrames` 枚。
- **ノードの上**: 全接続辺の先頭から、同じ巡回順で `budget` まで。

## 8b. パッカー

入力は §7 の作業ディレクトリ、出力は `<out>/manifest.json` + `<out>/<frames.base>…` + `pack.jsonl`。
色変換は DD22、冪等性は DD24。最終 manifest の `render` は `graphPreset` + `capture`(render_meta.json の内容)+ `pack`(AVIF設定、lowWidth、partial)。

## 9. 未確定(後続セッションで決める)

- `render.capture` の具体フィールド(現状は render_meta.json をそのまま取り込む)。
- 影キャッチャーレイヤー(D03)、重点エリア用の `span`/`stride`。
