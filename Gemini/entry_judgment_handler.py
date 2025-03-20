import json
import logging
import re
import requests
import time
from typing import Dict, List, Optional, Any
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from decimal import Decimal  # まだインポートしていない場合は追加

import google.generativeai as genai
from google.generativeai.types.generation_types import StopCandidateException

# TODO: エントリー判断の機能強化
# - 市場環境の考慮（VIX、セクター動向など）
# - マクロ経済指標の分析
# - 企業固有のイベント（決算、配当など）の考慮
# - テクニカル指標の重み付け調整
# - バックテスト結果の反映

class EntryJudgmentHandler:
    """
    Gemini APIを使用してエントリー判断を行うクラス
    
    このクラスは、株式のエントリー（購入）に関する意思決定支援を行います。
    Gemini Pro APIにプロンプトを送信し、エントリーの可否、信頼度、理由などを取得します。
    """
    
    def __init__(self, api_key: str, logger: Optional[logging.Logger] = None, test_mode: bool = False):
        """
        Gemini Proの設定とAPIキーの初期化を行います。
        
        Args:
            api_key (str): Gemini API Key
            logger (Optional[logging.Logger]): ロガーインスタンス（指定がなければ新規作成）
        """
        # APIキーの設定
        self.api_key = api_key
        genai.configure(api_key=api_key)
        
        # ロガーの設定
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
        
        # モデル設定
        if test_mode:
            model_name = os.getenv('GEMINI_THINKING_MODEL', 'gemini-1.5-flash')
        else:
            model_name = os.getenv('GEMINI_PURCHASE_MODEL', 'gemini-pro')
        self.model = genai.GenerativeModel(model_name)
        self.logger.info(f"EntryJudgmentHandler initialized with model: {model_name}")

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

    def _create_prompt(self, candidate: Dict[str, Any], historical_data: List[Dict[str, Any]]) -> str:
        """
        AIモデルへのプロンプトを作成します。
        
        Args:
            candidate (Dict): エントリー候補の情報
            historical_data (List[Dict]): 過去の価格・指標データ
            
        Returns:
            str: 作成されたプロンプト
        """
        stock_code = candidate.get('code', 'unknown')
        current_price = candidate.get('close', 0)
        
        # バックテスト結果の情報（存在する場合）
        backtest_info = ""
        if 'backtest_results' in candidate and candidate['backtest_results']:
            bt = candidate['backtest_results']
            backtest_info = f"""
バックテスト結果:
- 成功率: {bt.get('success_rate', 0):.1f}%
- 平均リターン: {bt.get('average_return', 0):.2f}
- 総取引回数: {bt.get('total_trades', 0)}
- 最良戦略: {bt.get('best_strategy', 'なし')}
"""

        # 最近のテクニカル指標情報
        recent_data = historical_data[-5:] if len(historical_data) >= 5 else historical_data
        technical_info = "直近のテクニカル指標:\n"
        for idx, data in enumerate(reversed(recent_data)):
            day = idx + 1
            technical_info += f"{day}日前: 終値={data.get('close', 0)}、RSI={data.get('rsi', 0):.1f}、"
            technical_info += f"ストキャスティクス%K={data.get('stoch_k', 0):.1f}、ADX={data.get('adx', 0):.1f}\n"
        
        # プロンプトの構築
        prompt = f"""
# 株式エントリー判断

## 銘柄情報
- 銘柄コード: {stock_code}
- 現在価格: {current_price}円

{backtest_info}

{technical_info}

## 判断指示
この銘柄に対してエントリー（購入）すべきかどうかを判断してください。
テクニカル指標、バックテスト結果、現在の価格水準を総合的に判断してください。

回答は以下の形式で提供してください:
```json
{{
  "should_enter": true/false,
  "confidence": 0-100,
  "reasoning": "判断理由を説明",
  "concerns": "考えられるリスクやその他の懸念点"
}}
```
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

    def judge_entry(self, candidate: Dict[str, Any], historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        株式エントリーの判断を行います。
        
        Args:
            candidate (Dict): エントリー候補銘柄の情報
            historical_data (List[Dict]): 過去の価格・指標データ
            
        Returns:
            Dict: エントリー判断結果
                - should_enter (bool): エントリーすべきかどうか
                - confidence (int): 判断の信頼度（0-100）
                - reasoning (str): 判断の理由
                - concerns (str): 懸念事項
        """
        try:
            # プロンプトの作成
            prompt = self._create_prompt(candidate, historical_data)
            
            # レスポンスの取得
            self.logger.info(f"Requesting judgment for stock code: {candidate.get('code', 'unknown')}")
            response = self._query_gemini(prompt)
            
            # レスポンスの解析
            judgment = self._parse_judgment(response.text)
            
            # トークン使用量の追加
            try:
                # 新しいバージョンのライブラリでの対応
                judgment['prompting_tokens'] = getattr(response.prompt_feedback, 'token_count', 0)
                judgment['completion_tokens'] = getattr(response.candidates[0], 'token_count', 0) if response.candidates else 0
                judgment['total_tokens'] = judgment['prompting_tokens'] + judgment['completion_tokens']
            except AttributeError as e:
                self.logger.warning(f"トークン情報の取得に失敗しました: {e}")
                judgment['prompting_tokens'] = 0
                judgment['completion_tokens'] = 0
                judgment['total_tokens'] = 0
            
            self.logger.info(f"Judgment completed for {candidate.get('code', 'unknown')}: " +
                           f"should_enter={judgment.get('should_enter', False)}, " +
                           f"confidence={judgment.get('confidence', 0)}")
            
            return judgment
            
        except Exception as e:
            self.logger.error(f"Error in judge_entry: {e}")
            # エラー時のフォールバック
            return {
                'should_enter': False,
                'confidence': 0,
                'reasoning': f"エラーが発生しました: {str(e)}",
                'concerns': "判断処理に失敗したため、エントリーを見送ります。",
                'error': str(e),
                'prompting_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            }

    def judge_entry_with_prompt(self, candidate: Dict[str, Any], custom_prompt: str) -> Dict[str, Any]:
        """
        カスタムプロンプトを使用して株式エントリーの判断を行います。
        
        Args:
            candidate (Dict): エントリー候補銘柄の情報
            custom_prompt (str): 外部から提供されるカスタムプロンプト
            
        Returns:
            Dict: エントリー判断結果
                - should_enter (bool): エントリーすべきかどうか
                - confidence (int): 判断の信頼度（0-100）
                - reasoning (str): 判断の理由
                - concerns (str): 懸念事項
        """
        try:
            stock_code = candidate.get('code', 'unknown')
            self.logger.info(f"カスタムプロンプトを使用した判断リクエスト: {stock_code}")
            
            # カスタムプロンプトを使用
            response = self._query_gemini(custom_prompt)
            print(f"response: {response}")
            
            # レスポンスの解析
            judgment = self._parse_judgment(response.text)
            
            # トークン使用量の追加
            try:
                # 新しいバージョンのライブラリでの対応
                judgment['prompting_tokens'] = getattr(response.prompt_feedback, 'token_count', 0)
                judgment['completion_tokens'] = getattr(response.candidates[0], 'token_count', 0) if response.candidates else 0
                judgment['total_tokens'] = judgment['prompting_tokens'] + judgment['completion_tokens']
            except AttributeError as e:
                self.logger.warning(f"トークン情報の取得に失敗しました: {e}")
                judgment['prompting_tokens'] = 0
                judgment['completion_tokens'] = 0
                judgment['total_tokens'] = 0
            
            self.logger.info(f"判断完了 {stock_code}: " +
                           f"should_enter={judgment.get('should_enter', False)}, " +
                           f"confidence={judgment.get('confidence', 0)}")
            
            return judgment
            
        except Exception as e:
            self.logger.error(f"judge_entry_with_promptでエラー: {e}")
            # エラー時のフォールバック
            return {
                'should_enter': False,
                'confidence': 0,
                'reasoning': f"エラーが発生しました: {str(e)}",
                'concerns': "カスタムプロンプトでの判断処理に失敗したため、エントリーを見送ります。",
                'error': str(e),
                'prompting_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            }

    def _query_gemini(self, prompt: str) -> Any:
        """
        Gemini APIに問い合わせを行います。
        
        Args:
            prompt (str): AIモデルへのプロンプト
            
        Returns:
            Any: Gemini APIからのレスポンス
        """
        # リトライ設定
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                generation_config = {
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
                
                safety_settings = [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                    }
                ]
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
                
                return response
                
            except StopCandidateException as e:
                self.logger.warning(f"Gemini API returned StopCandidateException: {e}")
                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying in {retry_delay} seconds (attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # バックオフ
                else:
                    raise
                    
            except Exception as e:
                self.logger.error(f"Gemini API error: {e}")
                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying in {retry_delay} seconds (attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
    
    def _parse_judgment(self, response_text: str) -> Dict[str, Any]:
        """
        APIレスポンスから判断情報を抽出します。
        
        Args:
            response_text (str): APIレスポンスの本文
            
        Returns:
            Dict: 解析された判断情報
        """
        # JSONブロックを検索
        json_pattern = r'```(?:json)?\s*({.*?})\s*```'
        json_matches = re.findall(json_pattern, response_text, re.DOTALL)
        
        if json_matches:
            try:
                # 最初のJSONブロックを解析
                judgment = json.loads(json_matches[0])
                
                # 型変換
                if 'should_enter' in judgment:
                    if isinstance(judgment['should_enter'], str):
                        judgment['should_enter'] = judgment['should_enter'].lower() == 'true'
                else:
                    judgment['should_enter'] = False
                    
                if 'confidence' in judgment:
                    if isinstance(judgment['confidence'], str):
                        # 数値に変換（'80%'などの場合も対応）
                        confidence_str = judgment['confidence'].replace('%', '')
                        try:
                            judgment['confidence'] = int(float(confidence_str))
                        except:
                            judgment['confidence'] = 0
                else:
                    judgment['confidence'] = 0
                
                # 必須フィールドの確認
                if 'reasoning' not in judgment:
                    judgment['reasoning'] = "理由は提供されませんでした"
                if 'concerns' not in judgment:
                    judgment['concerns'] = "懸念事項は提供されませんでした"
                
                return judgment
                
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析エラー: {e}")
        
        # JSONブロックが見つからない、または解析エラーの場合
        self.logger.warning("JSON構造が検出できませんでした。テキスト全体からの解析を試みます。")
        
        # テキストからの簡易解析
        judgment = {
            'should_enter': False,
            'confidence': 0,
            'reasoning': '解析できませんでした',
            'concerns': '解析エラーのため、エントリーを見送ります'
        }
        
        # should_enterの検出を試みる
        if 'エントリーすべき' in response_text or '購入すべき' in response_text or 'should_enter: true' in response_text:
            judgment['should_enter'] = True
            judgment['confidence'] = 50  # デフォルト値
        
        # confidenceの検出を試みる
        confidence_match = re.search(r'confidence: (\d+)', response_text)
        if confidence_match:
            try:
                judgment['confidence'] = int(confidence_match.group(1))
            except:
                pass
        
        return judgment

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

    def judge_exit_timing(self, code: str, industry_name: str, entry_price: float, 
                         current_price: float, holding_days: int) -> Dict[str, Any]:
        """
        保有銘柄の売却タイミングを判断します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 業種名
            entry_price (float): エントリー価格
            current_price (float): 現在価格
            holding_days (int): 保有日数
            
        Returns:
            Dict[str, Any]: 判断結果
                - should_exit (bool): 売却すべきかどうか
                - confidence (int): 信頼度（0-100）
                - reason (str): 判断理由
                - strategy (str): 推奨戦略
        """
        try:
            self.logger.info(f"銘柄 {code} の売却判断を開始します")
            
            # 損益率の計算
            profit_rate = ((current_price - entry_price) / entry_price) * 100
            
            # プロンプトの作成
            prompt = self._create_exit_prompt(
                code=code,
                industry_name=industry_name,
                entry_price=entry_price,
                current_price=current_price,
                profit_rate=profit_rate,
                holding_days=holding_days
            )
            
            # APIリクエスト
            response = self._query_gemini(prompt)
            
            if not response:
                self.logger.error(f"銘柄 {code} の売却判断でAPIレスポンスの取得に失敗しました")
                return {
                    "should_exit": False,
                    "confidence": 0,
                    "reason": "APIレスポンスの取得に失敗しました",
                    "strategy": "保持継続（デフォルト）"
                }
                
            # レスポンスの解析
            try:
                # _query_geminiはオブジェクトを返し、そのtext属性にレスポンステキストが含まれている
                response_text = response.text
                self.logger.debug(f"銘柄 {code} のAPIレスポンス: {response_text[:100]}...")
                
                # JSONブロックを抽出する試み
                json_block = self._extract_json_block(response_text)
                if json_block:
                    self.logger.debug(f"抽出されたJSONブロック: {json_block}")
                    result = json.loads(json_block)
                else:
                    # JSONブロックが見つからない場合は全体を解析
                    self.logger.debug("JSONブロックが見つからないため、全体をJSONとして解析を試みます")
                    result = json.loads(response_text)
                
                self.logger.info(f"銘柄 {code} の売却判断結果: {result}")
                
                # 結果が有効なJSONだが、必要なキーが欠けている場合
                if not all(key in result for key in ["should_exit", "confidence", "reason"]):
                    self.logger.warning(f"銘柄 {code} の売却判断結果に必要なキーが欠けています: {result}")
                    # 必要なキーがない場合は、あるものは保持しつつ、ないものはデフォルト値を設定
                    default_result = {
                        "should_exit": False,
                        "confidence": 0,
                        "reason": "結果のフォーマットが不完全です",
                        "strategy": "保持継続（デフォルト）"
                    }
                    # 既存のキーで上書き
                    for key in result:
                        if key in default_result:
                            default_result[key] = result[key]
                    result = default_result
                
                return result
                
            except json.JSONDecodeError as e:
                self.logger.error(f"銘柄 {code} の売却判断でJSONパースに失敗しました: {e}")
                # テキスト応答からの情報抽出を試みる
                response_text = response.text
                
                # よりインテリジェントなテキスト分析
                result = self._parse_text_response(response_text)
                self.logger.info(f"テキスト分析による売却判断結果: {result}")
                return result
                
        except Exception as e:
            self.logger.error(f"銘柄 {code} の売却判断中にエラーが発生しました: {e}", exc_info=True)
            return {
                "should_exit": False,
                "confidence": 0,
                "reason": f"エラーが発生しました: {e}",
                "strategy": "保持継続（エラー発生時のデフォルト）"
            }
            
    def _create_exit_prompt(self, code: str, industry_name: str, entry_price: float,
                           current_price: float, profit_rate: float, holding_days: int) -> str:
        """
        売却判断用のプロンプトを作成します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 業種名
            entry_price (float): エントリー価格
            current_price (float): 現在価格
            profit_rate (float): 損益率（%）
            holding_days (int): 保有日数
            
        Returns:
            str: 作成されたプロンプト
        """
        prompt = f"""
        あなたは株式投資の専門家です。以下の情報に基づいて、保有中の銘柄を売却すべきかどうかを判断してください。
        【トレードスタイル】
        - 短期スウィングトレード
        - 想定保有期間：１～１４日
        - ポジション：ロングのみ

        【銘柄情報】
        - 銘柄コード: {code}
        - 業種: {industry_name}
        - 購入価格: {entry_price:,.0f}円
        - 現在価格: {current_price:,.0f}円
        - 損益率: {profit_rate:.2f}%
        - 保有日数: {holding_days}日

        【判断基準】
        以下の要素を考慮して総合的に判断してください：
        1. 損益状況（利益確定や損切りのタイミング）
        2. 保有期間（短期・中期・長期の観点）
        3. 業種の市場動向
        4. テクニカル指標の状況
        5. リスク管理の観点

        【出力形式】
        以下のJSON形式で回答してください：
        {{
            "should_exit": true/false,  // 売却すべきかどうか
            "confidence": 0-100,        // 判断の信頼度（0-100）
            "reason": "判断理由の詳細な説明",
            "strategy": "今後の推奨戦略"
        }}

        JSONのみを出力し、その他の説明は不要です。
        """
        return prompt
        
    def _extract_reason_from_text(self, text: str) -> Optional[str]:
        """
        テキストから理由部分を抽出します
        
        Args:
            text (str): 抽出元のテキスト
            
        Returns:
            Optional[str]: 抽出された理由、見つからない場合はNone
        """
        # 理由を示す可能性のあるキーワード
        reason_keywords = ["理由", "判断", "分析", "考慮", "because", "reason", "analysis"]
        
        # テキストを行に分割
        lines = text.split('\n')
        
        # 各行をチェック
        for line in lines:
            for keyword in reason_keywords:
                if keyword in line.lower():
                    return line.strip()
                    
        # 見つからない場合は最初の実質的な行を返す
        for line in lines:
            if line.strip() and len(line.strip()) > 10:  # 実質的な内容がある行
                return line.strip()
                
        return None

    def _extract_json_block(self, text: str) -> Optional[str]:
        """
        テキストからJSONブロックを抽出します。マークダウンの```json...```形式や
        単なる{}で囲まれたJSON文字列を検出して抽出します。
        
        Args:
            text (str): 抽出対象のテキスト
            
        Returns:
            Optional[str]: 抽出されたJSON文字列、見つからない場合はNone
        """
        # マークダウンのJSON codeブロックを探す
        md_pattern = r'```(?:json)?\s*({.*?})\s*```'
        md_matches = re.findall(md_pattern, text, re.DOTALL)
        if md_matches:
            return md_matches[0]
        
        # JSON直接記述パターンを探す（{から始まり}で終わる全体をJSON候補として抽出）
        # より複雑な正規表現で中括弧のネストも考慮する
        json_pattern = r'({(?:[^{}]|(?:{[^{}]*})|(?:{(?:[^{}]|(?:{[^{}]*}))*}))*})'
        json_matches = re.findall(json_pattern, text, re.DOTALL)
        if json_matches:
            # 最も長いマッチを取る（おそらく完全なJSONオブジェクト）
            json_matches.sort(key=len, reverse=True)
            for match in json_matches:
                try:
                    # 実際にパースできるか試す
                    json.loads(match)
                    return match
                except json.JSONDecodeError:
                    continue
        
        return None
        
    def _parse_text_response(self, text: str) -> Dict[str, Any]:
        """
        レスポンステキストを解析して売却判断を抽出します
        
        Args:
            text (str): 解析対象のテキスト
            
        Returns:
            Dict[str, Any]: 解析結果
        """
        # デフォルト結果
        result = {
            "should_exit": False,
            "confidence": 50,  # デフォルト値
            "reason": "テキスト解析の結果",
            "strategy": "保持継続（テキスト解析による判断）"
        }
        
        # 売却推奨のキーワード
        exit_keywords = ["売却", "exit", "sell", "売り", "手放す", "クローズ", "利確", "損切り", "離脱"]
        hold_keywords = ["保持", "継続", "hold", "ホールド", "キープ", "待機"]
        
        # 売却判断の抽出
        should_exit = False
        for keyword in exit_keywords:
            if keyword in text.lower():
                should_exit = True
                result["strategy"] = "売却（テキスト解析による判断）"
                break
                
        # 保持推奨が明示的に含まれているかチェック
        for keyword in hold_keywords:
            if keyword in text.lower():
                should_exit = False
                result["strategy"] = "保持継続（テキスト解析による判断）"
                # exitキーワードよりholdキーワードを優先するため、すでにexit=Trueでも上書き
                break
                
        result["should_exit"] = should_exit
        
        # 理由の抽出
        reason = self._extract_reason_from_text(text)
        if reason:
            result["reason"] = reason
            
        # 信頼度のパターン
        confidence_pattern = r'(?:信頼度|confidence)[:\s]*(\d+)'
        confidence_match = re.search(confidence_pattern, text, re.IGNORECASE)
        if confidence_match:
            try:
                result["confidence"] = int(confidence_match.group(1))
            except ValueError:
                pass
                
        return result 