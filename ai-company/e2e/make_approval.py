"""Chỉ dùng trong E2E: cho Giám đốc Tăng trưởng xin chạy thí nghiệm trên trang thật (luôn cần duyệt) qua Tool Gateway thật."""

import asyncio

from app.core import db
from app.tools.gateway import invoke


async def main() -> None:
    async with db.engine().connect() as c:
        r = await invoke(c, agent_key="growth_director", tool_id="experiment", action="launch_live",
                         input={"page": "/san-pham/tra-sen", "variant": "nút mua to hơn"}, idempotency_key="e2e-exp-1")
    await db.dispose()
    print(r.status, r.approval_id)


asyncio.run(main())
