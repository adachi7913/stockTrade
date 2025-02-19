import backtrader as bt
import pandas as pd
from repository.backtest_repository import BacktestRepository
import logging
import math

logger = logging.getLogger(__name__)

class TrendFollowingStrategy(bt.Strategy):
    """
    順張り戦略: 一目均衡表 + MACD + ADXを利用します。
    """
    params = (('lot_size', 100),)  # デフォルト値を設定
    
    def __init__(self):
        self.ichimoku = bt.indicators.Ichimoku(self.data)
        self.macd = bt.indicators.MACD(self.data.close)
        self.adx = bt.indicators.ADX(self.data)
        self.order = None  # 注文オブジェクトを保持
        self.pre_cash = None  # 注文前の残高を保持

    def calculate_lot_size(self, current_price):
        """利用可能な資金から適切なロットサイズを計算"""
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
                logger.info(f'エントリー実行後: 残金={post_cash:,.0f}円 （差引額：{self.pre_cash - post_cash:,.0f}円）')
            elif order.issell():  # 売り注文の場合
                post_cash = self.broker.getcash()
                logger.info(f'決済実行後: 株価={self.data.close[0]:.0f}円 残金={post_cash:,.0f}円 （差引額：{post_cash - self.pre_cash:,.0f}円）')
        
        self.order = None  # 注文完了後にリセット

    def next(self):
        if self.order:  # 未約定の注文がある場合は何もしない
            return

        if not self.position:  # ポジションがない場合
            current_price = self.data.close[0]
            actual_size = self.calculate_lot_size(current_price)
            
            if actual_size >= 100 and self.macd.macd[0] > 0 and self.adx[0] > 25 and current_price > self.ichimoku.lines.senkou_span_a[0]:
                # エントリー前の残高を保存
                self.pre_cash = self.broker.getcash()
                trade_amount = current_price * actual_size
                logger.info(f'エントリー実行前: 株価={current_price:.0f}円 ロット={actual_size}株 '
                           f'必要金額={trade_amount:,.0f}円 現在残金={self.pre_cash:,.0f}円')
                
                # 注文実行
                self.order = self.buy(size=actual_size)

        elif self.position:  # ポジションがある場合
            if self.macd.macd[0] < 0 or self.data.close[0] < self.ichimoku.lines.senkou_span_b[0]:
                current_price = self.data.close[0]
                position_size = self.position.size
                self.pre_cash = self.broker.getcash()
                logger.info(f'決済実行前: 保有数量={position_size}株 株価={current_price:.0f}円 残金={self.pre_cash:,.0f}円')
                
                # 決済注文実行
                self.order = self.close()

class ReverseStrategy(bt.Strategy):
    """
    逆張り戦略: RSI + ストキャスティクス + ボリンジャーバンドを利用します。
    """
    params = (('lot_size', 100),)  # デフォルト値を設定
    
    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close)
        self.stochastic = bt.indicators.Stochastic(self.data)
        self.boll = bt.indicators.BollingerBands(self.data.close)

    def calculate_lot_size(self, current_price):
        """利用可能な資金から適切なロットサイズを計算"""
        available_cash = self.broker.getcash()
        affordable_size = math.floor((available_cash / current_price) / 100) * 100
        actual_size = min(self.params.lot_size, affordable_size)
        return actual_size if actual_size >= 100 else 0

    def next(self):
        if not self.position:
            current_price = self.data.close[0]
            actual_size = self.calculate_lot_size(current_price)
            
            if actual_size >= 100 and self.rsi[0] < 30 and self.stochastic.percK[0] < 20 and current_price <= self.boll.lines.bot[0]:
                # エントリー前の残高をログ出力
                pre_cash = self.broker.getcash()
                trade_amount = current_price * actual_size
                logger.info(f'エントリー実行前: 株価={current_price:.0f}円 ロット={actual_size}株 '
                           f'必要金額={trade_amount:,.0f}円 現在残金={pre_cash:,.0f}円')
                
                self.buy(size=actual_size)
                
                # エントリー後の残高をログ出力
                post_cash = self.broker.getcash()
                logger.info(f'エントリー実行後: 残金={post_cash:,.0f}円')
        else:
            if self.rsi[0] > 70 or self.data.close[0] >= self.boll.lines.mid[0]:
                pre_cash = self.broker.getcash()
                logger.info(f'決済実行前: 残金={pre_cash:,.0f}円')
                
                self.close()
                
                post_cash = self.broker.getcash()
                logger.info(f'決済実行後: 株価={self.data.close[0]:.0f}円 残金={post_cash:,.0f}円')

class BreakoutStrategy(bt.Strategy):
    """
    ブレイクアウト戦略: ATR + ボリンジャーバンド + 前日高値を利用します。
    """
    params = (('lot_size', 100),)  # デフォルト値を設定
    
    def __init__(self):
        self.atr = bt.indicators.ATR(self.data)
        self.boll = bt.indicators.BollingerBands(self.data.close)
        self.prev_high = None
        self.order = None  # 注文オブジェクトを保持
        self.pre_cash = None  # 注文前の残高を保持

    def calculate_lot_size(self, current_price):
        """利用可能な資金から適切なロットサイズを計算"""
        available_cash = self.broker.getcash()
        affordable_size = math.floor((available_cash / current_price) / 100) * 100
        actual_size = min(self.params.lot_size, affordable_size)
        return actual_size if actual_size >= 100 else 0

    def notify_order(self, order):
        """注文状態が変化した際に呼ばれるメソッド"""
        if order.status in [order.Completed]:  # 注文が約定した場合
            if order.isbuy():  # 買い注文の場合
                post_cash = self.broker.getcash()
                logger.info(f'エントリー実行後: 残金={post_cash:,.0f}円 （差引額：{self.pre_cash - post_cash:,.0f}円）')
            elif order.issell():  # 売り注文の場合
                post_cash = self.broker.getcash()
                logger.info(f'決済実行後: 株価={self.data.close[0]:.0f}円 残金={post_cash:,.0f}円 （差引額：{post_cash - self.pre_cash:,.0f}円）')
        
        self.order = None  # 注文完了後にリセット

    def next(self):
        if self.order:  # 未約定の注文がある場合は何もしない
            return

        if len(self.data) > 1:
            self.prev_high = self.data.high[-1]
        
        if not self.position:  # ポジションがない場合
            current_price = self.data.close[0]
            actual_size = self.calculate_lot_size(current_price)
            
            if actual_size >= 100 and self.prev_high is not None and current_price > self.boll.lines.top[0] and current_price > self.prev_high:
                # エントリー前の残高を保存
                self.pre_cash = self.broker.getcash()
                trade_amount = current_price * actual_size
                logger.info(f'エントリー実行前: 株価={current_price:.0f}円 ロット={actual_size}株 '
                           f'必要金額={trade_amount:,.0f}円 現在残金={self.pre_cash:,.0f}円')
                
                # 注文実行
                self.order = self.buy(size=actual_size)

        elif self.position:  # ポジションがある場合
            if self.data.close[0] < self.boll.lines.mid[0]:
                current_price = self.data.close[0]
                position_size = self.position.size
                self.pre_cash = self.broker.getcash()
                logger.info(f'決済実行前: 保有数量={position_size}株 株価={current_price:.0f}円 残金={self.pre_cash:,.0f}円')
                
                # 決済注文実行
                self.order = self.close()

def run_backtest(symbol: str, start_date: str, end_date: str, strategy_type: str, lot_size: int = 100):
    """
    指定した銘柄、期間、戦略でバックテストを実行します。
    
    引数:
      symbol: 銘柄シンボル（例: 'AAPL'）
      start_date: 開始日（YYYY-MM-DD形式）
      end_date: 終了日（YYYY-MM-DD形式）
      strategy_type: 戦略タイプ（'tr=[trend]', 're=[reverse]', 'bo=[breakout]'）
    """
    # DBからデータを取得
    repository = BacktestRepository()
    data_df = repository.fetch_historical_data(symbol, start_date, end_date)
    repository.close()

    if data_df.empty:
        logger.info("指定された期間のデータが見つかりませんでした。")
        return

    # 日付をdatetime型に変換し、インデックスに設定します。
    data_df['date'] = pd.to_datetime(data_df['date'])
    data_df.set_index('date', inplace=True)

    # BacktraderのCerebroインスタンスを作成
    cerebro = bt.Cerebro()

    # 戦略の選択
    if strategy_type == 'tr':
        cerebro.addstrategy(TrendFollowingStrategy, lot_size=lot_size)
    elif strategy_type == 're':
        cerebro.addstrategy(ReverseStrategy, lot_size=lot_size)
    elif strategy_type == 'bo':
        cerebro.addstrategy(BreakoutStrategy, lot_size=lot_size)
    else:
        raise ValueError("不明な戦略タイプです。")

    # データフィードの作成
    data_feed = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data_feed)

    # 初期キャッシュ設定（100万円）
    cerebro.broker.setcash(1000000.0)

    logger.info("バックテスト開始: {} 戦略 / 銘柄: {} / 期間: {} ～ {}".format(strategy_type, symbol, start_date, end_date))
    cerebro.run()
    final_value = cerebro.broker.getvalue()
    logger.info("最終ポートフォリオ価値: {:.2f}".format(final_value))
    cerebro.plot()
