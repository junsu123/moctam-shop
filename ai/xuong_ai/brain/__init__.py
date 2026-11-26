"""Bộ não "Trưởng văn phòng" của văn phòng AI chăm sóc website.

Vòng làm việc mỗi nhịp: Cảm nhận (senses) → Cân nhắc theo mục tiêu và nội quy (planner) → Giao việc cho nhân viên (core)
→ Học từ kết quả duyệt (learning) → Báo cáo (brief). Sổ sách lưu trong SQLite cục bộ (state).
Xem docs/VAN-PHONG-AI.md.
"""
from .core import Brain

__all__ = ["Brain"]
