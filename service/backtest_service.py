import backtrader as bt
import pandas as pd
from repository.backtest_repository import BacktestRepository
import logging
import math
import datetime
from repository.stock_repository import StockRepository
from typing import List, Dict, Optional, Tuple, Any

# モジュールレベルのロガーはそのまま残す（モジュール内で使用する場合用）
logger = logging.getLogger(__name__)

class TrendFollowingStrategy(bt.Strategy):
    """
    順張り戦略: 一目均衡表 + MACD + ADXを利用します。
    """
    params = (('lot_size', 100), ('logger', None))  # ロガーパラメータを追加
    
    def __init__(self):
        try:
            # 指標初期化前にデータのサイズをログ
            self.logger = self.params.logger or logger
            self.logger.debug(f"データサイズ: {len(self.data)} バー")
            
            # 各指標を初期化
            self.logger.debug("一目均衡表の初期化開始")
            self.ichimoku = bt.indicators.Ichimoku(self.data)
            self.logger.debug("MACDの初期化開始")
            self.macd = bt.indicators.MACD(self.data.close)
            self.logger.debug("ADXの初期化開始")
            self.adx = bt.indicators.ADX(self.data)
            
            self.order = None  # 注文オブジェクトを保持
            self.pre_cash = None  # 注文前の残高を保持
            self.trades = []  # 取引履歴を保存するリスト
            
            self.logger.debug("TrendFollowingStrategy初期化完了")
        except Exception as e:
            import traceback
            # ロガーが初期化前の場合に対応
            log = self.params.logger or logger
            log.error(f"TrendFollowingStrategy.__init__()でエラー発生: {e}")
            log.error(f"詳細なエラー情報: {traceback.format_exc()}")
            raise  # エラーを再スロー

    def calculate_lot_size(self, current_price):
        """利用可能な資金から適切なロットサイズを計算"""
        # 株価が0または極小値の場合は0を返す
        if current_price <= 0.01:  # 1銭以下は実質ゼロと見なす
            self.logger.warning(f"株価が異常値です: {current_price}円 - ロットサイズを0に設定します")
            return 0
        
        available_cash = self.broker.getcash()
        # 購入可能な最大ロット数を計算（100株単位）
        affordable_size = math.floor((available_cash / current_price) / 100) * 100
        # 指定されたロットサイズと購入可能ロット数の小さい方を採用
        actual_size = min(self.params.lot_size, affordable_size)
        # 最小ロット数（100株）未満の場合は0を返す
        return actual_size if actual_size >= 100 else 0

    def notify_order(self, order):
        """注文状態が変化した際に呼ばれるメソッド"""
        if order.status in [order.Completed]:  # 注文が約定した場合
            if order.isbuy():  # 買い注文の場合
                post_cash = self.broker.getcash()
                self.logger.info(f'エントリー実行後: 残金={post_cash:,.0f}円 （差引額：{self.pre_cash - post_cash:,.0f}円）')
                # 取引情報を記録
                self.trades.append({
                    "entry_date": self.data.datetime.date().isoformat(),
                    "entry_price": order.executed.price,
                    "lot": order.executed.size,
                    "post_entry_capital": post_cash
                })
            elif order.issell():  # 売り注文の場合
                post_cash = self.broker.getcash()
                self.logger.info(f'決済実行後: 株価={order.executed.price:,.0f}円 残金={post_cash:,.0f}円 （差引額：{post_cash - self.pre_cash:,.0f}円）')
                # 決済情報を前回のエントリーに追加
                if self.trades:
                    self.trades[-1]["exit_date"] = self.data.datetime.date().isoformat()
                    self.trades[-1]["exit_price"] = order.executed.price
                    self.trades[-1]["post_exit_capital"] = post_cash

        self.order = None  # 注文オブジェクトをリセット

    def next(self):
        try:
            if self.order:  # 未約定の注文がある場合は何もしない
                return

            if not self.position:  # ポジションがない場合
                current_price = self.data.close[0]
                actual_size = self.calculate_lot_size(current_price)
                
                # デバッグログを追加
                self.logger.debug(f"指標値チェック - MACD: {self.macd.macd[0]}, ADX: {self.adx[0]}, price: {current_price}, senkou_span_a: {self.ichimoku.lines.senkou_span_a[0]}")
                
                if actual_size >= 100 and self.macd.macd[0] > 0 and self.adx[0] > 25 and current_price > self.ichimoku.lines.senkou_span_a[0]:
                    # エントリー前の残高を保存
                    self.pre_cash = self.broker.getcash()
                    trade_amount = current_price * actual_size
                    self.logger.info(f'エントリー実行前: 株価={current_price:.0f}円 ロット={actual_size}株 '
                               f'必要金額={trade_amount:,.0f}円 現在残金={self.pre_cash:,.0f}円')
                    
                    # 注文実行
                    self.order = self.buy(size=actual_size)

            elif self.position:  # ポジションがある場合
                # デバッグログを追加
                self.logger.debug(f"決済判断 - MACD: {self.macd.macd[0]}, price: {self.data.close[0]}, senkou_span_b: {self.ichimoku.lines.senkou_span_b[0]}")
                
                if self.macd.macd[0] < 0 or self.data.close[0] < self.ichimoku.lines.senkou_span_b[0]:
                    current_price = self.data.close[0]
                    position_size = self.position.size
                    self.pre_cash = self.broker.getcash()
                    self.logger.info(f'決済実行前: 保有数量={position_size}株 株価={current_price:.0f}円 残金={self.pre_cash:,.0f}円')
                    
                    # 決済注文実行
                    self.order = self.close()
        except Exception as e:
            import traceback
            self.logger.error(f"TrendFollowingStrategy.next()でエラー発生: {e}")
            self.logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

class ReverseStrategy(bt.Strategy):
    """
    逆張り戦略: RSI + ストキャスティクス + ボリンジャーバンドを利用します。
    """
    params = (('lot_size', 100), ('logger', None))  # ロガーパラメータを追加
    
    def __init__(self):
        try:
            # 指標初期化前にデータのサイズをログ
            self.logger = self.params.logger or logger
            self.logger.debug(f"データサイズ: {len(self.data)} バー")
            
            # 各指標を初期化
            self.logger.debug("RSIの初期化開始")
            self.rsi = bt.indicators.RSI(self.data.close, period=14)
            self.logger.debug("Stochasticの初期化開始")
            self.stoch = bt.indicators.Stochastic(self.data)
            self.logger.debug("BollingerBandsの初期化開始")
            self.bband = bt.indicators.BollingerBands(self.data.close, period=20)
            
            self.order = None
            self.pre_cash = None
            self.trades = []
            
            self.logger.debug("ReverseStrategy初期化完了")
        except Exception as e:
            import traceback
            # ロガーが初期化前の場合に対応
            log = self.params.logger or logger
            log.error(f"ReverseStrategy.__init__()でエラー発生: {e}")
            log.error(f"詳細なエラー情報: {traceback.format_exc()}")
            raise  # エラーを再スロー

    def calculate_lot_size(self, current_price):
        """利用可能な資金から適切なロットサイズを計算"""
        # 株価が0または極小値の場合は0を返す
        if current_price <= 0.01:  # 1銭以下は実質ゼロと見なす
            self.logger.warning(f"株価が異常値です: {current_price}円 - ロットサイズを0に設定します")
            return 0
        
        available_cash = self.broker.getcash()
        affordable_size = math.floor((available_cash / current_price) / 100) * 100
        actual_size = min(self.params.lot_size, affordable_size)
        return actual_size if actual_size >= 100 else 0

    def notify_order(self, order):
        """注文状態が変化した際に呼ばれるメソッド"""
        if order.status in [order.Completed]:  # 注文が約定した場合
            if order.isbuy():  # 買い注文の場合
                post_cash = self.broker.getcash()
                self.logger.info(f'エントリー実行後: 残金={post_cash:,.0f}円 （差引額：{self.pre_cash - post_cash:,.0f}円）')
                # 取引情報を記録
                self.trades.append({
                    "entry_date": self.data.datetime.date().isoformat(),
                    "entry_price": order.executed.price,
                    "lot": order.executed.size,
                    "post_entry_capital": post_cash
                })
            elif order.issell():  # 売り注文の場合
                post_cash = self.broker.getcash()
                self.logger.info(f'決済実行後: 株価={order.executed.price:,.0f}円 残金={post_cash:,.0f}円 （差引額：{post_cash - self.pre_cash:,.0f}円）')
                # 決済情報を前回のエントリーに追加
                if self.trades:
                    self.trades[-1]["exit_date"] = self.data.datetime.date().isoformat()
                    self.trades[-1]["exit_price"] = order.executed.price
                    self.trades[-1]["post_exit_capital"] = post_cash

        self.order = None  # 注文オブジェクトをリセット

    def next(self):
        try:
            if self.order:  # 未約定の注文がある場合は何もしない
                return
                
            if not self.position:
                current_price = self.data.close[0]
                actual_size = self.calculate_lot_size(current_price)
                
                # デバッグログを追加
                self.logger.debug(f"指標値チェック - RSI: {self.rsi[0]}, Stoch K: {self.stoch.percK[0]}, price: {current_price}, bband_bot: {self.bband.lines.bot[0]}")
                
                if actual_size >= 100 and self.rsi[0] < 30 and self.stoch.percK[0] < 20 and current_price <= self.bband.lines.bot[0]:
                    # エントリー前の残高を保存
                    self.pre_cash = self.broker.getcash()
                    trade_amount = current_price * actual_size
                    self.logger.info(f'エントリー実行前: 株価={current_price:.0f}円 ロット={actual_size}株 '
                               f'必要金額={trade_amount:,.0f}円 現在残金={self.pre_cash:,.0f}円')
                    
                    # 注文実行
                    self.order = self.buy(size=actual_size)
            else:
                # デバッグログを追加
                self.logger.debug(f"決済判断 - RSI: {self.rsi[0]}, price: {self.data.close[0]}, bband_mid: {self.bband.lines.mid[0]}")
                
                if self.rsi[0] > 70 or self.data.close[0] >= self.bband.lines.mid[0]:
                    self.pre_cash = self.broker.getcash()
                    self.logger.info(f'決済実行前: 残金={self.pre_cash:,.0f}円')
                    
                    # 決済注文実行
                    self.order = self.close()
        except Exception as e:
            import traceback
            self.logger.error(f"ReverseStrategy.next()でエラー発生: {e}")
            self.logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

class BreakoutStrategy(bt.Strategy):
    """
    ブレイクアウト戦略: ATR + ボリンジャーバンド + 前日高値を利用します。
    """
    params = (('lot_size', 100), ('logger', None))  # ロガーパラメータを追加
    
    def __init__(self):
        try:
            # 指標初期化前にデータのサイズをログ
            self.logger = self.params.logger or logger
            self.logger.debug(f"データサイズ: {len(self.data)} バー")
            
            # 各指標を初期化
            self.logger.debug("ATRの初期化開始")
            self.atr = bt.indicators.ATR(self.data)
            self.logger.debug("BollingerBandsの初期化開始")
            self.bband = bt.indicators.BollingerBands(self.data.close, period=20)
            
            self.order = None
            self.pre_cash = None
            self.trades = []
            self.prev_high = None  # 前日高値を初期化
            
            self.logger.debug("BreakoutStrategy初期化完了")
        except Exception as e:
            import traceback
            # ロガーが初期化前の場合に対応
            log = self.params.logger or logger
            log.error(f"BreakoutStrategy.__init__()でエラー発生: {e}")
            log.error(f"詳細なエラー情報: {traceback.format_exc()}")
            raise  # エラーを再スロー

    def calculate_lot_size(self, current_price):
        """利用可能な資金から適切なロットサイズを計算"""
        # 株価が0または極小値の場合は0を返す
        if current_price <= 0.01:  # 1銭以下は実質ゼロと見なす
            self.logger.warning(f"株価が異常値です: {current_price}円 - ロットサイズを0に設定します")
            return 0
        
        available_cash = self.broker.getcash()
        affordable_size = math.floor((available_cash / current_price) / 100) * 100
        actual_size = min(self.params.lot_size, affordable_size)
        return actual_size if actual_size >= 100 else 0

    def notify_order(self, order):
        """注文状態が変化した際に呼ばれるメソッド"""
        if order.status in [order.Completed]:  # 注文が約定した場合
            if order.isbuy():  # 買い注文の場合
                post_cash = self.broker.getcash()
                self.logger.info(f'エントリー実行後: 残金={post_cash:,.0f}円 （差引額：{self.pre_cash - post_cash:,.0f}円）')
                # 取引情報を記録
                self.trades.append({
                    "entry_date": self.data.datetime.date().isoformat(),
                    "entry_price": order.executed.price,
                    "lot": order.executed.size,
                    "post_entry_capital": post_cash
                })
            elif order.issell():  # 売り注文の場合
                post_cash = self.broker.getcash()
                self.logger.info(f'決済実行後: 株価={order.executed.price:,.0f}円 残金={post_cash:,.0f}円 （差引額：{post_cash - self.pre_cash:,.0f}円）')
                # 決済情報を前回のエントリーに追加
                if self.trades:
                    self.trades[-1]["exit_date"] = self.data.datetime.date().isoformat()
                    self.trades[-1]["exit_price"] = order.executed.price
                    self.trades[-1]["post_exit_capital"] = post_cash

        self.order = None  # 注文オブジェクトをリセット

    def next(self):
        try:
            if self.order:  # 未約定の注文がある場合は何もしない
                return

            if len(self.data) > 1:
                self.prev_high = self.data.high[-1]
            
            if not self.position:  # ポジションがない場合
                current_price = self.data.close[0]
                
                # デバッグログを追加
                self.logger.debug(f"指標値チェック - price: {current_price}, bband_top: {self.bband.lines.top[0]}, prev_high: {self.prev_high if hasattr(self, 'prev_high') else 'None'}")
                
                actual_size = self.calculate_lot_size(current_price)
                
                if actual_size >= 100 and self.prev_high is not None and current_price > self.bband.lines.top[0] and current_price > self.prev_high:
                    # エントリー前の残高を保存
                    self.pre_cash = self.broker.getcash()
                    trade_amount = current_price * actual_size
                    self.logger.info(f'エントリー実行前: 株価={current_price:.0f}円 ロット={actual_size}株 '
                           f'必要金額={trade_amount:,.0f}円 現在残金={self.pre_cash:,.0f}円')
                    
                    # 注文実行
                    self.order = self.buy(size=actual_size)

            elif self.position:  # ポジションがある場合
                # デバッグログを追加
                self.logger.debug(f"決済判断 - price: {self.data.close[0]}, bband_mid: {self.bband.lines.mid[0]}")
                
                if self.data.close[0] < self.bband.lines.mid[0]:
                    current_price = self.data.close[0]
                    position_size = self.position.size
                    self.pre_cash = self.broker.getcash()
                    self.logger.info(f'決済実行前: 保有数量={position_size}株 株価={current_price:.0f}円 残金={self.pre_cash:,.0f}円')
                    
                    # 決済注文実行
                    self.order = self.close()
        except Exception as e:
            import traceback
            self.logger.error(f"BreakoutStrategy.next()でエラー発生: {e}")
            self.logger.error(f"詳細なエラー情報: {traceback.format_exc()}")

def run_backtest(symbol: str, start_date: str, end_date: str, strategy_type: str, lot_size: int = 100, logger=None):
    """
    単一の戦略と期間でバックテストを実行し、結果を返します。

    Args:
        symbol: 銘柄シンボル
        start_date: 開始日（YYYY-MM-DD形式）
        end_date: 終了日（YYYY-MM-DD形式）
        strategy_type: 戦略タイプ（'tr', 're', 'bo'のいずれか）
        lot_size: ロットサイズ（デフォルト: 100株）
        logger: ロガーインスタンス（デフォルト: None）

    Returns:
        dict: バックテスト結果（dict形式）
    """
    # ロガーの設定（渡されなかった場合はモジュールロガーを使用）
    log = logger or logging.getLogger(__name__)
    
    # ロギングする
    log.info(f"バックテスト開始: {strategy_type} 戦略 / 銘柄: {symbol} / 期間: {start_date} ～ {end_date}")

    # DBからデータを取得
    repository = BacktestRepository()
    data_df = repository.fetch_historical_data(symbol, start_date, end_date)
    repository.close()

    if data_df.empty:
        log.info("指定された期間のデータが見つかりませんでした。")
        return None
        
    # データの品質チェック
    log.debug(f"取得データ: {len(data_df)}行, カラム={list(data_df.columns)}")
    
    # データの先頭と末尾を確認
    log.debug(f"先頭のデータ: \n{data_df.head(3)}")
    log.debug(f"末尾のデータ: \n{data_df.tail(3)}")
    
    # 欠損値や0値のチェック
    zero_counts = (data_df == 0).sum()
    null_counts = data_df.isnull().sum()
    
    if null_counts.sum() > 0:
        log.warning(f"欠損値が存在します: {null_counts}")
        
    # 価格や出来高が0の行がある場合は警告
    if zero_counts['close'] > 0 or zero_counts['volume'] > 0:
        log.warning(f"価格または出来高が0のデータが存在します: {zero_counts}")
    
    # データ期間が短すぎないかチェック
    if len(data_df) < 30:  # 最低30日分必要
        log.warning(f"データ期間が短すぎます ({len(data_df)}行). 30行以上推奨です。")

    # 無効なデータを除外（株価が0または欠損値）
    original_len = len(data_df)
    data_df = data_df[data_df['close'] > 0]  # 終値が0より大きい行のみ残す
    data_df = data_df.dropna(subset=['open', 'high', 'low', 'close', 'volume'])  # 欠損値を含む行を削除
    filtered_len = len(data_df)
    
    if original_len > filtered_len:
        log.warning(f"無効なデータを {original_len - filtered_len} 行除外しました。残り {filtered_len} 行。")
    
    if filtered_len < 30:  # フィルタリング後のデータが少なすぎる場合
        log.error(f"有効なデータが不足しています ({filtered_len}行)。バックテストを中止します。")
        return None

    # 日付をdatetime型に変換し、インデックスに設定します。
    data_df['date'] = pd.to_datetime(data_df['date'])
    data_df.set_index('date', inplace=True)

    # BacktraderのCerebroインスタンスを作成
    cerebro = bt.Cerebro()

    # 戦略の選択
    strategy_name = ""
    if strategy_type == 'tr':
        cerebro.addstrategy(TrendFollowingStrategy, lot_size=lot_size)
        strategy_name = "trend"
    elif strategy_type == 're':
        cerebro.addstrategy(ReverseStrategy, lot_size=lot_size)
        strategy_name = "reverse"
    elif strategy_type == 'bo':
        cerebro.addstrategy(BreakoutStrategy, lot_size=lot_size)
        strategy_name = "breakout"
    else:
        raise ValueError("不明な戦略タイプです。")

    # データフィードの作成
    data_feed = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data_feed)

    # 初期キャッシュ設定（100万円）
    cerebro.broker.setcash(1000000.0)

    # バックテスト実行
    strategies = cerebro.run()
    strategy = strategies[0]
    
    # 最終ポートフォリオ価値
    final_value = cerebro.broker.getvalue()
    log.info("最終ポートフォリオ価値: {:.2f}".format(final_value))
    
    # 結果をJSON形式で返す
    result = {
        "strategy": strategy_name,
        "stock_code": symbol,
        "period": f"{start_date} to {end_date}",
        "trades": strategy.trades,
        "final_portfolio_value": final_value
    }
    
    # グラフ描画（必要な場合）
    # cerebro.plot()
    
    return result

def run_multiple_backtests(symbol: str, industry_name: str, strategies=None, periods=None, logger=None):
    """
    複数の戦略と期間でバックテストを実行し、結果を返します。
    
    Args:
      symbol: 銘柄シンボル
      industry_name: 業種名
      strategies: 戦略のリスト（デフォルト: ['tr', 're', 'bo']）
      periods: 期間のリスト（デフォルト: 5年前から現在、1年前から現在、2年前から1年前）
      logger: ロガーインスタンス（デフォルト: None）
      
    戻り値:
      list: バックテスト結果のリスト
    """
    # ロガーの設定（渡されなかった場合はモジュールロガーを使用）
    log = logger or logging.getLogger(__name__)
    
    if strategies is None:
        strategies = ['tr', 're', 'bo']
    
    if periods is None:
        today = datetime.date.today()
        five_years_ago = (today - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
        one_year_ago = (today - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
        two_years_ago = (today - datetime.timedelta(days=2*365)).strftime('%Y-%m-%d')
        today_str = today.strftime('%Y-%m-%d')
        
        periods = [
            (five_years_ago, today_str),  # 5年前から現在
            (one_year_ago, today_str),    # 1年前から現在
            (two_years_ago, one_year_ago) # 2年前から1年前
        ]
    
    results = []
    
    for strategy in strategies:
        for start_date, end_date in periods:
            try:
                result = run_backtest(symbol, start_date, end_date, strategy, logger=log)
                if result:
                    results.append(result)
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                log.error(f"バックテスト実行エラー: 銘柄={symbol}, 戦略={strategy}, 期間={start_date}～{end_date}, エラー={e}")
                log.error(f"詳細なエラー情報: {error_detail}")
    
    return results

class BacktestService:
    """
    バックテストを実行するサービスクラス
    """
    def __init__(self):
        self.backtest_repository = BacktestRepository()
        self.stock_repository = StockRepository()
        self.logger = logging.getLogger(__name__)
        
    def run_backtest(self, code: str, industry_name: str, start_date: str, end_date: str, 
                   strategy_type: str = 'tr', initial_funds: int = 1000000, lot_size: int = 100) -> Optional[Dict]:
        """
        指定した銘柄、期間、戦略でバックテストを実行します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 英語の業種名（テーブル接頭辞）
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）
            strategy_type (str): 戦略タイプ（'tr'=トレンド, 're'=逆張り, 'bo'=ブレイクアウト）
            initial_funds (int): 初期資金
            lot_size (int): 取引単位（株数）
            
        Returns:
            Optional[Dict]: バックテスト結果、エラー時はNone
        """
        try:
            self.logger.info(f"バックテスト開始: 銘柄={code}, 業種={industry_name}, 戦略={strategy_type}, 期間={start_date}～{end_date}")
            
            # 株価データの取得
            self.logger.debug(f"業種名（テーブル接頭辞）をそのまま使用: {industry_name}")
            
            # 株価データを取得
            stock_repository = StockRepository()
            stock_data = stock_repository.get_stock_price_data(
                code=code,
                industry_name=industry_name,  # 業種名は既に英語形式のテーブル接頭辞
                start_date=start_date,
                end_date=end_date
            )
            
            if not stock_data or len(stock_data) < 30:  # 最低限必要なデータ量
                self.logger.error(f"十分な株価データがありません: {code}")
                return None
                
            self.logger.info(f"株価データ取得成功: {len(stock_data)}件")
            
            # DataFrameに変換
            df = pd.DataFrame(stock_data)
            
            # 日付をdatetime型に変換し、インデックスに設定
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # backtradingのCerebroインスタンスを初期化
            cerebro = bt.Cerebro()
            
            # 初期資金の設定
            cerebro.broker.setcash(initial_funds)
            
            # データフィードを追加
            data = bt.feeds.PandasData(dataname=df)
            cerebro.adddata(data)
            
            # 戦略の追加
            if strategy_type == 'tr':
                cerebro.addstrategy(TrendFollowingStrategy, lot_size=lot_size)
            elif strategy_type == 're':
                cerebro.addstrategy(ReverseStrategy, lot_size=lot_size)
            elif strategy_type == 'bo':
                cerebro.addstrategy(BreakoutStrategy, lot_size=lot_size)
            else:
                self.logger.error(f"不明な戦略タイプ: {strategy_type}")
                return None
                
            # バックテスト実行前の資金計算
            initial_value = cerebro.broker.getvalue()
            self.logger.info(f"バックテスト開始資金: {initial_value:,.0f}円")
            
            # バックテスト実行
            strategies = cerebro.run()
            strategy = strategies[0]
            
            # 最終ポートフォリオ価値
            final_value = cerebro.broker.getvalue()
            self.logger.info(f"バックテスト終了資金: {final_value:,.0f}円")
            
            # 利益率計算
            profit_percentage = ((final_value - initial_value) / initial_value) * 100
            self.logger.info(f"利益率: {profit_percentage:.2f}%")
            
            # 取引履歴
            trades = strategy.trades
            
            # 戦略名称マッピング
            strategy_names = {
                'tr': 'trend',
                're': 'reverse',
                'bo': 'breakout'
            }
            
            # strategy.statsのアクセス方法を修正
            # ItemCollectionオブジェクトはgetメソッドを持たないため、hasattrでチェックしてから安全にアクセスする
            success_rate = 0
            average_return = 0
            max_drawdown = 0
            
            try:
                # 成功率の取得を試みる
                if hasattr(strategy, 'stats') and hasattr(strategy.stats, 'success_rate'):
                    success_rate = strategy.stats.success_rate
                # 平均リターンの取得を試みる
                if hasattr(strategy, 'stats') and hasattr(strategy.stats, 'avg_return'):
                    average_return = strategy.stats.avg_return
                # 最大ドローダウンの取得を試みる
                if hasattr(strategy, 'stats') and hasattr(strategy.stats, 'max_drawdown'):
                    max_drawdown = strategy.stats.max_drawdown
                    
                self.logger.debug(f"バックテスト統計情報: 成功率={success_rate}, 平均リターン={average_return}, 最大ドローダウン={max_drawdown}")
            except Exception as stats_error:
                self.logger.warning(f"バックテスト統計情報の取得中にエラー: {stats_error}")
            
            backtest_result = {
                'code': code,
                'strategy': strategy_names.get(strategy_type, strategy_type),
                'start_date': start_date,
                'end_date': end_date,
                'initial_funds': initial_funds,
                'final_portfolio_value': final_value,
                'return_percentage': ((final_value - initial_value) / initial_value) * 100,
                'trades': trades,
                'success_rate': success_rate,
                'average_return': average_return,
                'max_drawdown': max_drawdown,
                'total_trades': len(trades)
            }
            
            return backtest_result
            
        except Exception as e:
            self.logger.error(f"バックテスト実行中にエラー: {e}", exc_info=True)
            return None
            
    def run_multiple_strategy_backtest(self, code: str, industry_name: str, 
                                     initial_funds: int = 1000000, period_years: int = 5) -> List[Dict]:
        """
        複数の戦略と期間でバックテストを実行します
        
        Args:
            code (str): 銘柄コード
            industry_name (str): 業種名（英語のテーブル接頭辞）
            initial_funds (int): 初期資金
            period_years (int): バックテスト対象期間（年）
            
        Returns:
            List[Dict]: バックテスト結果のリスト
        """
        try:
            self.logger.info(f"複数戦略バックテスト開始: 銘柄={code}, 業種={industry_name}, 期間={period_years}年")
            
            # 戦略リスト
            strategies = ['tr', 're', 'bo']  # トレンドフォロー、逆張り、ブレイクアウト
            self.logger.info(f"実行戦略: {', '.join(strategies)}")
            
            # 期間の設定
            today = datetime.date.today()
            today_str = today.strftime('%Y-%m-%d')
            
            # 主要期間（全期間、直近1年、その前の1年）
            periods = []
            
            # 全期間（指定年数）
            years_ago = (today - datetime.timedelta(days=period_years*365)).strftime('%Y-%m-%d')
            periods.append((years_ago, today_str))
            
            # 直近1年
            one_year_ago = (today - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
            periods.append((one_year_ago, today_str))
            
            # その前の1年（もし指定期間が2年以上なら）
            if period_years >= 2:
                two_years_ago = (today - datetime.timedelta(days=2*365)).strftime('%Y-%m-%d')
                periods.append((two_years_ago, one_year_ago))
            
            self.logger.info(f"バックテスト期間: {len(periods)}期間 ({years_ago}～{today_str})")
            
            results = []
            
            # 各戦略と期間の組み合わせでバックテスト実行
            for strategy in strategies:
                for start_date, end_date in periods:
                    try:
                        self.logger.info(f"バックテスト実行: 戦略={strategy}, 期間={start_date}～{end_date}")
                        result = self.run_backtest(
                            code=code,
                            industry_name=industry_name,  # 業種名は既に英語形式のテーブル接頭辞
                            start_date=start_date,
                            end_date=end_date,
                            strategy_type=strategy,
                            initial_funds=initial_funds
                        )
                        
                        if result:
                            results.append(result)
                            return_percentage = result.get('return_percentage', 0)
                            self.logger.info(f"バックテスト結果: 戦略={strategy}, 期間={start_date}～{end_date}, リターン={return_percentage:.2f}%")
                        else:
                            self.logger.warning(f"バックテスト失敗: 戦略={strategy}, 期間={start_date}～{end_date}")
                            
                    except Exception as e:
                        self.logger.error(f"戦略 {strategy} のバックテスト中にエラー: {e}", exc_info=True)
            
            self.logger.info(f"複数戦略バックテスト完了: 成功={len(results)}件")
            return results
            
        except Exception as e:
            self.logger.error(f"複数戦略バックテスト実行中にエラー: {e}", exc_info=True)
            return []
