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
        $regex = '#^' . preg_replace('#\{(\w+)\}#', '(?P<$1>[^/]+)', rtrim($pattern, '/') ?: '/') . '/?$#u';
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
