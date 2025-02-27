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
        recent_data = technical_data[-3:] if len(technical_data) >= 3 else technical_data
        for idx, day_data in enumerate(reversed(recent_data)):
            day_num = idx + 1
            date = day_data.get('date', '不明')
            prompt += f"""
### {day_num}日前 ({date})
- 終値: {day_data.get('close', 0)}円
- RSI: {day_data.get('rsi', 0):.1f}
- ストキャスティクス %K: {day_data.get('stoch_k', 0):.1f}
- ADX: {day_data.get('adx', 0):.1f}
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
        
        # 簡略化したプロンプトを構築
        prompt = f"""
銘柄コード {stock_code}、現在価格 {current_price}円、事前スコア {entry_score:.1f}/100の株式エントリー判断

最新の主要指標:
- RSI: {rsi if rsi is not None else '不明'}
- ストキャスティクス %K: {stoch_k if stoch_k is not None else '不明'}
- ADX: {adx if adx is not None else '不明'}

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