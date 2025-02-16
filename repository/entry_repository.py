from typing import List, Dict, Optional
from datetime import datetime
from .base_repository import BaseRepository

class EntryRepository(BaseRepository):
    def fetch_best_entry_candidates(self, min_score: int = 650) -> List[Dict]:
        """
        エントリースコアが指定値以上のデータを期待リターンの降順で取得します
        
        Args:
            min_score (int): 最小エントリースコア（デフォルト: 650）
            
        Returns:
            List[Dict]: エントリー候補のリスト
        """
        try:
            query = """
            SELECT 
                code, date, close, rule_entry_price, rule_stop_limit,
                rule_top_price, rule_period, risk_reward, entry_score,
                expected_return, reason
            FROM api_response
            WHERE entry_score >= %s
            ORDER BY expected_return DESC;
            """
            
            self.cur.execute(query, (min_score,))
            rows = self.cur.fetchall()
            
            return [{
                'code': row[0],
                'date': row[1],
                'close': row[2],
                'entry_price': row[3],
                'stop_loss': row[4],
                'target_price': row[5],
                'period': row[6],
                'risk_reward': row[7],
                'entry_score': row[8],
                'expected_return': row[9],
                'reason': row[10]
            } for row in rows]

        except Exception as e:
            self.logger.error(f"エントリー候補取得エラー: {e}")
            return []

    def save_entry_info(self, entry_data: Dict) -> bool:
        """
        エントリー情報をDBに保存します
        
        Args:
            entry_data (Dict): 保存するエントリー情報
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            query = """
            INSERT INTO entries (
                code, entry_date, entry_price, stop_loss,
                target_price, reason, holding_period,
                risk_reward, quantity, status,
                created_at, updated_at
            ) VALUES (
                %(code)s, %(entry_date)s, %(entry_price)s, %(stop_loss)s,
                %(target_price)s, %(reason)s, %(holding_period)s,
                %(risk_reward)s, %(quantity)s, %(status)s,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            );
            """
            
            self.cur.execute(query, entry_data)
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"エントリー情報保存エラー: {e}")
            self.conn.rollback()
            return False 