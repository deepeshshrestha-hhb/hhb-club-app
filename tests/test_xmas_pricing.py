"""Unit tests for the Christmas Lunch 2026 pre-order pricing and validation.

Run with:  python -m unittest tests.test_xmas_pricing
(Pure functions only - nothing here reads or writes the data file or R2.)
"""
import unittest
from decimal import Decimal

from services import xmas2026_preorder_service as x

D = Decimal


def adult(meal_type="2course", starter="Chicken Pakora", main="Chicken Katsu", **kw):
    return {"menu_type": meal_type, "starter": starter, "main": main, **kw}


class PricingTests(unittest.TestCase):
    def test_two_course_plain(self):
        p = x.price_order(adult())
        self.assertEqual(p["food"], D("13.95"))
        self.assertEqual(p["tip"], D("2.00"))
        self.assertEqual(p["total"], D("15.95"))

    def test_three_course_plain(self):
        p = x.price_order(adult("3course", dessert="Rasmalai Milk Cake"))
        self.assertEqual(p["food"], D("16.95"))
        self.assertEqual(p["total"], D("18.95"))

    def test_chilli_momo_supplement(self):
        for s in ("Chilli Momo (Chicken)", "Chilli Momo (Veg)"):
            self.assertEqual(x.price_order(adult(starter=s))["food"], D("15.95"))

    def test_steam_momo_no_supplement(self):
        self.assertEqual(x.price_order(adult(starter="Steam Momo (Veg)"))["food"], D("13.95"))

    def test_lamb_and_goat_supplements(self):
        self.assertEqual(x.price_order(adult(main="Himalayan Lamb"))["food"], D("15.95"))
        self.assertEqual(x.price_order(adult(main="Gurkha's Goat Meat Curry"))["food"], D("16.95"))

    def test_chilli_momo_plus_lamb_three_course(self):
        p = x.price_order(adult("3course", "Chilli Momo (Chicken)", "Himalayan Lamb", dessert="Port Wine (50 ml)"))
        self.assertEqual(p["food"], D("20.95"))
        self.assertEqual(p["total"], D("22.95"))
        self.assertEqual([label for label, _ in p["parts"]], ["3 Course", "Chilli Momo", "Lamb"])

    def test_chilli_momo_plus_goat(self):
        p = x.price_order(adult("2course", "Chilli Momo (Veg)", "Gurkha's Goat Meat Curry"))
        self.assertEqual(p["food"], D("18.95"))
        self.assertEqual(p["total"], D("20.95"))

    def test_kids_menu(self):
        self.assertEqual(x.price_order({"menu_type": "kids", "kids_meal": "Fish Finger & Chips"})["total"], D("8.95"))
        p = x.price_order({"menu_type": "kids", "kids_meal": "Chicken Korma & Rice", "kids_icecream": True})
        self.assertEqual(p["food"], D("9.90"))
        self.assertEqual(p["total"], D("11.90"))

    def test_family_total_includes_tip_per_ordered_person(self):
        orders = [adult(), adult("3course", dessert="Rasmalai Milk Cake"),
                  {"menu_type": "kids", "kids_meal": "Fish Finger & Chips", "kids_icecream": True}]
        # 13.95 + 16.95 + 9.90 food + 3 x £2 tip
        self.assertEqual(x.family_total(orders), D("46.80"))
        self.assertEqual(x.family_total([]), D("0.00"))

    def test_money_format(self):
        self.assertEqual(x.money(D("22.9")), "£22.90")
        self.assertEqual(x.money(D("-3")), "-£3.00")


class SeedTests(unittest.TestCase):
    def test_headcount(self):
        self.assertEqual(x.HEADCOUNT, 29)
        self.assertEqual(len(x.FAMILIES), 9)
        children = sorted(m["name"] for f in x.FAMILIES for m in f["members"] if m["is_child"])
        self.assertEqual(children, ["Deelisha", "Hazel"])


class ValidationTests(unittest.TestCase):
    def test_curry_needs_rice(self):
        _, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                "starter": "Sha Phaley", "main": "Butter Chicken"})
        self.assertIn("rice", err)

    def test_two_course_drops_dessert_and_non_curry_drops_rice(self):
        o, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                "starter": "Sha Phaley", "main": "Chicken Katsu",
                                "dessert": "Rasmalai Milk Cake", "rice_naan": "Naan Bread"})
        self.assertIsNone(err)
        self.assertEqual((o["dessert"], o["rice_naan"]), ("", ""))

    def test_three_course_needs_dessert(self):
        _, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "3course",
                                "starter": "Sha Phaley", "main": "Chicken Katsu"})
        self.assertIn("dessert", err)

    def test_kids_menu_only_for_children(self):
        _, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "menu": "kids",
                                "kids_meal": "Fish Finger & Chips"})
        self.assertIsNotNone(err)
        o, err = x.clean_order({"family": "Barun Lal", "member": "Hazel", "menu": "kids",
                                "kids_meal": "Fish Finger & Chips", "kids_icecream": True,
                                "ic_flavour": "Vanilla", "ic_sauce": "Strawberry"})
        self.assertIsNone(err)
        self.assertEqual(o["menu_type"], "kids")

    def test_icecream_needs_flavour_and_sauce(self):
        _, err = x.clean_order({"family": "Barun Lal", "member": "Hazel", "menu": "kids",
                                "kids_meal": "Fish Finger & Chips", "kids_icecream": True, "ic_flavour": "Vanilla"})
        self.assertIn("sauce", err)

    def test_child_can_pick_lunch_menu(self):
        o, err = x.clean_order({"family": "Deepesh Shrestha", "member": "Deelisha", "menu": "lunch",
                                "meal_type": "2course", "starter": "Halloumi Fries", "main": "Chicken Katsu"})
        self.assertIsNone(err)
        self.assertEqual(x.price_order(o)["total"], D("15.95"))

    def test_unknown_member_and_long_notes(self):
        self.assertIsNotNone(x.clean_order({"family": "Pankaj Shah", "member": "Barun"})[1])
        _, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                "starter": "Sha Phaley", "main": "Chicken Katsu", "notes": "x" * 151})
        self.assertIn("150", err)


if __name__ == "__main__":
    unittest.main()
