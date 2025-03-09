# stockTradeプロジェクト

## プロジェクト構造

```
stockTrade/
├── bin/              # 実行ファイル（.py）を格納
│   ├── daily/           # 日次実行系
│   │   ├── daily_update.py          # 立花証券APIを使用した日次株価更新
│   │   ├── daily_update_yfinance.py # yFinanceを使用した日次株価更新（現在は非使用）
│   │   ├── auto_sell_stock.py       # 自動売却機能
│   │   └── purchase_stock.py        # 自動購入機能
│   ├── test/            # テスト実行系
│   │   └── test_tachibana_api.py    # 立花証券APIのテスト
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
├── service/          # サービス層
├── utils/            # ユーティリティ
├── repository/       # データアクセス層
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
```

#### コマンドライン引数
- `--max-calls <数値>`: AI判断の最大件数（デフォルト: 50件）
- `--min-score <数値>`: エントリースコアの最低値（デフォルト: 70.0）
- `--api-delay <秒数>`: API呼び出し間の待機時間（デフォルト: 30秒）
- `--test-mode`: テストモードの有効化（実際の購入処理をスキップ）

#### 環境変数による制御
1. **必須の環境変数**
   - `GEMINI_API_KEY`: Gemini APIのアクセスキー
   - `GEMINI_PRO_MODEL`: 使用するモデルのバージョン

2. **オプションの環境変数**
   - `STOCK_TEST_MODE`: テストモードの制御（'true'/'false'）
   - `USE_SIMPLIFIED_PROMPT`: 簡略化プロンプトの使用（'true'/'false'）

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