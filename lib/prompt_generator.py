#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class PromptGenerator:
    """
    AIモデル向けのプロンプトを生成するクラス
    
    低スペックのAIモデルでも効果的な判断ができるよう、
    必要最小限のデータを簡潔かつ構造化された形式で提供します。
    """
    
    def __init__(self, verbose: bool = False):
        """
        初期化
        
        Args:
            verbose (bool): 詳細なログ出力を行うかどうか
        """
        self.verbose = verbose
        self.logger = logger
    
    def generate_entry_prompt(self, 
                             stock_data: Dict[str, Any], 
                             backtest_results: Dict[str, Any], 
                             technical_data: List[Dict[str, Any]], 
                             entry_score: float) -> str:
        """
        エントリー判断用のプロンプトを生成
        
        Args:
            stock_data (Dict): 銘柄情報を含む辞書
            backtest_results (Dict): バックテスト結果の辞書
            technical_data (List[Dict]): テクニカル指標データのリスト（過去数日分）
            entry_score (float): 事前計算されたエントリースコア
            
        Returns:
            str: 生成されたプロンプト
        """
        # 最新のADX値をログに出力
        latest_data = technical_data[-1] if technical_data else {}
        
        # ADX値をログに出力（デバッグ用）
        adx_value = latest_data.get('adx')
        self.logger.debug(f"最新のADX値: {adx_value}")
        print(f"DEBUG - プロンプトに含まれるADX値: {adx_value}")
        
        # 基本的な銘柄情報
        stock_code = stock_data.get('code', 'unknown')
        company_name = stock_data.get('company_name', 'unknown')
        current_price = stock_data.get('close', 0)
        
        # プロンプトを構築する
        prompt = f"""
# 株式エントリー判断リクエスト

## 基本情報
- 銘柄コード: {stock_code}
- 企業名: {company_name}
- 現在価格: {current_price}円
- 事前スコア: {entry_score:.1f}/100

## 重要テクニカル指標（過去3日間）
"""

        # 直近3日分の重要な指標を抽出（少ないデータ量で効果的な情報を提供）
        recent_data = technical_data[-5:] if len(technical_data) >= 5 else technical_data
        
        # 技術指標の説明
        prompt += f"""
## 技術指標の説明
- **RSI (相対力指数)**: 0〜100の値。70以上は買われすぎ、30以下は売られすぎを示す。
- **ストキャスティクス %K**: 0〜100の値。80以上は買われすぎ、20以下は売られすぎを示す。
- **ADX (平均方向性指数)**: トレンドの強さを示す。25以上で強いトレンド、15以下で弱いトレンドを示す。
- **MACD**: 短期と長期の移動平均線の差。上向きならば上昇トレンド、下向きならば下降トレンドを示す。
- **ボリンジャーバンド**: 上下2σ（標準偏差）のバンドと中央移動平均線。価格がバンド外に出ると反転の可能性。
- **一目均衡表**: 日本発の複合指標。転換線・基準線のクロスや雲（先行スパンA/B間）の位置関係でトレンドを判断。
- **ATR (平均真価格範囲)**: ボラティリティの指標。高値は大きな値動き、低値は小さな値動きを示す。
"""

        # 直近5日分の詳細データを表示
        for idx, day_data in enumerate(reversed(recent_data)):
            day_num = idx + 1
            date = day_data.get('date', '不明')
            prompt += f"""
### {day_num}日前 ({date})
- **価格**: 始値={day_data.get('open', 0):.1f}円, 高値={day_data.get('high', 0):.1f}円, 安値={day_data.get('low', 0):.1f}円, 終値={day_data.get('close', 0):.1f}円
- **RSI**: {day_data.get('rsi', 0):.1f}
- **ストキャスティクス**: %K={day_data.get('stoch_k', 0):.1f}, %D={day_data.get('stoch_d', 0):.1f}
- **ADX**: {day_data.get('adx', 0):.1f}
- **MACD**: {day_data.get('macd', 0):.2f}
- **ボリンジャーバンド**: 下={day_data.get('bb_lower', 0):.1f}, 中={day_data.get('bb_middle', 0):.1f}, 上={day_data.get('bb_upper', 0):.1f}
- **一目均衡表**: 転換線={day_data.get('ichimoku_tenkan', 0):.1f}, 基準線={day_data.get('ichimoku_kijun', 0):.1f}, 先行スパンA={day_data.get('ichimoku_senkou_a', 0):.1f}, 先行スパンB={day_data.get('ichimoku_senkou_b', 0):.1f}
- **ATR**: {day_data.get('atr', 0):.2f}
"""

        # バックテスト結果のサマリー
        prompt += f"""
## バックテスト結果サマリー
- 勝率: {backtest_results.get('success_rate', 0):.1f}%
- 平均リターン: {backtest_results.get('average_return', 0):.2f}
- 取引回数: {backtest_results.get('total_trades', 0)}回
"""

        # 最も成功した戦略があれば追加
        if backtest_results.get('best_strategy'):
            prompt += f"- 最適戦略: {backtest_results.get('best_strategy', 'なし')}\n"

        # 判断指示を追加
        prompt += f"""
## 判断指示
この銘柄へのエントリー（購入）が推奨されるかどうかを判断してください。
考慮すべき点:
1. 上記の指標は買い時を示しているか
2. バックテスト結果は良好か
3. 現在のリスク/リターン比は良好か

以下の形式で回答してください:
```json
{{
  "should_enter": true/false,
  "confidence": 0-100,
  "reasoning": "判断理由を簡潔に説明",
  "concerns": "潜在的な懸念事項があれば記載"
}}
```
"""

        if self.verbose:
            self.logger.debug(f"生成されたプロンプト（長さ: {len(prompt)}文字）:\n{prompt}")
        
        return prompt
    
    def generate_simplified_prompt(self, stock_data: Dict[str, Any], entry_score: float) -> str:
        """
        最小限の情報のみを含む簡略化されたプロンプトを生成
        
        APIレートリミットが厳しい場合や、処理を迅速に行いたい場合に使用
        
        Args:
            stock_data (Dict): 銘柄情報と最新の技術指標を含む辞書
            entry_score (float): 事前計算されたエントリースコア
            
        Returns:
            str: 生成された簡略化プロンプト
        """
        stock_code = stock_data.get('code', 'unknown')
        current_price = stock_data.get('close', 0)
        
        # 技術指標を取得（最新のものがあれば）
        rsi = stock_data.get('rsi', None)
        stoch_k = stock_data.get('stoch_k', None)
        adx = stock_data.get('adx', None)
        macd = stock_data.get('macd', None)
        bb_lower = stock_data.get('bb_lower', None)
        bb_middle = stock_data.get('bb_middle', None)
        bb_upper = stock_data.get('bb_upper', None)
        ichimoku_tenkan = stock_data.get('ichimoku_tenkan', None)
        ichimoku_kijun = stock_data.get('ichimoku_kijun', None)
        ichimoku_senkou_a = stock_data.get('ichimoku_senkou_a', None)
        ichimoku_senkou_b = stock_data.get('ichimoku_senkou_b', None)
        atr = stock_data.get('atr', None)
        
        # 簡略化したプロンプトを構築
        prompt = f"""
銘柄コード {stock_code}、現在価格 {current_price}円、事前スコア {entry_score:.1f}/100の株式エントリー判断

技術指標の説明:
- RSI: 0〜100の値。70以上は買われすぎ、30以下は売られすぎ
- ストキャスティクス: 0〜100の値。80以上は買われすぎ、20以下は売られすぎ
- ADX: 25以上で強いトレンド、15以下で弱いトレンド
- MACD: 短期と長期の移動平均線の差。上向きは上昇トレンド、下向きは下降トレンド
- ボリンジャーバンド: 価格がバンド外に出ると反転の可能性
- 一目均衡表: 転換線・基準線のクロスやスパン間の位置でトレンドを判断

最新の主要指標:
- RSI: {rsi if rsi is not None else '不明'}
- ストキャスティクス %K: {stoch_k if stoch_k is not None else '不明'}
- ADX: {adx if adx is not None else '不明'}
- MACD: {macd if macd is not None else '不明'}
- ボリンジャーバンド: 下={bb_lower if bb_lower is not None else '不明'}, 中={bb_middle if bb_middle is not None else '不明'}, 上={bb_upper if bb_upper is not None else '不明'}
- 一目均衡表: 転換線={ichimoku_tenkan if ichimoku_tenkan is not None else '不明'}, 基準線={ichimoku_kijun if ichimoku_kijun is not None else '不明'}
          先行スパンA={ichimoku_senkou_a if ichimoku_senkou_a is not None else '不明'}, 先行スパンB={ichimoku_senkou_b if ichimoku_senkou_b is not None else '不明'}
- ATR: {atr if atr is not None else '不明'}

この銘柄は購入すべきですか？理由と共に回答してください。
以下のJSON形式で回答:
{{
  "should_enter": true/false,
  "confidence": 0-100,
  "reasoning": "理由",
  "concerns": "懸念点"
}}
"""
        
        if self.verbose:
            self.logger.debug(f"生成された簡略化プロンプト（長さ: {len(prompt)}文字）:\n{prompt}")
        
        return prompt
    
    def summarize_technical_data(self, technical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        テクニカル指標データを要約する
        
        Args:
            technical_data (List[Dict]): 過去のテクニカル指標データのリスト
            
        Returns:
            Dict: 要約されたテクニカル指標データ
        """
        if not technical_data:
            return {}
        
        # 直近のデータを取得
        latest = technical_data[-1] if technical_data else {}
        
        # 過去5日間のデータがあれば傾向を計算
        trends = {}
        if len(technical_data) >= 5:
            five_days = technical_data[-5:]
            
            # 価格トレンド
            close_prices = [day.get('close', 0) for day in five_days]
            if all(close_prices):
                price_change = ((close_prices[-1] / close_prices[0]) - 1) * 100
                trends['price_5day_change'] = f"{price_change:.1f}%"
            
            # RSIトレンド
            rsi_values = [day.get('rsi', None) for day in five_days]
            if all(v is not None for v in rsi_values):
                rsi_change = rsi_values[-1] - rsi_values[0]
                trends['rsi_trend'] = "上昇中" if rsi_change > 5 else "下降中" if rsi_change < -5 else "横ばい"
            
            # ストキャスティクストレンド
            stoch_values = [day.get('stoch_k', None) for day in five_days]
            if all(v is not None for v in stoch_values):
                stoch_change = stoch_values[-1] - stoch_values[0]
                trends['stoch_trend'] = "上昇中" if stoch_change > 10 else "下降中" if stoch_change < -10 else "横ばい"
        
        # 要約データを構築
        summary = {
            'latest_date': latest.get('date', '不明'),
            'latest_close': latest.get('close', 0),
            'latest_rsi': latest.get('rsi', None),
            'latest_stoch_k': latest.get('stoch_k', None),
            'latest_adx': latest.get('adx', None),
            'trends': trends
        }
        
        return summary

    def generate_entry_rule_evaluation_prompt(self, 
                             stock_data: Dict[str, Any], 
                             backtest_results: Dict[str, Any], 
                             technical_data: List[Dict[str, Any]], 
                             entry_score: float) -> str:
        """
        エントリールール評価に特化したプロンプトを生成
        
        Args:
            stock_data (Dict): 銘柄情報とエントリールール情報を含む辞書
            backtest_results (Dict): バックテスト結果の辞書
            technical_data (List[Dict]): テクニカル指標データのリスト（過去数日分）
            entry_score (float): 事前計算されたエントリースコア
            
        Returns:
            str: 生成されたプロンプト
        """
        # 最新のADX値をログに出力
        latest_data = technical_data[-1] if technical_data else {}
        
        # ADX値をログに出力（デバッグ用）
        adx_value = latest_data.get('adx')
        self.logger.debug(f"最新のADX値: {adx_value}")
        
        # 基本的な銘柄情報
        stock_code = stock_data.get('code', 'unknown')
        company_name = stock_data.get('company_name', 'unknown')
        current_price = stock_data.get('close', 0)
        
        # エントリールール情報
        entry_price = stock_data.get('entry_price') or stock_data.get('rule_entry_price', 'データなし')
        stop_loss = stock_data.get('stop_loss') or stock_data.get('rule_stop_limit', 'データなし')
        target_price = stock_data.get('target_price') or stock_data.get('rule_top_price', 'データなし')
        expected_period = stock_data.get('period') or stock_data.get('rule_period', 'データなし')
        risk_reward = stock_data.get('risk_reward', 'データなし')
        expected_return = stock_data.get('expected_return', 'データなし')
        
        # エントリー条件と決済条件
        entry_conditions = stock_data.get('entry_conditions', 'データなし')
        exit_conditions = stock_data.get('exit_conditions', 'データなし')
        
        # 市場分析と技術分析
        market_overview = stock_data.get('market_overview', 'データなし')
        technical_analysis = stock_data.get('technical_analysis', 'データなし')
        
        # プロンプトを構築する
        prompt = f"""
# 株式エントリールール評価リクエスト

## 基本情報
- 銘柄コード: {stock_code}
- 企業名: {company_name}
- 現在価格: {current_price}円
- 事前スコア: {entry_score:.1f}/100

## エントリールール詳細
- エントリー価格: {entry_price}円
- ストップロス: {stop_loss}円 
- 目標価格: {target_price}円
- 想定保有期間: {expected_period}日
- リスクリワード比: {risk_reward}
- 期待リターン: {expected_return}%

## エントリー・決済条件
- エントリー条件: {entry_conditions}
- 決済条件: {exit_conditions}

## 市場・技術分析
- 市場概況: {market_overview}
- 技術的分析: {technical_analysis}

## 現在の技術指標状況
"""
        
        # 直近5日分の詳細データを表示
        recent_data = technical_data[-3:] if len(technical_data) >= 3 else technical_data
        for idx, day_data in enumerate(reversed(recent_data)):
            day_num = idx + 1
            date = day_data.get('date', '不明')
            prompt += f"""
### {day_num}日前 ({date})
- **価格**: 始値={day_data.get('open', 0):.1f}円, 高値={day_data.get('high', 0):.1f}円, 安値={day_data.get('low', 0):.1f}円, 終値={day_data.get('close', 0):.1f}円
- **RSI**: {day_data.get('rsi', 0):.1f}
- **ストキャスティクス**: %K={day_data.get('stoch_k', 0):.1f}, %D={day_data.get('stoch_d', 0):.1f}
- **ADX**: {day_data.get('adx', 0):.1f}
- **MACD**: {day_data.get('macd', 0):.2f}
- **ボリンジャーバンド**: 下={day_data.get('bb_lower', 0):.1f}, 中={day_data.get('bb_middle', 0):.1f}, 上={day_data.get('bb_upper', 0):.1f}
"""

        # バックテスト結果のサマリー
        prompt += f"""
## バックテスト結果サマリー
- 勝率: {backtest_results.get('success_rate', 0):.1f}%
- 平均リターン: {backtest_results.get('average_return', 0):.2f}
- 取引回数: {backtest_results.get('total_trades', 0)}回
"""

        # 最も成功した戦略があれば追加
        if backtest_results.get('best_strategy'):
            prompt += f"- 最適戦略: {backtest_results.get('best_strategy', 'なし')}\n"

        # 判断指示を追加
        prompt += f"""
## 評価指示
上記のエントリールールを以下の観点から総合的に評価してください。

特に以下の点を重視してください:
1. 現在の技術指標はエントリールールの条件と一致しているか
2. リスクリワード比は適切か (2以上が望ましい)
3. ストップロスと目標価格の設定は現在の市場状況に合っているか
4. バックテスト結果はこのエントリー戦略を支持しているか
5. エントリー条件と決済条件の論理性と明確さ
6. 市場概況・技術分析とエントリールールの整合性

以下の形式で回答してください:
```json
{{
  "should_enter": true/false,
  "confidence": 0-100,
  "reasoning": "エントリールールの評価理由を簡潔に説明",
  "rule_evaluation": "エントリールールの強み・弱みについてのコメント",
  "current_match": "現在の市場状況とエントリールールの一致度(0-100)",
  "concerns": "潜在的な懸念事項があれば記載"
}}
```
"""

        if self.verbose:
            self.logger.debug(f"生成されたエントリールール評価プロンプト（長さ: {len(prompt)}文字）:\n{prompt}")
        
        return prompt


if __name__ == "__main__":
    # 使用例
    logging.basicConfig(level=logging.DEBUG)
    generator = PromptGenerator(verbose=True)
    
    # テストデータ
    stock_data = {
        'code': '1234',
        'company_name': 'テスト株式会社',
        'close': 1500
    }
    
    backtest_results = {
        'success_rate': 65.5,
        'average_return': 0.12,
        'total_trades': 25,
        'best_strategy': 'ボリンジャーバンド+RSI'
    }
    
    technical_data = [
        {'date': '2023-01-01', 'close': 1450, 'rsi': 45.5, 'stoch_k': 35.2, 'adx': 22.1},
        {'date': '2023-01-02', 'close': 1480, 'rsi': 52.3, 'stoch_k': 42.5, 'adx': 23.5},
        {'date': '2023-01-03', 'close': 1500, 'rsi': 55.7, 'stoch_k': 48.3, 'adx': 25.2}
    ]
    
    # エントリースコア
    entry_score = 75.5
    
    # プロンプト生成テスト
    prompt = generator.generate_entry_prompt(stock_data, backtest_results, technical_data, entry_score)
    print(prompt)
    
    # 簡略化プロンプト
    simplified = generator.generate_simplified_prompt(stock_data, entry_score)
    print("\n簡略化プロンプト:")
    print(simplified) 