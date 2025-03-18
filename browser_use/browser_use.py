import json
import logging
import re
from gradio_client import Client
import os
from dotenv import load_dotenv
from datetime import datetime
from utils.logging_config import setup_logging, cleanup_old_logs
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# .envファイルをロード
load_dotenv()

# 文字コードをUTF-8に設定
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

class BrowserUse:
    def __init__(self):
        logger = setup_logging("browser_use")
        self.logger = logger
        self.client = self._initialize_client()
        self.logger.info("Gradioクライアントの初期化が完了しました")

    def _initialize_client(self) -> Client:
        """Gradioクライアントの初期化を行う"""
        max_retries = 2
        retry_delay = 60  # 秒
        webui_startup_delay = 30  # WebUI起動待機時間（秒）

        for attempt in range(max_retries + 1):
            try:
                # 既存のChromeプロセスを終了
                if attempt > 0:
                    self.logger.info("既存のChromeプロセスを終了します")
                    try:
                        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], 
                                     capture_output=True, 
                                     text=True)
                        time.sleep(5)  # プロセス終了を待つ
                    except Exception as e:
                        self.logger.warning(f"Chromeプロセス終了中にエラーが発生: {e}")

                # WebUIの起動を試みる
                if attempt > 0:
                    self.logger.info("WebUIを起動します")
                    try:
                        webui_path = Path("C:/Users/hp/Documents/web-ui-main/webui.py")
                        if webui_path.exists():
                            # WebUIのディレクトリに移動
                            webui_dir = webui_path.parent
                            current_dir = os.getcwd()
                            os.chdir(webui_dir)
                            
                            # プロジェクトルートを取得
                            project_root = Path(__file__).parent.parent
                            
                            # WebUIのPythonパスにbrowser_useモジュールを追加
                            pythonpath = os.getenv("PYTHONPATH", "")
                            if pythonpath:
                                pythonpath = f"{project_root};{pythonpath}"
                            else:
                                pythonpath = str(project_root)
                            
                            # 環境変数を設定
                            env = os.environ.copy()
                            env["PYTHONPATH"] = pythonpath
                            
                            # WebUIを起動
                            process = subprocess.Popen(
                                [sys.executable, str(webui_path)],
                                creationflags=subprocess.CREATE_NEW_CONSOLE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                env=env
                            )
                            
                            self.logger.info(f"WebUIの起動を待機します（{webui_startup_delay}秒）")
                            time.sleep(webui_startup_delay)  # WebUIの起動を待つ
                            
                            # プロセスが正常に起動しているか確認
                            if process.poll() is not None:
                                stdout, stderr = process.communicate()
                                self.logger.error(f"WebUIの起動に失敗: {stderr}")
                                raise RuntimeError("WebUIの起動に失敗しました")
                            
                            # 元のディレクトリに戻る
                            os.chdir(current_dir)
                        else:
                            self.logger.error(f"WebUIが見つかりません: {webui_path}")
                    except Exception as e:
                        self.logger.error(f"WebUIの起動に失敗: {e}")
                        raise

                # クライアントの初期化を試みる
                self.logger.info(f"Gradioクライアントの初期化を試みます (試行 {attempt + 1}/{max_retries + 1})")
                client = Client("http://localhost:7788/")
                self.logger.info("Gradioクライアントの初期化に成功しました")
                return client

            except Exception as e:
                self.logger.error(f"Gradioクライアントの初期化に失敗: {e}")
                if attempt < max_retries:
                    self.logger.info(f"{retry_delay}秒後に再試行します")
                    time.sleep(retry_delay)
                else:
                    self.logger.error("最大リトライ回数に達しました")
                    raise

    def _launch_webui(self):
        """WebUIを起動する"""
        try:
            # 既存のChromeプロセスを終了
            self._terminate_chrome()
            
            # WebUIのディレクトリを取得
            webui_dir = Path(os.getenv("WEBUI_DIR", "C:/Users/hp/Documents/web-ui-main"))
            
            # プロジェクトルートを取得
            project_root = Path(__file__).parent.parent
            
            # WebUIのPythonパスにbrowser_useモジュールを追加
            pythonpath = os.getenv("PYTHONPATH", "")
            if pythonpath:
                pythonpath = f"{project_root};{pythonpath}"
            else:
                pythonpath = str(project_root)
            
            # 環境変数を設定
            env = os.environ.copy()
            env["PYTHONPATH"] = pythonpath
            
            # 現在の作業ディレクトリを保存
            original_dir = os.getcwd()
            
            # WebUIのディレクトリに移動
            os.chdir(webui_dir)
            
            # WebUIを起動
            self.logger.info("WebUIを起動します")
            process = subprocess.Popen(
                [sys.executable, "webui.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # プロセスの状態を確認
            if process.poll() is not None:
                # エラー出力を取得
                _, stderr = process.communicate()
                self.logger.error(f"WebUIの起動に失敗: {stderr}")
                raise RuntimeError("WebUIの起動に失敗しました")
            
            # 元のディレクトリに戻る
            os.chdir(original_dir)
            
            # WebUIの起動を待機
            self.logger.info("WebUIの起動を待機します（30秒）")
            time.sleep(30)  # WebUIの起動を待機
            
            return process
        except Exception as e:
            self.logger.error(f"WebUIの起動に失敗: {str(e)}")
            raise

    def _get_prompt(self):
        user_name = os.environ.get("SBI_USER_NAME")
        self.logger.info(f"user_name: {user_name}")
        login_password = os.environ.get("SBI_LOGIN_PASSWORD")
        self.logger.info("login_password: [MASKED]")
        prompt = f"""【タスク】
        1. 現在のブラウザの状態を確認してください。

        2. SBI証券のページが開いていない場合は、以下のURLにアクセスしてください：
           https://site1.sbisec.co.jp/ETGate/?_ControlID=WPLEThmR001Control&_PageID=DefaultPID&_DataStoreID=DSWPLEThmR001Control&_ActionID=DefaultAID&getFlg=on

        3. ログインしていない場合は、以下の認証情報でログインしてください：
           ユーザーネーム: {user_name}
           パスワード: {login_password}

        4. ポートフォリオページにアクセスしてください。
           すでにポートフォリオページが表示されている場合は、ページの更新（リロード）を行ってください。

        5. ポートフォリオから以下の情報を取得してください：
           - 銘柄コード（整数）
           - 現在価格
           取得した情報は**Pythonの辞書型**で返してください。

        **出力形式：
        {{
            "1301": "1000",
            "1302": "2000",
            "1303": "3000"
        }}**

        ※ブラウザの状態に応じて、不要なステップはスキップしてください。
        """
        return prompt

    def is_valid_stock_data(self, data):
        """株価データの形式が正しいかチェックする"""
        if not isinstance(data, dict):
            return False
        
        for code, price in data.items():
            # コードが文字列で数字のみで構成されているか確認
            if not isinstance(code, str) or not code.isdigit():
                return False
            # 価格が文字列または数値で、数値に変換可能か確認
            if not (isinstance(price, (str, int)) and str(price).isdigit()):
                return False
        return True

    def normalize_json_string(self, text):
        """JSON文字列を正規化する"""
        # バックスラッシュとエスケープシーケンスを処理
        text = text.replace('\\n', ' ').replace('\\', '')
        # 余分な空白を削除
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def extract_dict_from_response(self, response_str):
        """レスポンス文字列から辞書データを抽出する"""
        self.logger.info(f"辞書抽出を試行: {response_str}")
        
        try:
            # 1. 完全なJSONとして解析を試みる
            try:
                normalized = self.normalize_json_string(response_str)
                data = json.loads(normalized)
                if self.is_valid_stock_data(data):
                    converted_data = {k: int(v) for k, v in data.items()}
                    self.logger.info(f"完全なJSONとして抽出成功: {converted_data}")
                    return converted_data
            except json.JSONDecodeError:
                pass

            # 2. JSON形式の文字列を探す
            json_pattern = r'\{[^{}]*"[^"]+"\s*:\s*"[^"]+\"[^{}]*\}'
            matches = re.findall(json_pattern, response_str)
            
            for match in matches:
                try:
                    normalized = self.normalize_json_string(match)
                    data = json.loads(normalized)
                    if self.is_valid_stock_data(data):
                        converted_data = {k: int(v) for k, v in data.items()}
                        self.logger.info(f"JSON文字列として抽出成功: {converted_data}")
                        return converted_data
                except json.JSONDecodeError:
                    continue

            # 3. 'done'フィールド内のテキストを確認
            done_pattern = r'text\':\s*\'(\{[^}]+\})\''
            done_matches = re.findall(done_pattern, response_str)
            
            for match in done_matches:
                try:
                    normalized = self.normalize_json_string(match)
                    data = json.loads(normalized)
                    if self.is_valid_stock_data(data):
                        converted_data = {k: int(v) for k, v in data.items()}
                        self.logger.info(f"doneフィールドから抽出成功: {converted_data}")
                        return converted_data
                except json.JSONDecodeError:
                    continue

            return None
            
        except Exception as e:
            self.logger.error(f"辞書抽出中に予期せぬエラーが発生: {str(e)}")
            return None

    def extract_stock_data_from_text(self, text):
        """テキストから株価データを抽出する"""
        try:
            self.logger.info(f"テキストからの抽出を開始: {text}")
            
            # 'done'フィールドのテキストから直接抽出を試みる
            if isinstance(text, dict):
                if 'done' in text and 'text' in text['done']:
                    result = self.extract_dict_from_response(text['done']['text'])
                    if result:
                        return result
                # 辞書全体を文字列として処理
                text = str(text)
            
            # コロンで区切られたテキストの場合、最後の部分を使用
            if ":" in text:
                parts = text.split(":")
                # 最後の部分に辞書が含まれている可能性が高いため、最後の部分を使用
                text = parts[-1].strip()
            
            # 辞書形式のデータを抽出
            result = self.extract_dict_from_response(text)
            if result:
                return result
            
            return None
        except Exception as e:
            self.logger.error(f"テキストからの抽出に失敗: {e}, テキスト: {text}")
            return None

    def process_response_item(self, item):
        """レスポンスの各アイテムを処理する"""
        try:
            if item is None:
                return None

            # 文字列の場合
            if isinstance(item, str):
                # 直接JSON解析を試みる
                try:
                    data = json.loads(item)
                    if self.is_valid_stock_data(data):
                        converted_data = {k: int(v) for k, v in data.items()}
                        self.logger.info(f"直接JSON解析成功: {converted_data}")
                        return converted_data
                except json.JSONDecodeError:
                    pass

                # テキストから抽出を試みる
                return self.extract_stock_data_from_text(item)

            # 辞書の場合
            elif isinstance(item, dict):
                if 'done' in item and 'text' in item['done']:
                    text = item['done']['text']
                    try:
                        data = json.loads(text)
                        if self.is_valid_stock_data(data):
                            converted_data = {k: int(v) for k, v in data.items()}
                            self.logger.info(f"done.textから直接抽出成功: {converted_data}")
                            return converted_data
                    except json.JSONDecodeError:
                        return self.extract_stock_data_from_text(text)

            return None
        except Exception as e:
            self.logger.error(f"アイテム処理中にエラーが発生: {str(e)}")
            return None

    def run(self, task):
        self.logger.info("タスクを開始します")
        response = self.client.predict(
            agent_type="custom",                        # エージェントタイプ。'custom' 又は 'org'
            llm_provider="gemini",                        # LLM プロバイダー。例: "openai"
            llm_model_name=os.environ.get("GEMINI_THINKING_MODEL"),                      # 使用するモデル名。例: "gpt-4o"
            llm_temperature=1,                            # 温度パラメータ
            llm_base_url="",                              # ベース URL（必要に応じて）
            llm_api_key=os.environ.get("GEMINI_API_KEY2"),                               # API キー（必要に応じて）
            use_own_browser=True,                        # ブラウザ利用オプション
            keep_browser_open=False,                     # ブラウザを開いたままにするかどうか
            headless=True,                               # ヘッドレスモードかどうか
            disable_security=True,                        # セキュリティ機能の無効化
            window_w=1280,                                # ブラウザウィンドウの幅
            window_h=1100,                                # ブラウザウィンドウの高さ
            save_recording_path="./tmp/record_videos",    # 録画ファイルの保存パス
            save_agent_history_path="./tmp/agent_history",# エージェント履歴の保存パス
            save_trace_path="./tmp/traces",               # トレースファイルの保存パス
            enable_recording=True,                        # 録画を有効にするかどうか
            task=task,                                    # 実行タスクの内容
            add_infos="Hello!!",                          # 補足情報。必須項目です
            max_steps=100,                                # 最大実行ステップ数
            use_vision=True,                              # ビジョン機能の使用有無
            max_actions_per_step=10,                      # 1ステップあたりの最大アクション数
            tool_call_in_content=True,                    # ツールコールをコンテンツ内で使用するかどうか
            api_name="/run_with_stream"                   # 実行する API エンドポイント
        )
        
        # レスポンスの内容をログに記録
        self.logger.info("レスポンスを受信:")
        self.logger.info(f"レスポンスの型: {type(response)}")
        
        try:
            if isinstance(response, (list, tuple)):
                self.logger.info(f"レスポンスの要素数: {len(response)}")
                
                # 各要素を処理
                for i, item in enumerate(response):
                    self.logger.info(f"要素[{i}]の処理を開始:")
                    self.logger.info(f"要素[{i}]の型: {type(item)}")
                    self.logger.info(f"要素[{i}]の内容: {item}")
                    
                    result = self.process_response_item(item)
                    if result:
                        return result
            
            self.logger.warning("辞書データを抽出できませんでした")
            return None
            
        except Exception as e:
            self.logger.error(f"予期せぬエラーが発生しました: {str(e)}")
            return None

if __name__ == "__main__":
    browser_use = BrowserUse()
    response = browser_use.run(browser_use._get_prompt())
    if response:
        print("取得した株価データ:", response)
    else:
        print("株価データの取得に失敗しました。ログを確認してください。")
        # TODO 新規発注処理
        # TODO 保有証券確認処理
        # TODO 保有証券の評価
        # TODO 保有証券の買い増し処理