import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, date
from .base_repository import BaseRepository
import logging

class EntryRepository(BaseRepository):
    def __init__(self):
        super().__init__()
        
    def fetch_best_entry_candidates(self, min_score: int = 700, limit: int = 400) -> List[Dict]:
        """
        エントリースコアが指定値以上のデータを一日辺りの期待リターンの降順で取得します
        また、すでに保有している証券（entries.status = 'active'）を除外します
        
        Args:
            min_score (int): 最小エントリースコア（デフォルト: 700）
            limit (int): 取得する最大件数（デフォルト: 400）
            
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

            # 環境変数 ENTRY_CANDIDATE_LIMIT が設定されている場合、その値を使用（int変換）
            env_limit = os.getenv("ENTRY_CANDIDATE_LIMIT")
            self.logger.info(f"ENTRY_CANDIDATE_LIMIT: {env_limit}")
            if env_limit is not None:
                try:
                    limit = int(env_limit)
                except ValueError:
                    self.logger.error(f"環境変数ENTRY_CANDIDATE_LIMITの値が数値に変換できません: {env_limit}. デフォルト値10を使用します。")
                    limit = 10

            query = """
            SELECT 
                a.code, a.date, a.close, a.rule_entry_price, a.rule_stop_limit,
                a.rule_top_price, a.rule_period, a.risk_reward, a.entry_score,
                a.expected_return, a.reason, a.entry_conditions, a.exit_conditions,
                a.short_term_trend, a.mid_term_trend, a.long_term_trend,
                a.support_resistance, a.technical_patterns, a.indicator_analysis,
                a.no_entry_span
            FROM api_response a
            WHERE a.entry_score >= %s
            AND NOT EXISTS (
                SELECT 1 FROM entries e 
                WHERE e.code = a.code 
                AND e.status = 'active'
            )
            ORDER BY CASE 
                WHEN a.rule_period ~ E'^\\d+$' AND CAST(a.rule_period AS INTEGER) > 0 
                THEN CAST(a.expected_return AS NUMERIC) / CAST(a.rule_period AS INTEGER) 
                ELSE 0 
            END DESC
            LIMIT %s;
            """
            
            self.cur.execute(query, (min_score, limit))
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
                'reason': row[10],
                'entry_conditions': row[11],
                'exit_conditions': row[12],
                'market_analysis': {
                    'short_term_trend': row[13],
                    'mid_term_trend': row[14],
                    'long_term_trend': row[15],
                    'support_resistance': row[16]
                },
                'technical_patterns': row[17],
                'indicator_analysis': row[18],
                'no_entry_span': row[19]
            } for row in rows]

        except Exception as e:
            self.logger.error(f"エントリー候補取得エラー: {e}")
            return []

    def save_entry_info(self, entry_data: Dict) -> bool:
        """
        エントリー情報をDBに保存します
        
        Args:
            entry_data (Dict): 保存するエントリー情報 (position を含む必要がある)
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            # entriesテーブルにデータを挿入
            query = """
            INSERT INTO entries (
                code, entry_date, entry_price, stop_loss,
                target_price, reason, holding_period,
                risk_reward, quantity, status,
                is_test, created_at, updated_at,
                position
            ) VALUES (
                %(code)s, %(entry_date)s, %(entry_price)s, %(stop_loss)s,
                %(target_price)s, %(reason)s, %(holding_period)s,
                %(risk_reward)s, %(quantity)s, %(status)s,
                %(is_test)s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                %(position)s
            );
            """
            
            # is_testのデフォルト値を設定
            if 'is_test' not in entry_data:
                entry_data['is_test'] = False
            
            # 現在の利用可能資金を取得
            current_funds = self.get_available_funds(test_mode=entry_data.get('is_test', False))
            
            # 購入コストを計算
            try:
                purchase_cost = float(entry_data['entry_price']) * float(entry_data['quantity'])
            except (ValueError, TypeError, KeyError) as e:
                self.logger.error(f"購入コスト計算エラー: {e} - entry_price: {entry_data.get('entry_price')}, quantity: {entry_data.get('quantity')}")
                return False
                
            # 新しい残高を計算
            new_available_funds = current_funds - purchase_cost
            
            # trade_resultsテーブルに購入記録を追加（資金残高の更新）
            trade_query = """
            INSERT INTO trade_results (
                trade_type, symbol_code, entry_datetime, entry_price,
                quantity, available_funds, is_test
            ) VALUES (
                'entry', %(code)s, CURRENT_TIMESTAMP, %(entry_price)s,
                %(quantity)s, %(new_available_funds)s, %(is_test)s
            );
            """
            
            trade_data = {
                **entry_data,
                'new_available_funds': new_available_funds
            }
            
            # トランザクション開始（明示的に）
            with self.conn:
                # entriesテーブルへのインサート
                self.cur.execute(query, entry_data)
                
                # trade_resultsテーブルへのインサート
                self.cur.execute(trade_query, trade_data)
                
                # トランザクションをコミット
                self.conn.commit()
                
            self.logger.info(f"エントリー情報を保存しました: {entry_data['code']} - 購入金額: {purchase_cost:,.0f}円, 残高: {new_available_funds:,.0f}円")
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
        AI判断、株価データ、バックテスト結果を一括で保存
        
        Args:
            judgment_data (Dict): AIによる判断結果
            stock_data (Dict): 対象銘柄の株価データ
            backtest_data (Dict, optional): バックテスト結果
            processing_info (Dict, optional): 処理情報
            
        Returns:
            bool: 保存成功でTrue
        """
        try:
            # トランザクション開始
            with self.conn:
                # AIジャッジメントの保存
                judgment_id = self.save_ai_judgment(judgment_data, stock_data, processing_info)
                if not judgment_id:
                    self.logger.error("AIジャッジメントの保存に失敗")
                    return False
                
                # バックテスト結果の保存
                if backtest_data:
                    if not self.save_backtest_results(judgment_id, backtest_data):
                        self.logger.error("バックテスト結果の保存に失敗")
                        return False
                        
                return True
                
        except Exception as e:
            self.logger.error(f"判断データの一括保存中にエラー: {e}")
            return False

    def get_active_entries(self, test_mode: bool = False) -> List[Dict]:
        """
        アクティブな（保有中の）エントリー情報を取得します
        
        Args:
            test_mode (bool): テストモードの場合True。テストモードの場合はテストデータのみ、
                            本番モードの場合は本番データのみを取得します。
                            デフォルトはFalse（本番モード）
        
        Returns:
            List[Dict]: アクティブなエントリー情報のリスト
        """
        try:
            query = """
            SELECT 
                code, entry_date, entry_price, stop_loss, target_price, 
                reason, holding_period, risk_reward, quantity, status,
                created_at, updated_at
            FROM 
                entries
            WHERE 
                status = 'active'
                AND is_test = %s
            ORDER BY 
                entry_date DESC;
            """
            
            self.cur.execute(query, (test_mode,))
            rows = self.cur.fetchall()
            
            if not rows:
                return []
                
            entries = []
            for row in rows:
                entries.append({
                    'code': row[0],
                    'entry_date': row[1],
                    'entry_price': row[2],
                    'stop_loss': row[3],
                    'target_price': row[4],
                    'reason': row[5],
                    'holding_period': row[6],
                    'risk_reward': row[7],
                    'quantity': row[8],
                    'status': row[9],
                    'created_at': row[10],
                    'updated_at': row[11]
                })
                
            return entries
            
        except Exception as e:
            self.logger.error(f"アクティブなエントリー取得中にエラー: {e}")
            return []

    def update_exit_info(self, code: str, entry_date: date, exit_data: Dict, is_test: bool = False) -> bool:
        """
        is_testパラメータの追加
        """
        try:
            query = """
            UPDATE entries
            SET 
                status = 'sold',
                exit_date = %s,
                exit_price = %s,
                profit = %s,
                profit_rate = %s,
                exit_reason = %s,
                updated_at = NOW()
            WHERE 
                code = %s AND entry_date = %s;
            """
            
            self.cur.execute(query, (
                exit_data['exit_date'],
                exit_data['exit_price'],
                exit_data['profit'],
                exit_data['profit_rate'],
                exit_data['exit_reason'],
                code,
                entry_date
            ))
            
            self.conn.commit()
            
            # 更新された行数を確認
            if self.cur.rowcount > 0:
                self.logger.info(f"エントリー {code} ({entry_date}) の売却情報を更新しました")
                return True
            else:
                self.logger.warning(f"エントリー {code} ({entry_date}) の更新に失敗しました（該当レコードなし）")
                return False
                
        except Exception as e:
            self.logger.error(f"売却情報更新中にエラー: {e}")
            self.conn.rollback()
            return False 

    def get_available_funds(self, test_mode: bool = False) -> float:
        """
        現在の買付余力（利用可能資金）を取得
        
        Args:
            test_mode (bool): テストモードの場合True。テストモードの場合はテストデータのみ、
                            本番モードの場合は本番データのみを取得します。
                            デフォルトはFalse（本番モード）
        
        Returns:
            float: 利用可能な現金（円）。取得できない場合は0
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT available_funds 
                        FROM trade_results 
                        WHERE is_test = %s
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """, (test_mode,))
                    result = cur.fetchone()
                    available_funds = float(result[0]) if result and result[0] is not None else 0
                    
                    if self.logger:
                        self.logger.debug(f"買付余力: {available_funds:,}円")
                        
                    return available_funds
                    
        except Exception as e:
            if self.logger:
                self.logger.error(f"買付余力の取得に失敗: {e}")
            return 0.0 

    def get_test_trade_history(self) -> List[Dict]:
        """
        テストモードでの取引履歴を取得します
        
        Returns:
            List[Dict]: 取引履歴のリスト。各要素は以下のキーを含む辞書:
                - trade_id: int (取引ID)
                - created_at: datetime (取引日時)
                - trade_type: str (取引種別: 'buy' or 'sell')
                - symbol_code: str (銘柄コード)
                - entry_price: float (取引価格)
                - quantity: int (取引数量)
                - profit_loss: float (損益 - 売却時のみ)
                - available_funds: float (取引後の利用可能資金)
        """
        try:
            query = """
            SELECT 
                tr.trade_id,
                tr.created_at,
                CASE 
                    WHEN e.status = 'active' THEN 'buy'
                    WHEN e.status = 'sold' THEN 'sell'
                END as trade_type,
                e.code as symbol_code,
                CASE 
                    WHEN e.status = 'active' THEN e.entry_price
                    WHEN e.status = 'sold' THEN e.exit_price
                END as entry_price,
                e.quantity,
                e.profit as profit_loss,
                tr.available_funds
            FROM 
                trade_results tr
                JOIN entries e ON tr.trade_id = e.trade_id
            WHERE 
                tr.is_test = true
            ORDER BY 
                tr.created_at DESC;
            """
            
            self.cur.execute(query)
            rows = self.cur.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'trade_id': row[0],
                    'created_at': row[1],
                    'trade_type': row[2],
                    'symbol_code': row[3],
                    'entry_price': float(row[4]) if row[4] is not None else 0.0,
                    'quantity': int(row[5]) if row[5] is not None else 0,
                    'profit_loss': float(row[6]) if row[6] is not None else 0.0,
                    'available_funds': float(row[7]) if row[7] is not None else 0.0
                })
            
            return history
            
        except Exception as e:
            self.logger.error(f"テスト取引履歴の取得に失敗: {e}")
            return [] 

    def get_test_summary(self) -> Dict:
        """
        テスト実行結果のサマリーを取得します
        
        Returns:
            Dict: テスト結果のサマリー情報を含む辞書:
                - initial_funds: float (初期資金)
                - current_funds: float (現在の資金)
                - total_profit: float (総損益)
                - trade_count: int (取引回数)
                - win_count: int (勝ち取引数)
                - test_start: datetime (テスト開始日時)
                - test_end: datetime (最終取引日時)
        """
        try:
            query = """
            WITH test_data AS (
                SELECT 
                    MIN(tr.created_at) as test_start,
                    MAX(tr.created_at) as test_end,
                    MIN(tr.available_funds) as initial_funds,
                    MAX(CASE WHEN tr.created_at = (SELECT MAX(created_at) FROM trade_results WHERE is_test = true)
                        THEN tr.available_funds END) as current_funds,
                    COUNT(DISTINCT e.trade_id) as trade_count,
                    COUNT(DISTINCT CASE WHEN e.profit > 0 THEN e.trade_id END) as win_count,
                    SUM(e.profit) as total_profit
                FROM 
                    trade_results tr
                    LEFT JOIN entries e ON tr.trade_id = e.trade_id
                WHERE 
                    tr.is_test = true
            )
            SELECT 
                COALESCE(initial_funds, 0) as initial_funds,
                COALESCE(current_funds, 0) as current_funds,
                COALESCE(total_profit, 0) as total_profit,
                COALESCE(trade_count, 0) as trade_count,
                COALESCE(win_count, 0) as win_count,
                test_start,
                test_end
            FROM 
                test_data;
            """
            
            self.cur.execute(query)
            row = self.cur.fetchone()
            
            if not row:
                return {
                    'initial_funds': 0.0,
                    'current_funds': 0.0,
                    'total_profit': 0.0,
                    'trade_count': 0,
                    'win_count': 0,
                    'test_start': None,
                    'test_end': None
                }
            
            return {
                'initial_funds': float(row[0]) if row[0] is not None else 0.0,
                'current_funds': float(row[1]) if row[1] is not None else 0.0,
                'total_profit': float(row[2]) if row[2] is not None else 0.0,
                'trade_count': int(row[3]) if row[3] is not None else 0,
                'win_count': int(row[4]) if row[4] is not None else 0,
                'test_start': row[5],
                'test_end': row[6]
            }
            
        except Exception as e:
            self.logger.error(f"テストサマリーの取得に失敗: {e}")
            return {
                'initial_funds': 0.0,
                'current_funds': 0.0,
                'total_profit': 0.0,
                'trade_count': 0,
                'win_count': 0,
                'test_start': None,
                'test_end': None
            } 

    def reset_test_data(self, initial_funds: float = 1000000.0) -> bool:
        """
        テストデータをリセットし、初期資金を設定
        既存のテストデータは履歴として保持
        
        Args:
            initial_funds (float): 初期資金（デフォルト: 1,000,000円）
            
        Returns:
            bool: リセット成功でTrue
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. アクティブなエントリーを履歴に保存してからクローズ
                    cur.execute("""
                        -- 1.1 現在のエントリーを履歴に保存
                        INSERT INTO entries_history (
                            trade_id, code, entry_date, entry_price, stop_loss,
                            target_price, reason, holding_period, risk_reward,
                            quantity, status, exit_date, exit_price, profit,
                            profit_rate, exit_reason, created_at, updated_at, is_test
                        )
                        SELECT 
                            trade_id, code, entry_date, entry_price, stop_loss,
                            target_price, reason, holding_period, risk_reward,
                            quantity, status, exit_date, exit_price, profit,
                            profit_rate, exit_reason, created_at, updated_at, is_test
                        FROM entries
                        WHERE is_test = true;

                        -- 1.2 アクティブなエントリーをクローズ
                        UPDATE entries 
                        SET status = 'closed',
                            exit_date = CURRENT_DATE,
                            exit_price = (
                                SELECT close 
                                FROM stock_prices sp
                                WHERE sp.code = entries.code 
                                AND sp.date = CURRENT_DATE
                            ),
                            profit = CASE 
                                WHEN quantity > 0 THEN 
                                    quantity * ((
                                        SELECT close 
                                        FROM stock_prices sp
                                        WHERE sp.code = entries.code 
                                        AND sp.date = CURRENT_DATE
                                    ) - entry_price)
                                ELSE 0
                            END,
                            profit_rate = CASE 
                                WHEN entry_price > 0 THEN 
                                    ((
                                        SELECT close 
                                        FROM stock_prices sp
                                        WHERE sp.code = entries.code 
                                        AND sp.date = CURRENT_DATE
                                    ) - entry_price) / entry_price * 100
                                ELSE 0
                            END,
                            exit_reason = 'System Reset',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE is_test = true AND status = 'active'
                        RETURNING code, exit_price, profit, profit_rate;
                    """)
                    
                    # 2. trade_resultsの処理
                    cur.execute("""
                        -- 2.1 現在のtrade_resultsを履歴に保存
                        INSERT INTO trade_results_history (
                            trade_id, created_at, updated_at, trade_type,
                            symbol_code, entry_datetime, close_datetime,
                            entry_price, close_price, quantity, profit_loss,
                            available_funds, fee, order_type, position,
                            strategy_id, note, is_test
                        )
                        SELECT 
                            trade_id, created_at, updated_at, trade_type,
                            symbol_code, entry_datetime, close_datetime,
                            entry_price, close_price, quantity, profit_loss,
                            available_funds, fee, order_type, position,
                            strategy_id, note, is_test
                        FROM trade_results
                        WHERE is_test = true;

                        -- 2.2 既存のテスト取引をクローズ
                        UPDATE trade_results
                        SET trade_type = 'close',
                            close_datetime = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE is_test = true AND trade_type = 'entry';

                        -- 2.3 新しい初期状態の作成
                        INSERT INTO trade_results (
                            trade_type,
                            symbol_code,
                            entry_price,
                            quantity,
                            profit_loss,
                            available_funds,
                            is_test,
                            position,
                            created_at,
                            updated_at
                        ) VALUES (
                            'entry',
                            '0000',
                            0,
                            0,
                            0,
                            %s,
                            true,
                            'long',
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                    """, (initial_funds,))
                    
                    conn.commit()
                    return True
                
        except Exception as e:
            self.logger.error(f"テストデータのリセットに失敗: {e}")
            return False

    def save_test_trade_result(self, trade_data: Dict) -> bool:
        """
        テストモードでのトレード結果保存
        """
        try:
            query = """
            INSERT INTO trade_results (
                trade_type,
                symbol_code,
                entry_price,
                quantity,
                profit_loss,
                available_funds,
                is_test,
                position
            ) VALUES (
                %(trade_type)s,
                %(symbol_code)s,
                %(entry_price)s,
                %(quantity)s,
                %(profit_loss)s,
                %(available_funds)s,
                %(is_test)s,
                %(position)s
            );
            """
            
            self.cur.execute(query, trade_data)
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"テストトレード結果保存エラー: {e}")
            self.conn.rollback()
            return False 

    def fetch_entry_candidates_with_holdings(self, min_score: int = 700, limit: int = 400) -> List[Dict]:
        """
        エントリースコアが指定値以上のデータを一日辺りの期待リターンの降順で取得します
        保有中の銘柄も含めて取得します（買い増し許可モード）
        
        Args:
            min_score (int): 最小エントリースコア（デフォルト: 700）
            limit (int): 取得する最大件数（デフォルト: 400）
            
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

            # 環境変数 ENTRY_CANDIDATE_LIMIT が設定されている場合、その値を使用（int変換）
            env_limit = os.getenv("ENTRY_CANDIDATE_LIMIT")
            self.logger.info(f"ENTRY_CANDIDATE_LIMIT: {env_limit}")
            if env_limit is not None:
                try:
                    limit = int(env_limit)
                except ValueError:
                    self.logger.error(f"環境変数ENTRY_CANDIDATE_LIMITの値が数値に変換できません: {env_limit}. デフォルト値10を使用します。")
                    limit = 10

            # 既存のSQLから保有銘柄除外の条件を削除したクエリ
            query = """
            SELECT 
                a.code, a.date, a.close, a.rule_entry_price, a.rule_stop_limit,
                a.rule_top_price, a.rule_period, a.risk_reward, a.entry_score,
                a.expected_return, a.reason, a.entry_conditions, a.exit_conditions,
                a.short_term_trend, a.mid_term_trend, a.long_term_trend,
                a.support_resistance, a.technical_patterns, a.indicator_analysis,
                a.no_entry_span,
                CASE WHEN e.code IS NOT NULL THEN TRUE ELSE FALSE END AS is_holding
            FROM api_response a
            LEFT JOIN entries e ON a.code = e.code AND e.status = 'active'
            WHERE a.entry_score >= %s
            ORDER BY CASE 
                WHEN a.rule_period ~ E'^\\d+$' AND CAST(a.rule_period AS INTEGER) > 0 
                THEN CAST(a.expected_return AS NUMERIC) / CAST(a.rule_period AS INTEGER) 
                ELSE 0 
            END DESC
            LIMIT %s;
            """
            
            self.cur.execute(query, (min_score, limit))
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
                'reason': row[10],
                'entry_conditions': row[11],
                'exit_conditions': row[12],
                'market_analysis': {
                    'short_term_trend': row[13],
                    'mid_term_trend': row[14],
                    'long_term_trend': row[15],
                    'support_resistance': row[16]
                },
                'technical_patterns': row[17],
                'indicator_analysis': row[18],
                'no_entry_span': row[19],
                'is_holding': row[20] if len(row) > 20 else False
            } for row in rows]

        except Exception as e:
            self.logger.error(f"エントリー候補取得エラー（保有銘柄含む）: {e}")
            return []

    def get_current_holdings(self, is_test: bool = False) -> List[Dict]:
        """
        現在保有中の銘柄情報を取得します
        
        Args:
            is_test (bool): テストモードかどうか
            
        Returns:
            List[Dict]: 保有銘柄情報のリスト
        """
        try:
            query = """
            SELECT 
                code, entry_date, entry_price, stop_loss, target_price,
                holding_period, risk_reward, quantity, status
            FROM entries
            WHERE status = 'active' AND is_test = %s
            """
            
            self.cur.execute(query, (is_test,))
            rows = self.cur.fetchall()
            
            return [{
                'code': row[0],
                'entry_date': row[1],
                'entry_price': row[2],
                'stop_loss': row[3],
                'target_price': row[4],
                'holding_period': row[5],
                'risk_reward': row[6], 
                'quantity': row[7],
                'status': row[8]
            } for row in rows]
            
        except Exception as e:
            self.logger.error(f"保有銘柄情報取得エラー: {e}")
            return [] 

    def analyze_test_trading_history(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict:
        """
        テストトレードの履歴を分析し、パフォーマンスメトリクスを計算
        
        Args:
            start_date (date, optional): 分析開始日
            end_date (date, optional): 分析終了日
            
        Returns:
            Dict: 分析結果
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        WITH closed_trades AS (
                            SELECT 
                                h.code,
                                h.entry_date,
                                h.exit_date,
                                h.entry_price,
                                h.exit_price,
                                h.quantity,
                                h.profit,
                                h.profit_rate,
                                h.exit_reason,
                                h.archived_at
                            FROM entries_history h
                            WHERE h.is_test = true
                            AND h.status = 'closed'
                            AND (h.entry_date >= %s OR %s IS NULL)
                            AND (h.exit_date <= %s OR %s IS NULL)
                        )
                        SELECT 
                            COUNT(*) as total_trades,
                            COUNT(CASE WHEN profit > 0 THEN 1 END) as winning_trades,
                            COUNT(CASE WHEN profit <= 0 THEN 1 END) as losing_trades,
                            ROUND(AVG(profit)::numeric, 2) as avg_profit,
                            ROUND(AVG(profit_rate)::numeric, 2) as avg_profit_rate,
                            ROUND(MAX(profit)::numeric, 2) as max_profit,
                            ROUND(MIN(profit)::numeric, 2) as max_loss,
                            ROUND(SUM(profit)::numeric, 2) as total_profit,
                            ROUND(AVG(CASE WHEN profit > 0 THEN profit END)::numeric, 2) as avg_win,
                            ROUND(AVG(CASE WHEN profit < 0 THEN profit END)::numeric, 2) as avg_loss,
                            ROUND(AVG(EXTRACT(DAY FROM (exit_date - entry_date)))::numeric, 2) as avg_holding_days,
                            json_agg(DISTINCT exit_reason) as exit_reasons
                        FROM closed_trades
                    """, (start_date, start_date, end_date, end_date))
                    
                    metrics = cur.fetchone()
                    
                    # 月次パフォーマンスの取得
                    cur.execute("""
                        SELECT 
                            DATE_TRUNC('month', exit_date) as month,
                            COUNT(*) as trades,
                            ROUND(SUM(profit)::numeric, 2) as monthly_profit,
                            ROUND(AVG(profit_rate)::numeric, 2) as avg_profit_rate
                        FROM closed_trades
                        GROUP BY DATE_TRUNC('month', exit_date)
                        ORDER BY month
                    """)
                    monthly_performance = cur.fetchall()
                    
                    return {
                        "summary": {
                            "total_trades": metrics[0],
                            "winning_trades": metrics[1],
                            "losing_trades": metrics[2],
                            "win_rate": round(metrics[1] / metrics[0] * 100, 2) if metrics[0] > 0 else 0,
                            "avg_profit": metrics[3],
                            "avg_profit_rate": metrics[4],
                            "max_profit": metrics[5],
                            "max_loss": metrics[6],
                            "total_profit": metrics[7],
                            "profit_factor": abs(metrics[8] / metrics[9]) if metrics[9] else 0,
                            "avg_holding_days": metrics[10],
                            "exit_reasons": metrics[11]
                        },
                        "monthly_performance": [
                            {
                                "month": month,
                                "trades": trades,
                                "profit": profit,
                                "avg_profit_rate": rate
                            } for month, trades, profit, rate in monthly_performance
                        ]
                    }
                    
        except Exception as e:
            self.logger.error(f"テストトレード分析エラー: {e}")
            return {}

    def get_test_reset_history(self, limit: int = 10) -> List[Dict]:
        """
        テストモードのリセット履歴を取得
        
        Args:
            limit (int): 取得する履歴の数
            
        Returns:
            List[Dict]: リセット履歴のリスト
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        WITH reset_points AS (
                            SELECT 
                                archived_at as reset_time,
                                COUNT(*) as closed_positions,
                                ROUND(SUM(profit)::numeric, 2) as total_profit,
                                ROUND(AVG(profit_rate)::numeric, 2) as avg_profit_rate
                            FROM entries_history
                            WHERE is_test = true 
                            AND exit_reason = 'System Reset'
                            GROUP BY archived_at
                            ORDER BY archived_at DESC
                            LIMIT %s
                        ),
                        funds_history AS (
                            SELECT 
                                archived_at,
                                available_funds as initial_funds
                            FROM trade_results_history
                            WHERE is_test = true 
                            AND symbol_code = '0000'
                            AND trade_type = 'entry'
                        )
                        SELECT 
                            r.reset_time,
                            r.closed_positions,
                            r.total_profit,
                            r.avg_profit_rate,
                            f.initial_funds
                        FROM reset_points r
                        LEFT JOIN funds_history f 
                        ON DATE_TRUNC('second', r.reset_time) = DATE_TRUNC('second', f.archived_at)
                        ORDER BY r.reset_time DESC
                    """, (limit,))
                    
                    results = cur.fetchall()
                    return [{
                        "reset_time": row[0],
                        "closed_positions": row[1],
                        "total_profit": row[2],
                        "avg_profit_rate": row[3],
                        "initial_funds": row[4]
                    } for row in results]
                    
        except Exception as e:
            self.logger.error(f"リセット履歴取得エラー: {e}")
            return []

    def generate_test_performance_report(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict:
        """
        テストトレードのパフォーマンスレポートを生成
        
        Args:
            start_date (date, optional): レポート開始日
            end_date (date, optional): レポート終了日
            
        Returns:
            Dict: パフォーマンスレポート
        """
        try:
            # 基本的なパフォーマンス指標を取得
            performance_metrics = self.analyze_test_trading_history(start_date, end_date)
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # 業種別パフォーマンス
                    cur.execute("""
                        SELECT 
                            c.industry_name,
                            COUNT(*) as trades,
                            ROUND(AVG(h.profit_rate)::numeric, 2) as avg_profit_rate,
                            ROUND(SUM(h.profit)::numeric, 2) as total_profit
                        FROM entries_history h
                        JOIN companies c ON h.code = c.code
                        WHERE h.is_test = true
                        AND h.status = 'closed'
                        AND (h.entry_date >= %s OR %s IS NULL)
                        AND (h.exit_date <= %s OR %s IS NULL)
                        GROUP BY c.industry_name
                        ORDER BY total_profit DESC
                    """, (start_date, start_date, end_date, end_date))
                    industry_performance = cur.fetchall()
                    
                    # 保有期間別パフォーマンス
                    cur.execute("""
                        WITH holding_periods AS (
                            SELECT 
                                CASE 
                                    WHEN EXTRACT(DAY FROM (exit_date - entry_date)) <= 5 THEN '5日以内'
                                    WHEN EXTRACT(DAY FROM (exit_date - entry_date)) <= 10 THEN '6-10日'
                                    WHEN EXTRACT(DAY FROM (exit_date - entry_date)) <= 20 THEN '11-20日'
                                    ELSE '21日以上'
                                END as period_range,
                                profit,
                                profit_rate
                            FROM entries_history
                            WHERE is_test = true
                            AND status = 'closed'
                            AND (entry_date >= %s OR %s IS NULL)
                            AND (exit_date <= %s OR %s IS NULL)
                        )
                        SELECT 
                            period_range,
                            COUNT(*) as trades,
                            ROUND(AVG(profit_rate)::numeric, 2) as avg_profit_rate,
                            ROUND(SUM(profit)::numeric, 2) as total_profit
                        FROM holding_periods
                        GROUP BY period_range
                        ORDER BY 
                            CASE period_range
                                WHEN '5日以内' THEN 1
                                WHEN '6-10日' THEN 2
                                WHEN '11-20日' THEN 3
                                ELSE 4
                            END
                    """, (start_date, start_date, end_date, end_date))
                    holding_period_performance = cur.fetchall()
                    
                    return {
                        "summary": performance_metrics["summary"],
                        "monthly_performance": performance_metrics["monthly_performance"],
                        "industry_performance": [{
                            "industry": row[0],
                            "trades": row[1],
                            "avg_profit_rate": row[2],
                            "total_profit": row[3]
                        } for row in industry_performance],
                        "holding_period_performance": [{
                            "period_range": row[0],
                            "trades": row[1],
                            "avg_profit_rate": row[2],
                            "total_profit": row[3]
                        } for row in holding_period_performance]
                    }
                    
        except Exception as e:
            self.logger.error(f"パフォーマンスレポート生成エラー: {e}")
            return {} 