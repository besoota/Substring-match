# ONFAによる部分文字列マッチング　1回走査版

テキストの各境界について、そこから一致する部分文字列が始まるかを判定します。先読みだけを含む式では、テキストを右から左に1回読み、先読みと本体を同じ走査で評価します。実装は `src/onfa_regex/engine.py` にあります。既存の実験プロジェクトに組み込む場合は、同じパスのファイルと差し替えられます。

## 使い方

Python 3.10以降で、展開したディレクトリから `python -m pip install -e .` を実行します。

```python
from onfa_regex import build_ast, evaluate_ast, substring_match

pattern = "(?=.*a.*)(?=.*b.*)"
print(substring_match(pattern, "aba"))              # [0, 1]
print(evaluate_ast(build_ast(pattern), "aba"))      # [True, True, False, False]
print(substring_match("(?!.)", "aba"))              # [3]  末尾での空一致
```

`substring_match` は開始位置を昇順で返します。`evaluate_ast` は既定で開始位置の真偽値を長さ `n+1` のリストで返します。位置は0から数え、最後の位置 `n` は末尾の文字の直後です。先読みは `(?=r)`、否定先読みは `(?!r)` と書きます。`.` は改行を含む任意の1文字に一致します。

| `strategy` | 開始位置を求めるときの動作 |
| --- | --- |
| `"auto"`（既定） | 後読みを含まない式を右から左へ1回走査します。後読みを含む式は各表明の全位置のテープを使って評価します。 |
| `"baseline"` | 従来どおり、各表明について全位置のテープを作り、親のONFAから参照します。 |
| `"one_pass"` | 1回走査を指定します。本体と走査方向の異なる表明があれば例外 `ValueError` が発生します。 |

後読みだけを含む式について終了位置のテープが必要な場合は、`evaluate_ast(ast, text, direction=Direction.L2R)` と指定できます。`Direction` は `onfa_regex` からインポートできます。低水準の `Eval(direction, ast, text, context)` は従来のテープを `context` に保存します。

## 図5と実装の対応

原論文の図5は後読みを左から右に評価し、先読みには対称な手順を用いると説明しています。この実装では部分文字列の開始位置を求めるため、先読みを右から左に評価します。図5の入力の接頭辞に対する判定を部分文字列に適用するため、各境界で各ONFAの開始状態を加え、部分文字列のもう一方の端を自由に選べるようにしています。

1. `_lower_lookarounds` が入れ子の内側から表明に番号を振り、親の式にはその番号を参照するオラクル遷移を置きます。
2. `_simulate_one_pass` が各境界で、内側の表明、外側の表明、本体の順に状態集合を更新します。表明の受理状態から得た真偽値を同じ境界の親に渡します。否定表明では遷移時に真偽を反転します。
3. 次の境界に持ち越すのは各ONFAの到達状態です。全位置について保存するのは本体の出力テープ1本です。式の大きさを `m`、入力長を `n` とすると、1回走査の時間は `O(m(n+1))`、出力を除く作業領域は `O(m)` です。

たとえば `(?=.*a.*)(?=.*b.*)` の入力走査は、先読み2回と本体1回の計3回から1回になります。更新版でも各境界で3個のONFAの状態集合を更新するため、実行時間が3分の1になるとは限りません。

出典は Konstantinos Mamouras and Agnishom Chattopadhyay, *Efficient Matching of Regular Expressions with Lookaround Assertions*, POPL 2024, §5.2, Fig. 5, pp. 92:22–92:23 です。[DOI](https://doi.org/10.1145/3632934)

## 同じ条件で時間と傾きを比較する

```bash
python experiments/linear_scaling.py --strategy baseline --output-dir results/baseline
python experiments/linear_scaling.py --strategy one_pass --output-dir results/one_pass
```

入力は `a` を1,000文字から20,000文字まで1,000文字刻みで繰り返したものです。各条件で3回ウォームアップし、21回の実測値の中央値を取ります。対象は `(a*)*(?=.*b.*)`、`a*(?=.*b.*)`、`(?=.*a.*)(?=.*b.*)` の3式です。各反復で評価の準備、Thompson法による全ONFAの構築、走査、出力テープの作成を計測します。構文解析、テキスト生成、一致数の集計、ファイル出力は計測区間の外です。

両出力先の `slopes.csv` にある `slope_us_per_character` を同じ `regex` 同士で比較できます。傾きは、全20点の中央値に切片付き直線を最小二乗法で当てはめた値（µs/文字）です。`raw_timings.csv` は各反復の時間、`summary.csv` は各入力長の中央値と四分位数、`metadata.json` は実行環境と計測条件を記録します。

グラフを作成する場合と、正しさのテストを実行する場合のコマンドは次のとおりです。

```bash
python -m pip install -e ".[experiment,test]"
python scripts/plot_results.py results/baseline/summary.csv
python scripts/plot_results.py results/one_pass/summary.csv
python -m pytest -q
```
