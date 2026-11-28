#!/usr/bin/env bash
# Dựng website THẬT (PHP + MariaDB) cho kiểm thử tích hợp của ai-company (IT-PUB-01/02): CSDL riêng tên chứa "test",
# migrate + seed, tạo khóa catalog:read và content:publish, chạy máy chủ PHP tích hợp ở cổng $PORT.
# In ra các biến môi trường AICO_TEST_WEBSITE_* (dùng: eval "$(web/tests/it_server.sh)").
#   Biến vào: XUONG_IT_DB (mặc định xuong_it_test), PORT (8090), DB_HOST/DB_PORT/DB_USER/DB_PASS (mặc định như app/config.php).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
DB="${XUONG_IT_DB:-xuong_it_test}"
PORT="${PORT:-8090}"
case "$DB" in *test*) ;; *) echo "CSDL phải có tên chứa test" >&2; exit 2 ;; esac
CFG="$(mktemp -d)/config.php"
cat >"$CFG" <<PHP
<?php
\$c = require '$ROOT/app/config.sample.php';
\$c['debug'] = true;
\$c['base_url'] = 'http://127.0.0.1:$PORT';
\$c['db'] = ['host' => '${DB_HOST:-127.0.0.1}', 'port' => ${DB_PORT:-3306}, 'name' => '$DB', 'user' => '${DB_USER:-xuong}', 'password' => '${DB_PASS:-xuongpw}'];
\$c['app_key'] = str_repeat('i', 64);
\$c['session']['secure'] = false;
return \$c;
PHP
export XUONG_CONFIG="$CFG"
php -r "\$c = require getenv('XUONG_CONFIG'); \$d = \$c['db']; \$p = new PDO(\"mysql:host={\$d['host']};port={\$d['port']}\", \$d['user'], \$d['password']);
\$p->exec('DROP DATABASE IF EXISTS \`' . \$d['name'] . '\`'); \$p->exec('CREATE DATABASE \`' . \$d['name'] . '\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');"
php "$ROOT/bin/migrate.php" >/dev/null
php "$ROOT/bin/seed.php" >/dev/null
READ=$(php "$ROOT/bin/create_api_key.php" it-doc catalog:read | sed -n 2p)
PUB=$(php "$ROOT/bin/create_api_key.php" it-dang content:publish | sed -n 2p)
# khung giờ đăng của website tính theo giờ thật: mở cả ngày cho kiểm thử tích hợp
php -r "require '$ROOT/app/bootstrap.php'; App\Core\Settings::set('ai_publish_hours', '00:00-23:59');"
nohup php -S "127.0.0.1:$PORT" -t "$ROOT/public_html" "$HERE/devrouter.php" >"${TMPDIR:-/tmp}/xuong-it-server.log" 2>&1 &
for _ in $(seq 30); do curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/health" 2>/dev/null && break; sleep 0.5; done
echo "export AICO_TEST_WEBSITE_URL=http://127.0.0.1:$PORT AICO_TEST_WEBSITE_READ_KEY=$READ AICO_TEST_WEBSITE_PUBLISH_KEY=$PUB XUONG_IT_SERVER_PID=$!"
