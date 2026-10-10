# 開発ドキュメント(正)

発案ノート([`../ideas/`](../ideas/README.md))を基に、開発用に確定させた内容。食い違いは本ディレクトリが優先。

- [spec-manifest-v0.md](spec-manifest-v0.md) — manifest / 座標 / グラフ / resolve の仕様(v0)
- [decisions.md](decisions.md) — 開発上の決定ログ(発案ノートからの変更点を含む)

## システムとデータの流れ

アドオン(EXRマスター + manifest) → パッカー(AVIF連番 + 低解像度ノード画像) → ビューア

## リポジトリ構成

```
docs/ideas/        発案ノート(原文)
docs/dev/          開発ドキュメント(正)
python/knokin_core/  bpy非依存コア(標準ライブラリのみ。アドオンとパッカーが共有)
python/tests/      pytest
python/tools/      補助スクリプト(正解manifestの再生成など)
testdata/manifests/  共通正解データ(Python/TypeScript 両側で検証)
testdata/move_cases/ (予定) move/frameAt のテストケースJSON
viewer/            (予定) TypeScript。純関数パッケージ + Vite アプリ
python/packer/, python/addon/  (予定)
```

## 開発の進め方

| セッション | 内容 | 状態 |
| --- | --- | --- |
| 1 | コア: 座標、グラフ、格子プリセット、検証、manifest、resolve、撮影タスク列挙、正解manifest | 完了 |
| 2 | ジョブ状態管理(JSONL、中断再開、tmp→rename)、Blender層(カメラ配置・EXR保存・ヘッドレス) | 未 |
| 3 | ビューア純関数 `move`/`frameAt`/`prefetch` + テストケースJSON | 未 |
| 4 | パッカー | 未 |
| 5 | ビューア描画・入力・計測 | 未 |

## 開発コマンド

```
cd python && pip install pytest && python -m pytest
PYTHONPATH=. python tools/regen_golden.py   # 正解manifestを意図的に更新する時のみ
```
