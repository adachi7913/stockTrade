# stockTradeプロジェクト

## プロジェクト構造

``` text
stockTrade/
├── bin/              # 実行ファイル（.py）を格納
│   ├── daily/           # 日次実行系
│   │   ├── daily_update.py          # 立花証券APIを使用した日次株価更新
│   │   ├── daily_update_yfinance.py # yFinanceを使用した日次株価更新（現在は非使用）
│   │   ├── auto_sell_stock.py       # 自動売却機能
│   │   └── purchase_stock.py        # 自動購入機能
│   ├── test/            # テスト実行系
│   │   ├── test_tachibana_api.py    # 立花証券APIのテスト
│   │   └── test_entry_repository.py # EntryRepositoryのテスト
│   └── tools/           # その他のツール系
│
├── batch/            # バッチファイル（.bat）を格納
│   ├── daily/           # 日次実行系のバッチ
│   │   ├── run_daily_update.bat     # 日次株価更新の実行
│   │   ├── auto_sell_stock.bat      # 自動売却機能の本番実行（対話モード）
│   │   └── purchase_stock.bat        # 自動購入機能の本番実行
│   ├── test/            # テスト実行系のバッチ
│   │   └── auto_sell_stock_simulation_test.bat  # 自動売却機能のシミュレーション実行
│   └── purchase_stock_test.bat   # 自動購入機能のテスト実行
│
├── lib/              # ライブラリ
│   ├── tachibana_stock_api_base.py  # 立花証券API基本機能
│   ├── jquants_api.py               # jQuants API連携
│   ├── gemini_api.py                # Gemini API連携
│   └── edinet_api.py                # EDINET API連携
├── service/          # サービス層
│   ├── stock_service.py             # 株価データ処理サービス
│   ├── gemini_service.py            # AI判断サービス
│   ├── entry_service.py             # 売買エントリーサービス
│   └── browser_service.py           # ブラウザ操作サービス
├── utils/            # ユーティリティ
│   ├── technical_indicators.py      # テクニカル指標計算
│   ├── stock_utils.py              # 株式関連ユーティリティ
│   ├── logger.py                   # ログ管理
│   └── config.py                   # 設定管理
├── repository/       # データアクセス層
│   ├── stock_repository.py         # 株価データリポジトリ
│   ├── entry_repository.py         # エントリー情報リポジトリ
│   └── db_connection.py           # データベース接続管理
├── log/              # ログファイル
└── README.md
```

## 実行方法

### 日次株価データ更新

```batch
# バッチファイルを実行
batch/daily/run_daily_update.bat
```

### 立花証券APIテスト

```batch
# テスト用バッチファイルを実行
batch/test/run_tachibana_test.bat
```

### 自動売却機能

```bash
# 通常実行（対話モード）
python bin/daily/auto_sell_stock.py

# テストモード（売却を実行しない）
python bin/daily/auto_sell_stock.py --test

# 強制売却モード（確認なしで売却）
python bin/daily/auto_sell_stock.py --force-sell

# デバッグモード
python bin/daily/auto_sell_stock.py --debug
```

### 自動購入機能

```batch
# 本番実行
batch/daily/purchase_stock.bat

# テスト実行（購入をシミュレーション）
batch/test/purchase_stock_test.bat

# テストモードの取引履歴表示
python bin/daily/purchase_stock.py --show-history

# テストモードのサマリー表示
python bin/daily/purchase_stock.py --show-summary

# テストデータのリセット（初期資金200万円）
python bin/daily/purchase_stock.py --reset-test --initial-funds 2000000
```

### 自動購入機能のコマンドライン引数

#### 実行モード関連

- `--test`: テストモードを有効化。実際の購入処理をスキップし、シミュレーションのみ実行
- `--debug`: デバッグモードを有効化。詳細なログを出力

#### テストデータ管理

- `--show-history`: テストモードでの取引履歴を表示
- `--show-summary`: テストモードでの取引サマリー（損益、勝率など）を表示
- `--reset-test`: テストデータをリセット
- `--initial-funds <数値>`: テストデータリセット時の初期資金を指定（デフォルト: 1,000,000円）

#### AI判断制御

- `--max-calls <数値>`: AI判断を行う最大銘柄数を指定（デフォルト: 50件）
- `--min-score <数値>`: エントリー候補とする最低スコアを指定（デフォルト: 70.0）
- `--api-delay <秒数>`: AI API呼び出し間の待機時間を指定（デフォルト: 30秒）

#### 使用例

```bash
# テストモードで実行（購入シミュレーション）
python bin/daily/purchase_stock.py --test

# テストモードで実行（AI判断10件、最低スコア80）
python bin/daily/purchase_stock.py --test --max-calls 10 --min-score 80

# テストデータをリセットして初期資金200万円で開始
python bin/daily/purchase_stock.py --reset-test --initial-funds 2000000

# テストモードの取引履歴を確認
python bin/daily/purchase_stock.py --show-history

# デバッグモードで本番実行
python bin/daily/purchase_stock.py --debug
```

#### コマンドライン引数

- `--max-calls <数値>`: AI判断の最大件数（デフォルト: 50件）
- `--min-score <数値>`: エントリースコアの最低値（デフォルト: 70.0）
- `--api-delay <秒数>`: API呼び出し間の待機時間（デフォルト: 30秒）
- `--test`: テストモードの有効化（実際の購入処理をスキップ）
- `--show-history`: テストモードの取引履歴を表示
- `--show-summary`: テストモードのサマリーを表示
- `--reset-test`: テストデータをリセット
- `--initial-funds <数値>`: テストデータリセット時の初期資金（デフォルト: 1,000,000円）

#### 環境変数による制御

1. **必須の環境変数**
   - `GEMINI_API_KEY`: Gemini APIのアクセスキー
   - `GEMINI_PRO_MODEL`: 使用するモデルのバージョン
   - `DB_HOST`: データベースホスト
   - `DB_NAME`: データベース名
   - `DB_USER`: データベースユーザー
   - `DB_PASSWORD`: データベースパスワード

2. **処理制御用環境変数**
   - `STOCK_TEST_MODE`: テストモードの制御（'true'/'false'）
   - `USE_SIMPLIFIED_PROMPT`: 簡略化プロンプトの使用（'true'/'false'）
   - `STOP_PRICING_FLAG`: 価格取得処理の停止フラグ（'y'/'n'）
   - `PRICING_PROCESS_DONE`: 価格取得処理の完了フラグ（'y'/'n'）
   - `INDICATOR_PROCESS_DONE`: インジケーター計算処理の完了フラグ（'y'/'n'）

#### 動作モード

1. **通常モード**
   - 実際の購入処理まで実行
   - ブラウザ操作を含む
   - エントリー情報をDBに保存

2. **テストモード**
   - 購入処理をシミュレーションのみ
   - ブラウザ操作なし
   - テストフラグ付きでエントリー情報を保存

#### 処理フロー

1. エントリー候補の取得
2. 基本フィルタリングによる候補の絞り込み
3. 候補のスコアリングと上位候補の選択
4. AIによるエントリー判断
5. 推奨された候補の購入処理実行

#### 注意事項

- テストモードでは実際の購入は行われません
- API呼び出しには適切な間隔（デフォルト30秒）が必要です
- エントリースコアが最低値（デフォルト70.0）未満の候補は除外されます
- 環境変数の設定は`.env`ファイルで管理することを推奨します

### マテリアライズドビューの更新

```batch
# バッチファイルを実行
batch/daily/refresh_views.bat
```

### 自動売却機能のシミュレーション

```batch
# テスト用バッチファイルを実行
batch/test/auto_sell_stock_simulation_test.bat
```

## 自動売却機能について

### 概要

自動売却機能（`auto_sell_stock.py`）は、保有株式の評価と売却判断を自動化するツールです。以下の特徴があります：

- AIによる総合的な評価（Gemini API使用）
- テクニカル指標による判断
- 損益率に基づく判断
- 対話的な売却確認機能

### 評価基準

1. **AIによる総合評価**
   - トレンド分析（一目均衡表、MACD）
   - モメンタム（RSI、ストキャスティクス）
   - ボラティリティ（ボリンジャーバンド、ATR）
   - 出来高分析
   - 現在の株価位置

2. **テクニカル指標による判断**
   - RSI > 70: 過買いによる売却シグナル
   - RSI < 30: 過売りによる保持シグナル
   - MACDデッドクロス: 売却シグナル

3. **損益率による判断**
   - 損失 5%以上: 売却シグナル
   - 利益 10%以上: 利益確定売却シグナル

### 出力情報

- 保有銘柄の評価サマリー
- 売却候補一覧
- 売却実行結果

### 自動売却機能の注意事項

- 売却判断は確信度（confidence_score）が500以上の場合のみ有効
- テストモードでは実際の売却は行われません
- 強制売却モードは慎重に使用してください
- 売却実行前に必ず評価結果と売却理由を確認してください
- 市場休業日は売却が実行できません

## 全般的な注意事項

### 環境設定

- 実行前に必要な環境変数が設定されていることを確認してください
- 以下の環境変数が必要です：
  - `PYTHON_PATH`: Python実行ファイルのパス
  - `GEMINI_API_KEY`: Gemini APIのアクセスキー
  - その他必要な認証情報

### ログ管理

- ログファイルは`log/YYYY/MM/DD/`ディレクトリに出力されます
- エラーが発生した場合は、ログファイルを確認してください
- ログファイルは自動的に30日間保持されます

### データベース

- 株価データは日次で更新されます
- データベースのバックアップは自動的に実行されます
- エラー発生時はデータベースの整合性を確認してください

### データベース接続管理

- コネクションプールを使用して効率的なデータベース接続を管理
- 最小2接続、最大10接続
- 接続タイムアウト: 30秒
- 待機キュー最大サイズ: 20

### バッチ処理の最適化

- 株価データ取得の並列処理
- データ検証機能の強化
- エラーハンドリングとリトライ機能
- 処理の中断と再開機能

## EntryRepositoryについて

### EntryRepositoryの概要

EntryRepositoryは、資金管理と取引履歴管理を行うためのリポジトリクラスです。以下の機能を提供します：

### 主な機能

1. **資金管理**
   - `get_available_funds(test_mode=False)`: 利用可能な資金を取得
   - `reset_test_data(initial_funds=1000000.0)`: テストデータをリセット

2. **取引履歴管理**
   - `get_test_trade_history()`: テストモードの取引履歴を取得
   - `get_test_summary()`: テストモードのサマリー情報を取得

3. **エントリー管理**
   - `save_entry_info(entry_data)`: エントリー情報を保存
   - `get_active_entries(test_mode=False)`: アクティブなエントリーを取得
   - `update_exit_info(...)`: 売却情報を更新

### テストの実行方法

```bash
# EntryRepositoryのテストを実行
python bin/test/test_entry_repository.py

# 特定のテストメソッドのみ実行
python -m unittest bin.test.test_entry_repository.TestEntryRepository.test_get_available_funds
```

### テストケース

1. `test_get_available_funds`: 資金取得機能のテスト
2. `test_get_test_trade_history`: 取引履歴取得機能のテスト
3. `test_get_test_summary`: サマリー情報取得機能のテスト
4. `test_reset_test_data`: データリセット機能のテスト

### auto_sell_stock.py の動作仕様

1. **実行オプション**
   - `--test`: テストモード（売却を実行しない）
   - `--force-sell`: 強制売却モード（確認なしで売却）
   - `--debug`: デバッグモード

2. **評価プロセス**
   - ブラウザ操作による保有証券情報の取得
   - 各銘柄の過去データとインジケーター分析
   - Gemini APIによるAI評価
   - 確信度500以上のSELL判断を売却候補として抽出

3. **売却判断基準**
   - 損益率による判断（-5%以下で売却、+10%以上で利確）
   - テクニカル指標（RSI、MACD）による判断
   - AI評価による総合判断

## テスト実行について

### テストファイル一覧

#### バッチファイル (batch/test/)
- `purchase_stock_test.bat`: 自動購入機能のテスト実行
- `auto_sell_stock_simulation_test.bat`: 自動売却機能のシミュレーション
- `run_tachibana_test.bat`: 立花証券API接続テスト

#### Pythonテストファイル (bin/test/)
- `test_tachibana_api.py`: 立花証券APIのテスト
- `test_entry_repository.py`: エントリー情報管理のテスト
- `test_performance.py`: パフォーマンステスト
- `test_purchase_stock.py`: 自動購入機能のテスト
- `test_indicator.py`: テクニカル指標計算のテスト
- `test_report_dir.py`: レポート出力機能のテスト
- `wrapper_script.py`: テスト用ラッパースクリプト
- `fix_script.py`: データ修正用スクリプト

### テストの実行方法

#### 自動購入機能のテスト
```batch
# バッチファイルで実行
batch/test/purchase_stock_test.bat

# 直接実行
python bin/test/test_purchase_stock.py
```

#### 自動売却機能のシミュレーション
```batch
# バッチファイルで実行
batch/test/auto_sell_stock_simulation_test.bat
```

#### 立花証券APIテスト
```batch
# バッチファイルで実行
batch/test/run_tachibana_test.bat

# 直接実行
python bin/test/test_tachibana_api.py
```

#### テクニカル指標のテスト
```batch
python bin/test/test_indicator.py
```

#### パフォーマンステスト
```batch
python bin/test/test_performance.py
```

### テスト実行時の注意事項

1. **環境設定**
   - テスト実行前に必要な環境変数が設定されていることを確認
   - テストデータベースが適切に設定されていることを確認

2. **テストモード**
   - テストでは実際の取引は行われません
   - テストデータは独立したテーブルで管理されます

3. **パフォーマンステスト**
   - 大量のデータを扱うため、十分なメモリを確保してください
   - テスト実行時間が長くなる可能性があります

4. **データクリーンアップ**
   - テスト終了後、テストデータは自動的にクリーンアップされます
   - 手動でクリーンアップする場合は`test_purchase_stock.py --reset-test`を使用
