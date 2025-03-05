# stockTradeプロジェクト

## プロジェクト構造

```
stockTrade/
├── bin/              # 実行ファイル（.py）を格納
│   ├── daily/           # 日次実行系
│   │   ├── daily_update.py          # 立花証券APIを使用した日次株価更新
│   │   └── daily_update_yfinance.py # yFinanceを使用した日次株価更新（現在は非使用）
│   ├── test/            # テスト実行系
│   │   └── test_tachibana_api.py    # 立花証券APIのテスト
│   └── tools/           # その他のツール系
│
├── batch/            # バッチファイル（.bat）を格納
│   ├── daily/           # 日次実行系のバッチ
│   │   └── run_daily_update.bat     # 日次株価更新の実行
│   ├── test/            # テスト実行系のバッチ
│   └── tools/           # その他のツール系のバッチ
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

## 注意事項

- 実行前に必要な環境変数が設定されていることを確認してください
- ログファイルは`log/YYYY/MM/DD/`ディレクトリに出力されます
- エラーが発生した場合は、ログファイルを確認してください 