"""
Seed data for the initial migration. Matches docs/03, docs/06, docs/19.
Upsell priority (from checkout logic): cream first, mist second, heel third.
Sort order for menus: mist 1, cream 2, heel 3.
"""

PRODUCTS = [
    {
        "slug": "razaz-al-shaar",
        "sku": "SABA-MIST",
        "nav_ar": "رذاذ الشعر",
        "name_ar": "رذاذ ماء الإمارات",
        "category": "hair",
        "price_1": 199,
        "price_2": 279,
        "price_3": 349,
        "upsell_price": 99,
        "stock": 120,
        "scarcity_threshold": 25,
        "active": True,
        "sort": 1,
        "ingredients": [
            {"name": "ماء مُصفّى", "detail": "قاعدة الرذاذ. خفيفة وما تترك طبقة."},
            {"name": "جليسرين نباتي", "detail": "يمسك الرطوبة على الشعر الجاف من المكيف."},
            {"name": "بانثينول", "detail": "برو-فيتامين B5، معروف إنه يخلي الشعر أهدى للمس."},
            {"name": "مستخلص صبار", "detail": "لمسة ترطيب خفيفة."},
            {"name": "عطر خفيف", "detail": "ريحة نظيفة، مو عطر ثقيل."},
        ],
        "images": [
            "/images/mist-1.jpg",
            "/images/mist-2.jpg",
            "/images/mist-3.jpg",
            "/images/mist-4.jpg",
        ],
    },
    {
        "slug": "kareem-al-intiash",
        "sku": "SABA-CREAM",
        "nav_ar": "كريم الانتعاش",
        "name_ar": "كريم الانتعاش لكامل الجسم",
        "category": "body",
        "price_1": 199,
        "price_2": 279,
        "price_3": 349,
        "upsell_price": 99,
        "stock": 120,
        "scarcity_threshold": 25,
        "active": True,
        "sort": 2,
        "ingredients": [
            {"name": "جل خفيف سريع الامتصاص", "detail": "عشان ما يبقى فيلم تحت العباية."},
            {"name": "جليسرين", "detail": "يرطّب الطبقة الخارجية من البشرة."},
            {"name": "زبدة شيا", "detail": "تغذية ناعمة من غير ثقل كريمات الليل."},
            {"name": "نياسيناميد", "detail": "مكوّن معروف بدعم مظهر البشرة مع الاستخدام المنتظم."},
            {"name": "إحساس انتعاش خفيف", "detail": "برودة لطيفة. مو حرقة، ومو منتج طبي للتعرق."},
        ],
        "images": [
            "/images/cream-1.jpg",
            "/images/cream-2.jpg",
            "/images/cream-3.jpg",
            "/images/cream-4.jpg",
        ],
    },
    {
        "slug": "qalam-al-kaab",
        "sku": "SABA-HEEL",
        "nav_ar": "قلم الكعب",
        "name_ar": "قلم الكعب المشقق",
        "category": "heel",
        "price_1": 199,
        "price_2": 279,
        "price_3": 349,
        "upsell_price": 99,
        "stock": 120,
        "scarcity_threshold": 25,
        "active": True,
        "sort": 3,
        "ingredients": [
            {"name": "يوريا", "detail": "المكوّن الأكثر استخداماً لترطيب الجلد الجاف والخشن، ومنها الكعب."},
            {"name": "زبدة شيا", "detail": "تليين للموضع الجاف."},
            {"name": "زيت لوز حلو", "detail": "انزلاق القلم وقت التطبيق."},
            {"name": "شمع تجميلي", "detail": "يخلي التركيبة قلم، مو كريم يسيح في الشنطة."},
        ],
        "images": [
            "/images/heel-1.jpg",
            "/images/heel-2.jpg",
            "/images/heel-3.jpg",
            "/images/heel-4.jpg",
        ],
    },
]

# Nine sample reviews, three per product. source="sample" always shows نموذج ribbon.
REVIEWS = [
    # Mist
    {
        "id": "sample-mist-1",
        "product_slug": "razaz-al-shaar",
        "source": "sample",
        "name": "ميثة",
        "body": "أحطه في الشنطة. الرشة الثانية بعد الدوام هي اللي فرقت معي.",
    },
    {
        "id": "sample-mist-2",
        "product_slug": "razaz-al-shaar",
        "source": "sample",
        "name": "نورة",
        "body": "ريحته خفيفة. ما أحب العطر القوي في المكتب.",
    },
    {
        "id": "sample-mist-3",
        "product_slug": "razaz-al-shaar",
        "source": "sample",
        "name": "عائشة",
        "body": "استخدمه على الشيلة قبل ما أطلع من السيارة.",
    },
    # Cream
    {
        "id": "sample-cream-1",
        "product_slug": "kareem-al-intiash",
        "source": "sample",
        "name": "موزه",
        "body": "ينشرب وما يخلي العباية تلزق، وهذا كان طلبي.",
    },
    {
        "id": "sample-cream-2",
        "product_slug": "kareem-al-intiash",
        "source": "sample",
        "name": "فاطمة",
        "body": "الانتعاش خفيف، مو حرقة.",
    },
    {
        "id": "sample-cream-3",
        "product_slug": "kareem-al-intiash",
        "source": "sample",
        "name": "مريم",
        "body": "صار بعد الشاور مباشرة. كمية صغيرة تكفي.",
    },
    # Heel
    {
        "id": "sample-heel-1",
        "product_slug": "qalam-al-kaab",
        "source": "sample",
        "name": "ميثة",
        "body": "أسهل من الجرة، لأني أحطه على الكعب بس.",
    },
    {
        "id": "sample-heel-2",
        "product_slug": "qalam-al-kaab",
        "source": "sample",
        "name": "نورة",
        "body": "حطيته بالليل كم يوم، الكعب صار أهدى للمس.",
    },
    {
        "id": "sample-heel-3",
        "product_slug": "qalam-al-kaab",
        "source": "sample",
        "name": "عائشة",
        "body": "صغير في الشنطة قبل العزايم.",
    },
]
