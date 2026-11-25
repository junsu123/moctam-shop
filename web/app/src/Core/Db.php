<?php
declare(strict_types=1);

namespace App\Core;

use PDO;
use PDOException;
use Throwable;

/**
 * PDO với truy vấn có tham số (NFR-01) và giao dịch tự thử lại khi deadlock.
 */
final class Db
{
    private static ?PDO $pdo = null;
    private static int $depth = 0;

    public static function pdo(): PDO
    {
        if (self::$pdo === null) {
            $c = config('db');
            $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4', $c['host'], (int)($c['port'] ?? 3306), $c['name']);
            self::$pdo = new PDO($dsn, $c['user'], $c['password'], [
                PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES   => false,
                PDO::ATTR_STRINGIFY_FETCHES  => false,
            ]);
            self::$pdo->exec("SET time_zone = '+00:00', sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ENGINE_SUBSTITUTION,ERROR_FOR_DIVISION_BY_ZERO'");
        }
        return self::$pdo;
    }

    /** Dùng trong kiểm thử để mở kết nối mới. */
    public static function reset(): void
    {
        self::$pdo = null;
        self::$depth = 0;
    }

    public static function run(string $sql, array $params = []): \PDOStatement
    {
        $st = self::pdo()->prepare($sql);
        foreach ($params as $k => $v) {
            $name = is_int($k) ? $k + 1 : (str_starts_with($k, ':') ? $k : ':' . $k);
            $type = is_int($v) ? PDO::PARAM_INT : (is_bool($v) ? PDO::PARAM_BOOL : ($v === null ? PDO::PARAM_NULL : PDO::PARAM_STR));
            $st->bindValue($name, $v, $type);
        }
        $st->execute();
        return $st;
    }

    public static function one(string $sql, array $params = []): ?array
    {
        $row = self::run($sql, $params)->fetch();
        return $row === false ? null : $row;
    }

    public static function all(string $sql, array $params = []): array
    {
        return self::run($sql, $params)->fetchAll();
    }

    public static function val(string $sql, array $params = []): mixed
    {
        $v = self::run($sql, $params)->fetchColumn();
        return $v === false ? null : $v;
    }

    public static function exec(string $sql, array $params = []): int
    {
        return self::run($sql, $params)->rowCount();
    }

    public static function insert(string $table, array $data): int
    {
        $cols = array_keys($data);
        $sql = sprintf(
            'INSERT INTO `%s` (%s) VALUES (%s)',
            $table,
            implode(',', array_map(fn($c) => "`$c`", $cols)),
            implode(',', array_map(fn($c) => ":$c", $cols))
        );
        self::run($sql, $data);
        return (int)self::pdo()->lastInsertId();
    }

    public static function update(string $table, array $data, string $where, array $whereParams = []): int
    {
        $sets = [];
        $params = [];
        foreach ($data as $col => $v) {
            $sets[] = "`$col` = :set_$col";
            $params["set_$col"] = $v;
        }
        return self::exec(sprintf('UPDATE `%s` SET %s WHERE %s', $table, implode(',', $sets), $where), $params + $whereParams);
    }

    public static function inTx(): bool
    {
        return self::$depth > 0;
    }

    /**
     * Chạy $fn trong một giao dịch. Lỗi bất kỳ → hoàn tác toàn bộ.
     * Deadlock (1213) / lock wait timeout (1205) được thử lại.
     */
    public static function tx(callable $fn, int $retries = 3): mixed
    {
        if (self::$depth > 0) {
            return $fn(); // lồng: dùng giao dịch ngoài
        }
        $attempt = 0;
        while (true) {
            $attempt++;
            self::pdo()->beginTransaction();
            self::$depth = 1;
            try {
                $result = $fn();
                self::pdo()->commit();
                self::$depth = 0;
                return $result;
            } catch (Throwable $e) {
                self::$depth = 0;
                if (self::pdo()->inTransaction()) {
                    self::pdo()->rollBack();
                }
                if ($attempt < $retries && self::isRetryable($e)) {
                    usleep(random_int(20_000, 120_000));
                    continue;
                }
                throw $e;
            }
        }
    }

    public static function isRetryable(Throwable $e): bool
    {
        if (!$e instanceof PDOException) {
            return false;
        }
        $code = (int)($e->errorInfo[1] ?? 0);
        return $code === 1213 || $code === 1205;
    }

    public static function isDuplicate(Throwable $e, ?string $keyName = null): bool
    {
        if (!$e instanceof PDOException || (int)($e->errorInfo[1] ?? 0) !== 1062) {
            return false;
        }
        return $keyName === null || str_contains((string)($e->errorInfo[2] ?? ''), $keyName);
    }
}
