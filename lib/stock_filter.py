import yfinance as yf

def filter_stock(stock_code, close, market_cap, last_no_entry_date=None, no_entry_span=None, min_close_threshold=300, close_threshold=2000, market_cap_threshold=1_000_000_000):
    """
    指定した銘柄を以下の条件でフィルタリングする関数
    
    条件:
      1. 終値 (close) が min_close_threshold 以上かつ close_threshold 以下であること
         （デフォルト：300円以上、2000円以下）
      2. 時価総額が market_cap_threshold 以上であること（デフォルトは1,000,000,000円以上）
      3. （オプション）エントリー不可情報がある場合、最新api_responseの date と no_entry_span を元に、
         現在日付がその期間を過ぎていなければ除外する
    
    Args:
        stock_code (str): 銘柄コード
        close (float): 最新の終値
        ※ticker_objは使用せず、時価総額はmarket_cap引数で渡します。
        last_no_entry_date (str, optional): api_responseテーブルから取得した最後のエントリー不可日（"YYYY-MM-DD"形式）
        no_entry_span (int, optional): エントリー不可期間（日数）
        min_close_threshold (int, optional): 終値の下限値。デフォルトは300円。
        close_threshold (int, optional): 終値の上限値。デフォルトは2000円。
        market_cap_threshold (int, optional): 時価総額の下限値。デフォルトは1,000,000,000円。
    
    Returns:
        bool: 全ての条件を満たす場合は True、そうでない場合は False
    """
    # 終値の下限チェック
    if close < min_close_threshold:
        print(f"{stock_code}: 終値 {close} 円 は最低価格 {min_close_threshold} 円以上の条件を満たしていません。")
        return False

    # 終値の上限チェック
    if close > close_threshold:
        print(f"{stock_code}: 終値 {close} 円 は {close_threshold} 円以下の条件を満たしていません。")
        return False

    # 時価総額チェック
    if market_cap is None:
        print(f"{stock_code}: 時価総額情報が取得できなかったため除外。")
        return False
    if market_cap < market_cap_threshold:
        print(f"{stock_code}: 時価総額 {market_cap} 円 は {market_cap_threshold} 円以上の条件を満たしていません。")
        return False

    # エントリー不可期間のチェック
    if last_no_entry_date is not None and no_entry_span is not None:
        from datetime import datetime, timedelta
        try:
            last_date = datetime.strptime(last_no_entry_date, "%Y-%m-%d").date()
            allowed_date = last_date + timedelta(days=no_entry_span)
            today = datetime.today().date()
            if today < allowed_date:
                print(f"{stock_code}: エントリー不可期間内（{allowed_date}まで）であるため除外。")
                return False
        except Exception as e:
            print(f"{stock_code}: エントリー不可期間の日付変換エラー: {e}")

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
