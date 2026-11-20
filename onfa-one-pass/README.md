# ONFAによる部分文字列マッチング　1回走査とオラクル行列の事前計算

テキストの各境界について、そこから一致する部分文字列が始まるかを判定します。先読みと本体を同じ走査で評価する方法と、内部の表明を事前評価して本体走査の時間を調べる方法を比較できます。既存の実験プロジェクト（`src/onfa_regex/engine.py` がある構成）で事前計算の実験を行う場合は、`experiments/linear_scaling.py` を差し替えてください。ZIPにはエンジン、テスト、グラフ作成用の `scripts/plot_results.py` も含まれています。

## ONFAとオラクル行列を事前に用意する実験

式を `R`、テキストを `w` とします。この実験の出力は、境界 `i` から始まる `R` の一致があれば真となる `(?=R)` のテープです。`R` はマッチング対象の式そのものを渡します。

1. `(R, w)` ごとに1回、`R` の内部の先読み・後読みを内側から評価してオラクル行列を作り、表明をオラクル参照に置き換えた本体を反転してONFAを構築します。同梱のエンジンでは `engine.prepare_match` がこの準備を担当します。この関数を持たない旧版では、スクリプトが同じエンジンの `EvalAux`、`reverse_ast`、`ThompsonConstruction` を呼びます。
2. 各試行では、準備済みの行列を参照しながら本体ONFAでテキストを右から左へ1回走査します。どちらの版でも計測する処理は `SimulateR2L` によるこの走査と、新たな長さ `len(w)+1` の出力テープの確保・書き込みです。

たとえば `R = a(?=b)`、`w = aba` のとき、入力として準備する `(?=b)` の行は `[False, True, False, False]`、計測中に求める `(?=R)` のテープは `[True, False, False, False]` です。テキストが変わるたびに `prepare_match` を呼びます。

同梱のエンジンをPythonから呼ぶ例です。

```python
from onfa_regex import build_ast, prepare_match

prepared = prepare_match(build_ast("a(?=b)"), "aba")
print(prepared.start_tape())  # [True, False, False, False]
```

Python 3.10以降とLarkを使用します。以前の実験が動いていた環境では、プロジェクトのルートから次のコマンドを実行してください。スクリプトは同じプロジェクトの `src/onfa_regex` を優先して読み込みます。Larkが未導入の環境では、同じPythonで先に `python -m pip install -e .` を実行してください。

```bash
python experiments/linear_scaling.py --repetitions 21 --warmups 3 --output-dir results/run1
```

`--strategy` を省略すると `prepared` が選ばれます。入力はすべて `a` で、3式はいずれも先読みで `b` を要求するため、全条件で `match_count` は0になります。各反復では末尾を含む全境界を評価します。前処理を含む方式と比較するときは、別の出力先を指定します。

```bash
python experiments/linear_scaling.py --strategy baseline --output-dir results/baseline
python experiments/linear_scaling.py --strategy one_pass --output-dir results/one_pass
```

| 実験の指定 | タイマーに入る処理 |
| --- | --- |
| `prepared`（既定） | 構築済みの本体ONFAを走査し、最終テープを作成する。 |
| `baseline` | 内部表明のONFA構築・行列作成、本体ONFAの構築、`prepared` と同じ本体走査を行う。 |
| `one_pass` | 前回の1回走査版。全ONFAを構築し、内部表明と本体を一緒に走査する。 |

計測区間の違いを調べるには `baseline` と `prepared` の同じ式を比較します。3方式共通で、構文解析と入力生成はタイマーの前、一致数の集計はタイマーの後です。`prepared` は従来版で求めた参照テープと、各反復の全境界の真偽値をタイマーの外で照合します。内部表明が `k` 個なら、事前計算した行列は長さ `n+1` の行を `k` 本保持します。

`raw_timings.csv` に各反復、`summary.csv` に入力長別の中央値、`slopes.csv` に直線の傾き（µs/文字）、`metadata.json` に計測範囲と実行環境を保存します。`metadata.json` の `strategy` で選択された方式、`engine_file` で実際に読み込んだエンジンを確認できます。`prepared` の `summary.csv` の `prepare_once_ns` は、その入力でウォームアップ前に1回だけ計った準備時間です。主結果の `median_ns` とは集計方法が異なります。

同梱の `measured/` にこの方式の計測結果があります。入力は `a` の1,000〜20,000文字（1,000刻み）、各条件で3回のウォームアップ後に21回計測しています。今回の結果をグラフにするには `python -m pip install -e ".[experiment]"` の後に `python scripts/plot_results.py results/run1/summary.csv` を実行します。

この条件は、富家氏の先行研究でONFA構築とオラクル行列作成を計測から除いたと仮定した比較です。富家・寺内の論文第4節が明示した除外対象は接尾辞木の構築と部分木の葉の情報取得です。先行手法の比較対象は接尾辞木探索、本実験の比較対象はテキスト上の本体走査です。[富家・寺内の論文](https://doi.org/10.11309/jssst.43.3_37)

## 1回走査版の使い方

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

## 前処理を含む2方式の時間と傾き

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
