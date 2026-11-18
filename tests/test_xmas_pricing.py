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
        self.assertEqual(p["total"], D("13.95"))  # no tip per person

    def test_three_course_plain(self):
        p = x.price_order(adult("3course", dessert="Rasmalai Milk Cake"))
        self.assertEqual(p["food"], D("16.95"))
        self.assertEqual(p["total"], D("16.95"))

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
        self.assertEqual(p["total"], D("20.95"))
        self.assertEqual([label for label, _ in p["parts"]], ["3 Course", "Chilli Momo", "Lamb"])

    def test_chilli_momo_plus_goat(self):
        p = x.price_order(adult("2course", "Chilli Momo (Veg)", "Gurkha's Goat Meat Curry"))
        self.assertEqual(p["food"], D("18.95"))
        self.assertEqual(p["total"], D("18.95"))

    def test_kids_menu(self):
        self.assertEqual(x.price_order({"menu_type": "kids", "kids_meal": "Fish Finger & Chips"})["total"], D("6.95"))
        p = x.price_order({"menu_type": "kids", "kids_meal": "Chicken Korma & Rice", "kids_icecream": True})
        self.assertEqual(p["food"], D("9.90"))
        self.assertEqual(p["total"], D("9.90"))

    def test_family_total_adds_ten_percent_tip(self):
        orders = [adult(), adult("3course", dessert="Rasmalai Milk Cake"),
                  {"menu_type": "kids", "kids_meal": "Fish Finger & Chips", "kids_icecream": True}]
        # 13.95 + 16.95 + 9.90 = 40.80 food, + 4.08 tip
        self.assertEqual(x.family_total(orders), D("44.88"))
        self.assertEqual(x.family_total([]), D("0.00"))

    def test_tip_rounds_to_the_penny(self):
        self.assertEqual(x.tip_for(D("100.00")), D("10.00"))
        self.assertEqual(x.tip_for(D("13.95")), D("1.40"))   # 1.395 rounds half up
        self.assertEqual(x.tip_for(D("6.94")), D("0.69"))

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

    def test_non_curry_drops_rice(self):
        o, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                "starter": "Sha Phaley", "main": "Chicken Katsu", "rice_naan": "Naan Bread"})
        self.assertIsNone(err)
        self.assertEqual(o["rice_naan"], "")

    def test_two_course_any_two_courses(self):
        base = {"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course"}
        for combo in ({"starter": "Chilli Momo (Veg)", "main": "Chicken Katsu"},
                      {"main": "Himalayan Lamb", "rice_naan": "Naan Bread", "dessert": "Rasmalai Milk Cake"},
                      {"starter": "Chilli Momo (Veg)", "dessert": "Rasmalai Milk Cake"}):
            o, err = x.clean_order({**base, **combo})
            self.assertIsNone(err, combo)
            self.assertEqual(sum(1 for k in ("starter", "main", "dessert") if o[k]), 2)
        # supplements still apply whichever two are picked
        o, _ = x.clean_order({**base, "starter": "Chilli Momo (Veg)", "dessert": "Rasmalai Milk Cake"})
        self.assertEqual(x.price_order(o)["total"], D("15.95"))
        o, _ = x.clean_order({**base, "main": "Himalayan Lamb", "rice_naan": "Naan Bread", "dessert": "Rasmalai Milk Cake"})
        self.assertEqual(x.price_order(o)["total"], D("15.95"))

    def test_two_course_needs_exactly_two(self):
        base = {"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course"}
        for combo in ({"starter": "Sha Phaley"}, {},
                      {"starter": "Sha Phaley", "main": "Chicken Katsu", "dessert": "Rasmalai Milk Cake"}):
            self.assertIn("any two", x.clean_order({**base, **combo})[1])
        self.assertIn("dessert", x.clean_order({**base, "starter": "Sha Phaley", "dessert": "Cake"})[1])

    def test_two_course_view_without_main(self):
        o, _ = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                              "starter": "Sha Phaley", "dessert": "Rasmalai Milk Cake"})
        self.assertEqual(x._summary_text(o), "2 Course: Sha Phaley · Rasmalai Milk Cake")
        k = x._kitchen([o])
        self.assertEqual(k["mains"], [])
        self.assertEqual([r["name"] for r in k["desserts"]], ["Rasmalai Milk Cake"])

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
        self.assertEqual(x.price_order(o)["total"], D("13.95"))

    def test_unknown_member_and_long_notes(self):
        self.assertIsNotNone(x.clean_order({"family": "Pankaj Shah", "member": "Barun"})[1])
        _, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                "starter": "Sha Phaley", "main": "Chicken Katsu", "notes": "x" * 151})
        self.assertIn("150", err)


class DrinkTests(unittest.TestCase):
    def test_drink_and_hot_drink_added_to_price(self):
        p = x.price_order(adult(drink="Cobra (pint)", hot_drink="Nepalese Masala Tea"))
        self.assertEqual(p["food"], D("24.40"))   # 13.95 + 6.50 + 3.95
        self.assertEqual(p["total"], D("24.40"))
        self.assertEqual([label for label, _ in p["parts"]], ["2 Course", "Cobra (pint)", "Nepalese Masala Tea"])

    def test_kids_meal_with_soft_drink(self):
        p = x.price_order({"menu_type": "kids", "kids_meal": "Fish Finger & Chips", "drink": "Apple Juice (half)"})
        self.assertEqual(p["total"], D("9.45"))  # 6.95 + 2.50, tip is on the family total

    def test_drinks_are_optional(self):
        order, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                    "starter": "Sha Phaley", "main": "Chicken Katsu"})
        self.assertIsNone(err)
        self.assertEqual((order["drink"], order["hot_drink"]), ("", ""))

    def test_unknown_drink_rejected(self):
        _, err = x.clean_order({"family": "Pankaj Shah", "member": "Pankaj", "meal_type": "2course",
                                "starter": "Sha Phaley", "main": "Chicken Katsu", "drink": "Champagne"})
        self.assertIn("drink", err)

    def test_children_cannot_order_alcohol(self):
        base = {"family": "Barun Lal", "member": "Hazel", "menu": "kids", "kids_meal": "Fish Finger & Chips"}
        _, err = x.clean_order({**base, "drink": "Tennents (pint)"})
        self.assertIn("soft drink", err)
        order, err = x.clean_order({**base, "drink": "Coke", "hot_drink": "Hot Chocolate"})
        self.assertIsNone(err)
        self.assertEqual(order["drink"], "Coke")


if __name__ == "__main__":
    unittest.main()
