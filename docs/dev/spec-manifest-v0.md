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
| `image` | `width`, `height`, `alpha`(`premultiplied`), `colorSpace`(`sRGB`) |
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

## 8. 未確定(後続セッションで決める)

- `move` の規則詳細(`MoveOpt`、`Heading`、不感帯の定義、cosφ の適用位置)。
- `render` の具体フィールド、マスター(EXR)の配置、JSONLログの形式。
- 影キャッチャーレイヤー(D03)、重点エリア用の `span`/`stride`。
