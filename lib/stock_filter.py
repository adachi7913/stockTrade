import yfinance as yf

def filter_stock(stock_code, close, ticker_obj=None, min_close_threshold=300, close_threshold=2000, avg_volume_threshold=100000, market_cap_threshold=1_000_000_000):
    """
    指定した銘柄を以下の条件でフィルタリングする関数
    
    条件:
      1. 終値 (close) が min_close_threshold 以上かつ close_threshold 以下であること
         （デフォルト：300円以上、2000円以下）
      2. 過去20日間の出来高平均が avg_volume_threshold 以上であること（デフォルトは100,000以上）
      3. 時価総額が market_cap_threshold 以上であること（デフォルトは1,000,000,000円以上）
    
    Args:
        stock_code (str): yfinanceで利用するティッカーシンボル（例："7203.T"）
        close (float): 最新の終値
        ticker_obj (yfinance.Ticker, optional): 既に生成されたTickerオブジェクト。Noneの場合は新規生成します。
        min_close_threshold (int, optional): 終値の下限値。デフォルトは300円。
        close_threshold (int, optional): 終値の上限値。デフォルトは2000円。
        avg_volume_threshold (int, optional): 20日間平均出来高の下限値。デフォルトは100,000。
        market_cap_threshold (int, optional): 時価総額の下限値。デフォルトは1,000,000,000円。
    
    Returns:
        bool: 全ての条件を満たす場合は True、そうでない場合は False
    """
    # 条件0: 最低価格チェック
    if close < min_close_threshold:
        print(f"{stock_code}: 終値 {close} 円 は最低価格 {min_close_threshold} 円以上の条件を満たしていません。")
        return False

    # 条件1: 終値チェック（上限）
    if close > close_threshold:
        print(f"{stock_code}: 終値 {close} 円 は {close_threshold} 円以下の条件を満たしていません。")
        return False

    # ticker_obj が渡されなかった場合、新規に生成
    if ticker_obj is None:
        ticker_obj = yf.Ticker(stock_code)
    
    # yfinanceのTicker情報を取得
    info = ticker_obj.info

    # 条件3: 時価総額チェック
    market_cap = info.get("marketCap")
    if market_cap is None:
        print(f"{stock_code}: 時価総額情報が取得できなかったため除外。")
        return False

    if market_cap < market_cap_threshold:
        print(f"{stock_code}: 時価総額 {market_cap} 円 は {market_cap_threshold} 円以上の条件を満たしていません。")
        return False

    # 条件2: 過去20日間の平均出来高チェック
    hist = ticker_obj.history(period="1mo")
    if hist.empty:
        print(f"{stock_code}: 価格履歴が空のため除外。")
        return False

    n_days = min(20, len(hist))
    avg_volume = hist['Volume'].tail(n_days).mean()
    if avg_volume < avg_volume_threshold:
        print(f"{stock_code}: 過去{n_days}日間の平均出来高 {avg_volume} は {avg_volume_threshold} 以上の条件を満たしていません。")
        return False

    print(f"{stock_code}: 全てのフィルタ条件を満たしています。")
    return True


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
