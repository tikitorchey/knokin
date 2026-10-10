# 開発決定ログ

発案ノートの決定ログ(D01〜D11)は有効。ここは開発開始後の追加・変更のみ記す。

| ID | 論点 | 決定 | 理由 |
| --- | --- | --- | --- |
| DD01 | ドキュメントの扱い | 発案ノートは `docs/ideas/` に原文保存し更新しない。正は `docs/dev/` | 発案ノートはアイデアレベルのため |
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
| DD32 | デコード方式 | `createImageBitmap`(既定)と `ImageDecoder` を実行時に切替。`premultiplyAlpha` も切替(premultiply/none/default) | D-測定項目。どちらが速いか・縁が正しいかは実機で決める |
| DD33 | デバッグUI | `?dbg=1` でHUD(遅延/取得/デコードの p50・p95、ヒット率、デコード済み枚数、ヒープ)と MoveOpt/prefetch/キャッシュのスライダー、メトリクスJSONの書き出し | 実機で値を詰める作業を1画面で |
