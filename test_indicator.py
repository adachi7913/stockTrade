#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import pandas as pd
import numpy as np
import pandas_ta as ta
from datetime import datetime, timedelta
import sys
import os

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def create_test_data():
    """テスト用のOHLCVデータを作成"""
    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30, 0, -1)]
    
    # 正常なパターン（変動あり）
    normal_data = []
    for i, date in enumerate(dates):
        base_price = 1000 + i * 10
        normal_data.append({
            'date': date,
            'open': base_price - 5,
            'high': base_price + 15,
            'low': base_price - 15,
            'close': base_price + 5,
            'volume': 10000 + i * 100
        })
    
    # 問題パターン1（すべて同じ価格）
    flat_data = []
    for date in dates:
        flat_data.append({
            'date': date,
            'open': 1000,
            'high': 1000,
            'low': 1000,
            'close': 1000,
            'volume': 10000
        })
    
    # 問題パターン2（高値と安値が同じ）
    same_hl_data = []
    for i, date in enumerate(dates):
        price = 1000 + i * 10
        same_hl_data.append({
            'date': date,
            'open': price - 5,
            'high': price,
            'low': price,
            'close': price + 5,
            'volume': 10000
        })
    
    return normal_data, flat_data, same_hl_data

def calculate_stochastic(data):
    """独自実装のストキャスティクス計算（検証用）"""
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # 期間内の最高値と最安値を計算
    high_14 = df['high'].rolling(window=14).max()
    low_14 = df['low'].rolling(window=14).min()
    
    # ストキャスティクス %K の計算
    k_raw = 100 * ((df['close'] - low_14) / (high_14 - low_14))
    
    # 最高値と最安値が同じ場合（分母がゼロ）の処理
    k_raw = k_raw.replace([np.inf, -np.inf], np.nan)
    
    # ナンの置き換え方法を確認（0で置き換えるか、前の値で置き換えるか）
    k_replace_with_zero = k_raw.fillna(0)
    k_replace_with_previous = k_raw.fillna(method='ffill').fillna(0)
    
    # pandas_ta を使用した計算（現在のコードが使用している方法）
    stoch_df = ta.stoch(high=df['high'], low=df['low'], close=df['close'], k=14, d=3, smooth_k=3)
    
    # 結果の比較
    result = pd.DataFrame({
        'close': df['close'],
        'high_14': high_14,
        'low_14': low_14,
        'k_raw': k_raw,
        'k_replace_zero': k_replace_with_zero,
        'k_replace_prev': k_replace_with_previous,
        'pandas_ta_k': stoch_df.get("STOCHk_14_3_3", pd.Series(0, index=df.index))
    })
    
    return result

def test_stochastic_calculation():
    """異なるデータパターンでストキャスティクス計算をテスト"""
    normal_data, flat_data, same_hl_data = create_test_data()
    
    logger.info("=== 正常データでのストキャスティクス計算 ===")
    normal_result = calculate_stochastic(normal_data)
    logger.info(f"最後の5レコード:\n{normal_result.tail()}")
    logger.info(f"ゼロ値の数: {(normal_result['pandas_ta_k'] == 0).sum()}")
    
    logger.info("\n=== 横ばいデータでのストキャスティクス計算 ===")
    flat_result = calculate_stochastic(flat_data)
    logger.info(f"最後の5レコード:\n{flat_result.tail()}")
    logger.info(f"ゼロ値の数: {(flat_result['pandas_ta_k'] == 0).sum()}")
    
    logger.info("\n=== 高値=安値のデータでのストキャスティクス計算 ===")
    same_hl_result = calculate_stochastic(same_hl_data)
    logger.info(f"最後の5レコード:\n{same_hl_result.tail()}")
    logger.info(f"ゼロ値の数: {(same_hl_result['pandas_ta_k'] == 0).sum()}")
    
    return normal_result, flat_result, same_hl_result

def examine_production_code():
    """実際のコードからインポートしてテスト"""
    try:
        sys.path.append(os.getcwd())
        from lib.indicator_calculator import IndicatorCalculator
        
        normal_data, flat_data, same_hl_data = create_test_data()
        
        logger.info("\n=== 本番コード: 正常データ ===")
        calculator = IndicatorCalculator(normal_data)
        indicators = calculator.calculate_indicators()
        logger.info(f"最後の5レコードのストキャスティクス %K: {[ind.get('stoch_k', 0) for ind in indicators[-5:]]}")
        
        logger.info("\n=== 本番コード: 横ばいデータ ===")
        calculator = IndicatorCalculator(flat_data)
        indicators = calculator.calculate_indicators()
        logger.info(f"最後の5レコードのストキャスティクス %K: {[ind.get('stoch_k', 0) for ind in indicators[-5:]]}")
        
        logger.info("\n=== 本番コード: 高値=安値データ ===")
        calculator = IndicatorCalculator(same_hl_data)
        indicators = calculator.calculate_indicators()
        logger.info(f"最後の5レコードのストキャスティクス %K: {[ind.get('stoch_k', 0) for ind in indicators[-5:]]}")
        
    except Exception as e:
        logger.error(f"本番コードのテスト中にエラーが発生: {e}")

if __name__ == "__main__":
    logger.info("ストキャスティクス計算のテストを開始")
    normal_result, flat_result, same_hl_result = test_stochastic_calculation()
    
    # 本番コードをテスト
    examine_production_code()
    
    logger.info("テスト完了") 