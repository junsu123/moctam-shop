<?php
declare(strict_types=1);

namespace App\Core;

use DOMDocument;
use DOMElement;
use DOMNode;

/**
 * Lọc HTML nội dung theo danh sách trắng (NFR-01). Không cần thư viện ngoài.
 */
final class Html
{
    private const ALLOWED = [
        'p' => [], 'br' => [], 'strong' => [], 'b' => [], 'em' => [], 'i' => [], 'u' => [],
        'h2' => ['id'], 'h3' => ['id'], 'h4' => [], 'ul' => [], 'ol' => [], 'li' => [],
        'blockquote' => [], 'a' => ['href', 'title'], 'img' => ['src', 'alt', 'width', 'height'],
        'table' => [], 'thead' => [], 'tbody' => [], 'tr' => [], 'th' => [], 'td' => [],
        'figure' => [], 'figcaption' => [], 'hr' => [], 'span' => [],
    ];

    public static function sanitize(string $html): string
    {
        $html = trim($html);
        if ($html === '') {
            return '';
        }
        $doc = new DOMDocument('1.0', 'UTF-8');
        $prev = libxml_use_internal_errors(true);
        $doc->loadHTML('<?xml encoding="UTF-8"><div id="__root">' . $html . '</div>', LIBXML_HTML_NOIMPLIED | LIBXML_HTML_NODEFDTD | LIBXML_NONET);
        libxml_clear_errors();
        libxml_use_internal_errors($prev);
        $root = $doc->getElementById('__root');
        if (!$root) {
            return e(strip_tags($html));
        }
        self::clean($root);
        $out = '';
        foreach (iterator_to_array($root->childNodes) as $child) {
            $out .= $doc->saveHTML($child);
        }
        return $out;
    }

    private static function clean(DOMNode $node): void
    {
        foreach (iterator_to_array($node->childNodes) as $child) {
            if ($child instanceof DOMElement) {
                $tag = strtolower($child->tagName);
                if (in_array($tag, ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'link', 'meta'], true)) {
                    $node->removeChild($child);
                    continue;
                }
                if (!array_key_exists($tag, self::ALLOWED)) {
                    self::clean($child);
                    while ($child->firstChild) {
                        $node->insertBefore($child->firstChild, $child);
                    }
                    $node->removeChild($child);
                    continue;
                }
                foreach (iterator_to_array($child->attributes) as $attr) {
                    $name = strtolower($attr->name);
                    if (!in_array($name, self::ALLOWED[$tag], true)) {
                        $child->removeAttribute($attr->name);
                        continue;
                    }
                    if (in_array($name, ['href', 'src'], true) && !self::safeUrl($attr->value)) {
                        $child->removeAttribute($attr->name);
                    }
                }
                if ($tag === 'a') {
                    $child->setAttribute('rel', 'noopener nofollow');
                }
                self::clean($child);
            } elseif ($child->nodeType === XML_COMMENT_NODE) {
                $node->removeChild($child);
            }
        }
    }

    private static function safeUrl(string $url): bool
    {
        $url = trim($url);
        return (bool)preg_match('#^(https?://|/|\#|mailto:|tel:)#i', $url) && !preg_match('#^\s*javascript:#i', $url);
    }

    /** Chuyển văn bản thuần (ô textarea) sang đoạn HTML an toàn. */
    public static function fromText(?string $text): string
    {
        $text = trim((string)$text);
        if ($text === '') {
            return '';
        }
        $parts = preg_split('/\n{2,}/', $text) ?: [];
        return implode('', array_map(fn($p) => '<p>' . nl2br(e(trim($p))) . '</p>', $parts));
    }
}
