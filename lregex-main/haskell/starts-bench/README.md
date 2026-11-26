# Haskell で部分文字列マッチの全開始位置を計測する

富家功一朗氏の修士論文・図4.1（論文誌版・図6）で使用された3式について、入力を `a` の `n` 回繰り返しとして、`startPositions` が全開始位置を返すまでの時間を測ります。既定の入力長・反復数は以前の Python 実験に合わせています。

## 実行

[研究の公開リポジトリ](https://github.com/Agnishom/lregex)の `haskell/` に ZIP を展開します。`src/Extracted.hs` と `starts-bench/BenchStarts.hs` がこの配置で読めれば準備完了です。GHC と Python 3 を使います。動作確認した GHC は 9.6.6 です。

```bash
# lregex/haskell/ で実行
unzip haskell-starts-bench.zip
python3 starts-bench/run_benchmark.py
```

ZIP が別の場所にある場合は `unzip` にそのパスを渡してください。リポジトリを新たに取得する場合は次の2行で同じ場所に移動できます。

```bash
git clone https://github.com/Agnishom/lregex.git
cd lregex/haskell
```

元のコードで確認したコミットは `ffff8240e1b46d635974a3c62c7856a19064920a` です。展開先を自由に選ぶ場合は `--src-dir /path/to/lregex/haskell/src` を指定できます。

### 実験条件

| 項目 | 設定 |
|---|---|
| 正規表現 | `(a*)*(?=.*b.*)`、`a*(?=.*b.*)`、`(?=.*a.*)(?=.*b.*)` |
| 入力 | `replicate n 'a'`。既定は 1,000〜20,000 文字、1,000文字刻み |
| 各「式・入力長」の組 | 3回のウォームアップ後に21回を計測し、中央値を求める |
| 測定値 | Haskell の単調時計で取得した経過時間。生データはナノ秒、集計はナノ秒とミリ秒 |
| 正解確認 | この3式はすべて `b` を必要とするため、入力がすべて `a` なら結果は `[]` |

論文の表記 `(?>.*b.*)` は「この境界以降に b がある」という条件です。実験ではこれを Haskell の `LookAhead` で表します。CSV は `(?=.*b.*)`、グラフの凡例は図4.1に合わせて `(?>.*b.*)` と表記します。`a` に関する先読みも同様です。

短い動作確認と、グラフを付けた本計測の例です。グラフを付ける場合のみ、実行する Python 環境に Matplotlib が必要です。

```bash
python3 starts-bench/run_benchmark.py --lengths 1000 2000 --warmups 1 --repetitions 3
python3 starts-bench/run_benchmark.py --warmups 3 --repetitions 21 --output-dir results/haskell_starts --plot
```

### 計測済みの CSV からグラフを描き直す

`--plot-only` に手元の `summary.csv` を指定すると、同じディレクトリの `execution_time.png` を更新します。作図には Python と Matplotlib を使います。同梱の実測例で試すには次を実行してください。

```bash
python3 starts-bench/run_benchmark.py --plot-only starts-bench/example-results/summary.csv
```

研究室サーバーで計測した結果を使う場合は、引数をその実験の `results/haskell_starts/run-.../summary.csv` に置き換えてください。

## ファイル

| ファイル | 役割 |
|---|---|
| `SubstringStarts.hs` | 公開評価器から真になった文字境界を抽出するマッチング関数 |
| `BenchStarts.hs` | 3式の構文木と入力を作り、期待値の確認、ウォームアップ、各試行の計測を行う Haskell プログラム |
| `run_benchmark.py` | 上記の Haskell ファイルと公開元の `Extracted.hs`、`Utils.hs` を GHC の `-O2` オプションで一度ビルドし、各入力長でネイティブ実行ファイルを起動して集計する |
| `example-results/` | 作成時の検証環境で既定の全60条件を実行した結果。実行環境は同梱の `metadata.json` に記載 |

結果は実行したディレクトリの `results/haskell_starts/run-.../` に作成されます。`--output-dir` で親ディレクトリを変更できます。実行ごとに別のフォルダができ、完了時にそのパスが表示されます。

| 出力ファイル | 主な列・内容 |
|---|---|
| `raw_timings.csv` | `regex`、`text_length`、`repetition`（1始まり）、`elapsed_ns`、`match_count` |
| `summary.csv` | 式・入力長ごとの試行数、中央値 `median_ms`、`median_ns`、最小・最大時間、マッチ件数 |
| `metadata.json` | 入力長、反復数、タイマー、計測範囲、CPU、GHCバージョン、ソースの識別情報 |
| `execution_time.png` | `--plot` または `--plot-only` で出力。横軸は文字数、縦軸は実行時間（秒） |

グラフは図4.1と同じ500×700ピクセル（横5対縦7）です。横軸は `Size of string (number of characters)`、縦軸は `Time (seconds)` です。赤・青・緑の丸は各入力長の中央値を秒に換算した値（`median_ns / 1,000,000,000`）です。各色の実線は、入力長が2種類以上あるとき、その系列の中央値に最小二乗法で当てはめた一次近似直線です。左上の凡例では実線に `(poly fit, degree=1)` と添えています。軸の範囲は実測値と近似直線に合わせます。

## 測定に含む処理

```haskell
start <- getMonotonicTimeNSec
positions <- evaluate (force (startPositions regex input))
end <- getMonotonicTimeNSec
```

Haskell は値が必要になった時点で式を評価します。`let positions = startPositions regex input` だけでは、処理が後の出力時まで延びることがあります。`force` はリストの末尾と各整数まで評価するよう指定し、`evaluate` はその評価を時計の2回の読み取りの間に行わせます。`[]` の場合も、真の位置がないことが確定するまでが計測に入ります。

- 計測区間内でオラクル判定表を生成し、本体を逆方向に走査し、全開始位置を列挙します。実行中に発生したランタイムの GC も経過時間に含まれます。
- ビルド、プロセス起動、入力文字列と構文木の準備、明示的な GC、検算、CSV出力・作図は計測区間外です。正規表現は3式の構文木を Haskell で直接構築します。
- 同じ入力を再利用しつつ、各試行では `IORef` から引数を読み直してマッチング関数を呼びます。ウォームアップで評価済みの答えを本計測に使い回さないためです。
- 計測前に、マッチが存在する `"aab"` でも検算します。表の順に開始位置は `[0,1,2]`、`[0,1,2]`、`[0,1]` です。空文字マッチも開始位置に含めます。

富家氏の図4.1では、オラクル接尾辞木の構築と部分木の葉情報を取得する時間を除外しています。今回の Haskell 計測は構文木ができた後の全開始位置の取得時間です。以前の Python 実験の既定値 `--strategy prepared` は内部オラクルを準備した後、本体を走査して真偽値テープを返すまでを計測しています。図を並べる際は各系列にこの計測範囲を併記してください。[富家・寺内、論文誌版の実験条件](https://www.jstage.jst.go.jp/article/jssst/43/3/43_3_37/_pdf/-char/ja)

## Haskell のみで1つの入力長を試す

ランチャーと同じコンパイル設定を手動で試す場合の例です。実行ファイルの引数は順に「文字数、ウォームアップ回数、計測回数」です。標準出力に3式の各試行の結果が出ます。

```bash
# lregex/haskell/ で実行
mkdir -p build/starts
ghc --make -O2 -i -istarts-bench -isrc -outputdir build/starts starts-bench/BenchStarts.hs -o build/starts/bench-starts
./build/starts/bench-starts 1000 3 21
```
