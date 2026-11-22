"""Match catalog titles to the shape used by the design studio."""

# Specific names precede broader matches. Older snapshots only distinguish a
# handful of categories, so the shapes are derived from titles at read time.
MOCKUP_PATTERNS = (
    ('phone-case', r'phone case|iphone case'),
    ('sticker', r'\bsticker\b'),
    ('pillow', r'pillow|cushion'),
    ('cap', r'\b(cap|hat|snapback)\b'),
    ('bag', r'tote|backpack|fanny pack|crossbody'),
    ('wall-art', r'poster|canvas print|framed textile|metal sign|yard sign|wooden hanging sign|wall clock'),
    ('ornament', r'ornament|keychain|suncatcher|charm|magnet|acrylic (block|plaque|photo)|night light|window decor|phone grip|plant marker|paper clip|visor clip|photo block|picture frame'),
    ('card', r'greeting card|insert card|paper card|notebook|jigsaw puzzle|hand fan'),
    ('shoes', r'sneaker|\bshoes?\b'),
    ('mug', r'\bmug\b'),
    ('tumbler', r'tumbler|(?:shot|rocks) glass|tritan|mason jar|flower vase|candle (?:jar|holder)|bottle'),
    ('hoodie', r'hoodie|hooded'),
    ('onesie', r'onesie|bodysuit'),
    ('dress', r'\bdress\b'),
    ('bottoms', r'pants|leggings|shorts|sweatshort|boxer|skater skirt'),
    ('textile', r'blanket|towel|tapestry|doormat|mouse ?pad|\bmat\b|\brug\b|flag|banner|apron|bandana|stole'),
    ('accessory', r'socks|arm sleeves|pet collar|jewelry box|christmas stocking|tree skirt'),
    ('polo', r'\bpolo\b'),
    ('tank-top', r'\btank\b|racerback|sports bra|sleeveless'),
    ('sweatshirt', r'sweatshirt|sweater'),
    ('long-sleeve', r'long[ -]sleeve'),
    ('t-shirt', r'\bshirt\b|\btee\b|\bjersey\b|pajama set'),
)
MOCKUP_KINDS = tuple(kind for kind, _ in MOCKUP_PATTERNS) + ('other',)

# Both the expression and its bindings come from the static patterns above.
MOCKUP_KIND_SQL = (
    "CASE " + " ".join("WHEN regexp_matches(lower(title), ?) THEN ?" for _ in MOCKUP_PATTERNS)
    + " WHEN category = 'tank top' THEN 'tank-top'"
    + " WHEN category IN ('t-shirt', 'mug', 'hoodie', 'sweatshirt') THEN category ELSE 'other' END"
)
MOCKUP_KIND_PARAMS = tuple(value for kind, pattern in MOCKUP_PATTERNS for value in (pattern, kind))
