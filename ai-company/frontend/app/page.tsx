import { SystemStatus } from "./system-status";

export default function Home() {
  return (
    <main className="shell">
      <header className="head">
        <div>
          <h1>Trung tâm điều hành</h1>
          <p>AI Marketing Company của xưởng</p>
        </div>
        <p className="sprint">
          <b>Sprint 0</b>
          Khung hệ thống
        </p>
      </header>

      <section className="panel" aria-labelledby="sys-h">
        <h2 id="sys-h">Tình trạng hệ thống</h2>
        <SystemStatus />
      </section>

      <section className="panel" aria-labelledby="next-h">
        <h2 id="next-h">Sprint 1 sẽ thêm vào trang này</h2>
        <ul className="next">
          <li>Đăng nhập cho Owner, có xác thực hai lớp</li>
          <li>Cài đặt Telegram: dán token bot, kết nối điện thoại bằng mã 6 số</li>
          <li>Ngân sách LLM: trần ngày và tháng, cảnh báo khi đạt 80%</li>
          <li>Danh sách agent với nút tạm dừng và chạy lại</li>
          <li>Màn hình diễn biến trực tiếp</li>
        </ul>
      </section>

      <p className="foot">Trang chỉ mở được trên máy này (127.0.0.1).</p>
    </main>
  );
}
