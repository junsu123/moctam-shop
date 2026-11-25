"""BM25 Python phải cho điểm GIỐNG HỆT bản PHP trên website (để ngưỡng hiệu chỉnh dùng chung)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from xuong_ai import textnorm

WEB = Path(__file__).resolve().parents[2] / "web"
DOCS = {1: "Phí giao hàng được tính thế nào? theo vùng Hà Nội", 2: "Cách pha trà gừng mật ong ngon", 3: "Chính sách đổi trả hàng lỗi, hoàn tiền",
        4: "Cà phê Robusta rang mộc đậm đà pha phin", 5: "Bột ngũ cốc 25 loại hạt cho trẻ em"}
QUERIES = ["phi ship tinh the nao", "Trà gừng pha sao ạ?", "cafe robusta co tam khong", "đổi trả hàng lỗi", "ngũ cốc bé uống được ko", "Đặc sản Đà Lạt"]


def test_fold():
    assert textnorm.fold("Trà Gừng – Mật Ong ĐẶC BIỆT!") == "tra gung mat ong dac biet"
    assert textnorm.terms("ship cod ko") == ["giao", "cod", "khong", "giao_cod", "cod_khong"]


@pytest.mark.skipif(not shutil.which("php") or not (WEB / "app/src/Domain/Bm25.php").exists(), reason="cần PHP và mã website")
def test_same_scores_as_php():
    php = f"""
    namespace App\\Core {{ require '{WEB}/app/src/Core/Text.php'; }}
    namespace {{ require '{WEB}/app/src/Domain/Bm25.php';
      $docs = json_decode('{json.dumps(DOCS, ensure_ascii=False)}', true); $out = [];
      foreach (json_decode('{json.dumps(QUERIES, ensure_ascii=False)}', true) as $q) {{ $out[$q] = App\\Domain\\Bm25::rank($q, $docs); }}
      echo json_encode($out); }}
    """
    res = json.loads(subprocess.run(["php", "-r", php], capture_output=True, text=True, check=True).stdout)
    for q in QUERIES:
        py = {str(k): v for k, v in textnorm.rank(q, DOCS)}
        ph = {str(k): v for k, v in (res[q] or {}).items()}
        assert py.keys() == ph.keys(), q
        for k in py:
            assert abs(py[k] - ph[k]) < 1e-9, (q, k, py[k], ph[k])
