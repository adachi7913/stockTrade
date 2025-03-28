import logging
from typing import Dict, List, Optional, Any

class FundManager:
    """
    利用可能資金を管理するクラス
    
    複数銘柄購入時に、購入予定の資金を予約し、
    実際の利用可能資金を正確に管理するための機能を提供します。
    """
    
    def __init__(self, initial_funds: float, logger=None):
        """
        初期化
        
        Args:
            initial_funds (float): 初期利用可能資金
            logger: ロガーインスタンス
        """
        self._available_funds = initial_funds
        self._pending_purchases = []  # 購入予定リスト
        self.logger = logger or logging.getLogger(__name__)
        
    def can_purchase(self, cost: float) -> bool:
        """
        指定した金額の購入が可能かどうかを判定
        
        Args:
            cost (float): 購入予定金額
            
        Returns:
            bool: 購入可能な場合はTrue
        """
        return self._available_funds >= cost
        
    def reserve_funds(self, symbol: str, cost: float) -> bool:
        """
        購入予定の資金を予約
        
        Args:
            symbol (str): 銘柄コード
            cost (float): 購入予定金額
            
        Returns:
            bool: 予約成功の場合はTrue
        """
        if self.can_purchase(cost):
            self._available_funds -= cost
            self._pending_purchases.append({
                'symbol': symbol,
                'cost': cost
            })
            self.logger.info(f"資金予約: {symbol} - {cost:,.0f}円（残り: {self._available_funds:,.0f}円）")
            return True
        
        self.logger.warning(f"資金予約失敗: {symbol} - {cost:,.0f}円（利用可能: {self._available_funds:,.0f}円）")
        return False
        
    def release_reservation(self, symbol: str) -> float:
        """
        特定の銘柄の資金予約を解除
        
        Args:
            symbol (str): 銘柄コード
            
        Returns:
            float: 解除された金額
        """
        released_amount = 0
        for i, purchase in enumerate(self._pending_purchases):
            if purchase['symbol'] == symbol:
                released_amount = purchase['cost']
                self._available_funds += released_amount
                self._pending_purchases.pop(i)
                self.logger.info(f"資金予約解除: {symbol} - {released_amount:,.0f}円（残り: {self._available_funds:,.0f}円）")
                break
        
        return released_amount
        
    def clear_pending_purchases(self) -> float:
        """
        すべての資金予約を解除
        
        Returns:
            float: 解除された合計金額
        """
        total_released = sum(purchase['cost'] for purchase in self._pending_purchases)
        self._available_funds += total_released
        self._pending_purchases.clear()
        self.logger.info(f"全資金予約解除: {total_released:,.0f}円（残り: {self._available_funds:,.0f}円）")
        return total_released
        
    def get_available_funds(self) -> float:
        """
        現在の利用可能資金を取得
        
        Returns:
            float: 利用可能資金
        """
        return self._available_funds
        
    def get_pending_purchases(self) -> List[Dict]:
        """
        現在の購入予定リストを取得
        
        Returns:
            List[Dict]: 購入予定リスト
        """
        return self._pending_purchases.copy() 