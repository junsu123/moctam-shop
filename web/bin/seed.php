<?php
declare(strict_types=1);

/**
 * Dữ liệu mẫu cho bốn nhóm hàng (hồ sơ bàn giao).
 *   php bin/seed.php           — danh mục, sản phẩm, kho, vùng giao, ưu đãi, FAQ, trang chính sách, blog
 *   php bin/seed.php --demo-users — thêm tài khoản nhân viên mẫu (CHỈ dùng môi trường thử)
 * LƯU Ý: thành phần/dị ứng/cách dùng là dữ liệu MẪU — xưởng phải thay bằng thông tin nhãn thật trước khi mở bán.
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Clock;
use App\Core\Db;
use App\Core\Html;
use App\Core\Text;
use App\Domain\CatalogService;

if ((int)Db::val('SELECT COUNT(*) FROM products') > 0 && !in_array('--force', $argv, true)) {
    echo "Đã có sản phẩm — bỏ qua (dùng --force để vẫn chạy).\n";
    exit(0);
}
$now = Clock::nowDb();
$imgDir = BASE_ROOT . '/public_html/assets/img/products';
if (!is_dir($imgDir)) mkdir($imgDir, 0755, true);

// ------------------------------------------------------------ danh mục
$cats = [
    ['Trà túi lọc', 'tra-tui-loc', 'Trà thảo mộc, trà hoa sấy lạnh đóng túi lọc tiện dụng.', 30],
    ['Bột ngũ cốc', 'bot-ngu-coc', 'Ngũ cốc rang xay mịn cho bữa sáng nhanh, đủ chất.', 30],
    ['Bột thiên nhiên', 'bot-thien-nhien', 'Bột rau củ, lá, hoa sấy lạnh nghiền mịn.', 45],
    ['Cà phê', 'ca-phe', 'Cà phê rang mộc, không tẩm ướp.', 21],
];
$catIds = [];
foreach ($cats as $i => [$name, $slug, $desc, $days]) {
    $catIds[$slug] = Db::insert('categories', ['name' => $name, 'slug' => $slug, 'description' => $desc, 'repurchase_days' => $days, 'sort_order' => $i]);
}

// ------------------------------------------------------------ sản phẩm
// [danh mục, tên, mô tả ngắn, thành phần, cách dùng, bảo quản, dị ứng, từ khóa, nổi bật, [[sku, quy cách, gram, giá, tồn], ...]]
$P = [
 ['tra-tui-loc','Trà gừng mật ong','Ấm bụng, dễ uống cho ngày se lạnh.','Gừng sẻ sấy lạnh 70%, mật ong sấy khô 20%, cam thảo 10%.','Hãm 1 túi với 150–200ml nước sôi 3–5 phút.','Nơi khô ráo, tránh ánh nắng. Đậy kín sau khi mở.','Chứa mật ong — không dùng cho trẻ dưới 12 tháng.','tra gung, ginger tea',1,[['TRA-GUNG-20','Hộp 20 túi x 2g',40,65000,120],['TRA-GUNG-50','Túi 50 túi x 2g',100,145000,60]]],
 ['tra-tui-loc','Trà atiso Đà Lạt','Thanh mát, vị ngọt hậu tự nhiên.','Bông và lá atiso Đà Lạt 85%, rễ atiso 15%.','Hãm 1 túi với 200ml nước sôi 5 phút, dùng nóng hoặc đá.','Nơi khô ráo, nhiệt độ phòng.','Không có thành phần gây dị ứng phổ biến theo nhãn.','atiso, artichoke',1,[['TRA-ATISO-25','Hộp 25 túi x 2g',50,59000,150],['TRA-ATISO-100','Túi 100 túi x 2g',200,199000,40]]],
 ['tra-tui-loc','Trà hoa cúc','Hương dịu, dễ thư giãn buổi tối.','Hoa cúc vàng sấy 100%.','Hãm 1 túi với 200ml nước 90°C trong 3–4 phút.','Nơi khô ráo, tránh ẩm.','Người dị ứng họ Cúc nên tham khảo ý kiến bác sĩ.','hoa cuc, chamomile',0,[['TRA-CUC-20','Hộp 20 túi x 1,5g',30,69000,90]]],
 ['tra-tui-loc','Trà gạo lứt rang','Thơm mùi gạo rang, uống thay nước hằng ngày.','Gạo lứt đỏ rang 80%, đậu đen xanh lòng rang 20%.','Hãm 1–2 túi với 300ml nước sôi 5–7 phút.','Nơi khô ráo, đậy kín.','Có đậu đen.','gao lut, brown rice tea',1,[['TRA-GAOLUT-30','Hộp 30 túi x 5g',150,55000,200],['TRA-GAOLUT-60','Túi 60 túi x 5g',300,99000,80]]],
 ['tra-tui-loc','Trà lá vối','Vị chát nhẹ, truyền thống miền Bắc.','Lá vối ủ và sấy 100%.','Hãm 1 túi với 250ml nước sôi 5 phút.','Nơi khô ráo, thoáng mát.','Không có thành phần gây dị ứng phổ biến theo nhãn.','la voi',0,[['TRA-VOI-30','Hộp 30 túi x 3g',90,49000,0]]],
 ['bot-ngu-coc','Bột ngũ cốc 25 loại hạt','Bữa sáng nhanh, nhiều đạm thực vật.','Yến mạch, đậu nành, đậu đỏ, đậu xanh, mè đen, hạt sen, óc chó, hạnh nhân, gạo lứt… (25 loại).','Pha 30g với 150ml nước ấm 60–70°C, khuấy đều.','Đậy kín, nơi khô ráo; dùng trong 30 ngày sau khi mở.','Chứa đậu nành, gluten (yến mạch), hạt cây (óc chó, hạnh nhân), mè.','ngu coc, granola, bot dinh duong',1,[['NC-25H-500','Túi 500g',500,159000,70],['NC-25H-1KG','Hũ 1kg',1000,289000,35]]],
 ['bot-ngu-coc','Bột ngũ cốc lợi sữa','Công thức cho mẹ sau sinh.','Đậu đen, đậu xanh, gạo lứt, mè đen, hạt sen, đậu nành.','Pha 30g với 150ml nước ấm, ngày 2–3 lần.','Đậy kín sau khi mở.','Chứa đậu nành, mè.','loi sua, me bau',0,[['NC-LOISUA-500','Túi 500g',500,169000,50]]],
 ['bot-ngu-coc','Bột yến mạch nguyên cám','Mịn, không đường, dễ pha.','Yến mạch nguyên cám 100%.','Pha 3 thìa với nước ấm hoặc sữa, hoặc nấu cháo 3 phút.','Nơi khô ráo, đậy kín.','Chứa gluten (yến mạch có thể nhiễm chéo lúa mì).','yen mach, oat',0,[['NC-YENMACH-400','Túi 400g',400,89000,100]]],
 ['bot-ngu-coc','Bột đậu nành rang','Thơm béo, giàu đạm.','Đậu nành hạt rang 100%.','Pha 25g với 200ml nước ấm.','Đậy kín, nơi khô ráo.','Chứa đậu nành.','dau nanh, soy',0,[['NC-DAUNANH-500','Túi 500g',500,79000,80]]],
 ['bot-thien-nhien','Bột matcha Thái Nguyên','Màu xanh tự nhiên, pha latte, làm bánh.','Lá trà xanh Thái Nguyên che nắng, sấy lạnh, nghiền mịn 100%.','Rây 2g bột, đánh với 60ml nước 75°C rồi thêm sữa/đá.','Ngăn mát tủ lạnh sau khi mở, đậy kín, tránh ánh sáng.','Có caffeine.','matcha, tra xanh',1,[['BTN-MATCHA-50','Hũ 50g',50,95000,60],['BTN-MATCHA-100','Túi 100g',100,175000,30]]],
 ['bot-thien-nhien','Bột nghệ vàng nguyên chất','Nghệ vàng sấy lạnh, mịn, thơm.','Củ nghệ vàng 100%.','Pha 1 thìa cà phê với nước ấm và mật ong, hoặc dùng nấu ăn.','Nơi khô ráo, tránh ánh nắng.','Không có thành phần gây dị ứng phổ biến theo nhãn.','nghe, turmeric',0,[['BTN-NGHE-100','Hũ 100g',100,65000,90],['BTN-NGHE-250','Túi 250g',250,145000,40]]],
 ['bot-thien-nhien','Bột cần tây sấy lạnh','Tiện pha nước ép xanh mỗi sáng.','Cần tây sấy lạnh 100%.','Pha 3–5g với 200ml nước lọc hoặc nước ép.','Đậy kín, nơi khô ráo, dùng trong 45 ngày sau khi mở.','Cần tây là chất gây dị ứng ở một số người.','can tay, celery',0,[['BTN-CANTAY-60','Hộp 20 gói x 3g',60,129000,45]]],
 ['bot-thien-nhien','Bột tía tô','Thơm dịu, dùng pha uống hoặc làm đẹp.','Lá tía tô sấy lạnh 100%.','Pha 3g với 200ml nước ấm.','Đậy kín, nơi khô ráo.','Không có thành phần gây dị ứng phổ biến theo nhãn.','tia to, perilla',0,[['BTN-TIATO-100','Hũ 100g',100,85000,55]]],
 ['ca-phe','Cà phê Robusta rang mộc','Đậm, đắng sâu, hợp pha phin.','100% Robusta Đắk Lắk, rang mộc mức vừa, không tẩm ướp.','Pha phin 20–25g với 70ml nước 92–96°C.','Đóng kín van một chiều, nơi mát; dùng tốt nhất trong 4 tuần sau rang.','Có caffeine.','robusta, ca phe phin',1,[['CF-ROB-250-XAY','Túi 250g – xay pha phin',250,85000,100],['CF-ROB-500-HAT','Túi 500g – nguyên hạt',500,155000,60]]],
 ['ca-phe','Cà phê Arabica Cầu Đất','Chua thanh, hương trái cây.','100% Arabica Cầu Đất, rang vừa nhạt.','Pha pour-over 15g/250ml nước 90°C hoặc pha phin.','Đóng kín, nơi mát, tránh ánh sáng.','Có caffeine.','arabica, cau dat, pour over',1,[['CF-ARA-250-HAT','Túi 250g – nguyên hạt',250,145000,40],['CF-ARA-250-XAY','Túi 250g – xay pha phin',250,145000,25]]],
 ['ca-phe','Cà phê phin giấy tiện lợi','Pha nhanh mọi nơi, không cần phin.','Robusta 70%, Arabica 30%, rang mộc.','Treo phin giấy lên cốc, rót 120ml nước sôi làm 3 lần.','Nơi khô ráo, đóng kín.','Có caffeine.','phin giay, drip bag',0,[['CF-DRIP-10','Hộp 10 gói x 12g',120,79000,70]]],
];

$palette = [
    'tra-tui-loc' => ['#e8f0e3', '#5b7f4a', '#c9dcbf'],
    'bot-ngu-coc' => ['#f5ead8', '#a0743c', '#e8d4b3'],
    'bot-thien-nhien' => ['#eaf2df', '#6e8f2f', '#d3e4bb'],
    'ca-phe' => ['#efe4dc', '#5a3a28', '#d9c3b3'],
];
$productIds = [];
$skuIds = [];
foreach ($P as $idx => [$cat, $name, $short, $ingr, $usage, $storage, $allergen, $kw, $featured, $skus]) {
    $slug = Text::slug($name);
    $pid = Db::insert('products', [
        'category_id' => $catIds[$cat], 'name' => $name, 'slug' => $slug, 'short_desc' => $short,
        'description' => Html::sanitize('<p>' . e($short) . '</p><p>Sản phẩm được ' . e(setting('store_name')) . ' sơ chế và đóng gói tại xưởng, kiểm soát nguyên liệu theo từng mẻ.</p>'),
        'ingredients' => $ingr, 'usage_guide' => $usage, 'storage_guide' => $storage, 'allergens' => $allergen,
        'status' => 'active', 'is_featured' => $featured, 'search_text' => '', 'keywords' => $kw,
        'created_at' => Clock::db(Clock::now()->modify('-' . (40 - $idx) . ' days')), 'updated_at' => $now,
    ]);
    $productIds[$slug] = $pid;
    file_put_contents("$imgDir/$slug.svg", product_svg($cat, $name, $palette[$cat]));
    Db::insert('product_images', ['product_id' => $pid, 'path' => "/assets/img/products/$slug.svg", 'alt' => $name, 'sort_order' => 0]);
    foreach ($skus as $j => [$code, $label, $grams, $price, $stock]) {
        $sid = Db::insert('skus', ['product_id' => $pid, 'sku_code' => $code, 'variant_label' => $label, 'net_weight_g' => $grams, 'price' => $price, 'status' => 'active', 'sort_order' => $j, 'created_at' => $now, 'updated_at' => $now]);
        $skuIds[$code] = $sid;
        Db::insert('inventory', ['sku_id' => $sid, 'on_hand' => $stock, 'reserved' => 0, 'updated_at' => $now]);
        if ($stock > 0) {
            Db::insert('inventory_movements', ['sku_id' => $sid, 'type' => 'receive', 'on_hand_delta' => $stock, 'reserved_delta' => 0, 'on_hand_after' => $stock, 'reserved_after' => 0, 'reason' => 'Tồn đầu kỳ (dữ liệu mẫu)', 'created_at' => $now]);
        }
    }
    CatalogService::refreshSearchText($pid);
}

// Mua kèm (nhân viên duyệt sẵn)
$rel = [
    ['tra-gung-mat-ong', 'tra-hoa-cuc'], ['tra-gung-mat-ong', 'bot-nghe-vang-nguyen-chat'],
    ['bot-ngu-coc-25-loai-hat', 'bot-yen-mach-nguyen-cam'], ['bot-ngu-coc-25-loai-hat', 'bot-matcha-thai-nguyen'],
    ['ca-phe-robusta-rang-moc', 'ca-phe-phin-giay-tien-loi'], ['ca-phe-arabica-cau-dat', 'ca-phe-robusta-rang-moc'],
    ['bot-matcha-thai-nguyen', 'bot-yen-mach-nguyen-cam'], ['tra-atiso-da-lat', 'tra-gao-lut-rang'],
];
foreach ($rel as $k => [$a, $b]) {
    Db::insert('product_relations', ['product_id' => $productIds[$a], 'related_product_id' => $productIds[$b], 'source' => 'staff', 'status' => 'approved', 'sort_order' => $k, 'created_at' => $now]);
}

// ------------------------------------------------------------ vùng giao (34 tỉnh/thành sau sắp xếp 2025)
$zones = [
    ['Hà Nội', ['Hà Nội'], '1–2 ngày', 20000, 400000],
    ['Miền Bắc', ['Hải Phòng', 'Quảng Ninh', 'Bắc Ninh', 'Hưng Yên', 'Ninh Bình', 'Phú Thọ', 'Thái Nguyên', 'Tuyên Quang', 'Lào Cai', 'Lạng Sơn', 'Cao Bằng', 'Điện Biên', 'Lai Châu', 'Sơn La'], '2–3 ngày', 30000, 500000],
    ['Miền Trung', ['Thanh Hóa', 'Nghệ An', 'Hà Tĩnh', 'Quảng Trị', 'Huế', 'Đà Nẵng', 'Quảng Ngãi', 'Gia Lai', 'Khánh Hòa', 'Đắk Lắk', 'Lâm Đồng'], '3–4 ngày', 35000, 500000],
    ['Miền Nam', ['TP. Hồ Chí Minh', 'Đồng Nai', 'Tây Ninh', 'Cần Thơ', 'Vĩnh Long', 'Đồng Tháp', 'An Giang', 'Cà Mau'], '3–5 ngày', 35000, 500000],
];
foreach ($zones as $i => [$zn, $provs, $eta, $fee, $free]) {
    $zid = Db::insert('shipping_zones', ['name' => $zn, 'provinces' => json_enc($provs), 'eta_text' => $eta, 'is_active' => 1, 'sort_order' => $i]);
    Db::insert('shipping_rates', ['zone_id' => $zid, 'fee' => $fee, 'free_from' => $free, 'effective_from' => Clock::db(Clock::now()->modify('-365 days')), 'created_at' => $now]);
}

// ------------------------------------------------------------ ưu đãi
Db::insert('vouchers', ['code' => 'CHAOBAN20', 'description' => 'Giảm 20.000đ cho đơn từ 150.000đ', 'amount' => 20000, 'min_subtotal' => 150000, 'scope_type' => 'all', 'scope_ids' => '[]',
    'starts_at' => Clock::db(Clock::now()->modify('-7 days')), 'ends_at' => Clock::db(Clock::now()->modify('+90 days')), 'usage_limit' => 500, 'is_active' => 1, 'created_at' => $now, 'updated_at' => $now]);
Db::insert('vouchers', ['code' => 'CAPHE15', 'description' => 'Giảm 15.000đ cho cà phê từ 150.000đ', 'amount' => 15000, 'min_subtotal' => 150000, 'scope_type' => 'category', 'scope_ids' => json_enc([$catIds['ca-phe']]),
    'starts_at' => Clock::db(Clock::now()->modify('-7 days')), 'ends_at' => Clock::db(Clock::now()->modify('+60 days')), 'usage_limit' => 200, 'is_active' => 1, 'created_at' => $now, 'updated_at' => $now]);
$fs = Db::insert('flash_sales', ['name' => 'Flash Sale cuối tuần', 'starts_at' => Clock::db(Clock::now()->modify('-1 hour')), 'ends_at' => Clock::db(Clock::now()->modify('+3 days')), 'allow_voucher' => 0, 'is_active' => 1, 'created_at' => $now, 'updated_at' => $now]);
foreach (['TRA-GUNG-20' => 52000, 'NC-25H-500' => 135000, 'CF-ROB-250-XAY' => 72000, 'BTN-MATCHA-50' => 79000] as $code => $price) {
    Db::insert('flash_sale_items', ['flash_sale_id' => $fs, 'sku_id' => $skuIds[$code], 'sale_price' => $price]);
}

// ------------------------------------------------------------ nội dung
function seed_content(string $kind, string $title, string $body, ?int $catId = null, ?int $pid = null, ?string $slug = null): void
{
    $now = Clock::nowDb();
    $slug ??= Text::slug($title);
    if (Db::val('SELECT 1 FROM contents WHERE kind = :k AND slug = :s', ['k' => $kind, 's' => $slug])) {
        return; // đã có (VD: trang pháp lý do migration 004 tạo)
    }
    $body = Html::sanitize($body);
    $cid = Db::insert('contents', ['kind' => $kind, 'slug' => $slug, 'status' => 'published', 'source' => 'staff', 'category_id' => $catId, 'product_id' => $pid, 'created_at' => $now, 'updated_at' => $now]);
    $vid = Db::insert('content_versions', ['content_id' => $cid, 'version_no' => 1, 'title' => $title, 'meta_description' => Text::excerpt($body, 155), 'body' => $body, 'created_source' => 'staff', 'created_at' => $now]);
    Db::update('contents', ['current_version_id' => $vid, 'published_version_id' => $vid, 'pub_title' => $title, 'pub_meta_description' => Text::excerpt($body, 155),
        'pub_body' => $body, 'pub_search_text' => Text::fold($title . ' ' . Text::excerpt($body, 600)), 'published_at' => $now], 'id = :id', ['id' => $cid]);
}

$faqs = [
    ['Phí giao hàng được tính thế nào?', '<p>Phí giao hàng tính theo vùng: Hà Nội 20.000đ, Miền Bắc 30.000đ, Miền Trung và Miền Nam 35.000đ. Đơn đủ mức miễn phí theo vùng sẽ được miễn phí giao. Tổng tiền chính xác hiển thị ở giỏ hàng sau khi bạn chọn tỉnh/thành.</p>'],
    ['Bao lâu thì tôi nhận được hàng?', '<p>Thời gian giao dự kiến: Hà Nội 1–2 ngày, Miền Bắc 2–3 ngày, Miền Trung 3–4 ngày, Miền Nam 3–5 ngày kể từ khi đơn được xác nhận.</p>'],
    ['Thanh toán chuyển khoản VietQR như thế nào?', '<p>Sau khi đặt hàng, trang xác nhận hiển thị mã QR kèm đúng số tiền và nội dung chuyển khoản là mã đơn. Bạn quét bằng ứng dụng ngân hàng và giữ nguyên nội dung. Nhân viên đối soát xác nhận khi tiền về tài khoản, sau đó đơn mới được chuẩn bị giao.</p>'],
    ['Tôi chuyển khoản thiếu hoặc sai nội dung thì sao?', '<p>Khoản chuyển thiếu, thừa, sai nội dung hoặc sau hạn sẽ được nhân viên đối soát kiểm tra và liên hệ bạn để thống nhất: bổ sung, hoàn tiền hoặc tạo đơn thay thế.</p>'],
    ['Có được thanh toán khi nhận hàng (COD) không?', '<p>Có. Bạn chọn COD ở bước thanh toán và trả tiền mặt cho người giao hàng. Xưởng sẽ gọi xác nhận đơn trước khi giao.</p>'],
    ['Chính sách đổi trả ra sao?', '<p>Sản phẩm lỗi do đóng gói, vận chuyển hoặc hết hạn được đổi mới hoặc hoàn tiền. Vui lòng quay video khi mở hàng và liên hệ trong 3 ngày kể từ khi nhận. Chi tiết xem trang Chính sách đổi trả.</p>'],
    ['Bảo quản bột ngũ cốc sau khi mở thế nào?', '<p>Đậy kín túi/hũ, để nơi khô ráo thoáng mát, tránh ánh nắng và dùng thìa khô. Nên dùng hết trong khoảng 30 ngày sau khi mở để giữ hương vị.</p>'],
    ['Trẻ em có dùng được bột ngũ cốc không?', '<p>Trẻ từ 1 tuổi có thể dùng lượng nhỏ, pha loãng. Bột có chứa đậu nành, hạt cây và gluten — nếu bé có tiền sử dị ứng, vui lòng hỏi ý kiến bác sĩ trước khi dùng.</p>'],
    ['Cà phê có tẩm ướp hương liệu không?', '<p>Không. Cà phê của xưởng rang mộc 100%, không bơ, không đường, không hương liệu.</p>'],
    ['Pha trà túi lọc bao lâu là ngon?', '<p>Trà thảo mộc hãm với nước sôi 3–5 phút; trà hoa (hoa cúc) nên dùng nước khoảng 90°C. Có thể hãm lại lần hai.</p>'],
    ['Mã giảm giá có dùng chung với Flash Sale không?', '<p>Mỗi đơn dùng một mã giảm giá. Sản phẩm đang Flash Sale có thể không được tính vào điều kiện của mã, tùy quy tắc từng chương trình; giỏ hàng sẽ hiển thị chính xác số tiền được giảm.</p>'],
];
foreach ($faqs as [$q, $a]) seed_content('faq', $q, $a);

$draftNote = '<p><em>Bản mẫu — xưởng cần rà soát và xác nhận nội dung theo quy định áp dụng trước khi mở bán.</em></p>';
seed_content('page', 'Chính sách giao hàng', '<h2>Phạm vi giao hàng</h2><p>Giao toàn quốc theo các vùng được cấu hình. Phí giao hiển thị tại giỏ hàng theo tỉnh/thành.</p><h2>Thời gian</h2><p>1–5 ngày làm việc tùy vùng, tính từ khi đơn được xác nhận.</p>' . $draftNote, null, null, 'giao-hang');
seed_content('page', 'Chính sách thanh toán', '<h2>Hình thức</h2><ul><li>COD — thanh toán khi nhận hàng.</li><li>Chuyển khoản VietQR — nội dung chuyển khoản là mã đơn.</li></ul><p>Đơn VietQR được giữ hàng 24 giờ; quá hạn chưa nhận tiền, đơn tự hủy.</p>' . $draftNote, null, null, 'thanh-toan');
seed_content('page', 'Chính sách đổi trả', '<h2>Điều kiện</h2><p>Đổi/hoàn tiền cho sản phẩm lỗi do sản xuất, đóng gói hoặc vận chuyển, báo trong 3 ngày kể từ khi nhận kèm video mở hàng.</p><h2>Hoàn tiền</h2><p>Hoàn qua chuyển khoản trong 3–5 ngày làm việc sau khi xưởng nhận và kiểm hàng.</p>' . $draftNote, null, null, 'doi-tra');
seed_content('page', 'Chính sách bảo mật', '<h2>Dữ liệu thu thập</h2><p>Họ tên, số điện thoại, địa chỉ giao hàng — chỉ dùng để xử lý và giao đơn. Chỉ gửi thông tin chăm sóc/ưu đãi khi bạn đồng ý.</p><h2>Quyền của bạn</h2><p>Bạn có thể yêu cầu xem, sửa hoặc xóa dữ liệu qua kênh liên hệ.</p>' . $draftNote, null, null, 'bao-mat');
seed_content('page', 'Liên hệ', '<p>Hotline / Zalo và địa chỉ xưởng được cập nhật trong trang quản trị → Cấu hình.</p>', null, null, 'lien-he');

seed_content('blog', '5 cách pha trà gừng mật ong ngon cho ngày lạnh', '<p>Trà gừng mật ong là thức uống quen thuộc mỗi khi trời trở lạnh. Dưới đây là 5 cách pha đơn giản với trà túi lọc.</p><h2>1. Pha nóng truyền thống</h2><p>Hãm 1 túi với 200ml nước sôi trong 5 phút.</p><h2>2. Thêm lát chanh</h2><p>Vắt vài giọt chanh để vị tươi hơn.</p><h2>3. Trà gừng sữa</h2><p>Hãm đậm với 100ml nước rồi thêm 100ml sữa nóng.</p><h2>4. Trà gừng quế</h2><p>Thêm một thanh quế nhỏ khi hãm.</p><h2>5. Trà gừng đá</h2><p>Hãm đậm, để nguội rồi thêm đá.</p>', $catIds['tra-tui-loc'], $productIds['tra-gung-mat-ong']);
seed_content('blog', 'Robusta hay Arabica: chọn cà phê nào cho phin?', '<p>Robusta đậm và đắng, nhiều caffeine; Arabica chua thanh, hương trái cây. Với phin truyền thống, Robusta rang mộc cho ly cà phê đậm đà; nếu thích nhẹ nhàng, hãy thử phối 70/30.</p><h2>Gợi ý tỷ lệ</h2><ul><li>Phin 20–25g cà phê, 70ml nước 92–96°C.</li><li>Pour-over Arabica: 15g cho 250ml nước 90°C.</li></ul>', $catIds['ca-phe'], $productIds['ca-phe-robusta-rang-moc']);

echo "Đã nạp dữ liệu mẫu: " . count($P) . " sản phẩm, " . count($skuIds) . " SKU, 4 vùng giao, 2 voucher, 1 Flash Sale, " . count($faqs) . " FAQ.\n";

if (in_array('--demo-users', $argv, true)) {
    $users = [
        ['admin@xuong.local', 'Quản trị viên', 'admin'], ['vanhanh@xuong.local', 'Nhân viên vận hành', 'operations'],
        ['kho@xuong.local', 'Nhân viên kho', 'warehouse'], ['doisoat@xuong.local', 'Nhân viên đối soát', 'reconciliation'],
        ['noidung@xuong.local', 'Nhân viên nội dung', 'content'],
    ];
    foreach ($users as [$em, $nm, $role]) {
        Db::run('INSERT IGNORE INTO users (email, full_name, password_hash, role_code, created_at, updated_at) VALUES (:e,:n,:p,:r,:t,:t2)',
            ['e' => $em, 'n' => $nm, 'p' => password_hash('Demo@12345', PASSWORD_DEFAULT), 'r' => $role, 't' => $now, 't2' => $now]);
    }
    echo "Tài khoản mẫu (mật khẩu Demo@12345): " . implode(', ', array_column($users, 0)) . "\n";
}

function product_svg(string $cat, string $name, array $c): string
{
    [$bg, $main, $soft] = $c;
    $art = match ($cat) {
        'tra-tui-loc' => <<<SVG
<g transform="translate(200 210)">
  <path d="M-70 -20 h140 a20 20 0 0 1 20 20 v40 a70 70 0 0 1 -70 70 h-40 a70 70 0 0 1 -70 -70 v-40 a20 20 0 0 1 20 -20z" fill="#fff" stroke="$main" stroke-width="6"/>
  <path d="M90 10 a28 28 0 0 1 0 56" fill="none" stroke="$main" stroke-width="6"/>
  <path d="M-30 -60 q10 -20 0 -40 M0 -60 q10 -20 0 -40 M30 -60 q10 -20 0 -40" stroke="$main" stroke-width="5" fill="none" stroke-linecap="round" opacity=".5"/>
  <line x1="40" y1="-20" x2="70" y2="-90" stroke="$main" stroke-width="3"/>
  <rect x="58" y="-118" width="34" height="30" rx="4" fill="$soft" stroke="$main" stroke-width="3"/>
  <ellipse cx="0" cy="18" rx="62" ry="10" fill="$soft"/>
</g>
SVG,
        'bot-ngu-coc' => <<<SVG
<g transform="translate(200 220)">
  <path d="M-100 -10 h200 a100 90 0 0 1 -200 0z" fill="#fff" stroke="$main" stroke-width="6"/>
  <ellipse cx="0" cy="-10" rx="100" ry="18" fill="$soft" stroke="$main" stroke-width="6"/>
  <g fill="$main" opacity=".8"><ellipse cx="-40" cy="-14" rx="9" ry="5"/><ellipse cx="-10" cy="-8" rx="9" ry="5" transform="rotate(30 -10 -8)"/><ellipse cx="25" cy="-15" rx="9" ry="5"/><ellipse cx="55" cy="-9" rx="9" ry="5" transform="rotate(-25 55 -9)"/><circle cx="5" cy="-20" r="4"/><circle cx="-60" cy="-8" r="4"/></g>
  <path d="M60 -50 q30 -60 70 -70" stroke="$main" stroke-width="5" fill="none" stroke-linecap="round"/>
  <g fill="$main"><ellipse cx="110" cy="-108" rx="10" ry="5" transform="rotate(-30 110 -108)"/><ellipse cx="96" cy="-92" rx="10" ry="5" transform="rotate(-50 96 -92)"/><ellipse cx="124" cy="-96" rx="10" ry="5" transform="rotate(10 124 -96)"/></g>
</g>
SVG,
        'bot-thien-nhien' => <<<SVG
<g transform="translate(200 215)">
  <rect x="-65" y="-80" width="130" height="160" rx="22" fill="#fff" stroke="$main" stroke-width="6"/>
  <rect x="-75" y="-105" width="150" height="34" rx="10" fill="$main"/>
  <rect x="-45" y="-30" width="90" height="60" rx="8" fill="$soft"/>
  <path d="M-20 10 q20 -50 45 -40 q-5 45 -45 40z" fill="$main" opacity=".85"/>
  <path d="M-20 10 q15 -20 30 -30" stroke="#fff" stroke-width="2" fill="none"/>
  <path d="M-110 80 q40 -30 80 0 q-40 18 -80 0z" fill="$soft" stroke="$main" stroke-width="4"/>
</g>
SVG,
        default => <<<SVG
<g transform="translate(200 215)">
  <path d="M-70 -90 h140 l10 170 a10 10 0 0 1 -10 10 h-140 a10 10 0 0 1 -10 -10z" fill="#fff" stroke="$main" stroke-width="6"/>
  <path d="M-70 -90 l10 -20 h120 l10 20" fill="$soft" stroke="$main" stroke-width="6" stroke-linejoin="round"/>
  <g transform="translate(0 0)"><ellipse cx="0" cy="10" rx="34" ry="46" fill="$main"/><path d="M0 -34 q-16 44 0 88" stroke="$soft" stroke-width="6" fill="none"/></g>
  <g transform="translate(-105 70) rotate(-30)"><ellipse rx="16" ry="22" fill="$main"/><path d="M0 -20 q-8 20 0 40" stroke="$soft" stroke-width="3" fill="none"/></g>
  <g transform="translate(108 60) rotate(25)"><ellipse rx="16" ry="22" fill="$main"/><path d="M0 -20 q-8 20 0 40" stroke="$soft" stroke-width="3" fill="none"/></g>
</g>
SVG,
    };
    $n = e(mb_strlen($name) > 26 ? mb_substr($name, 0, 25) . '…' : $name);
    return <<<SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" role="img" aria-label="$n">
<rect width="400" height="400" fill="$bg"/>
<circle cx="330" cy="70" r="90" fill="$soft" opacity=".6"/>
<circle cx="60" cy="360" r="70" fill="$soft" opacity=".5"/>
$art
<text x="200" y="372" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif" font-size="22" fill="$main">$n</text>
</svg>
SVG;
}
