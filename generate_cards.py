#!/usr/bin/env python3
from PIL import Image, ImageDraw
import os

OUTPUT_DIR = "/home/user/stock_searching/figma_contents/2026/09"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CARD_W = 1560
HEADER_H = 176
PRICE_H = 144

# Colors (RGB)
C_HEADER_BG = (26, 43, 94)
C_BODY_BG = (245, 247, 255)
C_WHITE = (255, 255, 255)
C_HEADER_TEXT = (255, 255, 255)
C_BODY_TEXT = (45, 45, 45)
C_PRICE_TEXT = (27, 140, 78)
C_GAIN_TEXT = (199, 21, 21)
C_SECTION_TITLE = (26, 43, 94)
C_TICKER_BG = (61, 90, 254)
C_KW_BG = (232, 240, 254)
C_KW_TEXT = (26, 43, 94)
C_BORDER = (224, 224, 224)
C_SUB_TEXT = (160, 180, 220)

companies = [
    {
        "name": "テクノマセマティカル",
        "ticker": "3787.T",
        "industry": "情報・通信業（画像圧縮・映像処理）",
        "market": "東証スタンダード",
        "price": "¥677",
        "weekly": "+107%",
        "market_cap": "非公開（小型株）",
        "per": "非公開", "pbr": "非公開",
        "news": [
            "アバールデータが1株690円で株式交換・完全子会社化（2026-09-14）",
            "週間+107%の急騰 M&A価格への鞘寄せ完成（2026-09-16）",
            "2026年10月1日 東証スタンダード上場廃止予定",
        ],
        "keywords": ["画像圧縮技術(DMNA)", "映像・音声処理", "組込みソフトウェア", "半導体製造装置",
                     "M&A・株式交換", "上場廃止", "アルゴリズムライセンス", "ディープラーニング画像認識"],
        "trends": [
            "画像圧縮技術: 生成AI進展で高解像度映像処理需要が急増",
            "組込みソフト: 半導体市場回復・国産化需要が追い風",
            "M&A: 2026年の日本企業M&A件数59件、非公開化が加速",
        ],
        "filename": "20_テクノマセマティカル",
    },
    {
        "name": "メディシノバ",
        "ticker": "4875.T",
        "industry": "医薬品（バイオベンチャー・創薬）",
        "market": "東証スタンダード/NASDAQ",
        "price": "¥485",
        "weekly": "+79.6%",
        "market_cap": "約111億円",
        "per": "N/A（赤字）", "pbr": "N/A",
        "news": [
            "米国投資家カンファレンス参加・ALS治験データ発表への期待高まる（2026-09）",
            "SEANOBI-ALS試験 患者登録200名完了（2026-07-15）",
            "NIH支援試験 患者登録目標50%到達（2026-01-30）",
        ],
        "keywords": ["ALS治療薬", "イブジラスト(MN-166)", "神経変性疾患治療", "FDA希少疾病薬指定",
                     "バイオベンチャー", "フェーズ2/3臨床試験", "CIPN", "日米ダブル上場"],
        "trends": [
            "ALS治療: 根治療法が乏しくグローバルで臨床試験が進行中",
            "FDA希少疾病薬: 7年間排他的先発販売権・ファストトラック審査短縮",
            "バイオベンチャー: 2026年は日本バイオへの投資が増加",
        ],
        "filename": "20_メディシノバ",
    },
    {
        "name": "I-ne（アイエヌイー）",
        "ticker": "4933.T",
        "industry": "化学（D2Cライフスタイル・ヘアケア）",
        "market": "東証プライム",
        "price": "¥1,681",
        "weekly": "+67.1%",
        "market_cap": "約408億円",
        "per": "データ収集中", "pbr": "2.30倍",
        "news": [
            "上半期決算: 売上+20.1%・営業利益+19.2% 急騰+16.41%（2026-09-15）",
            "粗利率57.6%（前年53.2%） M&A効果で大幅改善",
            "通期売上高520〜540億円見込み (+6.2〜+10.3%)",
        ],
        "keywords": ["D2Cブランド戦略", "ヘアケア市場", "美容家電(SALONIA)", "ライフスタイルブランド",
                     "グローバル展開", "M&Aブランドファーム", "パーソナライズドビューティ", "SNSマーケティング"],
        "trends": [
            "D2C市場: 国内デジタルD2C市場2026年3兆円規模、SNS・EC主導が定着",
            "ヘアケア: グローバルCAGR7.21%成長、プレミアム品需要が拡大",
            "グローバル展開: 中国越境EC・東南アジアEC普及率が上昇",
        ],
        "filename": "20_Ine",
    },
    {
        "name": "リンカーズ",
        "ticker": "5131.T",
        "industry": "IT・サービス（B2Bビジネスマッチング）",
        "market": "東証グロース",
        "price": "¥185",
        "weekly": "+63.72%",
        "market_cap": "約17〜19億円",
        "per": "非公開（赤字）", "pbr": "非公開",
        "news": [
            "SBIホールディングスと資本業務提携・第三者割当増資（2026-09-11）",
            "SBI直接保有13.32%・間接保有含め21.24%の議決権比率",
            "週間+63.72% ストップ高連続後、週末-2.12%の利確売り",
        ],
        "keywords": ["B2Bビジネスマッチング", "ものづくり中小企業", "SaaS(Linkers TX)", "中小企業DX",
                     "SBI提携・フィンテック", "サプライチェーン最適化", "製造業デジタル化", "オープンイノベーション"],
        "trends": [
            "B2Bマッチング: 商談後支援機能強化でワンストップ化が差別化要因",
            "中小企業DX: AI品質検査・予知保全・デジタルツインが2026年トレンド",
            "サプライチェーン: 国内サプライチェーン再構築・国産化ニーズで需要増",
        ],
        "filename": "20_リンカーズ",
    },
    {
        "name": "レオパレス21",
        "ticker": "8848.T",
        "industry": "不動産（アパート建築請負・賃貸管理）",
        "market": "東証プライム",
        "price": "¥1,049",
        "weekly": "+58.30%",
        "market_cap": "約3,511億円",
        "per": "9.76倍", "pbr": "非公開",
        "news": [
            "光通信・MBKパートナーズが1株1,000円でTOB発表 最大2,676億円（2026-09-14）",
            "レオパレス株ストップ高連続 TOB価格1,000円へのサヤ寄せ（2026-09-15〜16）",
            "TOB成立後2027年内に完全非公開化（上場廃止）予定",
        ],
        "keywords": ["賃貸住宅(一括借り上げ)", "不動産TOB・MBO", "非公開化・上場廃止", "住宅管理DX",
                     "光通信・通信サービス統合", "法人向け短期賃貸", "都市部賃貸市場", "サプライチェーン再建"],
        "trends": [
            "賃貸住宅市場: 都心部から郊外へ賃料上昇が波及、物件間格差が二極化",
            "不動産TOB: 2026年は日本TOB案件59件、非公開化案件が急増",
            "通信サービス統合: 光通信の56万室への商材同梱提案が追加収益化の核",
        ],
        "filename": "20_レオパレス21",
    },
]

# Try to load a CJK-capable font
def get_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    from PIL import ImageFont
    return ImageFont.load_default()

def get_bold_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return get_font(size)

def wrap_text(text, font, max_width, draw):
    words = list(text)
    lines = []
    current = ""
    for ch in words:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines

def draw_rounded_rect(draw, x0, y0, x1, y1, radius, fill):
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*radius, y0 + 2*radius], fill=fill)
    draw.ellipse([x1 - 2*radius, y0, x1, y0 + 2*radius], fill=fill)
    draw.ellipse([x0, y1 - 2*radius, x0 + 2*radius, y1], fill=fill)
    draw.ellipse([x1 - 2*radius, y1 - 2*radius, x1, y1], fill=fill)

def render_card(company):
    PAD = 40
    SEC_PAD = 24
    LINE_H_SM = 36
    LINE_H_LG = 44

    # Estimate height
    font_reg_sm = get_font(22)
    font_reg_md = get_font(26)
    font_bold_lg = get_bold_font(36)
    font_bold_xl = get_bold_font(44)
    font_bold_xxl = get_bold_font(52)
    font_semi_md = get_font(28)

    # Build sections
    news_h = 72 + len(company["news"]) * 42 + SEC_PAD
    kw_x = PAD
    kw_y_start = 0
    kw_line_h = 52
    kw_rows = 1
    temp_x = PAD
    for kw in company["keywords"]:
        kw_len = len(kw) * 18 + 32
        if temp_x + kw_len > CARD_W - PAD:
            kw_rows += 1
            temp_x = PAD
        temp_x += kw_len + 12
    kw_h = 72 + kw_rows * kw_line_h + SEC_PAD
    trends_h = 72 + len(company["trends"]) * 52 + SEC_PAD

    total_h = HEADER_H + PRICE_H + news_h + kw_h + trends_h + 40
    img = Image.new("RGB", (CARD_W, total_h), C_WHITE)
    draw = ImageDraw.Draw(img)

    y = 0

    # === HEADER ===
    draw.rectangle([0, 0, CARD_W, HEADER_H], fill=C_HEADER_BG)
    name_font = get_bold_font(48)
    draw.text((PAD, 28), company["name"], font=name_font, fill=C_HEADER_TEXT)
    # Ticker badge
    ticker_font = get_bold_font(28)
    t_bbox = draw.textbbox((0, 0), company["ticker"], font=ticker_font)
    t_w = t_bbox[2] - t_bbox[0] + 32
    t_h = t_bbox[3] - t_bbox[1] + 16
    t_x = CARD_W - t_w - PAD
    t_y = 30
    draw_rounded_rect(draw, t_x, t_y, t_x + t_w, t_y + t_h, 8, C_TICKER_BG)
    draw.text((t_x + 16, t_y + 8), company["ticker"], font=ticker_font, fill=C_HEADER_TEXT)
    # Sub info
    sub_font = get_font(24)
    sub_text = company["market"] + "  |  " + company["industry"]
    draw.text((PAD, HEADER_H - 42), sub_text, font=sub_font, fill=C_SUB_TEXT)
    y = HEADER_H

    # === PRICE SECTION ===
    draw.rectangle([0, y, CARD_W, y + PRICE_H], fill=C_BODY_BG)
    lbl_font = get_font(22)
    val_font_price = get_bold_font(52)
    val_font_gain = get_bold_font(52)
    draw.text((PAD, y + 14), "現在値", font=lbl_font, fill=C_SECTION_TITLE)
    draw.text((PAD, y + 42), company["price"], font=val_font_price, fill=C_PRICE_TEXT)
    draw.text((360, y + 14), "週間騰落率", font=lbl_font, fill=C_SECTION_TITLE)
    draw.text((360, y + 42), company["weekly"], font=val_font_gain, fill=C_GAIN_TEXT)
    mc_font = get_font(24)
    draw.text((800, y + 20), "時価総額: " + company["market_cap"], font=mc_font, fill=C_BODY_TEXT)
    draw.text((800, y + 56), "PER: " + company["per"] + "   PBR: " + company["pbr"], font=mc_font, fill=C_BODY_TEXT)
    y += PRICE_H

    # Separator
    draw.line([0, y, CARD_W, y], fill=C_BORDER, width=2)

    # === NEWS SECTION ===
    draw.rectangle([0, y, CARD_W, y + news_h], fill=C_WHITE)
    sec_font = get_bold_font(32)
    draw.text((PAD, y + 18), "最新ニュース", font=sec_font, fill=C_SECTION_TITLE)
    ny = y + 66
    bullet_font = get_font(26)
    for news in company["news"]:
        lines = wrap_text("•  " + news, bullet_font, CARD_W - PAD * 2 - 20, draw)
        for ln in lines:
            draw.text((PAD + 10, ny), ln, font=bullet_font, fill=C_BODY_TEXT)
            ny += 36
        ny += 4
    y += news_h

    draw.line([0, y, CARD_W, y], fill=C_BORDER, width=2)

    # === KEYWORDS SECTION ===
    kw_sec_h = 72 + kw_rows * kw_line_h + SEC_PAD
    draw.rectangle([0, y, CARD_W, y + kw_sec_h], fill=C_BODY_BG)
    draw.text((PAD, y + 18), "業界キーワード", font=sec_font, fill=C_SECTION_TITLE)
    kx = PAD
    ky = y + 66
    kw_font = get_font(24)
    for kw in company["keywords"]:
        kw_bbox = draw.textbbox((0, 0), kw, font=kw_font)
        kw_w = kw_bbox[2] - kw_bbox[0] + 32
        kw_h_val = kw_bbox[3] - kw_bbox[1] + 16
        if kx + kw_w > CARD_W - PAD:
            kx = PAD
            ky += kw_line_h
        draw_rounded_rect(draw, kx, ky, kx + kw_w, ky + kw_h_val, 6, C_KW_BG)
        draw.text((kx + 16, ky + 8), kw, font=kw_font, fill=C_KW_TEXT)
        kx += kw_w + 12
    y += kw_sec_h

    draw.line([0, y, CARD_W, y], fill=C_BORDER, width=2)

    # === TRENDS SECTION ===
    draw.rectangle([0, y, CARD_W, y + trends_h + 40], fill=C_WHITE)
    draw.text((PAD, y + 18), "キーワード別 業界トレンド", font=sec_font, fill=C_SECTION_TITLE)
    ty = y + 68
    for trend in company["trends"]:
        lines = wrap_text("▸  " + trend, bullet_font, CARD_W - PAD * 2 - 20, draw)
        for ln in lines:
            draw.text((PAD + 10, ty), ln, font=bullet_font, fill=C_BODY_TEXT)
            ty += 36
        ty += 10
    y += trends_h + 40

    # Footer label
    footer_font = get_font(20)
    draw.text((PAD, y - 30), "Figma: 株式情報デザインカード_20260920 | 2026-09-20 JST", font=footer_font, fill=C_BORDER)

    # Save
    out_path = os.path.join(OUTPUT_DIR, company["filename"] + ".png")
    img.save(out_path, "PNG")
    print(f"Saved: {out_path}")
    return out_path

saved = []
for c in companies:
    path = render_card(c)
    saved.append(path)

print("\nAll done:")
for p in saved:
    print(f"  {p}")
