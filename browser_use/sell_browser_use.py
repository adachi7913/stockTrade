import logging
import os
from typing import Dict, Optional
from .browser_use import BrowserUse


class SellBrowserUse(BrowserUse):
    def __init__(self, logger: logging.Logger):
        super().__init__()
        self.logger = logger

    def _get_username(self) -> str:
        """
        SBI証券のユーザー名を取得

        Returns:
            str: SBI証券のユーザー名。取得失敗時は空文字列
        """
        username = os.environ.get("SBI_USER_NAME")
        if not username:
            self.logger.error("SBI証券のユーザー名が設定されていません")
            return ""
        return username

    def _get_password(self) -> str:
        """
        SBI証券のログインパスワードを取得

        Returns:
            str: SBI証券のログインパスワード。取得失敗時は空文字列
        """
        password = os.environ.get("SBI_LOGIN_PASSWORD")
        if not password:
            self.logger.error("SBI証券のパスワードが設定されていません")
            return ""
        return password

    def _get_tread_password(self) -> str:
        """
        SBI証券の取引パスワードを取得

        Returns:
            str: SBI証券の取引パスワード。取得失敗時は空文字列
        """
        password = os.environ.get("SBI_TREAD_PASSWORD")
        if not password:
            self.logger.error("SBI証券の取引パスワードが設定されていません")
            return ""
        return password

    def _get_sell_prompt(self, sell_data: Dict) -> str:
        """
        売却用のプロンプトを生成

        Args:
            sell_data (Dict): 売却情報
                必要なキー:
                - code: 銘柄コード
                - quantity: 株数
                - exit_price: 売却価格

        Returns:
            str: プロンプト文字列
        """
        # 株数の取得
        quantity = sell_data.get('quantity', 0)
        
        # 銘柄コード
        code = sell_data.get('code', '')
        
        # 売却価格
        exit_price = sell_data.get('exit_price', 0)

        prompt = f"""【タスク】
        1. 現在のブラウザの状態を確認してください。

        2. SBI証券のページが開いていない場合は、以下のURLにアクセスしてください：
           https://site1.sbisec.co.jp/ETGate/?_ControlID=WPLEThmR001Control&_PageID=DefaultPID&_DataStoreID=DSWPLEThmR001Control&_ActionID=DefaultAID&getFlg=on

        3. ログインしていない場合は、以下の認証情報でログインしてください：
           ユーザーネーム: {self._get_username()}
           パスワード: {self._get_password()}

        4. 「取引」タブをクリック
        5. 「注文照会取消・訂正」ボタンをクリック
        6. コードが{code}の行を見つけ、その行の「訂正」ボタンをクリック
        6. 株数に{quantity}を入力
        7. 「指値」を選択し、価格のテキストボックスに{exit_price}と入力
        8. 預かり区分はNISA預かりに変更する
        9. 期間は当日を選択
        10. 取引パスワードに{self._get_tread_password()}を入力
        11. 「注文確認画面を省略」にチェックを入れる
        12. 注文発注ボタンをクリック
        13. 注文が完了したら、注文の約定状況を確認し、以下のいずれかの結果を返してください：
           - 注文完了時: {{"success": true, "message": "売却注文が完了しました"}}
           - 注文失敗時: {{"success": false, "message": "エラーの内容"}}
        """

        return prompt

    def execute_sell(self, sell_data: Dict) -> bool:
        """
        売却処理を実行

        Args:
            sell_data (Dict): 売却情報

        Returns:
            bool: 売却成功でTrue
        """
        try:
            prompt = self._get_sell_prompt(sell_data)
            response = self.run(prompt)

            if response and isinstance(response, dict):
                return response.get("success", False)
            return False

        except Exception as e:
            self.logger.error(f"売却実行中にエラーが発生: {e}")
            return False 