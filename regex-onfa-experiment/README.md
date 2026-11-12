# ONFA linear-scaling experiment

正規表現を固定し、文字列`aaa…a`(`a^n`)の部分文字列マッチングを行う。
対象とする正規表現は, `(a*)*(?=.*b.*)`, `a*(?=.*b.*)`, `(?=.*a.*)(?=.*b.*)`の3つとする。

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

- `engine.py`: 構文解析、AST、Thompson構成、ONFAシミュレーション
- `linear_scaling.py`: 反復測定とCSV・実行環境情報の保存
- `plot_results.py`: グラフ作成
- `test_engine.py`: 基本テスト
- `notebooks/`: 元のNotebook

## サーバー上での準備
```bash
git clone <repository-url>
cd regex-onfa-experiment

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 事前テスト
実験前にテストを通します。
```bash
pytest
```

## 実験
```bash
python experiments/linear_scaling.py \
  --repetitions 21 \
  --warmups 3 \
  --output-dir results/run1
```
同じ条件で, 21回測定する。（最初の3回は記録しない）
```python
list(range(1_000, 20_001, 1_000))
```
```bash
python experiments/linear_scaling.py \
  --patterns literal positive_lookahead \
  --output-dir results/pilot
```

## 測定範囲
入力文字列をASTに変換する処理は測定に含めない。
各正規表現についてASTを1回だけ作成し, 各反復では以下を測定する。
1. `Context` の生成
2. 再帰的なOracleテープ作成
3. Thompson構成
4. ONFAシミュレーション

## 出力ファイル

実験後, 指定したディレクトリに以下が生成される。
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
PNGを生成する。
```bash
python scripts/plot_results.py results/run1/summary.csv
```
以下のファイルが追加される。
```text
results/run1/
├── execution_time.png
├── time_per_character.png
├── log_log_execution_time.png
├── complexity_estimates.csv
└── doubling_ratios.csv
```

