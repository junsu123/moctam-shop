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
})();
