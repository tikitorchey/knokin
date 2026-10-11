# 決定ログ

曖昧な点は黙って埋めず、ここに記録する(DD を連番で追加)。

## 基本方針(D01〜D11、発案時)

変更すると撮り直しになるものが多い。実測で決める項目は D10 のみ。

| ID | 論点 | 決定 |
| --- | --- | --- |
| D01 | マスター | EXR 16bit float・リニア・RGBA。ビュー変換は焼き込まない |
| D02 | アルファ | プリマルチプライド(Blender の EXR に合わせる) |
| D03 | 背景と影 | 背景は透過。接地影は必要な作品のみ影キャッチャーを別レイヤーで保存(未実装) |
| D04 | シミュレーション | 全フレーム同一時刻に固定し、ベイク済みキャッシュで撮る(方式の前提) |
| D05 | 解像度 | マスターと配信は同一。作品ごとに `image` で宣言。ズームは解像度でなくカメラ軌道の拡張で扱う |
| D06 | 骨組み | 30° 格子・φ ±60°・×(斜め2本)で 8 方向 |
| D07 | 刻み幅 | 1° |
| D08 | 低解像度ノード画像 | v0 に含める(初期表示と先読み用) |
| D09 | θ=0 と入力規約 | カメラ -Y 側、右ドラッグで θ 減少(ビューア側の約束なので後から変更可) |
| D10 | デノイズとシード | **未決**。テスト撮影で、チラつきとノイズの張り付きが少ない方を選ぶ |
| D11 | アドオン運用要件 | 中断再開・欠落検出・フレームごとのハッシュを必須 |

## 開発上の決定(DD)

| ID | 論点 | 決定 | 理由 |
| --- | --- | --- | --- |
| DD01 | ドキュメントの扱い | 発案ノートは廃止。`docs/` の3文書(onboarding / spec / decisions)が正 | 二重管理を避けるため |
| DD02 | ×の中心 | 中心を追加ノードとし、斜め1本を2エッジ(delta ±15, frames 16)に分割 | 「エッジはノードでのみ交わる」と「中心は共有ノード」を両立し、中心で曲がれる |
| DD03 | 総画像数 | 厳密値 5,928(発案ノートの約6,400は概算) | 手計算とテストで確認。撮影時間見積もりは約99時間(1分/枚) |
| DD04 | カメラ姿勢 | pivot を向く(発案ノートの「原点を向く」を修正) | `pivot` と矛盾していたため |
| DD05 | 格子プリセットの斜め指定 | `none` / `cross` を実装、`alternate` は未実装 | 試作は × のみ。サンプルの `alternate` 記載は誤り |
| DD06 | テンプレート | `{node}` `{edge}` `{i:04d}` のみの最小構文 | Python/TS 両側で同一実装にするため |
| DD07 | 低解像度ノード | `frames.nodeLow`(任意)で宣言 | D08 の配置が未定義だったため |
| DD08 | schema と coords の検証 | `schema` 完全一致、`coords` 宣言も完全一致でなければ拒否 | 規約変更に気づけるように |
| DD09 | Python | 3.11 以上、コアは標準ライブラリのみ | Blender 同梱Pythonへの導入不要 |
| DD10 | 完了判定 | ログ行 + ファイル存在 + サイズ一致。ハッシュ照合は `--verify` で任意 | 数千枚の起動時に全再ハッシュすると遅いため |
| DD11 | manifest と撮影条件 | 撮影中は manifest を書き換えず、条件は `render_meta.json` に保存。パッカーが `render` に取り込む | 再開時の manifest 同一性チェック(SHA-256)を保つため |
| DD12 | シード方針の切替 | `--seed-mode fixed|per-frame` を用意。既定は fixed | D10 のテスト撮影で比較できるようにするため |
| DD13 | Blender層の検証 | `pip install bpy`(5.2.2)で実機テスト。bpy がなければスキップ | Blender本体なしで CI/クラウドでも検証できる |
| DD14 | `use_file_extension` | 無効にして `*.part.exr` を厳密なパスで書く | Blender による拡張子の付与・変更を避ける |
| DD15 | move の状態 | `State = {pos, heading, acc}` を純関数の入出力にする(`Pos` だけでは粘り・直進を表せない) | 粘りと直進優先に履歴が必要なため |
| DD16 | 直進の扱い | 直進辺(heading と15°以内)へ進むときは粘りを課さない | 赤道を連続して回すときノードごとに止まるのを避ける |
| DD17 | 不感帯 | 選んだ辺とのずれが45°超なら動かない。×の内部ノードでは発動せず、φ端で効く | 8方向では最大ずれが22.5°のため |
| DD18 | cosφ の適用 | 辺の上は現在の t の φ、ノードから出る方向はノードの φ | 状態を持たずに済み、ノードで連続する |
| DD19 | prefetch の優先順 | 前方 → 端点ノード → 接続辺の先頭(ランク巡回)→ 後方 | 曲がった直後の待ちを減らすため |
| DD20 | TS の構成 | `viewer/` を npm workspaces にし、純関数は `packages/core`(DOM非依存、Vitest) | 描画・入力層を後で別パッケージにできる |
| DD21 | パッカーの依存 | NumPy + Pillow(ネイティブAVIF, ≥11.3)+ OpenEXR(pip)。`OpenImageIO`/`avifenc` は使わない | pip だけで入り、クラウドでも検証できる。ノートの候補は後で差し替え可(読込・書込は関数注入) |
| DD22 | 色変換 | EXR(シーン線形・premultiplied)→ 非premultipliedへ戻す → sRGB OETF → `image.alpha` に従い再乗算 → 8bit。Blender のビュー変換は Standard 前提 | OETF は非線形なので straight 色に掛ける必要がある |
| DD23 | 低解像度の縮小 | premultiplied 空間で LANCZOS。サイズは `image.low = {width,height}` に記録 | 透明部の色が縁に滲むのを避ける |
| DD24 | 冪等性 | `pack.jsonl` に出力ごと {マスターSHA-256, 設定ハッシュ, サイズ}。一致し、ファイルがあれば飛ばす | マスターの撮り直し・設定変更だけを再生成する |
| DD25 | 出力の検証 | 最後に `resolve` から導いた全参照の存在を確認し、足りなければ失敗。出力 manifest は `render.capture`/`render.pack` を取り込む | ビューアが404を踏まないことを撮影側で保証する |
| DD26 | `--partial` | 撮影済みだけをパックし `render.pack.partial=true`。通常は未撮影・破損があると拒否 | テスト撮影(約100枚)のサイズ計測に使う |
| DD27 | AVIF 既定値 | quality 60 / speed 6 / 4:2:0 | 仮置き。4:4:4 とのサイズ・縁の品質比較は実測項目 |
| DD28 | ビューアの構成 | `viewer/packages/app`(Vite・素のTS・Canvas 2D)。入力→move→frameAt→表示を `Controller`(DOM非依存・時計注入)に集約し、Vitestで検証 | 実機がなくても挙動を机上でテストできるように |
| DD29 | キャッシュ | `FrameCache`: 優先順の want リストを毎回置き換え。待機中は破棄、通信中は abort、超過分は未使用・LRU の順で `close()` | メモリ上限(Androidで最大の不確実要素)を設定値で絞れるように。`maxItems`・`concurrency` はスライダーで変更可 |
| DD30 | 未到着時の表示 | 直前のフレームを保持。ノード上では低解像度ノード画像を代役に出す(低解像度は起動時に全ノード先読み) | 白抜け・点滅を避ける。ミスは件数と入力→表示遅延で記録 |
| DD31 | 描画 | 最新の1枚だけを `requestAnimationFrame` で描く。遅延 = ポインタイベント時刻 → 描画直後 | 入力から表示までの実遅延を測るため |
| DD32 | デコード方式 | `createImageBitmap`(既定)と `ImageDecoder` を実行時に切替。`premultiplyAlpha` も切替(premultiply/none/default) | どちらが速いか・縁が正しいかは実機で決める |
| DD33 | デバッグUI | `?dbg=1` でHUD(遅延/取得/デコードの p50・p95、ヒット率、デコード済み枚数、ヒープ)と MoveOpt/prefetch/キャッシュのスライダー、メトリクスJSONの書き出し | 実機で値を詰める作業を1画面で |
| DD34 | `image.alpha` の既定 | **`straight`**(新規撮影)。`premultiplied` で AVIF 化するとパッカーが警告を出す | 実測(Chromium 実デコード、1080p、q60 4:2:0): 縁の帯の PSNR が straight 39.0 dB に対し premultiplied 25.6 dB、最大誤差 44 対 83。premultiplied は「色 ≤ α」が前提で、α≈0 の画素に量子化誤差が出ると色が 255 に飛び、暗い背景で明るい点になる(例: 元 `[0 0 0 0]` → 復号 `[255 0 0 1]`)。straight なら α≈0 の色は表示に効かない。→ measurements.md §3 |
| DD35 | `premultiplyAlpha` の既定 | `createImageBitmap` の `premultiply`(= 現状)のまま。3種(premultiply / none / default)と ImageDecoder は、canvas に合成した結果が同一(PSNR 差 0.1 dB 以内) | 見た目の差は出なかった。速度差は §4 で別に測る。straight の AVIF なら、どのモードでも縁に暗い輪郭は出ない |
| DD36 | 影キャッチャー(D03) | **使わない**。背景は透明のまま、影は付けない | 影キャッチャーは「地面」として不透明物扱いになり、カメラが地面の下に来る φ<0 では被写体が隠れて画像が空になる(確認済み。`measurements/coord-check-shadow-catcher.png` の下段右2枚が空)。φ±60° の仕様と両立しない。接地影が要る作品は、被写体の下に影を焼き込んだ別レイヤーとして φ≥0 の範囲限定で後日検討 |
| DD37 | `--device GPU` | 使える Cycles GPU が無ければ **エラーで止める**(CPU に黙って落ちない)。有効にしたデバイス名は `render_meta.json` の `settings.gpu_devices` に残す | 従来は `cy.device='GPU'` を設定するだけで、環境設定(compute_device_type とデバイスの `use`)が無かったため、GPU 指定でも CPU で撮り続ける実装だった。この環境には GPU が無いため、実GPUでの動作は**未検証**(エラー経路のみ自動テスト) |
| DD38 | シード方針 | 既定 `fixed` を維持。`per-frame` は使わない | 実測(480×270、16spp、θ 1°刻みの6枚): 隣接フレームの残差相関が fixed 0.78 / per-frame 0.04。フレーム間差の RMS は基準(ノイズなし)1.43 に対し、fixed 1.64(+0.20)、per-frame 2.15(+0.72)。per-frame はスクラブ時のちらつきが約3.5倍。デノイズ後は fixed 1.55 / per-frame 1.83 |
| DD39 | 縁の色にじみ(bleed) | `PackSettings.bleed`(straight のみ、α=0 の画素へ縁の色を N px 広げる)を用意するが、**既定は 0** | 実測(4:2:0、q60): bleed=2 で縁の PSNR +1.8 dB に対しサイズ +14%、4 以上はサイズだけ増える。4:4:4 では効果がほぼ無い。割に合わない |
| DD40 | 座標の向き(DD04)の実描画確認 | 仕様どおり。変更なし | Blender 実カメラ(`place_camera` → Cycles)で、非対称テストシーンの8視点を描画し目視: θ=0 でカメラ -Y 側(黄の鼻が手前、赤 +X が右)、θ=90 で +X 側(白い先端が手前、緑 +Y が右)、θ=180 で +Y 側、θ=270 で -X 側。φ=+45 で見下ろし、φ=-45 で見上げ。→ `measurements/coord-check.png` |
| DD41 | AVIF 既定値(DD27 の確定) | quality 60 / speed 6 / 4:2:0 を**維持**。alpha は straight(DD34) | q: 40→60 で縁 +3.5〜4.4 dB(+42〜78%)、60→80 は +1.8〜2.6 dB(+38〜63%)。speed: 4 はエンコード4〜5倍遅でサイズ -3〜8%、8 はサイズ +10〜26% で画質も下がる。4:4:4 はこの2シーンでは +2〜3% サイズで縁 +0.7〜1.9 dB だが、素材が単純であること、デコード +12%、Android ハードウェアデコーダの対応が未確認であることから、実素材と実機で確認するまで 4:2:0 を維持 |
| DD42 | デコード方式の既定(DD32 の確定) | `createImageBitmap`(`premultiply`)を維持。`ImageDecoder` は既定にしない | 1080p・デスクトップ Chromium で、デコードだけで 22.6 ms 対 99.7 ms(p50)、スクリプト操作中の入力→表示遅延 p50 17.5 ms 対 37.5 ms。Android では未確認だが、デスクトップで 4倍差のものを既定にする理由がない |
| DD43 | 計測の入口 | ビューアに URL パラメータ(`decode` `pm` `cache` `conc` `budget` `dpp` `turn` `dead` `sticky` `speed` `tag`)、スクリプト操作(`bench=1` で自動、`run scripted drag` ボタン)、メトリクス JSON のテキスト欄表示を追加。`scripts/measure.mjs` は Playwright で同じ操作を回し、`CPU_SLOWDOWN`/`NET` でエミュレーションできる | 実機で「どの設定で測ったか」が URL だけで再現でき、指で操作せず比較できる。エミュレーションは実機の代わりではなく、傾向確認と回帰検出用 |
| DD44 | パッカーの配信アルファ | 入力(`image.alpha`)が `premultiplied` でも、配信 AVIF は**常にストレート**で出す。最終 manifest の `image.alpha` は `straight`。DD34 の「警告だけ出して premultiplied のまま AVIF 化」は廃止 | DD34 の実測(縁 PSNR 25.6 dB 対 39.0 dB)に加え、Chromium 141 では premultiplied フラグ付き AVIF も `createImageBitmap` の `premultiplyAlpha` も補正に使われず、半透明部が暗く描画された(合成 PSNR 25 dB 対 straight 44 dB、q85)。premultiplied のマスターでも配信物が壊れないよう、パッカー側で変換する。`image.alpha` の撮影既定は DD34 のとおり `straight` |
