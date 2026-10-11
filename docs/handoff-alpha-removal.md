# 実装担当者への依頼: 配信画像からアルファを外し、背景を黒に固定する

以下をそのまま、次の実装セッションの最初のプロンプトとして渡す。決定の根拠は `docs/decisions.md` の DD45・DD46・DD47。

---

あなたは「Knokin」(プリレンダー式ターンテーブル3Dモデルビューア)の開発を担当します。今回の依頼は、**配信画像からアルファを外し、背景を黒に固定する**ための改修です。設計は決まっているので、実装・テスト・文書更新・再測定をお願いします。

## 最初にやること
1. `docs/onboarding.md`、`docs/spec.md`、`docs/decisions.md` を読む。特に **DD45・DD46・DD47**(今回の決定)と、失効する DD34・DD35・DD39・DD44。
2. 動作確認: `cd python && pip install pytest numpy "pillow>=11.3" OpenEXR && python -m pytest`、`cd viewer && npm install && npm test && npm run typecheck`。変更前に全部通ることを確かめる。
3. 作業ブランチはこのセッションの指示に従う。

## 決定事項(変更しない)
- **配信画像(AVIF)はアルファを持たない**(RGB のみ)。マスター(EXR、RGBA、乗算済み)は**変更しない。撮り直しはしない**(DD45)。
- **背景は黒に固定**し、**パック時に黒へ合成**する。`image.background = "#000000"` を manifest に持つ。**黒以外は未対応で、パッカーとビューアは拒否する**。`schema` は `knokin-turntable/0` のまま(DD46)。
- 影は付けない(DD36 は維持)。映り込み・照明は変えない。
- 黒への合成は、**乗算済みリニア RGB にそのまま sRGB OETF を掛ける**だけ(α での除算はしない)。NaN/Inf は 0/1 に丸め、RGB は [0,1] に clip する。
- `image.alpha`: パッカーの出力 manifest は常に `"none"`。入力(撮影側 manifest)の `alpha` には従来値(`premultiplied` / `straight`)が残りうるが、パッカーは値にかかわらずマスターを「乗算済みリニア RGBA」として扱う。
- 範囲外: 黒以外の背景、動画コーデック・コンテナ(zip)への移行(DD47 は方針のみ)。今回は手を付けない。

## 改修一覧

### A. パッカー(`python/knokin_packer/`)
- `color.py`: 乗算済みリニア RGBA → 8bit sRGB **RGB**(黒合成)の関数を追加(例 `encode_rgb8_over_black`)。`encode_rgba8`・`bleed_straight`・`PREMULTIPLIED/STRAIGHT` を撤去(または不要なら削除)。半透明画素は `OETF(乗算済みリニア)` になる点に注意(従来の `OETF(straight) × α` とは値が違う。前者が物理的に正しい)。
- `avif.py`: RGB のまま保存(アルファ面なし)。`downscale` の乗算済み空間処理と `alpha_premultiplied` を撤去し、RGB の LANCZOS 縮小にする。
- `pack.py` / `__main__.py`: `image.alpha` の検証・警告(DD34)を、「入力は無視、出力は `none`」に変更。`image.background` を出力 manifest に書く。manifest に黒以外の `image.background` があれば `PackError`。`PackSettings.bleed` と `--bleed` を撤去。**`PACK_VERSION` を上げる**(既存のパック済み出力が冪等性チェックで再生成されるように)。`render.pack` から `bleed` を外す。
- パックの冪等性・`--partial`・出力検証(DD24〜DD26)は変えない。

### B. manifest と仕様
- `docs/spec.md` §5: `image.alpha` に `"none"` を追加し、`image.background`(黒固定、文字列)を追加する。§3 周辺の説明を DD45・DD46 に合わせる。
- `python/knokin_core/manifest.py`、`viewer/packages/core/src/manifest.ts`: `image.background?: string` の型を追加。読み込みは緩く(キーが無い旧 manifest も受理)、**値があれば `"#000000"` のみ受理**。`schema` の検査は変えない。
- `testdata/manifests/minimal.json`、`grid30_cross.json`: `alpha` を `"none"`、`background` を `"#000000"` に更新。`python/tests/golden.py` と `tools/regen_golden.py` を合わせ、**Python と TS の両側が同じファイルで通る**ことを確認する。

### C. ビューア(`viewer/packages/app/`)
- `render.ts`: 余白の塗り色を `#1b1d22` から manifest の背景(黒)に変更。`checker` 表示と、`main.ts` の `checker bg` スイッチを撤去。キャンバスはすでに `alpha:false` で、そのままでよい。
- `loader.ts` / `main.ts` / `index.html`: `premultiplyAlpha` の切替(`Premultiply` 型、`pm=` URL パラメータ、UI セレクト)を撤去する。不透明画像ではどのモードも同じ結果になるため。`createImageBitmap` は既定の引数でよい。
- `viewer/scripts/premult.mjs` を削除。`measure.mjs` など、`pm` を参照している箇所を直す。
- デコード済みフレームのメモリ(約 7.9 MB/枚、`cacheMax`)は**変わらない**。設計を変えない。

### D. 撮影(Blender 層)
- `scene.py` の `film_transparent=True` は**そのまま**(変更不要)。
- `render_meta.json` の `settings` に背景モード(例 `"background": "film_transparent"`)を記録する(任意、低優先)。
- **要検証(中優先)**: ガラスなど屈折する被写体で、屈折した光線が環境(HDRI)を拾い、黒に合成しても環境が透けて見える場合がある。`python/tools/make_test_scene.py` に、ガラスの球と HDRI(または空のワールド)を含むケースを追加して目視確認する。透けて見えるなら、ワールドのシェーダーで Light Path の Is Camera Ray により、カメラ光線だけ黒にする方法を `scene.py` に入れ、テストで確認する。Blender 本体がない環境では `bpy` の pip モジュールを使う(`pip install bpy==5.2.2`)。使えなければ、手順だけを docs に残して報告する。

### E. 補助ツールとテスト
- `python/tests/test_packer.py`: アルファ関連(`test_color_transfer_and_alpha`、`test_straight_alpha_manifest`、`test_output_is_always_straight_alpha`、bleed のテスト)を置換する。新しいテスト: (1) 半透明画素が `OETF(乗算済みリニア)` に一致する、(2) 出力 AVIF にアルファ面がない(Pillow で開いて mode が `RGB`)、(3) 出力 manifest の `image.alpha == "none"` と `image.background == "#000000"`、(4) 黒以外の背景で拒否、(5) 冪等性が `PACK_VERSION` の変更で再生成される。
- `python/tools/make_test_manifest.py`: `--alpha` の既定を `none`(撮影側の manifest に従来値を残すなら、その旨をコメントに)。
- `python/tools/codec_bench.py`: アルファ分離(別ストリーム)の比較軸と、アルファ PSNR を削除し、RGB のみの比較にする。指標は「黒合成した正解との PSNR」。AVIF の比較基準は RGB。
- `python/tools/make_premult_truth.py` を削除。`bench_pack.py` は縁の帯 PSNR ではなく、黒合成との PSNR を出す。
- `python/tools/make_synthetic_capture.py`: RGBA マスターのまま。ビューアで黒背景になることを確認する。

### F. 文書
- `docs/decisions.md`: DD45〜DD47 は追記済み。実装中に新しい曖昧点が出たら、DD48 以降として追記する(黙って決めない)。
- `docs/measurements.md`: §3 の AVIF 数値は「アルファ込みの値」と注記する。再測定したら、新しい節を足して結果を記録する(元の数値は残す)。
- `docs/system-packer.md`、`docs/system-viewer.md`、`docs/android-measurement.md`、`docs/onboarding.md`、`docs/research-compression.md`: アルファ・`pm`・`checker bg`・`premult.mjs`・bleed に関する記述を整理する。`research-compression.md` には、アルファ分離の課題が消えたことを追記する。

## 再測定(黒合成の RGB AVIF で)
Blender 本体と実素材がなくても、既存のテストシーン(`make_test_scene.py`、`--busy`)で測れる範囲を測る。測れない項目は「未実施」と書く(推測で数値を作らない)。

1. 容量(KB/枚)と PSNR: quality 40/60/80、speed 6、**4:2:0 と 4:4:4**(DD41 の前提はアルファ縁だった。黒背景で結論が変わるか)。
2. デコード時間(`createImageBitmap`、1080p、デスクトップ Chromium): 従来の p50 22.6 ms から変わるか(DD42)。
3. 暗部のバンディング: 黒の近くのなめらかな暗い勾配の画像で、8bit sRGB の段差が目立たないか(目視+勾配のテスト画像)。
4. 結果が従来の決定(DD41・DD42)を変えるなら、新しい DD として記録する。

## 守る原則(`docs/onboarding.md` と同じ)
- ファイル名は `resolve` 経由のみ。骨組みはグラフのみ。カメラ条件・座標規約は変えない。
- 撮影中の manifest は書き換えない。曖昧な点は DD として記録する。
- Python と TypeScript は `testdata/` の共通正解データで一致を保つ。
- コミットは小さく、テストを通してから。

## 完了の条件
- Python・TS の全テストと型検査が通る。
- `make_synthetic_capture.py` → パッカー → ビューアで、黒背景の表示が Chromium で確認できる。
- 上の再測定の結果(または未実施の理由)が `docs/measurements.md` に残っている。
- アルファ関連の撤去漏れがない(`git grep -niE "premult|bleed|straight|checker"` で、失効を明記した文書以外に残っていない)。
