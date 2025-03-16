from dataclasses import dataclass
from typing import Optional

@dataclass
class EvaluationResult:
    """保有株式の評価結果を表すデータクラス"""
    code: str
    decision: str  # "HOLD" or "SELL"
    confidence_score: int  # 0-1000
    reason: str
    stop_loss: Optional[str]  # 価格 or "NG"
    target_price: Optional[str]  # 価格 or "NG"
    stop_loss_update_reason: Optional[str] = None  # ストップロス更新理由
    target_update_reason: Optional[str] = None  # 目標価格更新理由

    @classmethod
    def from_dict(cls, code: str, data: dict) -> 'EvaluationResult':
        """辞書形式のデータからインスタンスを生成"""
        return cls(
            code=code,
            decision=data.get('decision', 'HOLD'),
            confidence_score=int(data.get('confidence_score', 0)),
            reason=data.get('reason', ''),
            stop_loss=data.get('stop_loss', 'NG'),
            target_price=data.get('target_price', 'NG'),
            stop_loss_update_reason=data.get('stop_loss_update_reason'),
            target_update_reason=data.get('target_update_reason')
        )

    def to_dict(self) -> dict:
        """辞書形式にデータを変換"""
        return {
            'code': self.code,
            'decision': self.decision,
            'confidence_score': self.confidence_score,
            'reason': self.reason,
            'stop_loss': self.stop_loss,
            'target_price': self.target_price,
            'stop_loss_update_reason': self.stop_loss_update_reason,
            'target_update_reason': self.target_update_reason
        } 