# パッカー仕様(EXR → AVIF 連番)

現在の実装の記述。経緯は [research-notes.md](research-notes.md)。実装: `python/knokin_packer/`。

## 1. 役割と入出力

- 入力: 撮影作業ディレクトリ(`manifest.json`、`capture.jsonl`、`masters/**/*.exr`。`system-capture.md`)
- 出力: `<out>/manifest.json`(最終 manifest)、`<out>/<frames.base>…`(AVIF)、`<out>/pack.jsonl`(冪等性ログ)
- 出力は**ビューアがそのまま読める配置**(`frames.base` 以下に `n/`、`n-low/`、`e/`)。`<out>/` を静的配信すればよい。

```
python -m knokin_packer --workdir out/ --out dist/ \
   [--quality 60] [--speed 6] [--subsampling 4:2:0|4:4:4] [--low-width 480] [--bleed 0] [--partial] [--verify-masters]
```

依存: NumPy、Pillow ≥ 11.3(ネイティブ AVIF)、OpenEXR(pip)。`avifenc` / OpenImageIO は使わない(DD21。読み込み・書き込みは関数として注入できるので後で差し替え可)。

## 2. 処理の流れ

1. manifest を読み、`image.alpha` / `colorSpace=sRGB` / `frames.format=avif` を検証する。`image.alpha='premultiplied'` なら**警告**を出す(DD34)。
2. `capture.jsonl` が**その manifest のもの**か確認する(SHA-256)。
3. マスターの存在・サイズを走査する(`--verify-masters` でハッシュも照合)。未撮影・破損があれば**拒否**。`--partial` なら撮影済みだけをパックする(DD26)。
4. 出力計画を作る: 全タスク → フルサイズ画像1枚。ノードには追加で低解像度画像(`--low-width` が 0 でなければ)。
5. 各出力を、`resolve` が返すパスに書く。最後に**`resolve` から導いた全参照のファイルが存在すること**を確認し、足りなければ失敗する(ビューアが 404 を踏まないことを撮影側で保証、DD25)。

## 3. 色と画素(`color.py`、DD22)

EXR(シーン線形・アルファ乗算済み)→ 8bit sRGB RGBA:

1. NaN/Inf を 0/1 に、α を [0,1] に丸める。
2. 乗算済みの色を α で割って **straight** に戻す(α ≤ 1e-6 の画素は色 0)。
3. straight 色に sRGB OETF を掛ける(OETF は非線形なので、straight 色に掛ける必要がある)。
4. `image.alpha` に従う: `straight` はそのまま、`premultiplied` は α を再乗算。
5. 8bit に丸める。

**`image.alpha` は新規撮影では `straight` を使う**(DD34)。premultiplied で AVIF にすると、α≈0 の画素の量子化誤差で色が飛び、縁が汚れる(縁の PSNR が 25.6 → 39.0 dB)。

## 4. 低解像度ノード画像(DD23、DD07)

- ノードごとに1枚。`--low-width`(既定 480)に縮小。サイズは最終 manifest の `image.low = {width,height}` に記録し、`frames.nodeLow` を宣言する。`--low-width 0` で無効(`nodeLow` / `image.low` を出力しない)。
- 縮小は **premultiplied 空間で LANCZOS**(透明部の色が縁に滲まない)。
- ビューアは起動時に全ノードの低解像度を先読みし、フル画像が未到着のときの代役に使う(`system-viewer.md`)。
- **エッジには低解像度は無い**(1枚を全エッジで共有するのはノード画像のみ)。

## 5. AVIF 設定(DD27 → DD41)

| 設定 | 既定 | 備考 |
| --- | --- | --- |
| `--quality` | 60 | 40→60 で縁 +3.5〜4.4 dB(サイズ +42〜78%)、60→80 は +1.8〜2.6 dB(+38〜63%) |
| `--speed` | 6 | 4 はエンコード 4〜5倍遅でサイズ -3〜8%、8 はサイズ +10〜26% で画質低下 |
| `--subsampling` | 4:2:0 | 4:4:4 は単純なテストシーンで +2〜3% サイズ/縁 +0.7〜1.9 dB、デコード +12%。実素材・Android で要確認 |
| `--bleed` | 0 | straight のみ。α=0 の画素へ縁の色を N px 広げる。2px で縁 +1.8 dB / +14% サイズ。割に合わず既定 OFF(DD39) |

数値の根拠と条件は [measurements.md](measurements.md) §3。**容量は被写体と素材で大きく変わる**(テスト2シーンで 12〜37 KB/枚)ので、実作品のテスト撮影で `--partial` パックし、KB/枚 × 5,928 で見積り直す。

## 6. 冪等性(DD24)

`pack.jsonl` に出力ごと `{key, path, bytes, src_sha256, settings(ハッシュ), w, h}` を追記する。**ファイルが存在し、サイズ・ソース(マスター)の SHA-256・設定ハッシュが一致すれば飛ばす**。マスターの撮り直しや設定変更があった出力だけが作り直される。`*.part.avif` に書いて rename。途中切れの最終行は無視する。設定ハッシュは `PackSettings` 全体(AVIF 設定、低解像度幅、`partial`、`bleed`)。

## 7. 最終 manifest(DD25)

撮影時の manifest をもとに、`frames.nodeLow` / `image.low`(低解像度ありのとき)と `render.capture`(= `render_meta.json` の内容)と `render.pack`(AVIF 設定、`lowWidth`、`bleed`、`partial`)を加えて、決定的な書式で書く。`--partial` のときは `render.pack.partial=true`。

## 8. 既知の制約・注意

- `--partial` の出力は辺が途中で欠けるため、**ビューアの操作確認には使えない**(容量・画質の計測用)。
- Pillow の AVIF デコードは乗算済みで返す(`alpha_premultiplied` で保存したものを展開しても straight に戻らない)。テストで画素を比べるときは保存時と同じ alpha 規約で比べる。
- AVIF の色空間は sRGB 固定(`colorSpace='sRGB'` 以外は拒否)。HDR は対象外。
- 4:4:4 を Android のハードウェアデコーダが扱えるかは未確認。
