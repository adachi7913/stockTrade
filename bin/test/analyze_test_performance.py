#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import argparse
from datetime import datetime, date
from typing import Optional
import json
from rich.console import Console
from rich.table import Table
from rich import box
from repository.entry_repository import EntryRepository

def parse_date(date_str: str) -> Optional[date]:
    """日付文字列をdateオブジェクトに変換"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

def format_money(amount: float) -> str:
    """金額を見やすい形式に整形"""
    return f"¥{amount:,.0f}"

def create_summary_table(data: dict) -> Table:
    """サマリー情報のテーブルを作成"""
    table = Table(title="テストトレード サマリー", box=box.ROUNDED)
    
    table.add_column("項目", style="cyan")
    table.add_column("値", justify="right")
    
    table.add_row("総取引数", str(data["total_trades"]))
    table.add_row("勝率", f"{data['win_rate']}%")
    table.add_row("平均利益", format_money(data["avg_profit"]))
    table.add_row("平均利益率", f"{data['avg_profit_rate']}%")
    table.add_row("最大利益", format_money(data["max_profit"]))
    table.add_row("最大損失", format_money(data["max_loss"]))
    table.add_row("総利益", format_money(data["total_profit"]))
    table.add_row("平均保有日数", f"{data['avg_holding_days']}日")
    
    return table

def create_industry_table(data: list) -> Table:
    """業種別パフォーマンスのテーブルを作成"""
    table = Table(title="業種別パフォーマンス", box=box.ROUNDED)
    
    table.add_column("業種", style="cyan")
    table.add_column("取引数", justify="right")
    table.add_column("平均利益率", justify="right")
    table.add_column("総利益", justify="right")
    
    for row in data:
        table.add_row(
            row["industry"],
            str(row["trades"]),
            f"{row['avg_profit_rate']}%",
            format_money(row["total_profit"])
        )
    
    return table

def create_holding_period_table(data: list) -> Table:
    """保有期間別パフォーマンスのテーブルを作成"""
    table = Table(title="保有期間別パフォーマンス", box=box.ROUNDED)
    
    table.add_column("期間", style="cyan")
    table.add_column("取引数", justify="right")
    table.add_column("平均利益率", justify="right")
    table.add_column("総利益", justify="right")
    
    for row in data:
        table.add_row(
            row["period_range"],
            str(row["trades"]),
            f"{row['avg_profit_rate']}%",
            format_money(row["total_profit"])
        )
    
    return table

def create_monthly_table(data: list) -> Table:
    """月次パフォーマンスのテーブルを作成"""
    table = Table(title="月次パフォーマンス", box=box.ROUNDED)
    
    table.add_column("月", style="cyan")
    table.add_column("取引数", justify="right")
    table.add_column("総利益", justify="right")
    table.add_column("平均利益率", justify="right")
    
    for row in data:
        month_str = row["month"].strftime("%Y-%m")
        table.add_row(
            month_str,
            str(row["trades"]),
            format_money(row["profit"]),
            f"{row['avg_profit_rate']}%"
        )
    
    return table

def main():
    parser = argparse.ArgumentParser(description='テストトレードのパフォーマンス分析')
    parser.add_argument('--start-date', help='分析開始日 (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='分析終了日 (YYYY-MM-DD)')
    parser.add_argument('--reset-history', action='store_true', help='リセット履歴を表示')
    parser.add_argument('--json', action='store_true', help='JSON形式で出力')
    parser.add_argument('--save', help='分析結果をJSONファイルとして保存')
    
    args = parser.parse_args()
    
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    
    repository = EntryRepository()
    console = Console()
    
    # リセット履歴の表示
    if args.reset_history:
        reset_history = repository.get_test_reset_history()
        if args.json:
            print(json.dumps(reset_history, default=str, indent=2, ensure_ascii=False))
            return
            
        table = Table(title="テストモード リセット履歴", box=box.ROUNDED)
        table.add_column("リセット日時", style="cyan")
        table.add_column("クローズドポジション数", justify="right")
        table.add_column("総利益", justify="right")
        table.add_column("平均利益率", justify="right")
        table.add_column("初期資金", justify="right")
        
        for reset in reset_history:
            table.add_row(
                reset["reset_time"].strftime("%Y-%m-%d %H:%M:%S"),
                str(reset["closed_positions"]),
                format_money(reset["total_profit"]),
                f"{reset['avg_profit_rate']}%",
                format_money(reset["initial_funds"])
            )
        
        console.print(table)
        return
    
    # パフォーマンスレポートの生成
    report = repository.generate_test_performance_report(start_date, end_date)
    
    if args.json or args.save:
        json_data = json.dumps(report, default=str, indent=2, ensure_ascii=False)
        if args.save:
            with open(args.save, 'w', encoding='utf-8') as f:
                f.write(json_data)
            print(f"分析結果を {args.save} に保存しました。")
        if args.json:
            print(json_data)
        return
    
    # リッチテキスト形式での表示
    console.print(create_summary_table(report["summary"]))
    console.print()
    console.print(create_monthly_table(report["monthly_performance"]))
    console.print()
    console.print(create_industry_table(report["industry_performance"]))
    console.print()
    console.print(create_holding_period_table(report["holding_period_performance"]))

if __name__ == "__main__":
    main() 