"""Original artwork for the dashboard: the header banner and the section icons.

Everything here is drawn from simple shapes in inline SVG, so the page stays one
self-contained file and nothing is borrowed from the game's own art.
"""

BANNER = """<svg class="banner" viewBox="0 0 1000 220" preserveAspectRatio="xMidYMid slice" role="img" aria-label="A night market camp below the mountains">
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0b1020"/><stop offset="1" stop-color="#27324a"/>
  </linearGradient>
</defs>
<rect width="1000" height="220" fill="url(#sky)"/>
<g fill="#f6ecd0">
  <circle cx="70" cy="30" r="1.3"/><circle cx="160" cy="62" r="1"/><circle cx="240" cy="22" r="1.5"/><circle cx="330" cy="48" r="1"/>
  <circle cx="420" cy="18" r="1.2"/><circle cx="505" cy="58" r="1"/><circle cx="590" cy="26" r="1.4"/><circle cx="660" cy="70" r="1"/>
  <circle cx="735" cy="20" r="1"/><circle cx="890" cy="40" r="1.3"/><circle cx="950" cy="16" r="1"/><circle cx="120" cy="90" r="0.9"/>
  <circle cx="280" cy="86" r="0.9"/><circle cx="455" cy="92" r="0.8"/><circle cx="555" cy="12" r="0.9"/><circle cx="980" cy="76" r="0.9"/>
</g>
<circle cx="830" cy="58" r="30" fill="#f3e3b3"/>
<circle cx="842" cy="50" r="27" fill="#1a2236"/>
<polygon points="0,170 90,96 160,140 250,70 340,138 420,104 520,150 600,88 700,140 790,92 880,132 1000,84 1000,220 0,220" fill="#1d2638"/>
<polygon points="250,70 228,88 246,86 262,94 272,82" fill="#c9d3e6" opacity="0.55"/>
<polygon points="600,88 582,104 598,100 612,108 620,98" fill="#c9d3e6" opacity="0.55"/>
<polygon points="790,92 772,108 788,104 802,112 810,102" fill="#c9d3e6" opacity="0.55"/>
<polygon points="0,190 120,150 230,178 360,140 470,176 600,146 720,178 850,150 1000,176 1000,220 0,220" fill="#161d2b"/>
<g fill="#0f1520">
  <polygon points="40,200 52,160 64,200"/><polygon points="58,204 74,150 90,204"/><polygon points="96,202 106,170 116,202"/>
  <polygon points="860,204 876,152 892,204"/><polygon points="890,202 902,166 914,202"/><polygon points="918,204 936,146 954,204"/>
  <polygon points="954,202 966,170 978,202"/><polygon points="150,206 162,174 174,206"/><polygon points="790,206 800,178 810,206"/>
</g>
<rect y="200" width="1000" height="20" fill="#0f1520"/>
<polygon points="690,200 730,150 770,200" fill="#7a3b2a"/>
<polygon points="730,150 770,200 750,200" fill="#5c2b1f"/>
<polygon points="721,200 730,176 739,200" fill="#20140f"/>
<line x1="730" y1="150" x2="730" y2="138" stroke="#c7a46a" stroke-width="2"/>
<polygon points="730,138 746,142 730,146" fill="#e0b04f"/>
<g transform="translate(800,196)">
  <ellipse cx="0" cy="4" rx="20" ry="4" fill="#e0b04f" opacity="0.18"/>
  <line x1="-10" y1="4" x2="10" y2="-2" stroke="#4a3122" stroke-width="3"/>
  <line x1="-10" y1="-2" x2="10" y2="4" stroke="#4a3122" stroke-width="3"/>
  <polygon points="-7,0 0,-20 7,0" fill="#f08a3c"/>
  <polygon points="-4,0 0,-12 4,0" fill="#ffd56a"/>
</g>
<g transform="translate(660,194)">
  <rect x="-10" y="-8" width="20" height="14" rx="2" fill="#6b4a2f"/>
  <line x1="-10" y1="-2" x2="10" y2="-2" stroke="#3f2b1b" stroke-width="1.5"/>
  <circle cx="0" cy="-12" r="4" fill="#e0b04f"/>
</g>
</svg>"""


def _svg(body, label):
    return (f'<svg class="icon" viewBox="0 0 24 24" width="22" height="22" role="img" aria-label="{label}" '
            f'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


ICONS = {
    "fish": _svg('<path d="M3 12c3-4 8-5 12-3l4-3v12l-4-3c-4 2-9 1-12-3z"/><circle cx="8" cy="11" r="0.8" fill="currentColor"/>', "fish"),
    "herb": _svg('<path d="M12 21V10"/><path d="M12 13c-4 0-6-3-6-7 4 0 6 3 6 7z"/><path d="M12 11c4 0 6-3 6-7-4 0-6 3-6 7z"/>', "herb"),
    "ore": _svg('<path d="M4 16l4-8h8l4 8-8 4z"/><path d="M8 8l4 12M16 8l-4 12M4 16h16"/>', "ore"),
    "cloth": _svg('<rect x="5" y="4" width="14" height="4" rx="1"/><rect x="5" y="16" width="14" height="4" rx="1"/><path d="M7 8v8M17 8v8M7 10l10 2M7 14l10-2"/>', "cloth"),
    "pearl": _svg('<path d="M3 15c0-5 4-9 9-9s9 4 9 9z"/><path d="M8 15V9M12 15V6M16 15V9"/><circle cx="12" cy="18" r="2.2" fill="currentColor"/>', "pearl"),
    "anvil": _svg('<path d="M3 7h13c0 3 2 4 5 4v1H8l-1 3H5z"/><path d="M9 15l-2 5h10l-2-5"/>', "anvil"),
    "hammer": _svg('<path d="M14 4l6 6-3 3-6-6z"/><path d="M12 9L4 17l3 3 8-8"/>', "hammer"),
    "clock": _svg('<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>', "clock"),
    "up": _svg('<path d="M4 17l6-6 4 4 6-7"/><path d="M15 8h5v5"/>', "rising"),
    "down": _svg('<path d="M4 7l6 6 4-4 6 7"/><path d="M15 16h5v-5"/>', "falling"),
    "grid": _svg('<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>', "categories"),
    "eye": _svg('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', "watch"),
    "question": _svg('<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 .5c0 1.5-2.5 2-2.5 3.5"/><circle cx="12" cy="17" r="0.8" fill="currentColor"/>', "unknown"),
    "chest": _svg('<path d="M4 10h16v9H4z"/><path d="M4 10c0-3 2-5 4-5h8c2 0 4 2 4 5"/><path d="M4 13h16"/><rect x="10.5" y="11.5" width="3" height="3.5" rx=".6"/>', "investments"),
    "gem": _svg('<path d="M6 4h12l3 5-9 11L3 9z"/><path d="M3 9h18M9 4l3 16M15 4l-3 16"/>', "item"),
}

# category name (lower case, partial match) -> icon
_CATEGORY_ICONS = [("fish", "fish"), ("herb", "herb"), ("ore", "ore"), ("bar", "ore"), ("cloth", "cloth"),
                   ("leather", "cloth"), ("pearl", "pearl"), ("blacksmith", "anvil"), ("craft", "hammer")]


def icon_for(category):
    c = category.lower()
    for key, name in _CATEGORY_ICONS:
        if key in c:
            return ICONS[name]
    return ICONS["gem"]


def heading(text, icon_name=None, category=None, extra=""):
    ic = ICONS[icon_name] if icon_name else icon_for(category or text)
    return f'<h2>{ic}<span>{text}</span>{extra}</h2>'
