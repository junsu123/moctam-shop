/* Trang quản trị — tiện ích nhỏ, không phụ thuộc thư viện. */
(function () {
  'use strict';
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var t = document.querySelector('[data-nav-toggle]');
  if (t) t.addEventListener('click', function () {
    var n = document.getElementById('admin-nav');
    var open = n.classList.toggle('hidden') === false;
    t.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  // Xác nhận trước thao tác không hoàn tác được
  $$('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!window.confirm(f.getAttribute('data-confirm'))) e.preventDefault(); });
  });

  // Hiện ô nhập phụ theo lựa chọn (VD: lý do hủy, mã vận đơn)
  $$('[data-reveal]').forEach(function (sel) {
    var sync = function () {
      $$('[data-reveal-for="' + sel.name + '"]').forEach(function (box) {
        var show = box.getAttribute('data-reveal-when').split(',').indexOf(sel.value) >= 0;
        box.classList.toggle('hidden', !show);
      });
    };
    sel.addEventListener('change', sync); sync();
  });

  // Phạm vi voucher
  $$('[data-scope-type]').forEach(function (sel) {
    var sync = function () {
      $$('[data-scope-box]').forEach(function (b) { b.classList.toggle('hidden', b.getAttribute('data-scope-box') !== sel.value); });
    };
    sel.addEventListener('change', sync); sync();
  });

  // Thêm dòng SKU vào Flash Sale
  var add = document.querySelector('[data-fs-add]');
  if (add) add.addEventListener('click', function () {
    var tpl = document.querySelector('[data-fs-template]');
    var row = tpl.content.cloneNode(true);
    document.querySelector('[data-fs-rows]').appendChild(row);
  });
  document.addEventListener('click', function (e) {
    var rm = e.target.closest('[data-fs-remove]');
    if (rm) rm.closest('[data-fs-row]').remove();
  });

  // Gửi bộ lọc khi đổi lựa chọn
  $$('[data-autosubmit]').forEach(function (s) { s.addEventListener('change', function () { s.form.submit(); }); });

  // Nhóm menu: nhớ nhóm đang gập bằng cookie để máy chủ vẽ đúng ngay lần tải sau (không nhấp nháy)
  $$('[data-navgroup]').forEach(function (d) {
    d.addEventListener('toggle', function () {
      var closed = $$('[data-navgroup]').filter(function (x) { return !x.open; }).map(function (x) { return x.getAttribute('data-navgroup'); });
      document.cookie = 'a_nav=' + closed.join(',') + '; path=/admin; max-age=31536000; SameSite=Lax';
    });
  });

  // Phím "/" → ô tìm nhanh (trừ khi đang gõ trong ô khác)
  var quick = document.querySelector('[data-quick-search]');
  document.addEventListener('keydown', function (e) {
    if (!quick || e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || (document.activeElement && document.activeElement.isContentEditable)) return;
    e.preventDefault(); quick.focus(); quick.select();
  });

  // Đóng thông báo
  document.addEventListener('click', function (e) {
    var x = e.target.closest('[data-dismiss]');
    if (x) x.closest('[data-flash]').remove();
  });

  // Bấm vào cả dòng để mở chi tiết; Ctrl/⌘ hoặc chuột giữa → tab mới. Liên kết, nút, ô nhập trong dòng vẫn hoạt động riêng.
  var rowGo = function (e) {
    var tr = e.target.closest('tr[data-href]');
    if (!tr || e.target.closest('a, button, input, select, textarea, label, summary, details')) return;
    if (window.getSelection && String(window.getSelection()).length > 0) return; // đang bôi đen để sao chép
    var href = tr.getAttribute('data-href');
    if (e.ctrlKey || e.metaKey || e.button === 1) window.open(href, '_blank', 'noopener');
    else window.location.href = href;
  };
  document.addEventListener('click', rowGo);
  document.addEventListener('auxclick', function (e) { if (e.button === 1) rowGo(e); });

  // Xử lý đơn: chọn thao tác → hiện ô cần nhập, đổi nhãn và màu nút cho đúng việc sẽ làm
  $$('form[data-transition]').forEach(function (f) {
    var btn = f.querySelector('[data-transition-submit]');
    var reasonBox = f.querySelector('[data-reason-box]');
    var sync = function () {
      var r = f.querySelector('input[name="to"]:checked');
      $$('[data-show-for]', f).forEach(function (box) {
        box.classList.toggle('hidden', !r || box.getAttribute('data-show-for').split(',').indexOf(r.value) < 0);
      });
      if (!r) { btn.disabled = true; btn.textContent = 'Chọn thao tác'; return; }
      var danger = r.getAttribute('data-danger') === '1';
      btn.disabled = false;
      btn.textContent = r.getAttribute('data-action');
      btn.classList.toggle('btn-danger', danger);
      btn.classList.toggle('btn-primary', !danger);
      if (reasonBox) {
        var reason = reasonBox.querySelector('textarea');
        reason.required = danger;
        reasonBox.querySelector('[data-reason-label]').textContent = danger ? 'Lý do (bắt buộc)' : 'Ghi chú (không bắt buộc)';
      }
    };
    $$('input[name="to"]', f).forEach(function (r) { r.addEventListener('change', sync); });
    sync();
  });

  // Bộ lọc phụ: gập trên điện thoại, luôn mở trên màn hình rộng
  if (window.matchMedia && window.matchMedia('(min-width: 640px)').matches) {
    $$('details[data-open-desktop]').forEach(function (d) { d.open = true; });
  }

  // Gập/mở biểu mẫu trong dòng (VD: nhập kho) — đặt con trỏ vào ô đầu tiên khi mở
  var inline = $$('details[data-inline-form]');
  inline.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (!d.open) return;
      inline.forEach(function (o) { if (o !== d) o.open = false; }); // mỗi lần chỉ mở một biểu mẫu
      var i = d.querySelector('input[type=number], input[type=text], input:not([type]), select'); if (i) i.focus();
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    inline.forEach(function (d) { if (d.open) { d.open = false; d.querySelector('summary').focus(); } });
  });
  document.addEventListener('click', function (e) {
    inline.forEach(function (d) { if (d.open && !d.contains(e.target)) d.open = false; });
  });
})();
