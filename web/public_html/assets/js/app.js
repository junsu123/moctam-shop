/* Cửa hàng — JavaScript thuần, không phụ thuộc thư viện.
 * Giỏ hàng chỉ lưu SKU + số lượng trong LocalStorage; giá và khả năng bán do máy chủ quyết định. */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var CSRF = ($('meta[name="csrf-token"]') || {}).content || '';
  var fmt = function (n) { return new Intl.NumberFormat('vi-VN').format(n) + ' ₫'; };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };

  // ------------------------------------------------------------------ lưu trữ an toàn
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* trình duyệt chặn lưu trữ */ } },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) {} }
  };
  var ss = {
    get: function (k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { sessionStorage.setItem(k, v); } catch (e) {} },
    del: function (k) { try { sessionStorage.removeItem(k); } catch (e) {} }
  };

  // ------------------------------------------------------------------ giỏ hàng
  var Cart = {
    KEY: 'xuong_cart_v1',
    items: function () { return store.get(this.KEY, []).filter(function (i) { return i && i.sku_id > 0 && i.qty > 0; }); },
    save: function (items) { store.set(this.KEY, items); Cart.badge(); },
    add: function (skuId, qty, meta) {
      var items = this.items(), found = false;
      items.forEach(function (i) { if (i.sku_id === skuId) { i.qty = Math.min(99, i.qty + qty); found = true; } });
      if (!found) items.push({ sku_id: skuId, qty: Math.min(99, qty), name: meta && meta.name, label: meta && meta.label });
      this.save(items);
    },
    setQty: function (skuId, qty) { this.save(this.items().map(function (i) { if (i.sku_id === skuId) i.qty = Math.max(1, Math.min(99, qty)); return i; })); },
    remove: function (skuId) { this.save(this.items().filter(function (i) { return i.sku_id !== skuId; })); },
    clear: function () { store.del(this.KEY); Cart.badge(); },
    count: function () { return this.items().reduce(function (s, i) { return s + i.qty; }, 0); },
    badge: function () { $$('[data-cart-count]').forEach(function (b) { b.textContent = Cart.count(); }); }
  };
  var prefs = {
    get: function () { return store.get('xuong_checkout_prefs', {}); },
    set: function (patch) { var p = prefs.get(); for (var k in patch) p[k] = patch[k]; store.set('xuong_checkout_prefs', p); }
  };

  function toast(msg) {
    var t = $('[data-toast]'); if (!t) return;
    t.innerHTML = '<div class="pointer-events-auto rounded-lg bg-ink px-4 py-3 text-sm font-semibold text-white shadow-lg">' + esc(msg) + '</div>';
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.innerHTML = ''; }, 2600);
  }

  function api(path, body, headers) {
    var h = { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-Token': CSRF };
    for (var k in (headers || {})) h[k] = headers[k];
    return fetch(path, { method: 'POST', headers: h, body: JSON.stringify(body), credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, data: j }; }); });
  }

  // ------------------------------------------------------------------ trang sản phẩm
  function initProduct() {
    var root = $('[data-product]'); if (!root) return;
    var data = JSON.parse(root.getAttribute('data-product'));
    var bySku = {}; data.skus.forEach(function (s) { bySku[s.id] = s; });
    var qty = $('[data-qty]');
    function current() { var r = $('input[name="sku"]:checked', root); return r ? bySku[r.value] : null; }
    function render() {
      var s = current(); if (!s) return;
      var sale = s.sale_price !== null;
      $('[data-price]').textContent = fmt(sale ? s.sale_price : s.price);
      $('[data-price-was]').textContent = fmt(s.price);
      $('[data-price-was]').classList.toggle('hidden', !sale);
      $('[data-flash-chip]').classList.toggle('hidden', !sale);
      $('[data-flash-note]').classList.toggle('hidden', !sale);
      if (sale && s.flash_ends_at) {
        var d = new Date(s.flash_ends_at.replace(' ', 'T') + 'Z');
        $('[data-flash-end]').textContent = d.toLocaleString('vi-VN', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' });
      }
      $('[data-sku-code]').textContent = s.sku_code;
      $('[data-weight]').textContent = s.net_weight_g ? s.net_weight_g + ' g' : '—';
      var st = $('[data-stock]');
      st.textContent = s.available <= 0 ? 'Tạm hết hàng' : (s.available <= 10 ? 'Còn ' + s.available + ' sản phẩm' : 'Còn hàng');
      st.className = 'font-semibold ' + (s.available <= 0 ? 'text-alert' : (s.available <= 10 ? 'text-coffee' : 'text-tea'));
      $$('[data-add-to-cart],[data-buy-now]').forEach(function (b) { b.disabled = s.available <= 0; });
      qty.max = Math.max(1, Math.min(99, s.available));
      if (+qty.value > +qty.max) qty.value = qty.max;
    }
    $$('input[name="sku"]', root).forEach(function (r) { r.addEventListener('change', render); });
    $('[data-qty-dec]').addEventListener('click', function () { qty.value = Math.max(1, +qty.value - 1); });
    $('[data-qty-inc]').addEventListener('click', function () { qty.value = Math.min(+qty.max || 99, +qty.value + 1); });
    function add() {
      var s = current(); if (!s || s.available <= 0) return false;
      Cart.add(s.id, Math.max(1, parseInt(qty.value, 10) || 1), { name: data.name, label: s.variant_label });
      return true;
    }
    $('[data-add-to-cart]').addEventListener('click', function () { if (add()) toast('Đã thêm vào giỏ hàng'); });
    $('[data-buy-now]').addEventListener('click', function () { if (add()) location.href = '/gio-hang'; });
    $$('[data-thumb]').forEach(function (b) { b.addEventListener('click', function () { $('[data-main-img]').src = b.getAttribute('data-thumb'); }); });
    render();
  }

  // ------------------------------------------------------------------ báo giá
  var lastQuote = null;
  function requestQuote() {
    var p = prefs.get();
    return api('/api/quote', { items: Cart.items().map(function (i) { return { sku_id: i.sku_id, qty: i.qty }; }), voucher_code: p.voucher || '', province: p.province || '' })
      .then(function (r) { if (r.data.quote) { lastQuote = r.data.quote; return r.data.quote; } throw r; });
  }

  function renderTotals(q) {
    $$('[data-totals]').forEach(function (box) {
      $('[data-t-goods]', box).textContent = fmt(q.goods_subtotal);
      $('[data-t-discount]', box).textContent = q.discount > 0 ? '−' + fmt(q.discount) : '0 ₫';
      $('[data-t-vcode]', box).textContent = q.voucher && q.voucher.valid ? '(' + q.voucher.code + ')' : '';
      $('[data-t-ship]', box).textContent = q.shipping.served ? (q.shipping.fee > 0 ? fmt(q.shipping.fee) : 'Miễn phí') : (q.shipping.province ? 'Chưa phục vụ' : 'Chọn tỉnh/thành');
      $('[data-t-zone]', box).textContent = q.shipping.served ? '(' + q.shipping.zone_name + (q.shipping.eta ? ', ' + q.shipping.eta : '') + ')' : '';
      $('[data-t-total]', box).textContent = q.shipping.served ? fmt(q.total) : fmt(q.goods_subtotal - q.discount) + '*';
      var exp = new Date(q.expires_at.replace(' ', 'T') + 'Z');
      $('[data-t-expiry]', box).textContent = (q.shipping.served ? '' : '* Chưa gồm phí giao. ') + 'Báo giá có hiệu lực đến ' + exp.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }) + '.';
    });
    $$('[data-voucher-msg]').forEach(function (m) {
      if (!q.voucher) { m.textContent = ''; return; }
      m.textContent = q.voucher.message;
      m.className = 'mt-1 text-sm ' + (q.voucher.valid ? 'text-tea font-semibold' : 'text-alert');
    });
  }

  function issuesHtml(q) {
    if (!q.issues || !q.issues.length) return '';
    var names = {}; q.lines.forEach(function (l) { names[l.sku_id] = l.product_name + ' (' + l.variant_label + ')'; });
    return '<p class="font-semibold">Cần điều chỉnh trước khi đặt:</p><ul class="mt-1 list-disc pl-5">' + q.issues.map(function (i) {
      return '<li>' + esc(names[i.sku_id] || ('SKU #' + i.sku_id)) + ': ' + esc(i.message) + '</li>';
    }).join('') + '</ul>';
  }

  // ------------------------------------------------------------------ trang giỏ
  function initCart() {
    var page = $('[data-cart-page]'); if (!page) return;
    var p = prefs.get();
    var prov = $('[data-province]', page), vin = $('[data-voucher]', page);
    if (p.province) prov.value = p.province;
    if (p.voucher) vin.value = p.voucher;

    function refresh() {
      if (!Cart.items().length) { $('[data-cart-empty]').classList.remove('hidden'); $('[data-cart-body]').classList.add('hidden'); return; }
      requestQuote().then(function (q) {
        // loại các SKU không còn tồn tại khỏi giỏ
        var known = {}; q.lines.forEach(function (l) { known[l.sku_id] = true; });
        var list = $('[data-cart-lines]');
        list.innerHTML = q.lines.map(function (l) {
          return '<li class="flex gap-4 p-4 sm:p-5" data-line="' + l.sku_id + '">' +
            '<a href="/san-pham/' + esc(l.slug) + '" class="shrink-0"><img src="' + esc(l.image || '/assets/img/placeholder.svg') + '" alt="" width="80" height="80" class="h-20 w-20 rounded-lg bg-jade-50 object-cover"></a>' +
            '<div class="flex min-w-0 flex-1 flex-col gap-1">' +
              '<a href="/san-pham/' + esc(l.slug) + '" class="font-semibold text-ink no-underline">' + esc(l.product_name) + '</a>' +
              '<span class="text-sm text-ink-mute">' + esc(l.variant_label) + ' · ' + esc(l.sku_code) + '</span>' +
              '<span class="text-sm"><span class="font-semibold tabular-nums">' + fmt(l.unit_price) + '</span>' + (l.unit_price < l.list_price ? ' <span class="price-was">' + fmt(l.list_price) + '</span> <span class="chip-sale">Flash Sale</span>' : '') + '</span>' +
              '<div class="mt-1 flex items-center gap-3">' +
                '<label class="sr-only" for="q' + l.sku_id + '">Số lượng</label>' +
                '<input id="q' + l.sku_id + '" type="number" min="1" max="99" value="' + l.qty + '" class="field w-20 py-1.5" data-line-qty="' + l.sku_id + '">' +
                '<button type="button" class="text-sm font-semibold text-alert underline" data-line-remove="' + l.sku_id + '">Xóa</button>' +
              '</div>' +
            '</div>' +
            '<div class="text-right font-bold tabular-nums">' + fmt(l.line_total) + '</div>' +
          '</li>';
        }).join('') || '<li class="p-5">Các sản phẩm trong giỏ đã ngừng bán.</li>';
        var stale = Cart.items().filter(function (i) { return !known[i.sku_id]; });
        var issues = $('[data-cart-issues]');
        var html = issuesHtml(q) + (stale.length ? '<p class="mt-1">Một số sản phẩm đã ngừng bán và được bỏ khỏi giỏ.</p>' : '');
        if (stale.length) Cart.save(Cart.items().filter(function (i) { return known[i.sku_id]; }));
        issues.innerHTML = html; issues.classList.toggle('hidden', !html);
        renderTotals(q);
        var btn = $('[data-to-checkout]');
        var blocked = q.issues.length > 0 || !q.lines.length;
        btn.classList.toggle('pointer-events-none', blocked); btn.classList.toggle('opacity-50', blocked);
        btn.setAttribute('aria-disabled', blocked ? 'true' : 'false');
      }).catch(function () { toast('Không tải được báo giá, vui lòng thử lại.'); });
    }
    page.addEventListener('change', function (e) {
      if (e.target.matches('[data-line-qty]')) { Cart.setQty(+e.target.getAttribute('data-line-qty'), parseInt(e.target.value, 10) || 1); refresh(); }
      if (e.target === prov) { prefs.set({ province: prov.value }); refresh(); }
    });
    page.addEventListener('click', function (e) {
      var rm = e.target.closest('[data-line-remove]');
      if (rm) { Cart.remove(+rm.getAttribute('data-line-remove')); refresh(); }
    });
    $('[data-voucher-form]').addEventListener('submit', function (e) { e.preventDefault(); prefs.set({ voucher: vin.value.trim().toUpperCase() }); refresh(); });
    refresh();
  }

  // ------------------------------------------------------------------ thanh toán
  function initCheckout() {
    var page = $('[data-checkout-page]'); if (!page) return;
    var form = $('[data-checkout-form]');
    if (!Cart.items().length) { $('[data-cart-empty]').classList.remove('hidden'); form.classList.add('hidden'); return; }
    var p = prefs.get();
    ['name', 'phone', 'address'].forEach(function (k) { if (p[k]) form.elements[k].value = p[k]; });
    if (p.province) form.elements.province.value = p.province;
    var vin = $('[data-voucher]', page); if (p.voucher) vin.value = p.voucher;

    function refresh() {
      return requestQuote().then(function (q) {
        $('[data-summary-lines]').innerHTML = q.lines.map(function (l) {
          return '<li class="flex justify-between gap-3"><span><span class="font-semibold">' + esc(l.product_name) + '</span><br><span class="text-ink-mute">' + esc(l.variant_label) + ' × ' + l.qty + '</span></span><span class="font-semibold tabular-nums">' + fmt(l.line_total) + '</span></li>';
        }).join('');
        renderTotals(q);
        var err = $('[data-form-error]');
        var html = issuesHtml(q);
        err.innerHTML = html ? html + '<a href="/gio-hang" class="mt-2 inline-block font-semibold underline">Sửa giỏ hàng</a>' : '';
        err.classList.toggle('hidden', !html);
        return q;
      });
    }
    form.elements.province.addEventListener('change', function () { prefs.set({ province: form.elements.province.value }); clearErr('province'); refresh(); });
    $('[data-voucher-apply]').addEventListener('click', function () { prefs.set({ voucher: vin.value.trim().toUpperCase() }); refresh(); });
    $$('input,select,textarea', form).forEach(function (el) { el.addEventListener('input', function () { clearErr(el.name); }); });

    function clearErr(name) {
      var m = $('[data-err="' + name + '"]', form); if (m) { m.classList.add('hidden'); m.textContent = ''; }
      var f = form.elements[name]; if (f && f.classList) { f.classList.remove('field-error'); f.removeAttribute('aria-invalid'); }
    }
    function showErrors(fields) {
      var first = null;
      Object.keys(fields).forEach(function (k) {
        if (!fields[k]) return;
        var m = $('[data-err="' + k + '"]', form);
        var f = form.elements[k];
        if (m) { m.textContent = fields[k]; m.classList.remove('hidden'); }
        if (f && f.classList) { f.classList.add('field-error'); f.setAttribute('aria-invalid', 'true'); first = first || f; }
        if (k === 'items') { var e = $('[data-form-error]'); e.textContent = fields[k]; e.classList.remove('hidden'); }
      });
      if (first) first.focus();
    }
    function clientValidate(d) {
      var f = {};
      if (d.customer.name.length < 2) f.name = 'Vui lòng nhập họ tên.';
      if (!/^(0|\+84)(3|5|7|8|9)\d{8}$/.test(d.customer.phone.replace(/[\s.\-]/g, ''))) f.phone = 'Số điện thoại di động Việt Nam chưa đúng (VD: 0912345678).';
      if (!d.customer.province) f.province = 'Vui lòng chọn tỉnh/thành.';
      if (d.customer.address.length < 6) f.address = 'Vui lòng nhập địa chỉ chi tiết (số nhà, đường, phường/xã).';
      return f;
    }
    function payload(token) {
      var fd = form.elements;
      return {
        items: Cart.items().map(function (i) { return { sku_id: i.sku_id, qty: i.qty }; }),
        voucher_code: prefs.get().voucher || '',
        payment_method: (form.querySelector('input[name="payment_method"]:checked') || {}).value,
        marketing_consent: fd.marketing_consent.checked,
        quote_token: token,
        customer: { name: fd.name.value.trim(), phone: fd.phone.value.trim(), province: fd.province.value, address: fd.address.value.trim(), note: fd.note.value.trim() }
      };
    }
    // Khóa gửi lại: giữ nguyên khi khách bấm lại / mạng chập chờn với CÙNG nội dung
    function idemKey(body) {
      var sig = JSON.stringify([body.items, body.voucher_code, body.payment_method, body.customer, body.marketing_consent]);
      var saved = null; try { saved = JSON.parse(ss.get('xuong_idem') || 'null'); } catch (e) {}
      if (saved && saved.sig === sig) return saved.key;
      var key = 'ck_' + (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : Date.now().toString(36) + Math.random().toString(36).slice(2));
      ss.set('xuong_idem', JSON.stringify({ sig: sig, key: key }));
      return key;
    }

    var btn = $('[data-place-order]'), busy = false;
    function submit(token) {
      var body = payload(token);
      var fe = clientValidate(body);
      if (Object.keys(fe).length) { showErrors(fe); return; }
      busy = true; btn.disabled = true; btn.textContent = 'Đang đặt hàng…';
      prefs.set({ name: body.customer.name, phone: body.customer.phone, address: body.customer.address, province: body.customer.province });
      var key = idemKey(body);
      var attempt = function (n) {
        return api('/api/orders', body, { 'Idempotency-Key': key }).catch(function () {
          // lỗi mạng: thử lại với CÙNG khóa — máy chủ trả đơn đã tạo nếu có
          if (n < 3) return new Promise(function (res) { setTimeout(res, 800 * (n + 1)); }).then(function () { return attempt(n + 1); });
          throw new Error('network');
        });
      };
      attempt(0).then(function (r) {
        if (r.status === 201 || r.status === 200) {
          Cart.clear(); ss.del('xuong_idem'); prefs.set({ voucher: '' });
          location.href = r.data.order.confirm_url;
          return;
        }
        var err = (r.data && r.data.error) || {};
        var det = err.details || {};
        if (err.code === 'VALIDATION_ERROR') showErrors(det.fields || {});
        else if (err.code === 'QUOTE_CHANGED') showQuoteDialog(det.quote, err.message);
        else if (err.code === 'OUT_OF_STOCK' || err.code === 'ZONE_NOT_SERVED') {
          if (det.quote) { renderTotals(det.quote); }
          var box = $('[data-form-error]');
          box.innerHTML = '<p class="font-semibold">' + esc(err.message) + '</p>' + (det.quote ? issuesHtml(det.quote) : '') + '<a href="/gio-hang" class="mt-2 inline-block font-semibold underline">Sửa giỏ hàng</a>';
          box.classList.remove('hidden'); box.focus && box.scrollIntoView({ block: 'center' });
        } else {
          var b = $('[data-form-error]'); b.textContent = err.message || 'Không đặt được hàng, vui lòng thử lại.'; b.classList.remove('hidden');
        }
      }).catch(function () {
        var b = $('[data-form-error]'); b.textContent = 'Mất kết nối. Bấm "Đặt hàng" lần nữa — nếu đơn đã được tạo, hệ thống sẽ hiển thị đúng đơn đó, không tạo trùng.'; b.classList.remove('hidden');
      }).then(function () { busy = false; btn.disabled = false; btn.textContent = 'Đặt hàng'; });
    }
    function showQuoteDialog(q, msg) {
      var dlg = $('[data-quote-dialog]');
      lastQuote = q; renderTotals(q);
      $('[data-qd-msg]').textContent = msg;
      var rows = [['Tiền hàng', fmt(q.goods_subtotal)], ['Giảm giá', q.discount > 0 ? '−' + fmt(q.discount) : (q.voucher && !q.voucher.valid ? '0 ₫ — ' + q.voucher.message : '0 ₫')], ['Phí giao', fmt(q.shipping.fee)], ['Tổng mới', fmt(q.total)]];
      $('[data-qd-body]').innerHTML = rows.map(function (r, i) { return '<div class="flex justify-between gap-4' + (i === 3 ? ' border-t border-ink/10 pt-2 text-base font-bold' : '') + '"><dt>' + r[0] + '</dt><dd class="tabular-nums text-right">' + esc(r[1]) + '</dd></div>'; }).join('');
      var ok = $('[data-qd-confirm]');
      ok.disabled = q.issues && q.issues.length > 0;
      ok.onclick = function () { dlg.close(); submit(q.quote_token); };
      if (dlg.showModal) dlg.showModal(); else if (confirm(msg + '\nTổng mới: ' + fmt(q.total))) submit(q.quote_token);
    }
    form.addEventListener('submit', function (e) {
      e.preventDefault(); if (busy) return;
      // Luôn lấy báo giá mới nhất khách đang nhìn thấy, rồi gửi kèm mã báo giá
      refresh().then(function (q) { if (q.issues.length) return; submit(q.quote_token); }).catch(function () { submit(lastQuote && lastQuote.quote_token); });
    });
    refresh().catch(function () { toast('Không tải được báo giá, vui lòng thử lại.'); });
  }

  // ------------------------------------------------------------------ xác nhận đơn
  function initOrder() {
    var box = $('[data-qr]');
    if (box) {
      var draw = function () {
        if (!window.qrcode) return setTimeout(draw, 80);
        var qr = window.qrcode(0, 'M'); qr.addData(box.getAttribute('data-qr')); qr.make();
        box.innerHTML = qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true });
        var svg = box.querySelector('svg'); if (svg) { svg.setAttribute('width', '100%'); svg.removeAttribute('height'); }
      };
      draw();
    }
    $$('[data-copy]').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = b.getAttribute('data-copy');
        (navigator.clipboard ? navigator.clipboard.writeText(v) : Promise.reject()).then(function () { toast('Đã sao chép ' + v); }, function () { toast(v); });
      });
    });
  }

  // ------------------------------------------------------------------ đếm ngược Flash Sale
  function initCountdown() {
    $$('[data-countdown]').forEach(function (el) {
      var end = new Date(el.getAttribute('data-countdown')).getTime();
      var tick = function () {
        var s = Math.max(0, Math.floor((end - Date.now()) / 1000));
        var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
        var p = function (n) { return (n < 10 ? '0' : '') + n; };
        el.textContent = (d > 0 ? d + ' ngày ' : '') + p(h) + ':' + p(m) + ':' + p(x);
        if (s > 0) setTimeout(tick, 1000); else el.textContent = 'đã kết thúc';
      };
      tick();
    });
  }

  // ------------------------------------------------------------------ gợi ý tìm kiếm
  function initAutocomplete() {
    var input = $('[data-autocomplete]'), list = $('[data-autocomplete-list]'); if (!input || !list) return;
    var t;
    input.addEventListener('input', function () {
      clearTimeout(t);
      var q = input.value.trim();
      if (q.length < 2) { list.classList.add('hidden'); return; }
      t = setTimeout(function () {
        fetch('/api/products?per_page=6&q=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (j) {
          if (!j.items || !j.items.length) { list.innerHTML = '<p class="p-3 text-sm text-ink-mute">Không có sản phẩm phù hợp.</p>'; list.classList.remove('hidden'); return; }
          list.innerHTML = j.items.map(function (p) {
            return '<a href="' + esc(p.url) + '" class="flex items-center gap-3 px-3 py-2 text-ink no-underline hover:bg-jade-50"><img src="' + esc(p.image) + '" alt="" width="40" height="40" class="h-10 w-10 rounded object-cover"><span class="flex-1 text-sm font-medium">' + esc(p.name) + '</span><span class="text-sm font-bold tabular-nums">' + fmt(p.flash ? p.flash.sale : p.min_price) + '</span></a>';
          }).join('');
          list.classList.remove('hidden');
        });
      }, 220);
    });
    document.addEventListener('click', function (e) { if (!e.target.closest('[role="search"]')) list.classList.add('hidden'); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Escape') list.classList.add('hidden'); });
  }

  // ------------------------------------------------------------------ chat
  function initChat() {
    var root = $('[data-chat]'); if (!root) return;
    var panel = $('[data-chat-panel]'), log = $('[data-chat-log]'), form = $('[data-chat-form]'), input = $('#chat-input');
    $$('[data-chat-toggle]', root).forEach(function (b) {
      b.addEventListener('click', function () {
        var open = panel.classList.toggle('hidden') === false;
        $('[data-chat-toggle]', root).setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) input.focus();
      });
    });
    function bubble(html, mine) {
      var d = document.createElement('div');
      d.className = 'max-w-[85%] whitespace-pre-line rounded-xl p-3 shadow-sm ' + (mine ? 'ml-auto rounded-tr-sm bg-tea text-white' : 'rounded-tl-sm bg-white');
      d.innerHTML = html; log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
    }
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var msg = input.value.trim(); if (!msg) return;
      bubble(esc(msg), true); input.value = '';
      var wait = bubble('<span class="text-ink-mute">Đang trả lời…</span>');
      api('/api/chat', { message: msg }).then(function (r) {
        var d = r.data;
        if (!d.reply) { wait.innerHTML = esc((d.error && d.error.message) || 'Chưa trả lời được, vui lòng thử lại.'); return; }
        var html = esc(d.reply);
        if (d.products && d.products.length) html += '<div class="mt-2 space-y-1">' + d.products.map(function (p) { return '<a class="block font-semibold underline" href="' + esc(p.url) + '">' + esc(p.name) + '</a>'; }).join('') + '</div>';
        if (d.suggestions && d.suggestions.length) html += '<div class="mt-2 text-xs text-ink-mute">Thường mua kèm: ' + d.suggestions.map(function (s) { return '<a class="underline" href="' + esc(s.url) + '">' + esc(s.name) + '</a>'; }).join(', ') + '</div>';
        wait.innerHTML = html;
        log.scrollTop = log.scrollHeight;
      }).catch(function () { wait.textContent = 'Mất kết nối. Bạn có thể gọi hotline ở cuối trang.'; });
    });
  }

  // ------------------------------------------------------------------ xóa dữ liệu lưu trên trình duyệt (trang bảo mật)
  $$('[data-clear-local]').forEach(function (b) {
    b.addEventListener('click', function () {
      store.del(Cart.KEY); store.del('xuong_checkout_prefs'); ss.del('xuong_idem');
      Cart.badge(); b.disabled = true; b.textContent = 'Đã xóa thông tin trên trình duyệt này';
      toast('Đã xóa giỏ hàng và thông tin đã lưu');
    });
  });

  // ------------------------------------------------------------------ khác
  $$('[data-autosubmit]').forEach(function (s) { s.addEventListener('change', function () { s.form.submit(); }); });

  Cart.badge();
  initProduct(); initCart(); initCheckout(); initOrder(); initCountdown(); initAutocomplete(); initChat();
})();
