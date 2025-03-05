# ロギング設定ルール

## 基本方針

- ログレベルを適切に使い分け（DEBUG, INFO, WARNING, ERROR）
- 重要な操作やエラーは常にログに記録
- 機密情報はログに出力しない
- `utils.logging_config`モジュールを使用して統一的なログ設定

## 詳細ルール

### 1. 共通ロギングモジュールの使用

- 必ず`utils.logging_config`の`setup_logging`と`cleanup_old_logs`を使用
- ファイル内で独自のロギング設定を定義しない
- 例: `from utils.logging_config import setup_logging, cleanup_old_logs`

### 2. ログディレクトリ構造

- ログファイルは`/log/yyyy/mm/dd/`ディレクトリに格納する
- ファイル名は`{log_type}_{timestamp}.log`形式を使用
- 古いログファイルの自動クリーンアップ機能を利用する

### 3. ロガーの初期化

- ファイル名やモジュール名を使って初期化: `logger = setup_logging("module_name")`
- クラス内でロガーを使用する場合は、初期化済みロガーを渡す: `self.logger = logger`
- グローバルロガー`logging.getLogger()`は使用せず、必ず名前付きロガーを使用

### 4. クラス間でのロガー連携

- クラスのコンストラクタでロガーを引数として受け取れるようにする: `def __init__(self, logger=None):`
- 外部から渡されたロガーがある場合はそれを使用し、なければ新しく作成:
  ```python
  self.logger = logger if logger else setup_logging("default_name")
  ```
- 子クラスや依存するクラスにもロガーを渡す: `self.child = ChildClass(logger=self.logger)`

### 5. ログレベルの使い分け

- DEBUG: 開発時の詳細な情報（変数の中身、制御フロー）
- INFO: 正常な操作の記録（処理の開始・完了、主要データの入出力）
- WARNING: 想定内の問題（軽微なエラー、再試行で解決可能な問題）
- ERROR: エラー状態（処理が継続できない、ユーザーに影響がある問題）
- CRITICAL: 重大なエラー（システム全体に影響を及ぼす問題）

### 6. ルートロガーの設定変更禁止

- `logging.getLogger()`や`logging.getLogger().setLevel()`は使用しない
- 代わりに特定の名前付きロガーのレベルを変更する:
  ```python
  logger.setLevel(logging.DEBUG)
  logging.getLogger('module_name').setLevel(logging.DEBUG)
  ```

## 実装例

```python
from utils.logging_config import setup_logging, cleanup_old_logs

# ロガーの初期化（ファイル名やモジュール名を使用）
logger = setup_logging("module_name")

def main():
    logger.info("処理を開始します")
    try:
        # 処理内容
        logger.debug("変数の値: %s", some_var)
        
        # クラスへのロガー受け渡し
        processor = DataProcessor(logger=logger)
        result = processor.process()
        
        # 重要なステップの記録
        logger.info("重要な処理が完了しました")
    except Exception as e:
        logger.error("エラーが発生しました: %s", e)
    finally:
        logger.info("処理を終了します")

# 古いログのクリーンアップ（必要に応じて）
cleanup_old_logs("module_name") 