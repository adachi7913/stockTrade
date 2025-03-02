import logging
from datetime import datetime, timedelta
import yfinance as yf
import numpy as np

# ロガーの取得
logger = logging.getLogger(__name__)

def filter_stock(stock_code, close, market_cap, last_no_entry_date=None, no_entry_span=None, volume_data=None, atr=None, rsi=None, stoch_k=None, min_close_threshold=300, close_threshold=3000, market_cap_threshold=1_000_000_000):
    """
    指定した銘柄を以下の条件でフィルタリングする関数
    
    条件:
      1. 終値 (close) が min_close_threshold 以上かつ close_threshold 以下であること
         （デフォルト：300円以上、3000円以下）
      2. 時価総額が market_cap_threshold 以上であること（デフォルトは1,000,000,000円以上）
      3. （オプション）エントリー不可情報がある場合、最新api_responseの date と no_entry_span を元に、
         現在日付がその期間を過ぎていなければ除外する
      4. 過去20日の平均出来高が10万株未満の場合は除外する
    
    Args:
        stock_code (str): 銘柄コード
        close (float or str): 最新の終値
        market_cap (float or str): 時価総額
        last_no_entry_date (str, optional): api_responseテーブルから取得した最後のエントリー不可日（"YYYY-MM-DD"形式）
        no_entry_span (int, optional): エントリー不可期間（日数）
        volume_data (list, optional): 出来高データのリスト
        atr (float, optional): ATRの値
        rsi (float, optional): RSIの値
        stoch_k (float, optional): ストキャスティクス %Kの値
        min_close_threshold (int, optional): 終値の下限値。デフォルトは300円。
        close_threshold (int, optional): 終値の上限値。デフォルトは3000円。
        market_cap_threshold (int, optional): 時価総額の下限値。デフォルトは1,000,000,000円。
    
    Returns:
        bool: 全ての条件を満たす場合は True、そうでない場合は False
    """
    # 文字列型の値を数値型に変換
    try:
        close_float = float(close) if close is not None else 0
        market_cap_float = float(market_cap) if market_cap is not None else 0
    except (ValueError, TypeError) as e:
        logger.warning(f"{stock_code}: 数値変換エラー - close: {close}, market_cap: {market_cap}, エラー: {e}")
        return False
    
    # 終値の下限チェック
    if close_float < min_close_threshold:
        logger.info(f"{stock_code}: 終値 {close_float} 円 は最低価格 {min_close_threshold} 円以上の条件を満たしていません。")
        return False

    # 終値の上限チェック
    if close_float > close_threshold:
        logger.info(f"{stock_code}: 終値 {close_float} 円 は {close_threshold} 円以下の条件を満たしていません。")
        return False

    # 時価総額チェック
    if market_cap_float < market_cap_threshold:
        logger.info(f"{stock_code}: 時価総額 {market_cap_float:,} 円 は {market_cap_threshold:,} 円以上の条件を満たしていません。")
        return False

    # エントリー不可期間のチェック
    if last_no_entry_date is not None and no_entry_span is not None:
        try:
            last_date = datetime.strptime(last_no_entry_date, "%Y-%m-%d").date()
            allowed_date = last_date + timedelta(days=no_entry_span)
            today = datetime.today().date()
            if today < allowed_date:
                logger.info(f"{stock_code}: エントリー不可期間内（{allowed_date}まで）であるため除外。")
                return False
        except Exception as e:
            logger.error(f"{stock_code}: エントリー不可期間の日付変換エラー: {e}")

    # 追加: 過去20日の平均出来高が10万株未満の場合は除外する
    if volume_data is not None and len(volume_data) > 0:
        # 直近20日分を抽出（20日未満の場合は全データ）
        recent_volumes = volume_data[-20:] if len(volume_data) >= 20 else volume_data
        avg_volume = sum(recent_volumes) / len(recent_volumes)
        if avg_volume < 90000:
            logger.info(f"{stock_code}: 過去20日の平均出来高が10万株未満（{avg_volume}株）ため除外")
            return False

    # ATRフィルター：ATR比率（atr/close）が5%以上の場合エントリー見送り
    if atr is not None and close_float > 0:
         atr_ratio = atr / close_float
         if atr_ratio >= 0.05:
              logger.info(f"{stock_code}: ATR比率が {atr_ratio*100:.1f}% となり急激な値動きがあるため除外")
              return False

    # RSIフィルター：RSIが25以下の場合、過冷状態のためエントリー見送り
    if rsi is not None:
         if rsi <= 25:
              logger.info(f"{stock_code}: RSIが {rsi} で過冷状態（売られ過ぎ）のため除外")
              return False

    # ストキャスティクスフィルター：%Kが20以下の場合、過冷状態のためエントリー見送り
    if stoch_k is not None:
         # ストキャスティクスが0の場合は、計算エラーの可能性があるため、別の条件でチェック
         if stoch_k == 0:
             logger.debug(f"{stock_code}: ストキャスティクス%Kが0です。計算の問題の可能性があるため、他の指標で判断します。")
             # 0の場合はRSIと合わせて判断
             if rsi is not None and rsi <= 30:
                 logger.info(f"{stock_code}: ストキャスティクス%Kが0で、RSIも{rsi}と低いため除外")
                 return False
         # 通常の過冷状態チェック（0より大きく20以下）
         elif 0 < stoch_k <= 20:
             logger.info(f"{stock_code}: ストキャスティクス%Kが {stoch_k} で過冷状態のため除外")
             return False

    logger.info(f"{stock_code}: 全てのフィルタ条件を満たしています。")
    return True


def calculate_entry_score(stock_data, backtest_results, technical_indicators):
    """
    エントリースコアを計算する関数
    
    複数の指標を組み合わせて、0-100の範囲でエントリースコアを計算します。
    スコアが高いほど、エントリー推奨度が高いことを示します。
    
    Args:
        stock_data (dict): 株価データと基本情報を含む辞書
        backtest_results (dict): バックテスト結果を含む辞書
        technical_indicators (dict): 各種テクニカル指標を含む辞書
    
    Returns:
        float: 0-100の範囲のエントリースコア
    """
    scores = {}
    stock_code = stock_data.get('code', 'unknown')
    
    # スコア初期化
    total_score = 0
    max_score = 0
    
    # スコア配分の調整（合計100点満点）
    # - バックテスト結果: 40点
    # - テクニカル指標: 35点
    # - 保有期間とリターン: 25点
    
    # ----------------
    # バックテスト結果のスコアリング（40点）
    # ----------------
    if backtest_results and 'success_rate' in backtest_results and 'average_return' in backtest_results:
        # 勝率スコア (0-20点)
        success_rate = backtest_results.get('success_rate', 0)
        success_score = min(20, success_rate / 5)  # 勝率100%で最大20点
        scores['success_rate'] = success_score
        total_score += success_score
        max_score += 20
        
        # 平均リターンスコア (0-20点)
        avg_return = backtest_results.get('average_return', 0)
        return_score = min(20, max(0, avg_return * 20))  # 平均リターン1.0で最大20点
        scores['average_return'] = return_score
        total_score += return_score
        max_score += 20
    else:
        logger.warning(f"{stock_code}: バックテスト結果が不足しているため、スコアリングに影響します")
    
    # ----------------
    # テクニカル指標のスコアリング（35点）
    # ----------------
    if technical_indicators:
        # RSIスコア (0-10点): 50-70が最適範囲
        rsi = technical_indicators.get('rsi')
        if rsi is not None:
            if 50 <= rsi <= 70:
                rsi_score = 10
            elif 40 <= rsi < 50 or 70 < rsi <= 80:
                rsi_score = 7
            elif 30 <= rsi < 40 or 80 < rsi <= 90:
                rsi_score = 3
            else:
                rsi_score = 0
            scores['rsi'] = rsi_score
            total_score += rsi_score
            max_score += 10
        
        # ストキャスティクス%Kスコア (0-7点): 40-80が最適範囲
        stoch_k = technical_indicators.get('stoch_k')
        if stoch_k is not None:
            if 40 <= stoch_k <= 80:
                stoch_score = 7
            elif 20 <= stoch_k < 40 or 80 < stoch_k <= 90:
                stoch_score = 3
            else:
                stoch_score = 0
            scores['stoch_k'] = stoch_score
            total_score += stoch_score
            max_score += 7
        
        # トレンドスコア (0-10点): ADXとトレンド方向
        adx = technical_indicators.get('adx')
        if adx is not None:
            if adx >= 30:  # 強いトレンド
                trend_score = 10
            elif adx >= 20:  # 中程度のトレンド
                trend_score = 7
            elif adx >= 15:  # 弱いトレンド
                trend_score = 3
            else:  # トレンドなし
                trend_score = 0
            scores['trend'] = trend_score
            total_score += trend_score
            max_score += 10
        
        # ボリンジャーバンド位置 (0-8点)
        close = stock_data.get('close', 0)
        bb_lower = technical_indicators.get('bb_lower')
        bb_middle = technical_indicators.get('bb_middle')
        bb_upper = technical_indicators.get('bb_upper')
        
        if all(x is not None for x in [close, bb_lower, bb_middle, bb_upper]):
            try:
                # 全ての値を確実にfloat型に変換
                close_float = float(close)
                bb_lower_float = float(bb_lower)
                bb_middle_float = float(bb_middle)
                bb_upper_float = float(bb_upper)
                
                # 位置を0-1の範囲で正規化 (0=下限、0.5=中央、1=上限)
                if bb_upper_float > bb_lower_float:  # 分母がゼロにならないことを確認
                    bb_position = (close_float - bb_lower_float) / (bb_upper_float - bb_lower_float)
                    
                    # 理想的な位置は0.3〜0.5（やや下方から中央）
                    if 0.3 <= bb_position <= 0.5:
                        bb_score = 8
                    elif 0.1 <= bb_position < 0.3 or 0.5 < bb_position <= 0.7:
                        bb_score = 4
                    else:
                        bb_score = 0
                    
                    scores['bb_position'] = bb_score
                    total_score += bb_score
                    max_score += 8
            except (ValueError, TypeError) as e:
                logger.error(f"{stock_code}: ボリンジャーバンド計算中にエラー: {e}")
    else:
        logger.warning(f"{stock_code}: テクニカル指標が不足しているため、スコアリングに影響します")
    
    # ----------------
    # 保有期間と期待リターンのスコアリング（25点）
    # ----------------
    period = stock_data.get('period')
    close_price = stock_data.get('close')  # 終値
    entry_price = stock_data.get('entry_price')  # エントリー価格
    target_price = stock_data.get('target_price')  # 目標価格
    
    if period is not None and (close_price is not None or entry_price is not None) and target_price is not None:
        try:
            # 保有期間を数値に変換（"30日"などの文字列からは数値のみを抽出）
            if isinstance(period, str):
                period_value = int(''.join(filter(str.isdigit, period)))
            else:
                period_value = int(period)
                
            # 基準価格（closeがあればclose、なければentry_price）
            base_price = float(close_price if close_price is not None else entry_price)
            target_price = float(target_price)
            
            # 価格変動を計算
            price_change = target_price - base_price
            
            # 1日あたりの変動率(%)を計算
            if period_value > 0 and base_price > 0:
                daily_return_pct = ((price_change / period_value) / base_price) * 100
            else:
                daily_return_pct = 0
                
            # 期間の短さによるスコア (0-10点)
            # 1-4日: 最高点、5-9日: 高得点、10-14日: 中得点、15日以上: 低得点
            if period_value <= 4:
                period_score = 10
            elif period_value <= 9:
                period_score = 8
            elif period_value <= 14:
                period_score = 6
            else:
                # 14日以上は徐々に減少（最低2点）
                period_score = max(2, 8 - ((period_value - 14) // 7))
                
            scores['period'] = period_score
            total_score += period_score
            max_score += 10
            
            # 1日あたりの期待リターン率によるスコア (0-15点)
            # 1日あたり1.5%以上が最高点
            if daily_return_pct >= 1.5:
                return_rate_score = 15
            elif daily_return_pct >= 1.0:
                return_rate_score = 12
            elif daily_return_pct >= 0.7:
                return_rate_score = 9
            elif daily_return_pct >= 0.5:
                return_rate_score = 6
            elif daily_return_pct > 0:
                return_rate_score = 3
            else:
                return_rate_score = 0
                
            scores['daily_return'] = return_rate_score
            total_score += return_rate_score
            max_score += 15
            
            # 短期高リターンの組み合わせボーナス
            # 期間7日以下かつ1日あたり1%以上で特別加点
            if period_value <= 7 and daily_return_pct >= 1.0:
                combination_bonus = 5  # 短期高リターンボーナス
                scores['short_high_bonus'] = combination_bonus
                total_score += combination_bonus
                # この特別ボーナスの場合、max_scoreは加算しない（100点を超える可能性あり）
                # 最終的に100点に正規化されるため
                
            logger.info(f"{stock_code}: 期間={period_value}日, 1日あたり期待リターン={daily_return_pct:.2f}%/日, " +
                      f"期間スコア={period_score}, 日次リターンスコア={return_rate_score}")
                
        except (ValueError, TypeError) as e:
            logger.warning(f"{stock_code}: 期間またはリターンの変換エラー: {e}")
    # expected_returnが直接提供されている場合のフォールバック処理
    elif period is not None and stock_data.get('expected_return') is not None:
        try:
            # 保有期間を数値に変換
            if isinstance(period, str):
                period_value = int(''.join(filter(str.isdigit, period)))
            else:
                period_value = int(period)
                
            # 期待リターンを数値に変換
            expected_return = stock_data.get('expected_return')
            if isinstance(expected_return, str):
                expected_return_value = float(expected_return.replace('%', ''))
            else:
                expected_return_value = float(expected_return)
                
            # 1日あたりの期待リターンを計算
            daily_return_pct = expected_return_value / period_value if period_value > 0 else 0
            
            # 期間スコア（前と同じロジック）
            if period_value <= 4:
                period_score = 10
            elif period_value <= 9:
                period_score = 8
            elif period_value <= 14:
                period_score = 6
            else:
                period_score = max(2, 8 - ((period_value - 14) // 7))
                
            scores['period'] = period_score
            total_score += period_score
            max_score += 10
            
            # 1日あたりの期待リターン率によるスコア（前と同じロジック）
            if daily_return_pct >= 1.5:
                return_rate_score = 15
            elif daily_return_pct >= 1.0:
                return_rate_score = 12
            elif daily_return_pct >= 0.7:
                return_rate_score = 9
            elif daily_return_pct >= 0.5:
                return_rate_score = 6
            elif daily_return_pct > 0:
                return_rate_score = 3
            else:
                return_rate_score = 0
                
            scores['daily_return'] = return_rate_score
            total_score += return_rate_score
            max_score += 15
            
            # 短期高リターンボーナス（前と同じロジック）
            if period_value <= 7 and daily_return_pct >= 1.0:
                combination_bonus = 5
                scores['short_high_bonus'] = combination_bonus
                total_score += combination_bonus
                
            logger.info(f"{stock_code}: 期間={period_value}日, 1日あたり期待リターン={daily_return_pct:.2f}%/日, " +
                      f"期間スコア={period_score}, 日次リターンスコア={return_rate_score}")
                      
        except (ValueError, TypeError) as e:
            logger.warning(f"{stock_code}: 期間またはリターンの変換エラー: {e}")
    else:
        logger.warning(f"{stock_code}: 期間、価格情報が不足しています (period={period}, close={close_price}, target={target_price})")
    
    # 最終スコアの計算（0-100に正規化）
    final_score = (total_score / max_score * 100) if max_score > 0 else 0
    final_score = min(100, final_score)  # 100点以上にならないよう制限
    
    # スコアの詳細をログに記録
    logger.info(f"{stock_code}: エントリースコア計算 - 最終スコア: {final_score:.2f}/100")
    for key, value in scores.items():
        logger.debug(f"{stock_code}: {key}スコア: {value}")
    
    return final_score


if __name__ == "__main__":
    # テスト例
    # 注意: 日本株の場合、yfinanceではティッカーシンボルに「.T」のサフィックスが必要です
    test_stock = "7203.T"  # 例: トヨタ自動車
    # 本来は最新の終値を取得する処理が必要ですが、テスト用に仮の値を使用します。
    close_value = 1900

    # 既にTickerオブジェクトを生成して渡す場合
    ticker_obj = yf.Ticker(test_stock)
    
    if filter_stock(test_stock, close_value, ticker_obj=ticker_obj):
        print("エントリー対象の銘柄です。")
    else:
        print("エントリー対象ではありません。")
