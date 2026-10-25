"""Makes a believable screenshot graveyard to tidy: 20 PNGs with Windows-style names.

Every screen is drawn with Pillow, so there is nothing to download. Every name, shop and
person in them is made up.

  slothshot demo              -> ~/.slothshot/demo-screenshots/
  slothshot demo <folder>
"""

import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from slothshot.shared import DEMO_FOLDER

MARK = ".slothshot-demo"  # only a folder carrying this mark (or an empty one) is ever wiped
W, H = 1280, 800

# Line prefixes: "# " big, "~ " muted, "! " red, "+ " green, "> " prompt.
PAGES = [
    ("dark", None, [
        "> PS C:\\code\\ledger> python -m billing.run",
        "Traceback (most recent call last):",
        '  File "billing/run.py", line 41, in <module>',
        "    invoice = build_invoice(order)",
        '  File "billing/invoice.py", line 88, in build_invoice',
        '    customer = order["user_id"]',
        "! KeyError: 'user_id'",
    ]),
    ("light", "Kettle & Crumb Bakery", [
        "~ Order #4471 · Paid by UPI",
        "2 × Cardamom bun   ₹180",
        "1 × Sourdough loaf   ₹320",
        "1 × Cold coffee   ₹140",
        "# Total ₹640",
        "~ Thank you! Pick up after 5:30 PM",
    ]),
    ("light", "Boarding pass", [
        "# BLR → GOI",
        "Canopy Air · Flight CA 218 · Sat 1 Nov",
        "Gate 14 · Boarding 06:40 · Seat 17C",
        "~ Passenger: R. Mehta · PNR QX7L2P",
    ]),
    ("light", "Weekend trek", [
        "Anu: are we still doing Rajmachi on Saturday?",
        "Dev: yes!! bus leaves Lonavala at 6:15 am",
        "Anu: I'll bring the stove and maggi",
        "Kabir: who has the first aid kit",
        "Dev: me. also carry 2L water each, no shops after the fort",
    ]),
    ("note", "Studio wifi", ["# network: mossnet-5G", "# password: hangingaround42", "~ router is behind the bookshelf"]),
    ("light", "Banana bread (the lazy one)", [
        "You need: 3 very ripe bananas, 75 g melted butter, 150 g sugar,",
        "1 egg, 1 tsp baking soda, 190 g flour, a pinch of salt.",
        "Do: mash the bananas, stir everything in one bowl,",
        "pour into a loaf tin, bake at 175°C for 55 minutes.",
    ]),
    ("dark", None, [
        "~ // src/hooks/useRetry.ts",
        "export function useRetry(fn, { tries = 5, wait = 1000 } = {}) {",
        "  const [error, setError] = useState(null);",
        "  useEffect(() => {",
        "    let attempt = 0;",
        "    const run = async () => {",
        "      try { await fn(); } catch (e) {",
        "        if (++attempt < tries) setTimeout(run, wait * 2 ** attempt);",
        "        else setError(e);",
        "      }",
        "    };",
        "    run();",
        "  }, [fn]);",
        "  return error;",
        "}",
    ]),
    ("dark", None, [
        "> $ npm install",
        "! npm ERR! code ERESOLVE",
        "! npm ERR! ERESOLVE unable to resolve dependency tree",
        "npm ERR! While resolving: canopy-dashboard@0.4.1",
        "npm ERR! Found: react@19.1.0",
        'npm ERR! peer react@"^17.0.0" from chart-sprout@2.3.0',
        "npm ERR! Fix the upstream dependency conflict, or retry with --legacy-peer-deps",
    ]),
    ("light", "Q4 planning · notes", [
        "Decided: ship the offline mode before the Diwali sale",
        "Action items",
        "· Priya: pricing page copy by Thursday",
        "· Sam: fix the sync bug on Android",
        "· Leela: book the user interviews (5 people)",
        "~ Next sync: Monday 10:30",
    ]),
    ("light", "Your cart", [
        "# Oakline standing desk",
        "120 × 60 cm · walnut top · dual motor",
        "# ₹18,999",
        "~ Free delivery by Wed 29 Oct · 1 left in stock",
    ]),
    ("light", "Mira Okafor  @mossy.dev · 2h", [
        "hot take: the best code is the code you deleted",
        "on a Friday afternoon and nobody noticed",
        "~ 1,204 likes · 311 reposts · 87 replies",
    ]),
    ("light", "Dentist · Dr. Shah", [
        "# Tue 28 Oct, 4:30 PM",
        "Smile Studio Dental Clinic, 2nd floor, Aundh Road",
        "~ Bring the X-ray from last visit · Reminder 1 hour before",
    ]),
    ("light", "Why sloths climb down from their tree once a week", [
        "~ Field notes · 6 min read",
        "Three-toed sloths spend almost their whole lives in the canopy,",
        "but about once a week they make a slow, risky trip to the ground",
        "to go to the bathroom. Biologists think the trip feeds the moths",
        "that live in their fur, and the moths feed the algae that turns it green.",
    ]),
    ("light", "Payment successful", [
        "+ ✓ Paid",
        "# ₹250",
        "Paid to Bhau's Chai Stall",
        "~ UPI ref 529814402217 · 24 Oct, 5:12 PM",
    ]),
    ("light", "Out for delivery", [
        "# Arriving today by 7 PM",
        "Parcel from Leafline Books · 2 items · Tracking LB-77812-IN",
        "~ Driver: Suresh · OTP for handover: 4418",
    ]),
    ("light", "Pune", ["# 24° Light rain", "Feels like 26° · Humidity 88% · Wind 9 km/h", "~ Rain stops around 9 PM. Tomorrow: 27°, cloudy"]),
    ("light", "Fix race in retry loop #212", [
        "kabir-r wants to merge 3 commits into main",
        "The retry timer could fire after the component unmounted.",
        "This clears it in the cleanup function.",
        "~ 2 approvals · All checks passed",
    ]),
    ("dark", None, [
        "> ~/photos > du -sh *",
        "41G   Screenshots",
        "12G   Camera",
        "2.1G  Exports",
        "> ~/photos > ls Screenshots | wc -l",
        "! 3817",
    ]),
    ("light", "Invoice INV-0093", [
        "Bill to: Fernleaf Studio LLP",
        "Logo design, 3 rounds · ₹24,000",
        "Brand guide PDF · ₹6,000",
        "# Due ₹30,000 by 5 Nov",
        "~ Bank transfer only · Late fee 2% a month",
    ]),
    ("art", None, []),
]


def font(names, size):
    roots = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/Library/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
    for root in roots:
        for n in names:
            if (root / n).exists():
                return ImageFont.truetype(str(root / n), size)
    return ImageFont.load_default(size)


SANS = ["segoeui.ttf", "Arial.ttf", "DejaVuSans.ttf"]
BOLD = ["segoeuib.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
MONO = ["consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf"]


def draw_dark(d, lines):
    f = font(MONO, 22)
    colours = {"!": (239, 138, 128), "+": (156, 207, 138), "~": (136, 140, 134), ">": (143, 183, 232)}
    y = 48
    for line in lines:
        mark, text = (line[0], line[2:]) if line[:2] in ("! ", "+ ", "~ ", "> ") else ("", line)
        d.text((48, y), text, font=f, fill=colours.get(mark, (216, 220, 214)))
        y += 34


def draw_card(d, title, lines, paper=(255, 255, 255), back=(244, 244, 241)):
    d.rectangle([0, 0, W, H], fill=back)
    d.rounded_rectangle([80, 70, W - 80, H - 70], radius=18, fill=paper, outline=(222, 222, 216), width=2)
    d.text((120, 110), title, font=font(BOLD, 40), fill=(30, 30, 30))
    y = 190
    for line in lines:
        if line.startswith("# "):
            d.text((120, y), line[2:], font=font(BOLD, 46), fill=(30, 30, 30))
            y += 72
        elif line.startswith("~ "):
            d.text((120, y), line[2:], font=font(SANS, 24), fill=(120, 120, 116))
            y += 46
        elif line.startswith("+ "):
            d.text((120, y), line[2:], font=font(BOLD, 34), fill=(42, 122, 58))
            y += 56
        else:
            d.text((120, y), line, font=font(SANS, 28), fill=(40, 40, 40))
            y += 48


def draw_art(d):
    d.rectangle([0, 0, W, H], fill=(207, 224, 195))
    d.line([(0, 250), (400, 236), (800, 262), (W, 238)], fill=(107, 79, 53), width=22)
    d.ellipse([520, 270, 760, 460], fill=(138, 122, 98))
    d.ellipse([582, 272, 698, 388], fill=(183, 169, 143))
    d.ellipse([600, 316, 632, 334], fill=(59, 49, 40))
    d.ellipse([648, 316, 680, 334], fill=(59, 49, 40))
    d.line([(560, 300), (548, 246)], fill=(138, 122, 98), width=18)
    d.line([(720, 300), (732, 246)], fill=(138, 122, 98), width=18)


def make(folder: Path = DEMO_FOLDER) -> int:
    """Wipes the folder and draws a fresh set of screenshots in it. Returns how many."""
    folder = Path(folder).expanduser().resolve()
    if folder.exists():
        if folder != DEMO_FOLDER.resolve() and any(folder.iterdir()) and not (folder / MARK).exists():
            raise ValueError(f"{folder} already has files in it. Pick an empty or new folder for the demo.")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / MARK).write_text("Made by `slothshot demo`. Safe to delete.\n", encoding="utf-8")
    start = datetime(2026, 10, 18, 9, 12, 5)
    count = 0
    for n, (kind, title, lines) in enumerate(PAGES):
        img = Image.new("RGB", (W, H), (27, 29, 28))
        d = ImageDraw.Draw(img)
        if kind == "dark":
            draw_dark(d, lines)
        elif kind == "note":
            draw_card(d, title, lines, paper=(255, 244, 168), back=(214, 200, 176))
        elif kind == "art":
            draw_art(d)
        else:
            draw_card(d, title, lines)
        taken = start + timedelta(hours=7 * n + n * n % 5, minutes=13 * n, seconds=7 * n)
        png = folder / f"Screenshot {taken:%Y-%m-%d %H%M%S}.png"
        img.save(png)
        os.utime(png, (taken.timestamp(), taken.timestamp()))
        count += 1
    return count


def main(folder: str | None = None) -> None:
    target = Path(folder) if folder else DEMO_FOLDER
    try:
        n = make(target)
    except ValueError as err:
        sys.exit(str(err))
    print(f"Drew {n} sample screenshots in {Path(target).expanduser().resolve()}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
