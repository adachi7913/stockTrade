import requests
import os
import json  # json モジュールをインポート
import re
from decimal import Decimal
import time  # リトライ用に追加
import logging

class ApiHandler:
    def __init__(self, data, backtest_results=None):
        self.data = data
        self.backtest_results = backtest_results or []

    def get_prompt(self):
        # Decimal 型の値を float に変換するヘルパー関数
        def convert_decimals(obj):
            if isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            elif isinstance(obj, Decimal):
                return float(obj)
            return obj

        # 最新データ(full_data)から最終レコードを抽出
        latest_record = self.data[-1]
        # convert_decimals関数を使用して終値を整形（convert_decimalsは消さないでください）
        entry_close = convert_decimals(latest_record["close"])
        
        # バックテスト結果をJSON形式に変換
        backtest_results_json = json.dumps(convert_decimals(self.backtest_results), ensure_ascii=False, indent=2)
        
        prompt = f"""
        【前提】
        **日本語のみ**で回答してください。
        あなたは優秀な個人投資家かつトレード戦略構築のエキスパートです。過去のデータや各種テクニカル指標をもとに、エントリー判断を段階的フィルタリングで実施し、その結果に基づいてエントリーの信頼性を1000点満点で評価してください。
        
        【エントリー判断の評価基準】
        1. リターン値とリスク値を算出し、リスクリワード比を求める（基礎点300点）
        2. 各指標の整合性評価（最大400点）：
           - トレンド分析（一目均衡表、MACD）：100点
           - モメンタム（RSI、ストキャスティクス）：100点
           - ボラティリティ（ボリンジャーバンド、ATR）：100点
           - 出来高分析：100点
        3. バックテスト結果の反映（最大300点）：
           - 勝率と期待値：100点
           - ドローダウン：100点
           - 一貫性：100点

        【エントリー価格の設定】
        エントリー価格は、最新の終値（{entry_close} 円）付近に設定してください。大幅な乖離がある場合は、必ず最新の終値に近い価格に調整してください。

        【データ品質チェック】
        - 各指標の欠損や異常値をチェック
        - 銘柄によっては過去データが不足している場合があるので、その部分を考慮せず、確認できるデータの範囲で評価してください。
        - データの欠落などで、連続性のないデータ不備がある場合は、該当指標を明記し、スコアを減点

        【バックテスト戦略の説明】
        提供されるバックテスト結果は、以下の3つの戦略を使用して生成されています。各戦略の特徴を理解し、現在の市場状況に最も適した戦略を判断してください。

        1. トレンドフォロー戦略（trend）:
           - 使用指標: 一目均衡表、MACD、ADX（平均方向性指数）
           - エントリー条件: MACD > 0 かつ ADX > 25 かつ 株価 > 一目均衡表の先行スパンA
           - 決済条件: MACD < 0 または 株価 < 一目均衡表の先行スパンB
           - 特徴: 相場のトレンドに沿って取引を行い、強いトレンドが発生している場合に効果的

        2. 逆張り戦略（reverse）:
           - 使用指標: RSI、ストキャスティクス、ボリンジャーバンド
           - エントリー条件: RSI < 30 かつ ストキャスティクスK < 20 かつ 株価 <= ボリンジャーバンド下限
           - 決済条件: RSI > 70 または 株価 >= ボリンジャーバンド中央線
           - 特徴: 過度に売られた状態からの反発を狙い、レンジ相場で効果的

        3. ブレイクアウト戦略（breakout）:
           - 使用指標: ATR、ボリンジャーバンド、前日高値
           - エントリー条件: 株価 > ボリンジャーバンド上限 かつ 株価 > 前日高値
           - 決済条件: 株価 < ボリンジャーバンド中央線
           - 特徴: 価格が重要なレベルを突破した際のモメンタムを捉え、急激な値動きで利益を得る

        【バックテスト期間】
        バックテスト結果は以下の3つの期間で実施されています:
        1. 5年前から現在まで: 長期的な戦略の有効性を評価
        2. 1年前から現在まで: 最近の市場環境での戦略の有効性を評価
        3. 2年前から1年前まで: 過去の異なる市場環境での戦略の有効性を評価

        【バックテスト結果の解釈】
        - 各取引（trades）の詳細: エントリー日、エントリー価格、ロットサイズ、決済日、決済価格、利益
        - 最終ポートフォリオ価値（final_portfolio_value）: バックテスト終了時の資産価値（初期資金100万円）
        - 戦略間の比較: 各戦略の勝率、平均利益、最大ドローダウンを比較
        - 期間による違い: 異なる期間での戦略の有効性の違いを分析

        【提供データ】
        {json.dumps(convert_decimals(self.data), ensure_ascii=False)}

        【バックテスト結果】
        {backtest_results_json}

        【タスク】
        1. 提供データを元に段階的フィルタリングを実施
        2. 各評価基準に基づいてスコアリング
        3. バックテストによる検証
           - 各戦略の結果を分析し、現在の市場状況に最も適した戦略を特定
           - 期間による結果の違いから、市場環境の変化を考慮
           - 取引パターンから、成功率の高いエントリー・決済条件を抽出
        4. データ品質の確認と反映
        5. 信頼性のスコアが700点を超える場合、ロングポジションでのエントリールール（entryPrice, stop_loss, target_price, period, risk_reward）を出力してください。
        6. 信頼性のスコアが700点を超えない場合、ロングポジションでのエントリールール（entryPrice, stop_loss, target_price, period, risk_reward）はNGを出力してください。

        【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
        {{
            "entry_score": <0〜1000の整数>,
            "reason": "エントリー判断の理由及び各段階での点数根拠",
            "rule": {{
                "entryPrice": "エントリー価格（金額のみ）" or "NG",
                "stop_loss": "ストップロス価格（金額のみ）" or "NG",
                "target_price": "利確目標（金額のみ）" or "NG",
                "period": "推奨保有期間（整数）" or "NG",
                "risk_reward": "リスクリワード比（計算結果）" or "NG"
            }},
            "no_entry_span": <再判断までの日数（整数:1 - 14）>
        }}
        """
        return prompt


    def _extract_json(self, content):
        """
        Gemini API のレスポンス中、マークダウンの ```json ... ``` 形式で囲まれている場合、
        その中身のみを抽出するヘルパー関数
        """
        match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1)
        return content

    def call_gemini_api(self):
        print("call_gemini_api() started")
        print("Calling Gemini API")
        api_key = os.environ.get("GEMINI_API_KEY")  # 環境変数からAPIキーを取得
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            return "API key not set"  # APIキーがない場合はエラーメッセージを返す
        model = os.environ.get("GEMINI_MODEL")  # 環境変数からモデル名を取得
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        prompt = self.get_prompt() # getPrompt関数でプロンプトを生成
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt} # 生成したプロンプトをpayloadに設定
                    ]
                }
            ]
        }
        headers = {'Content-Type': 'application/json'}

        max_retries = 3  # 最大リトライ回数
        attempt = 0
        while attempt < max_retries:
            try:
                response = requests.post(api_url, json=payload, headers=headers)
                # 503の場合はリトライ
                if response.status_code == 503:
                    attempt += 1
                    print(f"Gemini API returned 503. Retrying {attempt}/{max_retries} after 5 seconds...")
                    time.sleep(5)
                    continue
                response.raise_for_status()
                json_response = response.json()
                # print("API response:", json_response)
                
                # Gemini APIからのレスポンスを処理します
                # if json_response and 'candidates' in json_response and json_response['candidates']:
                #     content = json_response['candidates'][0]['content']['parts']['text']
                try:
                    # usageMetadataからトークン情報をログ出力する
                    usage = json_response.get("usageMetadata", {})
                    logging.info("入力トークン(promptTokenCount): %s", usage.get("promptTokenCount", "不明"))
                    logging.info("候補トークン(candidatesTokenCount): %s", usage.get("candidatesTokenCount", "不明"))
                    logging.info("合計トークン(totalTokenCount): %s", usage.get("totalTokenCount", "不明"))
                    content = json_response['candidates'][0]['content']['parts'][0]['text']
                    json_text = self._extract_json(content)
                    return json_text
                except Exception as e:
                    print("JSON parse error:", e)
                    return {"error": "JSON parse error", "raw": json_response.get('candidates', [{}])[0].get('content')}
                # else:
                #     return {"error": "No prediction found or invalid API response"}
            except requests.RequestException as e:
                if e.response is not None and e.response.status_code == 503:
                    attempt += 1
                    print(f"RequestException with 503 received. Retrying {attempt}/{max_retries} after 5 seconds...")
                    time.sleep(5)
                    continue
                else:
                    print(f"Gemini API call failed: {e}, request: {e.request}, response: {e.response}")
                    return f"Gemini API call failed: {e}"
        return {"error": "Failed after multiple retries due to 503 response."}
    
    