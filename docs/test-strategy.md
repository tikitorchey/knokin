# 実測テストの戦略(縮小版)

本番(5,928枚 × 1920×1080)をこの環境で撮ると、実測で約26時間かかる(CPU 4コア、後述)。そこで、**何を測りたいか**ごとに規模を落とす。数値は必ず「どの環境・どの規模で測ったか」を添えて記録する。

## 環境(2026-10 時点の開発セッション)

| 項目 | 内容 |
| --- | --- |
| Blender | `pip install bpy==5.2.2`(Blender 本体の GUI なし。Cycles / OIDN は本物) |
| CPU | 4コア / RAM 15GB |
| GPU | なし(`--device GPU` はエラーで止まることだけ確認。GPU 実測は未実施) |
| ブラウザ | Playwright 同梱の Chromium(headless、デスクトップ向け) |
| Android 実機 | なし(手順と計測入口だけ用意。`measurements-viewer.md` 参照) |

## 縮小の方針

| 目的 | 規模 | 理由 |
| --- | --- | --- |
| 座標の目視確認 | 480×270、8視点 | 向きの確認に解像度は要らない |
| 撮影時間・容量・ノイズの比較 | 480×270、12枚、サンプル数 4〜128 | 同じ12枚を全条件で撮り、高サンプル(512)を基準に PSNR で比較 |
| 実規模の撮影コスト | **本番グラフ**(30°・1°・×、5,928枚)から100枚を均等抽出(`--test-shoot 100`)、1920×1080、32spp | 実際の解像度での1枚あたり時間・EXR容量・AVIF容量が取れ、5,928枚へ換算できる |
| パック品質 | 上の100枚(1080p)を `--partial` でパック | AVIF の quality/speed/サブサンプリング、縁の品質、総容量 |
| ビューア挙動 | 縮小グラフ(60°・10°刻み・×、276枚)を **全部** 撮る | 辺をたどる操作はグラフが閉じている必要がある。枚数だけ減らす |
| Android | 未実施 | 端末がない。`?dbg=1&bench=1` で同じ操作を再現できるようにしてある |

縮小グラフは `python tools/make_test_manifest.py out.json --cell 60 --step 10`。構造は本番と同じ(格子+×、30ノード・78エッジ)で、角度の刻みだけ粗い。

## この環境で測れないこと(推測で埋めない)

- GPU(OptiX/CUDA/HIP)での撮影時間。
- Android 実機の遅延・デコード時間・メモリ・`ImageDecoder` の速度。デスクトップ Chromium の値は参考にとどめる。
- 実際の作品シーン(被写体の複雑さ、反射、髪・半透明)でのサンプル数。テストシーンは単純なので、**必要サンプル数は実シーンで再測定が必要**。
- 操作感(`degPerPx` 等)。実機で指を動かさないと決められない。

## 再現コマンド

```
cd python
python tools/make_test_scene.py /tmp/k/scene.blend [--shadow-catcher]
python tools/coord_check.py /tmp/k/scene.blend sheet.png
python tools/bench_capture.py --blend /tmp/k/scene.blend --out /tmp/k/bench
python tools/bench_seed.py /tmp/k/scene.blend --spp 16 [--denoise]
python tools/make_test_manifest.py /tmp/k/m_real.json --cell 30 --step 1 --width 1920 --height 1080
python addon/run_capture.py -- --blend /tmp/k/scene.blend --manifest /tmp/k/m_real.json --workdir /tmp/k/w_real --test-shoot 100 --samples 32
```

(`bpy` モジュールで走らせるときは `--blend` が要る。Blender 本体なら `blender -b scene.blend -P python/addon/run_capture.py -- ...` で従来どおり。)
