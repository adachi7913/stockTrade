import requests
import os
import json  # json モジュールをインポート
import re
from decimal import Decimal
import time  # リトライ用に追加
import logging
import google.generativeai as genai  # ★ インポート追加
import unicodedata  # 文字列サニタイズ用に追加

class ApiHandler:

    def get_prompt(self):
        # 文字列をサニタイズするヘルパー関数を追加
        def sanitize_string(text):
            if isinstance(text, str):
                # 非ASCII文字や制御文字を除去または置換
                # unicodedataを使用して正規化し、制御文字（Cf）を除去
                return ''.join(c for c in unicodedata.normalize('NFKD', text) 
                              if not unicodedata.category(c).startswith('C') or c in ['\n', '\t'])
            return text

        # Decimal 型の値を float に変換し、さらに文字列をサニタイズするヘルパー関数
        def convert_decimals_and_sanitize(obj):
            if isinstance(obj, dict):
                return {k: convert_decimals_and_sanitize(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals_and_sanitize(item) for item in obj]
            elif isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, str):
                return sanitize_string(obj)  # 文字列をサニタイズ
            return obj

        # 最新データから最終レコードを抽出し、サニタイズも行う
        latest_record = self.data[-1]
        # convert_decimals_and_sanitize関数を使用してデータを整形
        entry_close = convert_decimals_and_sanitize(latest_record["close"])
        
        # データとバックテスト結果をサニタイズしてからJSONに変換
        sanitized_data = convert_decimals_and_sanitize(self.data)
        sanitized_backtest_results = convert_decimals_and_sanitize(self.backtest_results)
        
        # バックテスト結果をJSON形式に変換
        backtest_results_json = json.dumps(sanitized_backtest_results, ensure_ascii=False, indent=2)
        
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
        {json.dumps(sanitized_data, ensure_ascii=False)}

        【バックテスト結果】
        {backtest_results_json}

        【追加分析要求】
        提供データに基づいて、以下の項目について詳細な分析を行ってください：

        1. エントリー/決済のトリガー条件：
           - 最適なエントリー条件を具体的なテクニカル指標の数値で明示（例：「RSIが30以下から上昇転換したとき」）
           - 最適な決済条件を具体的なテクニカル指標の数値や価格レベルで明示（例：「目標価格到達時または20日移動平均線を下抜けたとき」）
           - 時間外でも判断できる条件を優先すること

        2. トレンド分析：
           - 短期（5-20日）、中期（20-60日）、長期（60日以上）それぞれのトレンド方向
           - トレンドの強さの定量的評価（ADXなどの数値で）
           - 主要な移動平均線（5日、20日、60日など）の配置と方向性
           - サポート/レジスタンスとなる重要な価格帯

        3. テクニカルパターン分析：
           - 現在形成されている主要なチャートパターン（ダブルボトム、三角保ち合いなど）
           - 価格形成の特徴（高値切り上げ/安値切り上げなど）
           - 直近の重要な価格変動ポイントとその意味

        4. 複合指標分析：
           - 複数の指標を組み合わせた総合判断
           - 順張り/逆張りのどちらが有効か
           - 指標間の乖離や収束の状況分析
           - 過去の類似パターンとの比較分析

        【タスク】
        1. 提供データを元に段階的フィルタリングを実施し、ロングポジションとショートポジションの両方についてエントリーの妥当性を評価してください。
        2. 各評価基準に基づいて、ロングとショートそれぞれのエントリー信頼性スコアを算出してください（1000点満点）。
        3. バックテストによる検証：
           - 各戦略の結果を分析し、現在の市場状況に最も適した戦略をロング・ショートそれぞれで特定。
           - 期間による結果の違いから、市場環境の変化を考慮。
           - 取引パターンから、成功率の高いエントリー・決済条件をロング・ショートそれぞれで抽出。
        4. データ品質の確認と反映。
        5. 上記の追加分析を実施。
        6. **ロング**の信頼性スコアが700点を超える場合、ロングポジションでのエントリールールを出力候補とします。
        7. **ショート**の信頼性スコアが700点を超える場合、ショートポジションでのエントリールールを出力候補とします。（ショートの目標価格はエントリー価格より低く、ストップロスはエントリー価格より高くなります）
        8. ロング・ショート両方のスコアが700点を超える場合は、**よりスコアの高い方**のルールを採用してください。
        9. ロング・ショートどちらか一方のスコアのみが700点を超える場合は、そのポジションのルールを採用してください。
        10. ロング・ショート両方のスコアが700点以下の場合、ポジションは「hold」（見送り）とし、ルールはすべて"NG"としてください。

        【出力形式】（以下のJSON形式を厳守し、その他の内容は含めないでください）
        {{
            "position": "long" or "short" or "hold",
            "entry_score": <0〜1000の整数 (採用されたポジションのスコア、見送りの場合は0)>,
            "reason": "エントリー判断の理由及び各段階での点数根拠（ロング・ショート両方の評価を含む）",
            "rule": {{
                "entryPrice": "エントリー価格（金額のみ）" or "NG",
                "stop_loss": "ストップロス価格（金額のみ）" or "NG",
                "target_price": "利確目標（金額のみ）" or "NG",
                "period": "推奨保有期間（整数:1 - 14）" or "NG",
                "risk_reward": "リスクリワード比（計算結果）" or "NG"
            }},
            "entry_conditions": "具体的なエントリートリガー条件（採用ポジション）",
            "exit_conditions": "具体的な決済条件（採用ポジション）",
            "market_analysis": {{
                "short_term_trend": "短期トレンドの方向と強さ",
                "mid_term_trend": "中期トレンドの方向と強さ",
                "long_term_trend": "長期トレンドの方向と強さ",
                "support_resistance": "主要なサポート/レジスタンスレベル"
            }},
            "technical_patterns": "検出されたチャートパターンと価格形成の特徴",
            "indicator_analysis": "複数指標の総合分析結果（ロング・ショート両視点）",
            "no_entry_span": <再判断までの日数（整数:1 - 14）>
        }}
        """
        self.logger.debug(f"生成されたプロンプトのサイズ: {len(prompt)}バイト")
        return prompt

    def __init__(self, data, prompt=None, backtest_results=None, logger=None):
        self.data = data
        self.backtest_results = backtest_results or []
        self.logger = logger if logger else logging.getLogger(__name__) # ★ ロガーのデフォルト名を修正
        self.prompt = prompt if prompt else self.get_prompt()

        # ★ APIキーの設定とモデルの初期化を追加
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            self.logger.error("GEMINI_API_KEY environment variable not set.")
            raise ValueError("APIキーが設定されていません。")
        genai.configure(api_key=api_key)

        # 使用するモデル名を取得 (環境変数 or デフォルト値)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
        self.model = genai.GenerativeModel(model_name)
        self.logger.info(f"ApiHandler initialized with model: {model_name}")

    def _extract_json(self, content):
        """APIレスポンスからJSON部分を抽出"""
        if not content:
            self.logger.error("抽出しようとしたコンテンツが空です")
            return None
            
        # 1. Markdown形式のJSONブロックを探す - より柔軟なパターン
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        code_blocks = re.findall(code_block_pattern, content)
        
        if code_blocks:
            for block in code_blocks:
                # ブロックから空白行を取り除く
                cleaned_block = block.strip()
                if cleaned_block:
                    # JSONオブジェクトまたは配列として始まるか確認
                    if cleaned_block.startswith('{') or cleaned_block.startswith('['):
                        self.logger.info("{}で囲まれた部分からJSONを抽出しました")
                        # 一部の特殊なJSONフォーマットエラーを事前に修正
                        return cleaned_block
                    else:
                        self.logger.warning(f"マークダウンブロック内のテキストがJSONオブジェクトまたは配列で始まっていません: {cleaned_block[:30]}...")
        
        # 2. JSONオブジェクトの検索（markdown形式でない場合）
        self.logger.info("マークダウンブロックが見つからなかったため、テキスト内でJSONを検索します")
        
        # 単一行でのJSON表現
        json_pattern1 = r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}"
        json_matches1 = re.findall(json_pattern1, content)
        
        # 配列形式のJSON表現
        json_pattern2 = r"\[(?:[^\[\]]|(?:\[[^\[\]]*\]))*\]"
        json_matches2 = re.findall(json_pattern2, content)
        
        # 両方の結果を結合し、長さでソート
        all_json_candidates = json_matches1 + json_matches2
        if all_json_candidates:
            # 最も長いものを選択（最も完全なJSONである可能性が高い）
            all_json_candidates.sort(key=len, reverse=True)
            best_candidate = all_json_candidates[0]
            
            # 事前検証: 基本的な構造の確認
            if (best_candidate.startswith('{') and best_candidate.endswith('}')) or \
               (best_candidate.startswith('[') and best_candidate.endswith(']')):
                self.logger.info(f"テキスト内からJSONオブジェクトを検出しました（長さ: {len(best_candidate)}文字）")
                # 一部の特殊なJSONフォーマットエラーを事前に修正
                return best_candidate
        
        # 3. 前処理: テキスト全体が大きなJSONのような構造を持っているが、
        # マークダウンブロックでない場合（特にAPIが誤って```jsonを省略した場合）
        content_cleaned = content.strip()
        if content_cleaned.startswith('{') and content_cleaned.endswith('}'):
            self.logger.info("レスポンス全体がJSONオブジェクトの可能性があります")
            # 全体をJSONとして試す
            return content_cleaned
        elif content_cleaned.startswith('[') and content_cleaned.endswith(']'):
            self.logger.info("レスポンス全体がJSON配列の可能性があります")
            # 全体をJSONとして試す
            return content_cleaned
        
        # 4. 特別なケース: コードブロックはあるが、JSONとして認識されていないケース
        general_code_pattern = r"```([\s\S]*?)```"
        general_blocks = re.findall(general_code_pattern, content)
        if general_blocks:
            for block in general_blocks:
                cleaned_block = block.strip()
                if cleaned_block.startswith('{') or cleaned_block.startswith('['):
                    self.logger.info("一般的なコードブロックからJSONを抽出しました")
                    return cleaned_block
        
        # 5. 特別なケース: JSONが```で囲まれていないが、始まりと終わりが明確な場合
        # 特に行の先頭から始まるJSONオブジェクト
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('{'):
                # このラインからJSONが始まっている可能性
                json_text = ""
                bracket_count = 0
                for j in range(i, len(lines)):
                    json_text += lines[j] + "\n"
                    bracket_count += lines[j].count('{') - lines[j].count('}')
                    if bracket_count == 0 and '}' in lines[j]:
                        # 閉じ括弧が見つかった
                        self.logger.info("行先頭から始まるJSONブロックを検出しました")
                        return json_text.strip()
        
        # 6. その他の場合: JSON抽出に失敗
        self.logger.error("有効なJSON形式が見つかりませんでした")
        return None

    def call_gemini_api(self, prompt=None, temperature=0.5, top_k=3, top_p=0.9, max_output_tokens=4096, safety_filter=None, stock_code=None, retry_count=0):
        """
        Gemini APIを呼び出してテキスト生成を行い、JSONレスポンスを取得します
        
        Args:
            prompt (str, optional): 送信するプロンプト。Noneの場合はself.promptを使用
            temperature (float, optional): 生成の温度パラメータ。デフォルトは0.5
            top_k (int, optional): 生成のtop_kパラメータ。デフォルトは3
            top_p (float, optional): 生成のtop_pパラメータ。デフォルトは0.9
            max_output_tokens (int, optional): 最大出力トークン数。デフォルトは4096
            safety_filter (list, optional): 安全性フィルター設定
            stock_code (str, optional): 処理対象の銘柄コード
            retry_count (int, optional): リトライ回数。デフォルトは0
            
        Returns:
            dict or None: 解析されたJSONオブジェクト、または失敗時はNone
        """
        # promptが指定されていない場合は、インスタンス変数のself.promptを使用
        if prompt is None:
            prompt = self.prompt
            self.logger.info("インスタンス変数のプロンプトを使用します")
        
        if retry_count >= 5:
            self.logger.error("リトライ回数上限に達しました。処理を中止します。")
            return None
        
        try:
            # 完全なプロンプトログ（長すぎる場合は先頭と末尾500文字）
            if len(prompt) > 1000:
                self.logger.info(f"プロンプト(先頭500文字): {prompt[:500]}...")
                self.logger.info(f"プロンプト(末尾500文字): ...{prompt[-500:]}")
            else:
                self.logger.info(f"プロンプト: {prompt}")
            
            # 生成パラメータ設定
            generation_config = {
                "temperature": temperature,
                "top_k": top_k,
                "top_p": top_p,
                "max_output_tokens": max_output_tokens,
            }
            
            # 安全性設定
            safety_settings = []
            if safety_filter:
                safety_settings = safety_filter

            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # レスポンス情報のログ記録
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                
                # メタデータからトークン情報を抽出
                if hasattr(response, 'usage_metadata'):
                    metadata = response.usage_metadata
                    self.logger.info(f"入力トークン(promptTokenCount): {metadata.prompt_token_count}")
                    self.logger.info(f"候補トークン(candidatesTokenCount): {metadata.candidates_token_count}")
                    self.logger.info(f"合計トークン(totalTokenCount): {metadata.total_token_count}")
                
                # finish_reasonの確認
                finish_reason = getattr(candidate, 'finish_reason', None)
                
                # finish_reasonの値による処理分岐
                if finish_reason == 'MAX_TOKENS' or finish_reason == 1:
                    self.logger.warning(f"API応答が最大トークン数に達して途切れました。finishReason: {finish_reason}")
                elif finish_reason == 'SAFETY' or finish_reason == 2:
                    self.logger.error(f"APIの安全フィルターにより応答が途切れました。finishReason: {finish_reason}")
                    raise Exception(f"APIの安全フィルターにより応答が途切れました: {finish_reason}")
                elif finish_reason != 'STOP' and finish_reason is not None and finish_reason != 0:
                    self.logger.warning(f"想定外のfinishReason: {finish_reason}")
            
            if hasattr(response, 'text'):
                text = response.text
            elif hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts'):
                text = response.candidates[0].content.parts[0].text
            else:
                self.logger.error(f"APIレスポンスの構造が想定と異なります: {response}")
                if retry_count < 5:
                    self.logger.info(f"APIリクエストをリトライします ({retry_count+1}/5)")
                    time.sleep(3 * (retry_count + 1))  # 指数バックオフ
                    return self.call_gemini_api(prompt, temperature, top_k, top_p, max_output_tokens, safety_filter, stock_code, retry_count + 1)
                return None
            
            # レスポンス全体をログ（常に完全な内容をログ）
            self.logger.info(f"APIレスポンス全文: {text}")
            
            # JSONの抽出試行
            json_content = self._extract_json(text)
            
            if json_content:
                self.logger.info("マークダウンブロックからJSONを正常に抽出・検証しました")
                
                # ジェイソンの整形と検証
                try:
                    json_obj = json.loads(json_content)
                    # 銘柄コードのログ記録
                    if stock_code:
                        self.logger.info(f"銘柄コード: {stock_code}")
                    
                    # 整形済みJSON
                    formatted_json = json.dumps(json_obj, ensure_ascii=False, indent=4)
                    self.logger.info(f"Gemini API response: {formatted_json}")
                    
                    return json_obj
                except json.JSONDecodeError as e:
                    # JSON構文チェックエラー - 修復を試みる
                    self.logger.error(f"JSONの構文チェックに失敗: {e}")
                    
                    # エラー位置の情報を取得
                    error_msg = str(e)
                    error_pos = None
                    if "char " in error_msg:
                        error_pos = int(error_msg.split("char ")[-1].rstrip(")"))
                    
                    if error_pos is not None:
                        # エラー位置の前後のテキストを表示
                        start_pos = max(0, error_pos - 20)
                        end_pos = min(len(json_content), error_pos + 20)
                        context = json_content[start_pos:end_pos]
                        self.logger.error(f"エラー位置周辺のテキスト: {context}")
                    
                    # JSON修復の試み
                    self.logger.info("JSONエラー修復を試みます")
                    
                    # 問題のあるJSONを修復
                    repaired_json = self.repair_json(json_content)
                    self.logger.info("JSON修復を適用しました")
                    
                    try:
                        # 修復したJSONを再パース
                        json_obj = json.loads(repaired_json)
                        self.logger.info("JSON修復に成功しました")
                        
                        # 銘柄コードのログ記録
                        if stock_code:
                            self.logger.info(f"銘柄コード: {stock_code}")
                        
                        # 整形済みJSON
                        formatted_json = json.dumps(json_obj, ensure_ascii=False, indent=4)
                        self.logger.info(f"修復後のGemini API response: {formatted_json}")
                        
                        return json_obj
                    except json.JSONDecodeError as e2:
                        # 修復が失敗した場合、テキスト内の特殊文字を徹底的に処理
                        self.logger.error(f"JSON修復に失敗しました: {e2}")
                        
                        # さらに修復試行:
                        # 1. 引用符で囲まれた部分内にある「コロンで区切られた数値表記」を特殊処理
                        bracketed_pattern = r'"([^"]*\([^"]*?[A-Za-z]+:\d+(?:\.\d+)?[^"]*?\))[^"]*"'
                        matches = re.finditer(bracketed_pattern, repaired_json)
                        enhanced_json = repaired_json
                        for match in matches:
                            escaped = match.group(1).replace(":", "\\:")
                            enhanced_json = enhanced_json.replace(match.group(1), escaped)
                            self.logger.info(f"引用符内のコロン記法をエスケープしました")
                        
                        try:
                            # さらに修復したJSONを再パース
                            json_obj = json.loads(enhanced_json)
                            self.logger.info("拡張JSON修復に成功しました")
                            
                            # 銘柄コードのログ記録
                            if stock_code:
                                self.logger.info(f"銘柄コード: {stock_code}")
                            
                            # 整形済みJSON
                            formatted_json = json.dumps(json_obj, ensure_ascii=False, indent=4)
                            self.logger.info(f"拡張修復後のGemini API response: {formatted_json}")
                            
                            return json_obj
                        except json.JSONDecodeError as e3:
                            # 全ての修復が失敗した場合
                            self.logger.error(f"JSONデコードエラー: {e3}")
                            self.logger.error(f"対象テキスト: {json_content[:100]}...")
                            
                            # エラー位置の情報
                            error_msg = str(e3)
                            if "char " in error_msg:
                                error_pos = int(error_msg.split("char ")[-1].rstrip(")"))
                                start_pos = max(0, error_pos - 15)
                                end_pos = min(len(enhanced_json), error_pos + 15)
                                context = enhanced_json[start_pos:end_pos]
                                self.logger.error(f"エラー位置周辺のテキスト: {context}")
                                self.logger.error(f"エラー位置: {error_pos}")
                            
                            # ログを残してエラーメッセージを表示
                            if stock_code:
                                self.logger.warning(f"{stock_code}: AIレスポンスの解析に失敗しました")
                        
                            # AIリトライ
                            if retry_count < 3:
                                self.logger.info(f"新しいプロンプトでAPIリクエストをリトライします ({retry_count+1}/3)")
                                # 少し待機して再試行
                                time.sleep(3 * (retry_count + 1))
                                
                                # よりシンプルなプロンプトを試す
                                if retry_count >= 1:
                                    prompt = self.simplify_prompt(prompt)
                                    self.logger.info("プロンプトを簡略化しました")
                                
                                return self.call_gemini_api(prompt, temperature, top_k, top_p, max_output_tokens, safety_filter, stock_code, retry_count + 1)
                                
                            # 最終的なフォールバック：テキスト内でJSONライクな構造を探す
                            self.logger.info("フォールバック: テキスト内でJSONライクな構造を検索")
                            json_candidates = self._extract_json_fallback(text)
                            
                            if json_candidates:
                                self.logger.info(f"代替JSONパターンを検出: {len(json_candidates)}候補")
                                for i, candidate in enumerate(json_candidates):
                                    try:
                                        json_obj = json.loads(candidate)
                                        self.logger.info(f"候補{i+1}のJSONパースに成功")
                                        
                                        # 銘柄コードのログ記録
                                        if stock_code:
                                            self.logger.info(f"銘柄コード: {stock_code}")
                                        
                                        # 整形済みJSON
                                        formatted_json = json.dumps(json_obj, ensure_ascii=False, indent=4)
                                        self.logger.info(f"代替パースのGemini API response: {formatted_json}")
                                        
                                        return json_obj
                                    except:
                                        continue
                                
                                self.logger.error("すべての代替JSON候補のパースに失敗")
                            
                            return None
            else:
                self.logger.error("APIレスポンスからJSONの抽出に失敗しました")
                
                # フォールバック：テキスト全体をJSONとして解析
                try:
                    # テキスト全体にJSON修復を試みる
                    self.logger.info("レスポンス全体をJSONとして解析を試みます")
                    repaired_text = self.repair_json(text)
                    json_obj = json.loads(repaired_text)
                    self.logger.info("レスポンス全体のJSON解析に成功しました")
                    
                    # 銘柄コードのログ記録
                    if stock_code:
                        self.logger.info(f"銘柄コード: {stock_code}")
                    
                    # 整形済みJSON
                    formatted_json = json.dumps(json_obj, ensure_ascii=False, indent=4)
                    self.logger.info(f"全体解析のGemini API response: {formatted_json}")
                    
                    return json_obj
                except:
                    self.logger.error("レスポンス全体のJSON解析にも失敗しました")
                    
                    # リトライ
                    if retry_count < 3:
                        self.logger.info(f"APIリクエストをリトライします ({retry_count+1}/3)")
                        # 少し待機して再試行
                        time.sleep(3 * (retry_count + 1))
                        
                        # よりシンプルなプロンプトを試す
                        if retry_count >= 1:
                            prompt = self.simplify_prompt(prompt)
                            self.logger.info("プロンプトを簡略化しました")
                        
                        return self.call_gemini_api(prompt, temperature, top_k, top_p, max_output_tokens, safety_filter, stock_code, retry_count + 1)
                    
                    # 最終的な失敗
                    self.logger.error("JSONデータの取得に失敗しました")
                    if stock_code:
                        self.logger.warning(f"{stock_code}: AIレスポンスの解析に失敗しました")
                    return None
        
        except Exception as e:
            # 安全性フィルターに関するエラー
            if "safety" in str(e).lower():
                self.logger.error(f"安全性フィルターによりAPIリクエストがブロックされました: {e}")
                if stock_code:
                    self.logger.warning(f"{stock_code}: 安全性フィルターにより処理がブロックされました")
                return None
            
            # 一般的なAPI関連エラー
            elif "google.api_core" in str(type(e)) or "googleapiclient" in str(type(e)):
                self.logger.error(f"Google API エラー: {e}")
                
                # 503エラーの場合、リトライロジック
                if "503" in str(e) and retry_count < 5:
                    self.logger.info(f"サーバー過負荷(503)のため、リトライします ({retry_count+1}/5)")
                    time.sleep(5 * (retry_count + 1))  # より長い待機時間
                    return self.call_gemini_api(prompt, temperature, top_k, top_p, max_output_tokens, safety_filter, stock_code, retry_count + 1)
                
                if stock_code:
                    self.logger.warning(f"{stock_code}: APIエラーにより処理に失敗しました")
                return None
            
            # その他の予期せぬエラー
            else:
                self.logger.error(f"予期せぬエラー: {e}")
                self.logger.exception("スタックトレース:")
                if stock_code:
                    self.logger.warning(f"{stock_code}: 予期せぬエラーにより処理に失敗しました")
                return None
                
    def _extract_json_fallback(self, text):
        """テキスト内でJSONライクな構造を検索するフォールバックメソッド"""
        candidates = []
        
        # 候補1: 中括弧で囲まれた部分を抽出
        pattern1 = r'\{[^{]*?\}'
        matches = re.finditer(pattern1, text)
        for match in matches:
            if len(match.group(0)) > 50:  # 最低文字数でフィルター
                candidates.append(match.group(0))
        
        # 候補2: 角括弧で囲まれた部分を抽出
        pattern2 = r'\[[^[]*?\]'
        matches = re.finditer(pattern2, text)
        for match in matches:
            if len(match.group(0)) > 50:  # 最低文字数でフィルター
                candidates.append(match.group(0))
        
        # 候補の優先順位をサイズ順にソート（より長いものが完全なJSONである可能性が高い）
        candidates.sort(key=len, reverse=True)
        
        return candidates
        
    def simplify_prompt(self, prompt):
        """リトライ時のプロンプトを簡略化"""
        # コメントや詳細な指示を削除し、核となる部分のみを残す
        simplified = re.sub(r'(注意|備考|例|例えば).*?\n', '', prompt)
        simplified = re.sub(r'#.*?\n', '', simplified)
        # 長い説明をカット
        simplified = re.sub(r'\n.*?の詳細.*?\n', '\n', simplified)
        
        # JSONに関する要求を強調
        simplified += "\n\n重要: 返答は必ず有効なJSONフォーマットで返してください。Markdownの```json```ブロック内に配置してください。"
        
        return simplified
    
    def repair_json(self, json_str):
        """JSON文字列の問題を修復する関数
        
        Args:
            json_str (str): 修復対象のJSON文字列
            
        Returns:
            str: 修復後のJSON文字列
        """
        # 問題1: "key":value の形式で key が不適切に引用符で囲まれているケース（"D":48.04 など）
        # 正規表現でマッチして修正（より厳密なパターン）
        pattern = r'(\s|,|\{)("([^"]+)")(:[\s]*)(\d+\.?\d*|\d*\.\d+|\d+)'
        replacement = r'\1\3\4\5'
        fixed_str = re.sub(pattern, replacement, json_str)
        
        # "D" のような特定パターンも修正
        pattern2 = r'"([A-Za-z])"\s*:(\s*\d+\.?\d*)'
        replacement2 = r'\1:\2'
        fixed_str = re.sub(pattern2, replacement2, fixed_str)
        
        self.logger.info(f"引用符で囲まれたキーを修正しました（例: \"D\":48.04 → D:48.04）")
        
        # 問題2: 文字列としてJSONで処理すべき部分の修正
        # "key": "value" の形式になっていない場合を検出・修正
        pattern3 = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^",{\[\]}\s][^,{\[\]}\s]*)'
        replacement3 = r'"\1": "\2"'
        # ただし数値には適用しない (上記のパターンだと数値も変換してしまうため)
        
        # 特定の部分的なJSONエラーを修正：ストキャスティクス(K:41.5,"D":48.04)
        # このような文字列は厳密にはJSONではないが、エラーの原因となる
        pattern4 = r'ストキャスティクス\(K:(\d+\.?\d*),"?D"?:(\d+\.?\d*)\)'
        replacement4 = r'ストキャスティクス(K:\1,D:\2)'
        fixed_str = re.sub(pattern4, replacement4, fixed_str)
        
        # 問題3: コロン後の値に余分なカンマがある場合
        fixed_str = re.sub(r':\s*,', r':', fixed_str)
        self.logger.info(f"余分なカンマを削除しました（例: : , → :）")
        
        # 問題4: 末尾の余分なカンマを削除
        fixed_str = re.sub(r',(\s*[\]}])', r'\1', fixed_str)
        self.logger.info(f"末尾の余分なカンマを削除しました")
        
        # 問題5: 1.5のような数値の前に+がついている場合
        fixed_str = re.sub(r':\s*\+(\d+\.?\d*)', r':\1', fixed_str)
        self.logger.info(f"数値の前の+記号を削除しました")
        
        # 問題6: プレーンテキスト内のJSONのような構造を特定して修正
        # 例: "～という文言(K:10,D:20)が～" のような表記を検出し、JSONパースを妨げないよう修正
        try:
            # まず簡易的なJSON整合性チェック
            json.loads(fixed_str)
            self.logger.info("修復したJSONは整合性チェックに通過しました")
        except json.JSONDecodeError as e:
            # エラー位置のコンテキストを取得
            error_pos = int(str(e).split('char ')[-1].strip(')'))
            start = max(0, error_pos - 30)
            end = min(len(fixed_str), error_pos + 30)
            error_context = fixed_str[start:end]
            self.logger.warning(f"初回の修復後もJSONエラーが発生: {e}")
            self.logger.warning(f"エラー位置周辺のテキスト: {error_context}")
            
            # 追加の修復作業: エラー周辺の不適切なフォーマットを検出・修正
            # 例: key:"value" のような形式を "key":"value" に修正
            if re.search(r'[a-zA-Z_][a-zA-Z0-9_]*:"[^"]+"', error_context):
                pattern5 = r'([a-zA-Z_][a-zA-Z0-9_]*):"([^"]+)"'
                replacement5 = r'"\1":"\2"'
                fixed_str = re.sub(pattern5, replacement5, fixed_str)
                self.logger.info("キーが引用符で囲まれていない箇所を修正しました")
            
            # 括弧内の数値表記(例: (K:41.5,D:48.04))を検出し、必要に応じてエスケープ
            pattern6 = r'\(([a-zA-Z]+):(\d+\.?\d*),([a-zA-Z]+):(\d+\.?\d*)\)'
            matches = re.finditer(pattern6, fixed_str)
            for match in matches:
                original = match.group(0)
                escaped = f'({match.group(1)}:{match.group(2)},{match.group(3)}:{match.group(4)})'
                fixed_str = fixed_str.replace(original, escaped.replace('"', '\\"'))
                self.logger.info(f"括弧内の数値表記をエスケープ: {original} → {escaped}")
        
        return fixed_str
    
    