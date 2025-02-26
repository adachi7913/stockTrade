import logging
from typing import List, Dict, Any, Optional
from repository.base_repository import BaseRepository

class MaterializedViewRepository(BaseRepository):
    """
    マテリアライズドビューの更新を管理するリポジトリクラス
    """
    
    def __init__(self):
        """
        初期化処理
        """
        super().__init__()
        self.logger = logging.getLogger(__name__)
    
    def refresh_all_views(self) -> bool:
        """
        すべてのマテリアライズドビューを更新します
        
        Returns:
            bool: 更新が成功した場合はTrue、失敗した場合はFalse
        """
        # 現在の接続を閉じて新しい接続を取得
        self.close()
        self.connect()
        
        try:
            self.logger.info("マテリアライズドビューの更新を開始します")
            
            # 自動コミットモードを有効にする
            self.conn.autocommit = True
            
            # 株価データのマテリアライズドビューを更新
            self.cur.execute("REFRESH MATERIALIZED VIEW all_stock_prices_indexed")
            self.logger.info("all_stock_prices_indexed の更新が完了しました")
            
            # インジケーターデータのマテリアライズドビューを更新
            self.cur.execute("REFRESH MATERIALIZED VIEW all_stock_indicators_indexed")
            self.logger.info("all_stock_indicators_indexed の更新が完了しました")
            
            self.logger.info("マテリアライズドビューの更新が正常に完了しました")
            return True
            
        except Exception as e:
            self.logger.error(f"マテリアライズドビューの更新中にエラーが発生しました: {e}")
            return False
    
    def get_all_materialized_views(self) -> List[Dict[str, Any]]:
        """
        データベース内のすべてのマテリアライズドビューの一覧を取得します
        
        Returns:
            List[Dict[str, Any]]: マテリアライズドビューの情報リスト
        """
        try:
            query = """
            SELECT matviewname, matviewowner, ispopulated, 
                   pg_size_pretty(pg_relation_size(schemaname || '.' || matviewname)) as size
            FROM pg_matviews
            WHERE schemaname = 'public'
            ORDER BY matviewname
            """
            self.cur.execute(query)
            columns = [desc[0] for desc in self.cur.description]
            result = [dict(zip(columns, row)) for row in self.cur.fetchall()]
            return result
        except Exception as e:
            self.logger.error(f"マテリアライズドビュー一覧の取得中にエラーが発生しました: {e}")
            return []
    
    def refresh_view(self, view_name: str) -> bool:
        """
        指定されたマテリアライズドビューを更新します
        
        Args:
            view_name (str): 更新するマテリアライズドビューの名前
            
        Returns:
            bool: 更新が成功した場合はTrue、失敗した場合はFalse
        """
        # 現在の接続を閉じて新しい接続を取得
        self.close()
        self.connect()
        
        try:
            self.logger.info(f"マテリアライズドビュー {view_name} の更新を開始します")
            
            # マテリアライズドビューが存在するか確認
            self.cur.execute("""
                SELECT 1 FROM pg_matviews 
                WHERE schemaname = 'public' AND matviewname = %s
            """, (view_name,))
            
            if self.cur.fetchone() is None:
                self.logger.error(f"マテリアライズドビュー {view_name} は存在しません")
                return False
            
            # 自動コミットモードを有効にする
            self.conn.autocommit = True
            
            # マテリアライズドビューを更新
            self.cur.execute(f"REFRESH MATERIALIZED VIEW {view_name}")
            
            self.logger.info(f"マテリアライズドビュー {view_name} の更新が完了しました")
            return True
            
        except Exception as e:
            self.logger.error(f"マテリアライズドビュー {view_name} の更新中にエラーが発生しました: {e}")
            return False
    
    def get_view_last_refresh_time(self, view_name: str) -> Optional[str]:
        """
        マテリアライズドビューの最終更新時間を取得します
        
        Args:
            view_name (str): マテリアライズドビューの名前
            
        Returns:
            Optional[str]: 最終更新時間（取得できない場合はNone）
        """
        try:
            # PostgreSQLのstatsビューから最終更新時間を取得
            query = """
            SELECT pg_stat_get_last_vacuum_time(c.oid) as last_refresh_time
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = %s AND n.nspname = 'public'
            """
            self.cur.execute(query, (view_name,))
            result = self.cur.fetchone()
            
            if result and result[0]:
                return result[0].strftime('%Y-%m-%d %H:%M:%S')
            return None
            
        except Exception as e:
            self.logger.error(f"ビュー {view_name} の最終更新時間取得中にエラーが発生しました: {e}")
            return None
