import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union
import io
import logging
from matplotlib.figure import Figure

def create_stock_chart(data: List[Dict], code: str, title: Optional[str] = None) -> bytes:
    """
    株価データとインジケーターデータからチャート画像を生成し、バイト列として返します。
    
    Args:
        data (List[Dict]): StockRepositoryから取得した株価とインジケーターのデータ
        code (str): 銘柄コード
        title (Optional[str]): グラフタイトル（デフォルトは銘柄コードを使用）
        
    Returns:
        bytes: 生成されたチャート画像のバイト列
    """
    logger = logging.getLogger(__name__)
    
    if not data:
        logger.error(f"データが空のため、チャート生成できません: code={code}")
        # 空のデータの場合は、エラーメッセージの画像を返す
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, f"データが不足しているためチャートを生成できません (銘柄コード: {code})", 
                ha='center', va='center', fontsize=12)
        ax.axis('off')
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    
    # リストをDataFrameに変換
    try:
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df.set_index('date', inplace=True)
    except Exception as e:
        logger.error(f"データフレーム変換エラー: {e}")
        # エラーの場合はエラーメッセージの画像を返す
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, f"データ処理エラー: {str(e)[:100]}...", 
                ha='center', va='center', fontsize=12)
        ax.axis('off')
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    
    # 描画用にまだ必要な列があるかチェックし、なければデフォルト値や計算値を設定
    required_columns = [
        'open', 'high', 'low', 'close', 'volume',
        'macd', 'rsi', 'stoch_k', 'stoch_d', 
        'bb_lower', 'bb_middle', 'bb_upper', 'adx'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = np.nan
    
    # タイトル設定
    if title is None:
        title = f"銘柄コード: {code} - チャート分析"
    
    # 6つの分割グラフを作成
    fig = plt.figure(figsize=(15, 20))
    
    # グラフ1: ローソク足 + ボリンジャーバンド
    ax1 = plt.subplot2grid((6, 1), (0, 0), rowspan=2)
    ax1.set_title(title, fontsize=16)
    
    # ローソク足
    up = df[df.close >= df.open]
    down = df[df.close < df.open]
    
    # 上昇ローソク（陽線）
    ax1.bar(up.index, up.high - up.low, width=0.6, bottom=up.low, color='white', edgecolor='red', alpha=0.5)
    ax1.bar(up.index, up.close - up.open, width=0.6, bottom=up.open, color='red', edgecolor='red')
    
    # 下降ローソク（陰線）
    ax1.bar(down.index, down.high - down.low, width=0.6, bottom=down.low, color='white', edgecolor='blue', alpha=0.5)
    ax1.bar(down.index, down.open - down.close, width=0.6, bottom=down.close, color='blue', edgecolor='blue')
    
    # ボリンジャーバンド
    if not df['bb_upper'].isnull().all() and not df['bb_middle'].isnull().all() and not df['bb_lower'].isnull().all():
        ax1.plot(df.index, df.bb_upper, 'g--', alpha=0.5, label='BB Upper')
        ax1.plot(df.index, df.bb_middle, 'g-', alpha=0.5, label='BB Middle')
        ax1.plot(df.index, df.bb_lower, 'g--', alpha=0.5, label='BB Lower')
    
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel('価格', fontsize=12)
    
    # グラフ2: 出来高
    ax2 = plt.subplot2grid((6, 1), (2, 0), rowspan=1, sharex=ax1)
    ax2.bar(df.index, df.volume, color='indigo', alpha=0.5)
    ax2.set_ylabel('出来高', fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    # グラフ3: MACD
    ax3 = plt.subplot2grid((6, 1), (3, 0), rowspan=1, sharex=ax1)
    if 'macd' in df.columns and not df['macd'].isnull().all():
        # シグナルラインとヒストグラムはデータになければ計算
        if 'macd_signal' not in df.columns:
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        if 'macd_hist' not in df.columns:
            df['macd_hist'] = df['macd'] - df['macd_signal']
        
        ax3.plot(df.index, df.macd, 'b-', label='MACD')
        ax3.plot(df.index, df.macd_signal, 'r-', label='Signal')
        ax3.bar(df.index, df.macd_hist, color='gray', alpha=0.5)
        ax3.axhline(y=0, color='k', linestyle='-', alpha=0.2)
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)
    ax3.set_ylabel('MACD', fontsize=12)
    
    # グラフ4: RSI
    ax4 = plt.subplot2grid((6, 1), (4, 0), rowspan=1, sharex=ax1)
    if 'rsi' in df.columns and not df['rsi'].isnull().all():
        ax4.plot(df.index, df.rsi, 'purple', label='RSI')
        ax4.axhline(y=70, color='r', linestyle='--', alpha=0.5)
        ax4.axhline(y=30, color='g', linestyle='--', alpha=0.5)
        ax4.axhline(y=50, color='k', linestyle='-', alpha=0.2)
        ax4.fill_between(df.index, df.rsi, 70, where=(df.rsi >= 70), color='r', alpha=0.3)
        ax4.fill_between(df.index, df.rsi, 30, where=(df.rsi <= 30), color='g', alpha=0.3)
    ax4.set_ylim(0, 100)
    ax4.legend(loc='upper left')
    ax4.grid(True, alpha=0.3)
    ax4.set_ylabel('RSI', fontsize=12)
    
    # グラフ5: ストキャスティクス
    ax5 = plt.subplot2grid((6, 1), (5, 0), rowspan=1, sharex=ax1)
    if 'stoch_k' in df.columns and 'stoch_d' in df.columns and not df['stoch_k'].isnull().all() and not df['stoch_d'].isnull().all():
        ax5.plot(df.index, df.stoch_k, 'k-', label='%K')
        ax5.plot(df.index, df.stoch_d, 'r--', label='%D')
        ax5.axhline(y=80, color='r', linestyle='--', alpha=0.5)
        ax5.axhline(y=20, color='g', linestyle='--', alpha=0.5)
        ax5.fill_between(df.index, df.stoch_k, 80, where=(df.stoch_k >= 80), color='r', alpha=0.3)
        ax5.fill_between(df.index, df.stoch_k, 20, where=(df.stoch_k <= 20), color='g', alpha=0.3)
    ax5.set_ylim(0, 100)
    ax5.legend(loc='upper left')
    ax5.grid(True, alpha=0.3)
    ax5.set_ylabel('Stochastic', fontsize=12)
    
    # X軸の日付フォーマット
    for ax in [ax1, ax2, ax3, ax4, ax5]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    
    plt.tight_layout()
    plt.subplots_adjust(hspace=0.1)
    
    # グラフをバイト列に保存
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100)
    plt.close(fig)
    buf.seek(0)
    
    return buf.getvalue() 