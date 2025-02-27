import os
from typing import List, Dict, Optional, Any
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
            # 環境変数 MIN_ENTRY_SCORE が設定されている場合、その値を使用（int変換）
            env_min_score = os.getenv("MIN_ENTRY_SCORE")
            if env_min_score is not None:
                try:
                    min_score = int(env_min_score)
                except ValueError:
                    self.logger.error(f"環境変数MIN_ENTRY_SCOREの値が数値に変換できません: {env_min_score}. デフォルト値650を使用します。")
                    min_score = 650

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

    def save_ai_judgment(self, judgment_data: Dict, stock_data: Dict, processing_info: Dict = None) -> Optional[int]:
        """
        AIによるエントリー判断結果をai_entry_judgmentsテーブルに保存します
        
        Args:
            judgment_data (Dict): AIによる判断結果
                - should_enter: bool
                - confidence: int
                - reasoning: str
                - concerns: str (optional)
            stock_data (Dict): 元の銘柄情報
                - code: str
                - entry_price: float
                - stop_loss: float
                - target_price: float
                - expected_return: float
                - entry_score: int
                - reason: str
            processing_info (Dict, optional): 処理情報
                - prompting_tokens: int
                - completion_tokens: int
                - total_tokens: int
                - processing_time: float
                - model_version: str
                
        Returns:
            Optional[int]: 保存に成功した場合はjudgment_id、失敗した場合はNone
        """
        try:
            query = """
            INSERT INTO ai_entry_judgments (
                code, judgment_date, judgment_time, should_enter, confidence,
                reasoning, concerns, entry_price, stop_loss, target_price,
                expected_return, entry_score, entry_reason,
                prompting_tokens, completion_tokens, total_tokens,
                processing_time, model_version
            ) VALUES (
                %(code)s, CURRENT_DATE, CURRENT_TIMESTAMP, %(should_enter)s, %(confidence)s,
                %(reasoning)s, %(concerns)s, %(entry_price)s, %(stop_loss)s, %(target_price)s,
                %(expected_return)s, %(entry_score)s, %(entry_reason)s,
                %(prompting_tokens)s, %(completion_tokens)s, %(total_tokens)s,
                %(processing_time)s, %(model_version)s
            )
            RETURNING judgment_id;
            """
            
            # データの型を適切に変換
            try:
                should_enter = bool(judgment_data['should_enter'])
            except (KeyError, ValueError, TypeError):
                should_enter = False
                
            try:
                confidence = int(judgment_data['confidence']) if judgment_data.get('confidence') is not None else 0
            except (ValueError, TypeError):
                confidence = 0
                
            try:
                entry_price = float(stock_data['entry_price']) if stock_data.get('entry_price') is not None else 0.0
            except (ValueError, TypeError):
                entry_price = 0.0
                
            try:
                stop_loss = float(stock_data['stop_loss']) if stock_data.get('stop_loss') is not None else 0.0
            except (ValueError, TypeError):
                stop_loss = 0.0
                
            try:
                target_price = float(stock_data.get('target_price', 0)) if stock_data.get('target_price') is not None else 0.0
            except (ValueError, TypeError):
                target_price = 0.0
                
            try:
                expected_return = float(stock_data.get('expected_return', 0)) if stock_data.get('expected_return') is not None else 0.0
            except (ValueError, TypeError):
                expected_return = 0.0
                
            try:
                entry_score = int(stock_data.get('entry_score', 0)) if stock_data.get('entry_score') is not None else 0
            except (ValueError, TypeError):
                entry_score = 0
                
            # 辞書をマージしてパラメータを作成
            params = {
                'code': str(stock_data['code']),
                'should_enter': should_enter,
                'confidence': confidence,
                'reasoning': str(judgment_data.get('reasoning', '不明')),
                'concerns': str(judgment_data.get('concerns', '')) if judgment_data.get('concerns') else None,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'target_price': target_price,
                'expected_return': expected_return,
                'entry_score': entry_score,
                'entry_reason': str(stock_data.get('reason', '不明')),
                'prompting_tokens': None,
                'completion_tokens': None,
                'total_tokens': None,
                'processing_time': None,
                'model_version': None
            }
            
            # 処理情報がある場合は追加
            if processing_info:
                try:
                    prompting_tokens = int(processing_info.get('prompting_tokens', 0)) if processing_info.get('prompting_tokens') is not None else None
                except (ValueError, TypeError):
                    prompting_tokens = None
                    
                try:
                    completion_tokens = int(processing_info.get('completion_tokens', 0)) if processing_info.get('completion_tokens') is not None else None
                except (ValueError, TypeError):
                    completion_tokens = None
                    
                try:
                    total_tokens = int(processing_info.get('total_tokens', 0)) if processing_info.get('total_tokens') is not None else None
                except (ValueError, TypeError):
                    total_tokens = None
                    
                try:
                    processing_time = float(processing_info.get('processing_time', 0)) if processing_info.get('processing_time') is not None else None
                except (ValueError, TypeError):
                    processing_time = None
                    
                params.update({
                    'prompting_tokens': prompting_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': total_tokens,
                    'processing_time': processing_time,
                    'model_version': str(processing_info.get('model_version', '')) if processing_info.get('model_version') else None
                })
            
            self.cur.execute(query, params)
            result = self.cur.fetchone()
            self.conn.commit()
            
            # 挿入されたIDを返す
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"AI判断結果保存エラー: {e}")
            self.conn.rollback()
            return None

    def save_backtest_results(self, judgment_id: int, backtest_data: Dict) -> bool:
        """
        バックテスト結果をbacktest_resultsテーブルに保存し、
        各戦略の詳細をbacktest_strategy_detailsテーブルに保存します
        
        Args:
            judgment_id (int): ai_entry_judgmentsテーブルのID
            backtest_data (Dict): バックテスト結果
                - success_rate: float
                - average_return: float
                - total_trades: int
                - total_profit: float
                - best_strategy: str
                - worst_strategy: str
                - strategy_summary: Dict[str, Dict]
                
        Returns:
            bool: 保存成功でTrue
        """
        try:
            # データが空の場合は何もせずTrueを返す
            if not backtest_data:
                self.logger.warning("バックテストデータが空のため保存をスキップします")
                return True
                
            # まずbacktest_resultsテーブルに結果概要を挿入
            backtest_query = """
            INSERT INTO backtest_results (
                judgment_id, success_rate, average_return, total_trades,
                total_profit, best_strategy, worst_strategy,
                backtest_date, backtest_time
            ) VALUES (
                %(judgment_id)s, %(success_rate)s, %(average_return)s, %(total_trades)s,
                %(total_profit)s, %(best_strategy)s, %(worst_strategy)s,
                CURRENT_DATE, CURRENT_TIMESTAMP
            )
            RETURNING backtest_id;
            """
            
            # データの型を適切に変換
            try:
                success_rate = float(backtest_data.get('success_rate', 0)) if backtest_data.get('success_rate') is not None else 0.0
            except (ValueError, TypeError):
                success_rate = 0.0
                
            try:
                average_return = float(backtest_data.get('average_return', 0)) if backtest_data.get('average_return') is not None else 0.0
            except (ValueError, TypeError):
                average_return = 0.0
                
            try:
                total_trades = int(backtest_data.get('total_trades', 0)) if backtest_data.get('total_trades') is not None else 0
            except (ValueError, TypeError):
                total_trades = 0
                
            try:
                total_profit = float(backtest_data.get('total_profit', 0)) if backtest_data.get('total_profit') is not None else 0.0
            except (ValueError, TypeError):
                total_profit = 0.0
                
            best_strategy = str(backtest_data.get('best_strategy', '')) if backtest_data.get('best_strategy') else 'unknown'
            worst_strategy = str(backtest_data.get('worst_strategy', '')) if backtest_data.get('worst_strategy') else 'unknown'
            
            params = {
                'judgment_id': int(judgment_id),
                'success_rate': success_rate,
                'average_return': average_return,
                'total_trades': total_trades,
                'total_profit': total_profit,
                'best_strategy': best_strategy,
                'worst_strategy': worst_strategy
            }
            
            self.cur.execute(backtest_query, params)
            result = self.cur.fetchone()
            
            if not result:
                raise Exception("バックテスト結果の挿入に失敗しました")
                
            backtest_id = result[0]
            
            # 戦略ごとの詳細情報をbacktest_strategy_detailsテーブルに挿入
            strategy_summary = backtest_data.get('strategy_summary', {})
            
            if not strategy_summary:
                self.logger.warning("戦略サマリーが空のため、詳細情報の保存をスキップします")
                self.conn.commit()
                return True
            
            strategy_query = """
            INSERT INTO backtest_strategy_details (
                backtest_id, strategy_name, win_count, loss_count,
                total_profit, avg_profit, trade_count,
                period_start, period_end
            ) VALUES (
                %(backtest_id)s, %(strategy_name)s, %(win_count)s, %(loss_count)s,
                %(total_profit)s, %(avg_profit)s, %(trade_count)s,
                %(period_start)s, %(period_end)s
            );
            """
            
            for strategy_name, details in strategy_summary.items():
                # 戦略詳細データの型を適切に変換
                try:
                    win_count = int(details.get('win_count', 0)) if details.get('win_count') is not None else 0
                except (ValueError, TypeError):
                    win_count = 0
                    
                try:
                    loss_count = int(details.get('loss_count', 0)) if details.get('loss_count') is not None else 0
                except (ValueError, TypeError):
                    loss_count = 0
                    
                try:
                    strategy_total_profit = float(details.get('total_profit', 0)) if details.get('total_profit') is not None else 0.0
                except (ValueError, TypeError):
                    strategy_total_profit = 0.0
                    
                try:
                    avg_profit = float(details.get('avg_profit', 0)) if details.get('avg_profit') is not None else 0.0
                except (ValueError, TypeError):
                    avg_profit = 0.0
                    
                try:
                    trade_count = int(details.get('trade_count', 0)) if details.get('trade_count') is not None else 0
                except (ValueError, TypeError):
                    trade_count = 0
                
                strategy_params = {
                    'backtest_id': backtest_id,
                    'strategy_name': str(strategy_name),
                    'win_count': win_count,
                    'loss_count': loss_count,
                    'total_profit': strategy_total_profit,
                    'avg_profit': avg_profit,
                    'trade_count': trade_count,
                    'period_start': None,  # 期間情報がない場合はNULL
                    'period_end': None
                }
                
                self.cur.execute(strategy_query, strategy_params)
                
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"バックテスト結果保存エラー: {e}")
            self.conn.rollback()
            return False
            
    def save_full_judgment_data(self, judgment_data: Dict, stock_data: Dict, 
                              backtest_data: Dict = None, processing_info: Dict = None) -> bool:
        """
        AIによる判断結果とバックテスト結果を一括で保存します
        
        Args:
            judgment_data (Dict): AIによる判断結果
            stock_data (Dict): 銘柄情報
            backtest_data (Dict, optional): バックテスト結果
            processing_info (Dict, optional): 処理情報
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            # トランザクション開始
            self.conn.autocommit = False
            
            # AI判断結果を保存
            judgment_id = self.save_ai_judgment(judgment_data, stock_data, processing_info)
            
            if not judgment_id:
                raise Exception("AI判断結果の保存に失敗しました")
                
            # バックテスト結果がある場合は保存
            if backtest_data:
                backtest_success = self.save_backtest_results(judgment_id, backtest_data)
                if not backtest_success:
                    raise Exception("バックテスト結果の保存に失敗しました")
            
            # すべて成功したらコミット
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"全データ保存エラー: {e}")
            self.conn.rollback()
            return False
        finally:
            # 自動コミットを戻す
            self.conn.autocommit = True 