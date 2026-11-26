<?php
declare(strict_types=1);

namespace App\Core;

final class Router
{
    private array $routes = [];

    public function get(string $pattern, callable|array $handler): void
    {
        $this->add('GET', $pattern, $handler);
    }

    public function post(string $pattern, callable|array $handler): void
    {
        $this->add('POST', $pattern, $handler);
    }

    public function add(string $method, string $pattern, callable|array $handler): void
    {
        // Phần chữ cố định được thoát (VD dấu "." trong ".html"); {ten} → nhóm bắt một đoạn đường dẫn
        $parts = preg_split('#(\{\w+\})#', rtrim($pattern, '/') ?: '/', -1, PREG_SPLIT_DELIM_CAPTURE);
        $body = implode('', array_map(fn($p) => preg_match('#^\{(\w+)\}$#', $p, $m) ? '(?P<' . $m[1] . '>[^/]+)' : preg_quote($p, '#'), $parts));
        $regex = '#^' . $body . '/?$#u';
        $this->routes[] = [$method, $regex, $handler];
    }

    public function dispatch(string $method, string $path): mixed
    {
        $path = rawurldecode(parse_url($path, PHP_URL_PATH) ?: '/');
        $allowed = false;
        foreach ($this->routes as [$m, $regex, $handler]) {
            if (preg_match($regex, $path, $mm)) {
                if ($m !== $method && !($method === 'HEAD' && $m === 'GET')) {
                    $allowed = true;
                    continue;
                }
                $params = array_filter($mm, 'is_string', ARRAY_FILTER_USE_KEY);
                if (is_array($handler)) {
                    [$class, $fn] = $handler;
                    return (new $class())->$fn(...array_values($params));
                }
                return $handler(...array_values($params));
            }
        }
        throw new ApiError($allowed ? 'METHOD_NOT_ALLOWED' : 'NOT_FOUND', $allowed ? 'Phương thức không được hỗ trợ.' : 'Không tìm thấy trang.', $allowed ? 405 : 404);
    }
}
