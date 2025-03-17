from dataclasses import dataclass
from typing import Optional

@dataclass
class EvaluationResult:
    """保有株式の評価結果を表すデータクラス"""
    code: str
    decision: str  # "HOLD" or "SELL"
    confidence_score: int  # 0-1000
    reason: str
    stop_loss: str
    target_price: str
    close: Optional[str] = None
    stop_loss_update_reason: Optional[str] = None  # ストップロス更新理由
    target_update_reason: Optional[str] = None  # 目標価格更新理由

    def __init__(self, code: str, decision: str, confidence_score: int, 
                 reason: str, stop_loss: str, target_price: str, close: str = None):
        self.code = code
        self.decision = decision
        self.confidence_score = confidence_score
        self.reason = reason
        self.stop_loss = stop_loss
        self.target_price = target_price
        self.close = close  # 現在値を追加
        self.stop_loss_update_reason = None
        self.target_update_reason = None

    @classmethod
    def from_dict(cls, code: str, data: dict) -> 'EvaluationResult':
        """辞書形式のデータからインスタンスを生成"""
        return cls(
            code=code,
            decision=data.get('decision', 'HOLD'),
            confidence_score=data.get('confidence_score', 0),
            reason=data.get('reason', ''),
            stop_loss=data.get('stop_loss', 'NG'),
            target_price=data.get('target_price', 'NG'),
            close=data.get('close', None)  # closeを追加
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
            'close': self.close,
            'stop_loss_update_reason': self.stop_loss_update_reason,
            'target_update_reason': self.target_update_reason
        } 