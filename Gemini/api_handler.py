import requests
import os
import json  # json モジュールをインポート
import re
from decimal import Decimal
import time  # リトライ用に追加
import logging

class ApiHandler:
    def __init__(self, data):
        self.data = data

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
        
        # prompt = f"""
        # 【前提】英語で思考し、**日本語のみ**で回答してください。
        # 【内容】
        # あなたは優秀な個人投資家であり、短期スウィングトレードに精通しています。
        # 市場動向、各種インジケーター、そして株価の推移をもとに、エントリーの可否と最適なトレード戦略を構築してください。
        # エントリー可否の判断は、以下のルールに従ってください:
        # ・エントリー可否は、**可能/不可**のいずれかで回答してください。
        # ・リスクリワードが2.0以上の場合のみエントリー可能とします。
        # ・エントリーはロングのみとします
        # ・作成したトレードルールを自己採点し、**Scoreを0 ~ 100で算出**してください。
        # ・エントリー不可の場合、Scoreは0とします。
        # ・エントリー価格は、最新の終値（{entry_close} 円）から大幅に乖離しないようにしてください。具体的には、必ず最新の終値に近接する価格帯で設定し、乖離が大きい場合は最新の終値に近い価格に調整してください。
        # ・推奨保有期間は、**〇日～〇日**の形式とします。
        # ・エントリー不可の場合、no_entry_spanに再判断するまでの期間を記載してください。**数字で日数のみ**記載してください。
        # 今回は、DBから取得した最大過去数年間分の株価データと各インジケーター（以下がそのデータ構造）を提供します。
        # 各レコードは、次の構成になっています:

        # 　{{
        # 　　　"code": 株式コード,
        # 　　　"date": "YYYYMMDD形式の日付",
        # 　　　"open": 始値,
        # 　　　"high": 高値,
        # 　　　"low": 安値,
        # 　　　"close": 終値,
        # 　　　"volume": 出来高,
        # 　　　"ichimoku": {{
        # 　　　　"tenkan": 転換線,
        # 　　　　"kijun": 基準線,
        # 　　　　"senkou_a": 先行スパンA,
        # 　　　　"senkou_b": 先行スパンB
        # 　　　}},
        # 　　　"adx": ADX,
        # 　　　"bb": {{
        # 　　　　"lower": ボリンジャーバンド下限,
        # 　　　　"middle": ボリンジャーバンド中央値,
        # 　　　　"upper": ボリンジャーバンド上限
        # 　　　}},
        # 　　　"stoch": {{
        # 　　　　"stoch_k": ストキャスティクス%K,
        # 　　　　"stoch_d": ストキャスティクス%D
        # 　　　}},
        # 　　　"atr": ATR,
        # 　　　"rsi": RSI,
        # 　　　"macd": MACD
        # 　}}


        # 【提供データ】
        # {json.dumps(convert_decimals(self.data), ensure_ascii=False)}
        # **1.提供データを元にエントリールールについて思考してください
        # **2.思考したエントリールールでバックテストを行い、考案したエントリールールにエッジがあるかを確認してください**
        # **3.エントリールールにエッジがない場合、エントリールールを修正してください**
        # 出力形式は下記です。**JSONの形式を厳守**し、その他の内容は回答に含めないでください。:
        # 【出力形式】
        # {{isEntry:**"可能" / "不可"**, reason:**"理由"**, rule:{{entryPrice:**"Entry価格（金額のみ）"** / "NG", sl:**"SL価格"** / "NG", tp:**"利確目標"** / "NG", period:**"推奨保有期間"** / "NG", riskReward:**"リスクリワード"** / "NG"}}, score:**"0 ~ 100"**, no_entry_span:**"1 ~ 14"**}}
        # """
        # return prompt
        
        prompt = f"""
        【前提】英語で思考し、**日本語のみ**で回答してください。

        【内容】
        あなたは優秀な個人投資家であり、短期スウィングトレードに精通しています。市場動向、各種インジケーター、そして株価の推移をもとに、エントリーの可否と最適なトレード戦略を構築してください。

        【エントリー判断の評価基準】
        - エントリー判断は**可能/不可**のいずれかで回答してください。
        - リスクリワード比は、(利確目標 - エントリー価格) ÷ (エントリー価格 - SL価格) で計算し、**2.0以上**の場合のみエントリー可能とします。
        - エントリーはロングのみとし、エントリー価格は最新の終値（{entry_close} 円）付近に設定してください。大幅な乖離がある場合は、必ず最新の終値に近い価格に調整してください。

        【評価と自己採点】
        - 作成したトレードルールを、以下の評価項目に基づき自己採点してください：
        1. **エントリールールの明確性**：判断基準やシグナルが具体的かどうか。
        2. **バックテストの有効性**：過去データに対するルールのパフォーマンス（勝率、利益率、ドローダウンなど）。
        3. **リスクリワード比の信頼性**：計算されたリスクリワード比の妥当性。
        - 自己採点は**Scoreを0 ~ 100**で算出してください。エントリー不可の場合、Scoreは0とします。

        【バックテスト結果のフィードバックループ】
        - 提供データを用いてバックテストを実施し、構築したエントリールールに有利なエッジが存在するかを確認してください。
        - バックテストの結果、エッジが見られない場合は、以下の点を再検討し、エントリールールを修正してください：
        - 指標間のシグナルの一貫性とタイミング
        - 市場のボラティリティやノイズへの対応
        - エントリーおよび決済ポイントの最適化
        - 修正後のルールについても、同様の評価基準で再評価し、必要に応じて自己採点を更新してください.

        【追加インジケーター要素の説明】
        - dynamic_threshold: ATRの比率から計算される動的な閾値。現在の株価の変動性を反映します。
        - weekly_trend: 週次のSMAを使用して判断された市場のトレンド（"UP" または "DOWN"）です。市場全体の傾向を示します。
        - pca_signal: PCAによる次元削減で算出された最新データの第一主成分のシグナルです.
        
        【提供データ】
        {json.dumps(convert_decimals(self.data), ensure_ascii=False)}

        **タスク**
        1. 提供データを元にエントリールールについて思考し、具体的なトレード戦略を構築してください。
        2. 構築したエントリールールでバックテストを行い、ルールに有利なエッジがあるかを確認してください。
        3. バックテストでエッジが見られなかった場合、エントリールールを修正し、再評価してください。

        【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
        {{
        "isEntry": "可能" or "不可",
        "reason": "エントリー判断の理由（評価基準やバックテスト結果に基づく説明）",
        "rule": {{
            "entryPrice": "エントリー価格（金額のみ）" or "NG",
            "sl": "SL価格" or "NG",
            "tp": "利確目標" or "NG",
            "period": "推奨保有期間（例：3日～5日）" or "NG",
            "riskReward": "リスクリワード比（計算結果）" or "NG"
        }},
        "score": "0 ~ 100",
        "no_entry_span": "1 ~ 14"  // エントリー不可の場合の再判断までの日数（数字のみ）
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
    
    