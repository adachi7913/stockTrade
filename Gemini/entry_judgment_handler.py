import json
import logging
import re
import requests
import time
from typing import Dict, List, Optional
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# TODO: エントリー判断の機能強化
# - 市場環境の考慮（VIX、セクター動向など）
# - マクロ経済指標の分析
# - 企業固有のイベント（決算、配当など）の考慮
# - テクニカル指標の重み付け調整
# - バックテスト結果の反映

class EntryJudgmentHandler:
    def __init__(self, api_key: str, logger: logging.Logger):
        self.logger = logger
        self.api_key = api_key

    def _get_model_name(self) -> str:
        """
        実行時に.envファイルを読み込んでモデル名を取得
        
        Returns:
            str: Geminiモデル名
        """
        load_dotenv(override=True)  # 既存の環境変数を上書き
        return os.environ.get("GEMINI_PRO_MODEL")

    # TODO: プロンプトの最適化
    # - より詳細な市場分析の要求
    # - リスク要因の具体的な列挙
    # - 期待リターンの計算根拠の要求
    # - 代替シナリオの検討要求

    def _create_prompt(self, stock_data: Dict, historical_data: List[Dict]) -> str:
        """
        エントリー判断用のプロンプトを生成
        
        Args:
            stock_data (Dict): 銘柄情報
            historical_data (List[Dict]): 過去の価格データ
            
        Returns:
            str: プロンプト文字列
        """
        # 直近の価格トレンドを文字列化
        price_trend = "\n".join([
            f"- {data['date']}: 始値{data['open']}, 高値{data['high']}, "
            f"安値{data['low']}, 終値{data['close']}, 出来高{data['volume']}"
            for data in historical_data[-5:]  # 直近5日分
        ])

        prompt = f"""
        以下の銘柄について、現時点でのエントリー（買い）判断を行ってください。

        【銘柄情報】
        - コード: {stock_data['code']}
        - エントリー候補価格: {stock_data['entry_price']}
        - 想定損切り価格: {stock_data['stop_loss']}
        - 期待リターン: {stock_data['expected_return']}
        - エントリースコア: {stock_data.get('entry_score', 'N/A')}
        - エントリー理由: {stock_data['reason']}

        【直近の価格推移】
        {price_trend}

        【判断基準】
        1. 直近の価格トレンド
        2. ボリューム（出来高）の推移
        3. 想定リスク/リワード比
        4. その他の市場要因

        【回答形式】
        以下のJSON形式で回答してください：
        {{
            "should_enter": true/false,  # エントリー推奨ならtrue
            "confidence": 0-100,         # 判断の確信度
            "reasoning": "判断理由",      # 判断の根拠
            "concerns": "懸念事項"        # ある場合のみ
        }}
        """
        return prompt

    def _extract_json(self, content: str) -> str:
        """
        Gemini API のレスポンス中、マークダウンの ```json ... ``` 形式で囲まれている場合、
        その中身のみを抽出するヘルパー関数
        """
        match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1)
        return content

    async def judge_entry(self, stock_data: Dict, historical_data: List[Dict]) -> Dict:
        """
        エントリー判断を実行
        
        Args:
            stock_data (Dict): 銘柄情報
            historical_data (List[Dict]): 過去の価格データ
            
        Returns:
            Dict: 判断結果
        """
        try:
            prompt = self._create_prompt(stock_data, historical_data)
            model_name = self._get_model_name()  # 実行時にモデル名を取得
            
            if not model_name:
                self.logger.error("Geminiモデル名が設定されていません")
                return {
                    "should_enter": False,
                    "confidence": 0,
                    "reasoning": "Geminiモデル名が設定されていません",
                    "concerns": None
                }
                
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ]
            }
            headers = {'Content-Type': 'application/json'}

            max_retries = 3
            attempt = 0
            
            while attempt < max_retries:
                try:
                    response = requests.post(api_url, json=payload, headers=headers)
                    
                    if response.status_code == 503:
                        attempt += 1
                        self.logger.warning(f"Gemini API returned 503. Retrying {attempt}/{max_retries} after 5 seconds...")
                        time.sleep(5)
                        continue
                        
                    response.raise_for_status()
                    json_response = response.json()
                    
                    try:
                        # トークン使用量をログ出力
                        usage = json_response.get("usageMetadata", {})
                        self.logger.info("入力トークン(promptTokenCount): %s", usage.get("promptTokenCount", "不明"))
                        self.logger.info("候補トークン(candidatesTokenCount): %s", usage.get("candidatesTokenCount", "不明"))
                        self.logger.info("合計トークン(totalTokenCount): %s", usage.get("totalTokenCount", "不明"))
                        
                        content = json_response['candidates'][0]['content']['parts'][0]['text']
                        json_text = self._extract_json(content)
                        
                        # JSONパースとバリデーション
                        result = json.loads(json_text)
                        if self._validate_judgment_result(result):
                            return result
                            
                    except Exception as e:
                        self.logger.error(f"レスポンス解析エラー: {e}")
                        
                except requests.RequestException as e:
                    if e.response is not None and e.response.status_code == 503:
                        attempt += 1
                        self.logger.warning(f"RequestException with 503 received. Retrying {attempt}/{max_retries} after 5 seconds...")
                        time.sleep(5)
                        continue
                    else:
                        self.logger.error(f"API呼び出しエラー: {e}")
                        break

            return {
                "should_enter": False,
                "confidence": 0,
                "reasoning": "APIリクエストに失敗しました",
                "concerns": None
            }
            
        except Exception as e:
            self.logger.error(f"エントリー判断中にエラーが発生: {e}")
            return {
                "should_enter": False,
                "confidence": 0,
                "reasoning": f"エラーが発生: {str(e)}",
                "concerns": None
            }

    def _validate_judgment_result(self, result: Dict) -> bool:
        """
        判断結果のバリデーション
        
        Args:
            result (Dict): 判断結果
            
        Returns:
            bool: バリデーション成功でTrue
        """
        required_fields = ['should_enter', 'confidence', 'reasoning']
        if not all(field in result for field in required_fields):
            return False
            
        if not isinstance(result['should_enter'], bool):
            return False
            
        if not isinstance(result['confidence'], (int, float)) or not 0 <= result['confidence'] <= 100:
            return False
            
        if not isinstance(result['reasoning'], str):
            return False
            
        return True

    def evaluate_entry(self, candidate: Dict, historical_data: List[dict]) -> Optional[Dict]:
        """
        エントリー候補の評価を行う
        
        Args:
            candidate (Dict): エントリー候補データ
            historical_data (List[dict]): 過去の価格とインジケーターのデータ
            
        Returns:
            Optional[Dict]: 評価結果、評価失敗時はNone
        """
        try:
            # Gemini APIへのプロンプトを構築
            prompt = f"""
            【前提】
            英語で思考し、**日本語のみ**で回答してください。
            あなたは優秀な個人投資家かつトレード戦略構築のエキスパートです。
            提案されたエントリー条件について、過去のデータや各種テクニカル指標をもとに、エントリーの実行可否を判断してください。

            【評価基準】
            1. トレンド分析（一目均衡表、MACD）
            2. モメンタム（RSI、ストキャスティクス）
            3. ボラティリティ（ボリンジャーバンド、ATR）
            4. 出来高分析
            5. 提案されたエントリー条件との整合性

            【提案されたエントリー条件】
            証券コード: {candidate['code']}
            想定エントリー価格: {candidate['entry_price']}
            ストップロス: {candidate['stop_loss']}
            利確目標: {candidate['target_price']}
            想定保有期間: {candidate['period']}
            リスクリワード比: {candidate['risk_reward']}
            エントリー理由: {candidate['reason']}

            【過去データ】
            {json.dumps(historical_data, ensure_ascii=False)}

            【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
            {{
                "should_enter": true or false,
                "confidence_score": <0〜1000の整数>,
                "reason": "判断の理由",
                "modified_conditions": {{
                    "entry_price": "修正後のエントリー価格（変更なしの場合は元の値）",
                    "stop_loss": "修正後のストップロス（変更なしの場合は元の値）",
                    "target_price": "修正後の利確目標（変更なしの場合は元の値）"
                }}
            }}
            """

            # GeminiAPIにリクエスト送信
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ]
            }
            headers = {'Content-Type': 'application/json'}

            max_retries = 3
            attempt = 0
            
            while attempt < max_retries:
                try:
                    response = requests.post(api_url, json=payload, headers=headers)
                    
                    if response.status_code == 503:
                        attempt += 1
                        self.logger.warning(f"Gemini API returned 503. Retrying {attempt}/{max_retries} after 5 seconds...")
                        time.sleep(5)
                        continue
                        
                    response.raise_for_status()
                    json_response = response.json()
                    
                    try:
                        content = json_response['candidates'][0]['content']['parts'][0]['text']
                        json_text = self._extract_json(content)
                        evaluation = json.loads(json_text)
                        self.logger.info(f"評価結果: {evaluation}")
                        return evaluation
                            
                    except Exception as e:
                        self.logger.error(f"レスポンス解析エラー: {e}")
                        
                except requests.RequestException as e:
                    if e.response is not None and e.response.status_code == 503:
                        attempt += 1
                        self.logger.warning(f"RequestException with 503 received. Retrying {attempt}/{max_retries} after 5 seconds...")
                        time.sleep(5)
                        continue
                    else:
                        self.logger.error(f"API呼び出しエラー: {e}")
                        break

            return None

        except Exception as e:
            self.logger.error(f"エントリー評価中にエラーが発生: {e}")
            return None 