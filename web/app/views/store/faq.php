<section class="wrap py-10">
  <h1 class="text-3xl">Hỏi đáp</h1>
  <p class="mt-2 max-w-[60ch] text-ink-soft">Không thấy câu trả lời? Bấm "Hỏi xưởng" ở góc màn hình hoặc gọi <?= e(setting('hotline')) ?>.</p>
  <div class="mt-8 max-w-3xl divide-y divide-ink/10 rounded-xl bg-white">
    <?php foreach ($faqs as $f): ?>
      <details class="group px-5 py-4" id="<?= e($f['slug']) ?>">
        <summary class="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold"><?= e($f['pub_title']) ?><span class="text-ink-mute transition-transform group-open:rotate-45" aria-hidden="true">+</span></summary>
        <div class="prose-x mt-2"><?= $f['pub_body'] ?></div>
      </details>
    <?php endforeach; ?>
  </div>
</section>
