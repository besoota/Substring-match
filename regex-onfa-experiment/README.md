# ONFA linear-scaling experiment

正規表現を固定し、テキスト `a^n` の長さを
`1000, 2000, ..., 20000` と変化させて、ONFAによる部分文字列マッチングの
実行時間が `n` に対して線形に増加するかを調べるプロジェクトです。

## ファイル構成

```text
regex-onfa-experiment/
├── src/onfa_regex/
│   ├── __init__.py
│   └── engine.py
├── experiments/
│   └── linear_scaling.py
├── scripts/
│   └── plot_results.py
├── tests/
│   └── test_engine.py
├── notebooks/
│   └── regex_search-lookaround-exp.ipynb
├── results/
│   └── .gitkeep
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

- `engine.py`: Larkによる構文解析、AST、Thompson構成、Oracle処理、ONFAシミュレーション
- `linear_scaling.py`: 反復測定とCSV・実行環境情報の保存
- `plot_results.py`: グラフ、対数傾き、倍増比の作成
- `test_engine.py`: 純粋正規表現と4種類のlookaroundの基本テスト
- `notebooks/`: 元のNotebookを参照用として保存

## サーバー上での準備

```bash
git clone <repository-url>
cd regex-onfa-experiment

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

インストールされた正確なライブラリのバージョンも保存する場合は、実験前に次を実行します。

```bash
python -m pip freeze > environment-lock.txt
```

## 正しさの確認

実験前にテストを通します。

```bash
pytest
```

## 実験の実行

```bash
python experiments/linear_scaling.py \
  --repetitions 21 \
  --warmups 3 \
  --output-dir results/run1
```

テキスト長は次の20条件で固定されています。

```python
list(range(1_000, 20_001, 1_000))
```

正規表現は次の7条件です。

| 条件 | 正規表現 |
|---|---|
| リテラル | `aa` |
| Kleene star | `aa*` |
| 肯定先読み | `a(?=a)` |
| 肯定後読み | `(?<=a)a` |
| 否定先読み | `a(?!b)` |
| 否定後読み | `(?<!b)a` |
| 入れ子の先読み | `a(?=a(?=a))` |

特定の条件だけ測定することもできます。

```bash
python experiments/linear_scaling.py \
  --patterns literal positive_lookahead \
  --output-dir results/pilot
```

## 測定範囲

主実験では正規表現文字列をLarkでASTへ変換する処理を測定に含めません。
各正規表現についてASTを1回だけ作成し、各反復では次を測定します。

1. `Context` の生成
2. 再帰的なlookaround評価とOracleテープ作成
3. Thompson構成
4. ONFAシミュレーション

入力文字列 `"a" * n` の生成、結果の `sum()`、CSV出力も測定区間外です。

## 出力ファイル

実験後、指定したディレクトリに以下が生成されます。

```text
results/run1/
├── raw_timings.csv
├── summary.csv
└── metadata.json
```

- `raw_timings.csv`: 各反復の測定値
- `summary.csv`: 各条件の中央値、四分位数、1文字当たりの時間など
- `metadata.json`: Python、OS、ライブラリ、コミット、実験条件

## グラフと分析値の作成

サーバーに画面がなくてもPNGを生成できます。

```bash
python scripts/plot_results.py results/run1/summary.csv
```

次のファイルが追加されます。

```text
results/run1/
├── execution_time.png
├── time_per_character.png
├── log_log_execution_time.png
├── complexity_estimates.csv
└── doubling_ratios.csv
```

線形性は次の観点から確認します。

- `execution_time.png` がおおむね直線になる
- `time_per_character.png` が大きい `n` でほぼ一定になる
- `complexity_estimates.csv` の推定指数が1に近い
- `doubling_ratios.csv` の `T(2n) / T(n)` が2に近い

## 実験上の注意

- 正規表現は固定し、独立変数はテキスト長 `n` だけにする
- 提案手法の比較は同じサーバー、同じPython環境で行う
- 共有サーバーでは割り当てられたCPUまたはジョブ管理システムを使用する
- 最初は反復回数を減らしたpilot実験を行う
- 本実験のCSVと `metadata.json` は削除せず保管する

