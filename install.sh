#!/usr/bin/env bash
# Cài đặt / cập nhật website trên Hostinger bằng MỘT dòng lệnh (chạy trong SSH):
#
#   curl -fsSL https://raw.githubusercontent.com/junsu123/moctam-shop/main/install.sh | bash
#
# Lần đầu: hỏi tên miền, CSDL, tài khoản quản trị → cài xong.
# Chạy lại cùng lệnh: cập nhật mã mới + migration, GIỮ cấu hình, ảnh và dữ liệu.
# Không muốn bị hỏi: đặt sẵn biến DOMAIN DB_NAME DB_USER DB_PASS ADMIN_EMAIL ADMIN_PASS [STORE_NAME SAMPLE=1|0 DB_HOST].
set -euo pipefail

REPO="${REPO:-junsu123/moctam-shop}"
BRANCH="${BRANCH:-main}"
G=$'\e[32m'; R=$'\e[31m'; B=$'\e[1m'; N=$'\e[0m'
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s▸ %s%s\n' "$B" "$*" "$N"; }
die()  { printf '\n%s✘ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }
TTY=/dev/tty; [ -r "$TTY" ] || TTY=/dev/stdin
ask() { # ask BIẾN "Câu hỏi" [mặc định] [secret]
  local __v="$1" __q="$2" __d="${3:-}" __s="${4:-}" __a=""
  [ -n "${!__v:-}" ] && return 0
  if [ -n "$__s" ]; then printf '  %s: ' "$__q" >&2; read -rs __a <"$TTY"; printf '\n' >&2
  else printf '  %s%s: ' "$__q" "${__d:+ [$__d]}" >&2; read -r __a <"$TTY"; fi
  printf -v "$__v" '%s' "${__a:-$__d}"
}

say "${B}Cài đặt website bán hàng — ${REPO}@${BRANCH}${N}"

# ------------------------------------------------------------ PHP
step "Kiểm tra PHP"
PHP_BIN="${PHP_BIN:-}"
if [ -z "$PHP_BIN" ]; then
  for c in php /opt/alt/php83/usr/bin/php /opt/alt/php82/usr/bin/php /opt/alt/php81/usr/bin/php /opt/alt/php80/usr/bin/php php8.3 php8.2 php8.1 php8.0; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -r 'exit(PHP_VERSION_ID >= 80000 ? 0 : 1);' 2>/dev/null; then PHP_BIN="$(command -v "$c")"; break; fi
  done
fi
[ -n "$PHP_BIN" ] || die "Không tìm thấy PHP 8.0+. Vào hPanel → Advanced → PHP Configuration chọn PHP 8.2/8.3 rồi chạy lại."
say "  • $("$PHP_BIN" -r 'echo "PHP ", PHP_VERSION;') ($PHP_BIN)"

# ------------------------------------------------------------ thư mục tên miền
step "Chọn tên miền"
if [ -z "${DOMAIN:-}" ] && [ -d "$HOME/domains" ]; then
  mapfile -t LIST < <(ls -1 "$HOME/domains" 2>/dev/null)
  if [ "${#LIST[@]}" -eq 1 ]; then DOMAIN="${LIST[0]}"; say "  • Tìm thấy: $DOMAIN";
  elif [ "${#LIST[@]}" -gt 1 ]; then say "  Các tên miền trên tài khoản: ${LIST[*]}"; fi
fi
ask DOMAIN "Tên miền (VD: xuongtramoc.vn)"
[ -n "$DOMAIN" ] || die "Chưa nhập tên miền."
ROOT="${INSTALL_ROOT:-$HOME/domains/$DOMAIN}"
WEBROOT="$ROOT/public_html"
mkdir -p "$WEBROOT"
say "  • Cài vào $ROOT"

MODE=install; [ -f "$ROOT/app/config.php" ] && MODE=update
say "  • Chế độ: $([ $MODE = install ] && echo 'cài mới' || echo 'cập nhật (giữ cấu hình & dữ liệu)')"

# ------------------------------------------------------------ thông tin lần đầu
if [ $MODE = install ]; then
  step "Thông tin cơ sở dữ liệu (tạo trước trong hPanel → Databases → MySQL Databases)"
  ask DB_NAME "Tên CSDL (VD: u123456789_shop)"
  ask DB_USER "Người dùng CSDL" "$DB_NAME"
  ask DB_PASS "Mật khẩu CSDL" "" secret
  DB_HOST="${DB_HOST:-localhost}"
  for try in 1 2 3; do
    ERR="$(DB_HOST="$DB_HOST" DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASS="$DB_PASS" "$PHP_BIN" -r '
      try { new PDO("mysql:host=".getenv("DB_HOST").";dbname=".getenv("DB_NAME").";charset=utf8mb4", getenv("DB_USER"), getenv("DB_PASS")); }
      catch (Throwable $e) { echo $e->getMessage(); exit(1); }' 2>&1)" && { say "  • Kết nối CSDL thành công"; break; }
    say "  ${R}Không kết nối được: ${ERR#SQLSTATE*] }${N}"
    [ "$try" = 3 ] && die "Kiểm tra lại tên CSDL, người dùng, mật khẩu trong hPanel → Databases rồi chạy lại."
    [ "$TTY" = /dev/tty ] || die "Sai thông tin CSDL."
    DB_NAME=""; DB_USER=""; DB_PASS=""
    ask DB_NAME "Tên CSDL"; ask DB_USER "Người dùng CSDL" "$DB_NAME"; ask DB_PASS "Mật khẩu CSDL" "" secret
  done
  step "Cửa hàng và tài khoản quản trị"
  ask STORE_NAME "Tên cửa hàng" "Xưởng Trà Mộc"
  ask ADMIN_EMAIL "Email đăng nhập quản trị"
  while :; do
    ask ADMIN_PASS "Mật khẩu quản trị (≥ 10 ký tự)" "" secret
    [ "${#ADMIN_PASS}" -ge 10 ] && break; say "  ${R}Mật khẩu quá ngắn.${N}"; ADMIN_PASS=""
  done
  ask SAMPLE "Nạp sản phẩm mẫu để xem thử? (1 = có, 0 = không)" "1"
fi

# ------------------------------------------------------------ tải mã nguồn
step "Tải mã nguồn"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ -n "${SRC_DIR:-}" ]; then
  SRC="$SRC_DIR"                                   # dùng khi thử nghiệm
else
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH" -o "$TMP/src.tgz" || die "Không tải được mã nguồn từ GitHub (repo phải ở chế độ Public)."
  tar -xzf "$TMP/src.tgz" -C "$TMP"
  SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
fi
[ -f "$SRC/web/public_html/index.php" ] || die "Mã nguồn không hợp lệ."
say "  • Xong"

# ------------------------------------------------------------ đặt tệp
step "Cài đặt tệp"
copy() { # copy NGUỒN ĐÍCH (ghi đè mã, không xóa tệp lạ)
  if command -v rsync >/dev/null 2>&1; then rsync -a "$@"; else cp -R "${@: -2:1}/." "${@: -1}"; fi
}
if [ $MODE = install ] && ! grep -qs "Front controller" "$WEBROOT/index.php" \
   && [ -n "$(ls -A "$WEBROOT" 2>/dev/null | grep -v '^\(default.php\|.well-known\|cgi-bin\)$' || true)" ]; then
  BK="$ROOT/public_html.cu-$(date +%Y%m%d%H%M%S)"
  mv "$WEBROOT" "$BK"; mkdir -p "$WEBROOT"; say "  • public_html cũ đã chuyển sang $(basename "$BK")"
fi
rm -f "$WEBROOT/default.php"
mkdir -p "$ROOT/app"
copy --exclude 'config.php' "$SRC/web/app/" "$ROOT/app/"
copy "$SRC/web/bin/" "$ROOT/bin/"
copy "$SRC/web/migrations/" "$ROOT/migrations/"
copy --exclude 'uploads/products' "$SRC/web/public_html/" "$WEBROOT/"
mkdir -p "$ROOT/storage/logs" "$ROOT/storage/backups" "$WEBROOT/uploads/products"
chmod 750 "$ROOT/storage" "$ROOT/storage/logs" "$ROOT/storage/backups" 2>/dev/null || true
say "  • Mã nguồn tại $ROOT (app/, bin/, migrations/ nằm ngoài public_html)"

# ------------------------------------------------------------ cấu hình + CSDL
step "Cấu hình và cơ sở dữ liệu"
if [ $MODE = update ]; then "$PHP_BIN" "$ROOT/bin/backup.php" >/dev/null 2>&1 && say "  • Đã sao lưu trước khi cập nhật" || say "  • (không sao lưu được — tiếp tục)"; fi
DB_HOST="${DB_HOST:-localhost}" DB_NAME="${DB_NAME:-}" DB_USER="${DB_USER:-}" DB_PASS="${DB_PASS:-}" \
BASE_URL="${BASE_URL:-https://$DOMAIN}" STORE_NAME="${STORE_NAME:-}" ADMIN_EMAIL="${ADMIN_EMAIL:-}" ADMIN_PASS="${ADMIN_PASS:-}" SAMPLE="${SAMPLE:-0}" \
  "$PHP_BIN" "$ROOT/bin/install.php" | grep -v '^OK$' || die "Cài đặt dừng lại — xem thông báo ở trên."

# ------------------------------------------------------------ cron
step "Tác vụ định kỳ"
CRON1="*/5 * * * * $PHP_BIN $ROOT/bin/cron.php >/dev/null 2>&1"
CRON2="15 2 * * * $PHP_BIN $ROOT/bin/backup.php >/dev/null 2>&1"
CRON_MANUAL=1
if [ "${NO_CRON:-0}" != 1 ] && command -v crontab >/dev/null 2>&1; then
  if { { crontab -l 2>/dev/null || true; } | awk -v a="$ROOT/bin/cron.php" -v b="$ROOT/bin/backup.php" 'index($0,a)==0 && index($0,b)==0'; echo "$CRON1"; echo "$CRON2"; } | crontab - 2>/dev/null \
     && crontab -l 2>/dev/null | grep -qF "$ROOT/bin/cron.php"; then
    CRON_MANUAL=0; say "  • Đã đặt cron: hết hạn đơn mỗi 5 phút, sao lưu 02:15 hằng ngày"
  fi
fi
if [ "${CRON_MANUAL:-0}" = 1 ]; then
  say "  ${B}Thêm 2 Cron Job trong hPanel → Advanced → Cron Jobs (chọn \"Custom\"):${N}"
  say "    Mỗi 5 phút:      $PHP_BIN $ROOT/bin/cron.php"
  say "    Hằng ngày 2:15:  $PHP_BIN $ROOT/bin/backup.php"
fi
"$PHP_BIN" "$ROOT/bin/cron.php" >/dev/null 2>&1 || true

# ------------------------------------------------------------ xong
printf '\n%s✔ %s xong.%s\n' "$G" "$([ $MODE = install ] && echo 'Cài đặt' || echo 'Cập nhật')" "$N"
say "  Cửa hàng:  https://$DOMAIN"
say "  Quản trị:  https://$DOMAIN/admin"
if [ $MODE = install ]; then
  say "  Việc tiếp theo: đăng nhập quản trị → Cấu hình (hotline, Zalo, tài khoản VietQR)."
  say "  Trước ngày mở bán: Quản trị → Làm mới dữ liệu để xóa dữ liệu thử."
fi
say "  Cập nhật sau này: chạy lại đúng dòng lệnh đã dùng để cài."
