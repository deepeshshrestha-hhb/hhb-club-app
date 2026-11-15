"""
Christmas Lunch 2026 pre-order & payment tracker: data/xmas2026_preorders.xlsx

Sits beside the unlisted Christmas Lunch RSVP (christmas_dinner_service.py), for
the same private group of 9 families (29 people). Each person picks their meal
from the restaurant's lunch menu (plus four momo starters agreed for our party);
children can pick the kids menu instead. Families see their running total and
tick "We have transferred the payment" once they've paid Deepesh.

Storage follows annual_dinner_service.py's Excel pattern: one workbook with
`orders`, `payments` and `settings` sheets, a lock around every
read-modify-write, an atomic temp-file save, and a backgrounded R2 upload. data/
is already an R2 synced prefix, so the file comes back down on every startup.

Prices always come from MENU_XMAS2026 on the server (price_order) - the browser
works out a preview price for the live price line but it's never stored.
"""
import io
import logging
import os
import threading
from collections import Counter, defaultdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from config import Config
from services import r2_service
from services.spond_service import LOCAL_TZ

logger = logging.getLogger("xmas2026")

DATA_PATH = Path(Config.DATA_DIR) / "xmas2026_preorders.xlsx"

EVENT = {
    "title": "Christmas Lunch 2026",
    "date": "Saturday 12 December 2026",
    "time": "from 12:30 pm",
    "venue": "City of Temple Kathmandu (by Dé Buddha)",
    "address": "First Floor, 8 Moss Street, Paisley PA1 1BL",
    "organiser": "Deepesh",
}

LOCKED_MESSAGE = "Orders are closed — contact Deepesh for changes."

TIP_PER_PERSON = 2
EXPECTED_HEADCOUNT = 29
NOTES_MAX = 150

# --------------------------------------------------------------------------
# Seed data: families and members
# --------------------------------------------------------------------------

def _m(name, is_child=False):
    return {"name": name, "is_child": is_child}


FAMILIES = [
    {"family": "Barun Lal", "members": [_m("Barun"), _m("Archana"), _m("Ojal"), _m("Hazel", True), _m("Aama")]},
    {"family": "Birendra Shrestha", "members": [_m("Birendra"), _m("Anu"), _m("Vijay")]},
    {"family": "Deepak Subedi", "members": [_m("Deepak"), _m("Ava")]},
    {"family": "Deepesh Shrestha", "members": [_m("Deepesh"), _m("Utsheela"), _m("Unnabh"), _m("Deelisha", True)]},
    {"family": "Kalyan Bhandari", "members": [_m("Kalyan"), _m("Taptika"), _m("Aarabh"), _m("Nishad")]},
    {"family": "Keshav Bhattarai", "members": [_m("Krisha"), _m("Kundan"), _m("Prakriti"), _m("Keshav B")]},
    {"family": "Keshav Dahal", "members": [_m("Anjana")]},
    {"family": "Pankaj Shah", "members": [_m("Pankaj")]},
    {"family": "Ram Aryal", "members": [_m("Ram"), _m("Saroja"), _m("Shreya"), _m("Grishma"), _m("Aarambha")]},
]

HEADCOUNT = sum(len(f["members"]) for f in FAMILIES)
if HEADCOUNT != EXPECTED_HEADCOUNT:
    logger.warning("Christmas Lunch 2026 seed has %d people, expected %d", HEADCOUNT, EXPECTED_HEADCOUNT)

_MEMBERS = {(f["family"], m["name"]): m for f in FAMILIES for m in f["members"]}
_FAMILY_NAMES = [f["family"] for f in FAMILIES]

# --------------------------------------------------------------------------
# Menu (all prices as strings, turned into Decimal - change prices here only)
# --------------------------------------------------------------------------

MENU_XMAS2026 = {
    "meal_types": {
        "2course": {"label": "2 Course", "price": "13.95", "courses": "Starter + Main"},
        "3course": {"label": "3 Course", "price": "16.95", "courses": "Starter + Main + Dessert"},
    },
    "starters": [
        {"group": "Momo – Special for our party", "items": [
            {"name": "Steam Momo (Chicken)"},
            {"name": "Steam Momo (Veg)", "tags": ["V"]},
            {"name": "Chilli Momo (Chicken)", "tags": ["chilli"], "supplement": "2.00", "short": "Chilli Momo"},
            {"name": "Chilli Momo (Veg)", "tags": ["V", "chilli"], "supplement": "2.00", "short": "Chilli Momo"},
        ]},
        {"group": "Starters", "items": [
            {"name": "Himalayan Noodles Soup (Thukpa)", "tags": ["chilli"]},
            {"name": "Vegetable Thukpa", "tags": ["V"]},
            {"name": "Sha Phaley"},
            {"name": "Chicken Pakora"},
            {"name": "Vegetable Pakora", "tags": ["V"]},
            {"name": "Spicy Garlic Hot Wings", "tags": ["chilli", "GF"]},
            {"name": "Haggis Bon-Bons"},
            {"name": "Halloumi Fries", "tags": ["V"]},
        ]},
    ],
    "mains": [
        {"group": "Mains", "items": [
            {"name": "Chicken Katsu"},
            {"name": "Fried Chicken Burger"},
            {"name": "Grilled Halloumi Burger", "tags": ["V", "GF option"]},
            {"name": "Chicken Chili", "tags": ["chilli"]},
        ]},
        {"group": "Curries – with rice or naan", "curry": True, "items": [
            {"name": "Chicken Kathmandu", "tags": ["chilli", "GF"]},
            {"name": "Vegetable Kathmandu", "tags": ["V", "chilli", "GF"]},
            {"name": "Chicken Korma", "tags": ["GF"]},
            {"name": "Chicken Chasni", "tags": ["GF"]},
            {"name": "Butter Chicken", "tags": ["GF"]},
            {"name": "Himalayan Lamb", "tags": ["chilli", "GF"], "supplement": "2.00", "short": "Lamb"},
            {"name": "Gurkha's Goat Meat Curry", "tags": ["chilli", "GF"], "supplement": "3.00", "short": "Goat"},
        ]},
    ],
    "rice_naan": ["Boiled Rice", "Fried Rice", "Naan Bread"],
    "desserts": [
        {"name": "Gulab Jamun with Vanilla Ice-cream"},
        {"name": "Rasmalai Milk Cake"},
        {"name": "Selection of Ice-cream (2 scoops)", "desc": "Vanilla & Belgian Chocolate"},
        {"name": "Selection of Sorbet (2 scoops)", "desc": "Mango & Scottish Raspberry"},
        {"name": "Port Wine (50 ml)"},
    ],
    "kids_meals": [
        {"name": "Fish Finger & Chips"},
        {"name": "Chicken Nuggets & Chips"},
        {"name": "Chicken Korma & Rice"},
        {"name": "Chicken Chasni & Rice"},
    ],
    "kids_meal_price": "6.95",
    "kids_icecream": {"price": "2.95", "flavours": ["Vanilla", "Chocolate"], "sauces": ["Chocolate", "Strawberry"]},
}


def _dr(group, items, alcohol=False):
    return {"group": group, "alcohol": alcohol, "items": [{"name": n, "price": p} for n, p in items]}


def _sizes(names, half, full):
    out = []
    for n in names:
        out += [(f"{n} (half)", half), (f"{n} (full)", full)]
    return out


# Optional drinks, one per person, from the City of Temple Cocktail & Drink Menu
# 2026. Alcohol groups are hidden from (and refused for) the children.
DRINKS_XMAS2026 = [
    _dr("Soft drinks (can)", [(n, "2.50") for n in ("Coke", "Diet Coke", "Fanta", "Sprite", "Irn Bru", "Diet Irn Bru")]
        + [("Fentimans Classic Ginger Beer", "3.95"), ("J20 (Orange and Passion Fruit)", "3.95"),
           ("Appletiser", "3.95"), ("Fever-Tree Tonic (200ml)", "2.50")]),
    _dr("Draught soft drinks", _sizes(["Soda Water"], "1.50", "2.80")
        + _sizes(["Soda & Lime", "Soda & Orange", "Soda & Blackcurrant"], "2.50", "3.50")
        + _sizes(["Coke (draught)", "Diet Coke (draught)", "Lemonade"], "2.50", "3.80")
        + _sizes(["Apple Juice", "Orange Juice", "Cranberry Juice"], "2.50", "3.95")),
    _dr("Water", [("Still Water (330ml)", "3.50"), ("Sparkling Water (330ml)", "3.50"),
                  ("Still Water (750ml)", "6.50"), ("Sparkling Water (750ml)", "6.50")]),
    _dr("Alcohol-free beer & cider", [("San Miguel 0.0% (bottle)", "4.20"),
                                      ("Kopparberg Non-Alcoholic Cider", "4.50")], alcohol=True),  # adults only
    _dr("Draught beer", [("Tennents (pint)", "5.50"), ("Tennents (half)", "3.50"),
                         ("Cobra (pint)", "6.50"), ("Cobra (half)", "4.50")], alcohol=True),
    _dr("Bottled beer & cider", [("Kathmandu Beer (500ml)", "6.50"), ("Nepali Beer (630ml)", "7.20"),
                                 ("Gluten Free Beer", "4.50"), ("Magners Cider", "4.50"),
                                 ("Kopparberg Cider", "4.95")], alcohol=True),
    _dr("Nepali drinks", [("Rice Wine – Chhyang (175ml)", "6.50"), ("Yarchagumba Whisky", "12.95"),
                          ("Khukuri Rum", "4.80"), ("Himalayan Brandy", "4.80")], alcohol=True),
    _dr("City of Temple cocktails", [("City of Temple “Kathmandu”", "10.50"), ("High Hill Stupa", "9.95"),
                                     ("Mandala", "9.50"), ("The Laughing Buddha", "9.95"),
                                     ("The Singing Bowl", "9.50")], alcohol=True),
    _dr("Classic cocktails", [("Old Fashioned", "9.50"), ("Cosmopolitan", "8.95"), ("Negroni", "9.95"),
                              ("Daiquiri", "8.95"), ("Tequila Sunrise", "8.95")], alcohol=True),
    _dr("Gin", [("Gordon's", "4.20"), ("Gordon's Pink", "4.50"), ("The Botanist", "5.20"),
                ("Caorunn", "5.20"), ("Brockmans", "5.20"), ("Hendricks", "5.20")], alcohol=True),
    _dr("Vodka & rum", [("Smirnoff Vodka", "4.20"), ("Grey Goose", "5.20"), ("Bacardi", "4.20"),
                        ("Captain Morgan Spiced Rum", "4.20")], alcohol=True),
    _dr("Whisky & brandy", [("Jameson", "4.20"), ("Jack Daniels", "4.20"), ("Isle of Jura (10 yrs)", "4.50"),
                            ("Talisker (10 yrs)", "4.50"), ("Glenfiddich (12 yrs)", "4.50"),
                            ("Famous Grouse", "3.80"), ("Bells", "3.80"), ("Martell", "4.50"),
                            ("Remy Martin VSOP", "4.80")], alcohol=True),
    _dr("Liqueurs & shots", [("Glayva", "3.50"), ("Amaretto", "3.50"), ("Cointreau", "3.50"),
                             ("Disaronno", "3.50"), ("Martini Rosso", "3.50"), ("Drambuie", "3.80"),
                             ("Kahlua", "3.80"), ("Southern Comfort", "4.20"), ("Malibu", "4.50"),
                             ("Baileys (50ml)", "4.80"), ("Tequila Silver", "3.50"), ("Tequila Rose", "3.50"),
                             ("Limoncello", "3.50"), ("Sambuca", "3.50"), ("Jagermeister", "3.80")], alcohol=True),
]

# Optional hot beverage, one per person, from the City of Temple Hot Beverages menu.
HOT_DRINKS_XMAS2026 = [{"name": n, "price": p} for n, p in (
    ("Breakfast Tea", "2.95"), ("Earl Grey Tea", "2.95"), ("Green Tea", "2.95"), ("Fruit Tea", "2.95"),
    ("Nepalese Masala Tea", "3.95"), ("Cappuccino", "3.95"), ("Caffe Latte", "3.95"),
    ("Flat White", "3.95"), ("Americano", "3.50"), ("Espresso", "2.95"), ("Hot Chocolate", "3.95"),
)]

_CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(_CENT, ROUND_HALF_UP)


def money(v) -> str:
    """£0.00 formatting (negative as -£1.00)."""
    d = _d(v)
    return f"-£{-d:.2f}" if d < 0 else f"£{d:.2f}"


def _label(item: dict) -> str:
    tags = item.get("tags", [])
    parts = [item["name"]]
    if "V" in tags:
        parts.append("(V)")
    if "chilli" in tags:
        parts.append("🌶")
    if "GF" in tags:
        parts.append("(GF)")
    if "GF option" in tags:
        parts.append("(GF option)")
    if item.get("desc"):
        parts.append(f"– {item['desc']}")
    if item.get("supplement"):
        parts.append(f"(+{money(item['supplement'])})")
    return " ".join(parts)


def _flat(groups):
    return {i["name"]: i for g in groups for i in g["items"]}


_STARTERS = _flat(MENU_XMAS2026["starters"])
_MAINS = _flat(MENU_XMAS2026["mains"])
_CURRIES = {i["name"] for g in MENU_XMAS2026["mains"] if g.get("curry") for i in g["items"]}
_DESSERTS = {i["name"]: i for i in MENU_XMAS2026["desserts"]}
_KIDS = {i["name"]: i for i in MENU_XMAS2026["kids_meals"]}
_IC = MENU_XMAS2026["kids_icecream"]
_DRINKS = {i["name"]: {**i, "alcohol": g["alcohol"]} for g in DRINKS_XMAS2026 for i in g["items"]}
_HOT = {i["name"]: i for i in HOT_DRINKS_XMAS2026}
assert len(_DRINKS) == sum(len(g["items"]) for g in DRINKS_XMAS2026), "duplicate drink name"


def _drink_label(item: dict) -> str:
    return f"{item['name']} – {money(item['price'])}"


def menu_for_template() -> dict:
    """The menu with display labels, for building the dropdowns."""
    def items(lst):
        return [{**i, "label": _label(i), "supplement": i.get("supplement", "0.00")} for i in lst]

    m = MENU_XMAS2026
    return {
        "meal_types": [{"key": k, **v, "price_label": money(v["price"])} for k, v in m["meal_types"].items()],
        "starters": [{"group": g["group"], "items": items(g["items"])} for g in m["starters"]],
        "mains": [{"group": g["group"], "curry": bool(g.get("curry")), "items": items(g["items"])} for g in m["mains"]],
        "rice_naan": m["rice_naan"],
        "desserts": items(m["desserts"]),
        "kids_meals": items(m["kids_meals"]),
        "kids_meal_price": m["kids_meal_price"],
        "kids_icecream": _IC,
        "tip": str(TIP_PER_PERSON),
        "drinks": [{"group": g["group"], "alcohol": g["alcohol"],
                    "items": [{**i, "label": _drink_label(i)} for i in g["items"]]} for g in DRINKS_XMAS2026],
        "hot_drinks": [{**i, "label": _drink_label(i)} for i in HOT_DRINKS_XMAS2026],
    }


# --------------------------------------------------------------------------
# Pricing (pure - see tests/test_xmas_pricing.py)
# --------------------------------------------------------------------------

def price_order(order: dict) -> dict:
    """Server-side price for one person's order. Returns the itemised parts,
    food, tip and total, all as Decimal."""
    parts = []
    if order.get("menu_type") == "kids":
        parts.append(("Kids meal", _d(MENU_XMAS2026["kids_meal_price"])))
        if order.get("kids_icecream"):
            parts.append(("Kid's Ice Cream", _d(_IC["price"])))
    else:
        mt = MENU_XMAS2026["meal_types"][order["menu_type"]]
        parts.append((mt["label"], _d(mt["price"])))
        for item in (_STARTERS.get(order.get("starter")), _MAINS.get(order.get("main"))):
            if item and item.get("supplement"):
                parts.append((item.get("short", item["name"]), _d(item["supplement"])))
    for item in (_DRINKS.get(order.get("drink")), _HOT.get(order.get("hot_drink"))):
        if item:
            parts.append((item["name"], _d(item["price"])))
    food = sum((p for _, p in parts), ZERO)
    tip = _d(TIP_PER_PERSON)
    return {"parts": parts, "food": food, "tip": tip, "total": food + tip}


def family_total(orders) -> Decimal:
    """Sum of totals (food + tip) for the members who have ordered."""
    return sum((price_order(o)["total"] for o in orders), ZERO)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1", "yes", "on")


def clean_order(payload: dict):
    """Validate one person's order. Returns (order, None) or (None, error)."""
    family = str(payload.get("family") or "").strip()
    member = str(payload.get("member") or "").strip()
    m = _MEMBERS.get((family, member))
    if not m:
        return None, "Please choose your family and name."

    notes = " ".join(str(payload.get("notes") or "").split())
    if len(notes) > NOTES_MAX:
        return None, f"Notes can be up to {NOTES_MAX} characters."

    order = {
        "family": family, "member": member, "is_child": m["is_child"],
        "menu_type": "", "starter": "", "main": "", "rice_naan": "", "dessert": "",
        "kids_meal": "", "kids_icecream": False, "ic_flavour": "", "ic_sauce": "",
        "drink": "", "hot_drink": "", "notes": notes,
    }

    drink = str(payload.get("drink") or "").strip()
    if drink:
        if drink not in _DRINKS:
            return None, "Please choose a drink from the list."
        if m["is_child"] and _DRINKS[drink]["alcohol"]:
            return None, "Please choose a soft drink for children."
        order["drink"] = drink
    hot = str(payload.get("hot_drink") or "").strip()
    if hot:
        if hot not in _HOT:
            return None, "Please choose a hot drink from the list."
        order["hot_drink"] = hot

    menu = payload.get("menu") or "lunch"
    if menu not in ("lunch", "kids"):
        return None, "Please choose Kids Menu or Lunch Menu."
    if menu == "kids":
        if not m["is_child"]:
            return None, "The kids menu is for children only."
        kids_meal = payload.get("kids_meal")
        if kids_meal not in _KIDS:
            return None, "Please choose a kids meal."
        order.update(menu_type="kids", kids_meal=kids_meal)
        if _truthy(payload.get("kids_icecream")):
            flavour, sauce = payload.get("ic_flavour"), payload.get("ic_sauce")
            if flavour not in _IC["flavours"]:
                return None, "Please choose an ice cream flavour."
            if sauce not in _IC["sauces"]:
                return None, "Please choose an ice cream sauce."
            order.update(kids_icecream=True, ic_flavour=flavour, ic_sauce=sauce)
        return order, None

    meal_type = payload.get("meal_type")
    if meal_type not in MENU_XMAS2026["meal_types"]:
        return None, "Please choose 2 Course or 3 Course."
    starter, main = payload.get("starter"), payload.get("main")
    if starter not in _STARTERS:
        return None, "Please choose a starter."
    if main not in _MAINS:
        return None, "Please choose a main."
    order.update(menu_type=meal_type, starter=starter, main=main)
    if main in _CURRIES:
        rice = payload.get("rice_naan")
        if rice not in MENU_XMAS2026["rice_naan"]:
            return None, "Please choose rice or naan for your curry."
        order["rice_naan"] = rice
    if meal_type == "3course":
        dessert = payload.get("dessert")
        if dessert not in _DESSERTS:
            return None, "Please choose a dessert."
        order["dessert"] = dessert
    return order, None


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

ORDER_COLS = ["family", "member", "is_child", "menu_type", "starter", "main", "rice_naan", "dessert",
              "kids_meal", "kids_icecream", "ic_flavour", "ic_sauce", "drink", "hot_drink", "notes",
              "food_price", "tip",
              "total", "updated_at"]
PAYMENT_COLS = ["family", "paid", "paid_amount", "paid_at"]
SETTINGS_COLS = ["key", "value"]

_lock = threading.Lock()  # one gunicorn worker, 4 threads, all sharing this file


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _rows(ws):
    it = ws.iter_rows(values_only=True)
    header = [(_s(h)) for h in next(it, [])]
    for row in it:
        if any(v is not None for v in row):
            yield dict(zip(header, row))


def _empty() -> dict:
    return {"orders": {}, "payments": {}, "locked": False}


def _load() -> dict:
    data = _empty()
    if not DATA_PATH.exists():
        return data
    try:
        wb = load_workbook(DATA_PATH)
    except Exception:
        logger.exception("Could not read %s", DATA_PATH)
        return data
    if "orders" in wb.sheetnames:
        for r in _rows(wb["orders"]):
            key = (_s(r.get("family")), _s(r.get("member")))
            if key not in _MEMBERS:
                continue
            o = {c: _s(r.get(c)) for c in ORDER_COLS}
            if o["menu_type"] not in ("2course", "3course", "kids"):
                continue
            o["is_child"] = _MEMBERS[key]["is_child"]
            o["kids_icecream"] = _truthy(r.get("kids_icecream"))
            data["orders"][key] = o
    if "payments" in wb.sheetnames:
        for r in _rows(wb["payments"]):
            fam = _s(r.get("family"))
            if fam in _FAMILY_NAMES:
                try:
                    amount = _d(r.get("paid_amount") or 0)
                except Exception:
                    amount = ZERO
                data["payments"][fam] = {"paid": _truthy(r.get("paid")), "paid_amount": amount,
                                         "paid_at": _s(r.get("paid_at"))}
    if "settings" in wb.sheetnames:
        for r in _rows(wb["settings"]):
            if _s(r.get("key")) == "orders_locked":
                data["locked"] = _truthy(r.get("value"))
    return data


def _build_workbook(data: dict) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("orders")
    ws.append(ORDER_COLS)
    for f in FAMILIES:
        for m in f["members"]:
            o = data["orders"].get((f["family"], m["name"]))
            if not o:
                continue
            p = price_order(o)
            row = {**o, "food_price": float(p["food"]), "tip": float(p["tip"]), "total": float(p["total"])}
            ws.append([row.get(c, "") for c in ORDER_COLS])
    ws = wb.create_sheet("payments")
    ws.append(PAYMENT_COLS)
    for fam in _FAMILY_NAMES:
        p = data["payments"].get(fam)
        if p:
            ws.append([fam, p["paid"], float(p["paid_amount"]), p["paid_at"]])
    ws = wb.create_sheet("settings")
    ws.append(SETTINGS_COLS)
    ws.append(["orders_locked", bool(data["locked"])])
    return wb


def _save(data: dict):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_PATH.with_name(DATA_PATH.stem + ".tmp.xlsx")
    _build_workbook(data).save(tmp)
    os.replace(tmp, DATA_PATH)
    threading.Thread(target=r2_service.upload_file, args=(DATA_PATH,), daemon=True).start()


def _now() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

def save_order(payload: dict, is_admin: bool = False):
    """Validate, price and upsert one person's order. Returns (order_view, None)
    or (None, error). Admins can still save while orders are locked."""
    order, error = clean_order(payload)
    if error:
        return None, error
    order["updated_at"] = _now()
    with _lock:
        data = _load()
        if data["locked"] and not is_admin:
            return None, LOCKED_MESSAGE
        data["orders"][(order["family"], order["member"])] = order
        _save(data)
    return _order_view(order), None


def set_paid(payload: dict):
    """Tick/untick "We have paid" for a family. Ticking stores the family total
    at that moment. Returns (payment, None) or (None, error)."""
    family = str(payload.get("family") or "").strip()
    if family not in _FAMILY_NAMES:
        return None, "Please choose your family."
    paid = _truthy(payload.get("paid"))
    with _lock:
        data = _load()
        if paid:
            orders = [o for (fam, _), o in data["orders"].items() if fam == family]
            payment = {"paid": True, "paid_amount": family_total(orders), "paid_at": _now()}
        else:
            payment = {"paid": False, "paid_amount": ZERO, "paid_at": ""}
        data["payments"][family] = payment
        _save(data)
    return payment, None


def set_locked(locked: bool):
    with _lock:
        data = _load()
        data["locked"] = bool(locked)
        _save(data)


def is_locked() -> bool:
    with _lock:
        return _load()["locked"]


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------

def _menu_label(o) -> str:
    if o["menu_type"] == "kids":
        return "Kids"
    return MENU_XMAS2026["meal_types"].get(o["menu_type"], {}).get("label", o["menu_type"])


def _ic_text(o) -> str:
    return f"Kid's Ice Cream ({o['ic_flavour']}, {o['ic_sauce']} sauce)" if o.get("kids_icecream") else ""


def _drinks_text(o) -> str:
    return ", ".join(d for d in (o.get("drink"), o.get("hot_drink")) if d)


def _summary_text(o) -> str:
    if o["menu_type"] == "kids":
        bits = [o["kids_meal"]] + ([_ic_text(o)] if o.get("kids_icecream") else [])
        text = "Kids: " + " + ".join(bits)
    else:
        main = o["main"] + (f" ({o['rice_naan']})" if o.get("rice_naan") else "")
        bits = [o["starter"], main] + ([o["dessert"]] if o.get("dessert") else [])
        text = f"{_menu_label(o)}: " + " · ".join(bits)
    drinks = _drinks_text(o)
    return f"{text} · Drinks: {drinks}" if drinks else text


def _order_view(o: dict) -> dict:
    p = price_order(o)
    return {
        **o,
        "menu_label": _menu_label(o),
        "summary": _summary_text(o),
        "dessert_or_addon": o.get("dessert") or _ic_text(o),
        "drinks_text": _drinks_text(o),
        "parts": [[label, f"{amt:.2f}"] for label, amt in p["parts"]],
        "food": f"{p['food']:.2f}", "tip": f"{p['tip']:.2f}", "total": f"{p['total']:.2f}",
        "total_label": money(p["total"]),
    }


def _sorted_counts(counter: Counter, details=None) -> list:
    rows = []
    for name, n in counter.items():
        detail = ""
        if details and details.get(name):
            detail = ", ".join(f"{k} {v}" for k, v in sorted(details[name].items(), key=lambda kv: (-kv[1], kv[0])))
        rows.append({"name": name, "count": n, "detail": detail})
    return sorted(rows, key=lambda r: (-r["count"], r["name"]))


def _kitchen(orders: list) -> dict:
    starters, mains, desserts, kids, ic = Counter(), Counter(), Counter(), Counter(), Counter()
    sides = defaultdict(Counter)
    stats = Counter()
    drinks, hot = Counter(), Counter()
    for o in orders:
        stats[o["menu_type"]] += 1
        if o.get("drink"):
            drinks[o["drink"]] += 1
        if o.get("hot_drink"):
            hot[o["hot_drink"]] += 1
        if o["menu_type"] == "kids":
            kids[o["kids_meal"]] += 1
            if o.get("kids_icecream"):
                ic[f"{o['ic_flavour']} ice cream, {o['ic_sauce']} sauce"] += 1
            continue
        starters[o["starter"]] += 1
        mains[o["main"]] += 1
        if o.get("rice_naan"):
            sides[o["main"]][o["rice_naan"]] += 1
        if o.get("dessert"):
            desserts[o["dessert"]] += 1
    return {
        "received": len(orders), "expected": HEADCOUNT,
        "two_course": stats["2course"], "three_course": stats["3course"], "kids": stats["kids"],
        "starters": _sorted_counts(starters),
        "mains": _sorted_counts(mains, sides),
        "desserts": _sorted_counts(desserts),
        "kids_meals": _sorted_counts(kids),
        "icecream_total": sum(ic.values()),
        "icecream": _sorted_counts(ic),
        "drinks": _sorted_counts(drinks),
        "hot_drinks": _sorted_counts(hot),
    }


def _build_state(data: dict) -> dict:
    families, all_orders = [], []
    grand_food = grand_tip = total_paid = ZERO
    for f in FAMILIES:
        fam = f["family"]
        members, rows = [], []
        food = ZERO
        for m in f["members"]:
            o = data["orders"].get((fam, m["name"]))
            members.append({"name": m["name"], "is_child": m["is_child"], "ordered": bool(o)})
            if o:
                v = _order_view(o)
                rows.append(v)
                all_orders.append(o)
                food += Decimal(v["food"])
        tip = _d(TIP_PER_PERSON) * len(rows)
        total = food + tip
        pay = data["payments"].get(fam) or {"paid": False, "paid_amount": ZERO, "paid_at": ""}
        diff = (total - pay["paid_amount"]) if pay["paid"] else ZERO
        grand_food += food
        grand_tip += tip
        if pay["paid"]:
            total_paid += pay["paid_amount"]
        families.append({
            "family": fam, "members": members, "orders": rows,
            "member_count": len(members), "ordered_count": len(rows),
            "remaining": len(members) - len(rows),
            "food": f"{food:.2f}", "tip": f"{tip:.2f}", "total": f"{total:.2f}",
            "food_label": money(food), "tip_label": money(tip), "total_label": money(total),
            "paid": pay["paid"], "paid_amount": f"{pay['paid_amount']:.2f}",
            "paid_amount_label": money(pay["paid_amount"]), "paid_at": pay["paid_at"],
            "diff": f"{diff:.2f}", "diff_label": money(abs(diff)),
        })
    grand_total = grand_food + grand_tip
    return {
        "locked": data["locked"],
        "locked_message": LOCKED_MESSAGE,
        "families": families,
        "kitchen": _kitchen(all_orders),
        "totals": {
            "food": money(grand_food), "tip": money(grand_tip), "total": money(grand_total),
            "paid": money(total_paid), "outstanding": money(grand_total - total_paid),
        },
    }


def get_state() -> dict:
    with _lock:
        data = _load()
    return _build_state(data)


# --------------------------------------------------------------------------
# Excel export for the restaurant
# --------------------------------------------------------------------------

def export_workbook() -> io.BytesIO:
    state = get_state()
    wb = Workbook()
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DDEBF7")
    fam_fill = PatternFill("solid", fgColor="F2F2F2")
    gbp = '"£"#,##0.00'

    ws = wb.active
    ws.title = "All orders"
    header = ["Family", "Name", "Menu", "Starter", "Main", "Rice/Naan", "Dessert / Kids add-on",
              "Drink", "Hot drink", "Notes", "Food & drinks", "Tip", "Total"]
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = bold, head_fill
    for f in state["families"]:
        paid = f"Paid ({f['paid_amount_label']})" if f["paid"] else "Not paid"
        ws.append([f["family"], f"{f['ordered_count']}/{f['member_count']} ordered", paid,
                   "", "", "", "", "", "", "", float(f["food"]), float(f["tip"]), float(f["total"])])
        for c in ws[ws.max_row]:
            c.font, c.fill = bold, fam_fill
        for o in f["orders"]:
            main = o["kids_meal"] if o["menu_type"] == "kids" else o["main"]
            ws.append([f["family"], o["member"], o["menu_label"], o["starter"], main, o["rice_naan"],
                       o["dessert_or_addon"], o["drink"], o["hot_drink"], o["notes"],
                       float(o["food"]), float(o["tip"]), float(o["total"])])
    ws.append([])
    t = state["totals"]
    for label, val in (("Grand total food & drinks", t["food"]), ("Total tip", t["tip"]),
                       ("Grand total", t["total"]), ("Total marked paid", t["paid"]),
                       ("Outstanding", t["outstanding"])):
        ws.append([label] + [""] * 11 + [float(val.replace("£", "").replace(",", ""))])
        ws.cell(ws.max_row, 1).font = bold
    for row in ws.iter_rows(min_row=2, min_col=11, max_col=13):
        for c in row:
            c.number_format = gbp
    for col, width in zip("ABCDEFGHIJKLM", (20, 16, 9, 30, 30, 12, 40, 28, 18, 36, 12, 7, 9)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    ks = wb.create_sheet("Kitchen summary")
    k = state["kitchen"]
    ks.append([f"Orders received {k['received']} / {k['expected']}", f"2-course {k['two_course']}",
               f"3-course {k['three_course']}", f"Kids menu {k['kids']}"])
    ks.cell(1, 1).font = bold
    for title, rows in (("Starters", k["starters"]), ("Mains", k["mains"]), ("Desserts", k["desserts"]),
                        ("Kids meals", k["kids_meals"]), ("Kid's Ice Cream", k["icecream"]),
                        ("Drinks", k["drinks"]), ("Hot drinks", k["hot_drinks"])):
        if not rows:
            continue
        ks.append([])
        ks.append([title, "Count", "Breakdown"])
        for c in ks[ks.max_row]:
            c.font, c.fill = bold, head_fill
        for r in rows:
            ks.append([r["name"], r["count"], r["detail"]])
    ks.column_dimensions["A"].width = 40
    ks.column_dimensions["B"].width = 12
    ks.column_dimensions["C"].width = 40
    ks.column_dimensions["D"].width = 14

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out
