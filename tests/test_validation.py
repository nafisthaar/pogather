import unittest
from datetime import datetime

from app import rules, validation
from app.errors import ValidationError

NOW = datetime(2026, 3, 1, 10, 0)


class PriceQuotaAndQuantityTests(unittest.TestCase):
    def test_price_accepts_plain_and_thousand_separated_numbers(self):
        for raw, expected in [("15000", 15000), ("15.000", 15000), ("Rp 1.500.000", 1_500_000),
                              ("15,000", 15000), ("  2500 ", 2500)]:
            with self.subTest(raw=raw):
                self.assertEqual(validation.parse_price(raw), expected)

    def test_price_rejects_bad_input(self):
        # "15.5" must not be read as 155: dots only work as thousand separators.
        for raw in ["", "   ", "abc", "-5", "15.5", "15.00", "0", "1e5", None, str(rules.MAX_PRICE + 1)]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_price(raw)

    def test_quota_is_a_whole_number_in_range(self):
        self.assertEqual(validation.parse_quota(" 40 "), 40)
        for raw in ["", "0", "-1", "2.5", "abc", None, str(rules.MAX_QUOTA + 1)]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_quota(raw)

    def test_quantity_blank_means_zero_and_the_limit_applies(self):
        self.assertEqual(validation.parse_quantity(""), 0)
        self.assertEqual(validation.parse_quantity(str(rules.MAX_QTY_PER_ITEM)), rules.MAX_QTY_PER_ITEM)
        for raw in ["-1", "1.5", "abc", str(rules.MAX_QTY_PER_ITEM + 1)]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_quantity(raw)

    def test_quantities_keep_only_items_above_zero(self):
        self.assertEqual(validation.parse_quantities({1: "2", 2: "", 3: "0", 4: "5"}), {1: 2, 4: 5})

    def test_quantities_need_at_least_one_item(self):
        for raw in [{}, {1: "", 2: "0"}]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_quantities(raw)


class DeadlineTests(unittest.TestCase):
    def test_future_deadline_is_accepted_and_seconds_are_dropped(self):
        self.assertEqual(validation.parse_deadline("2026-03-05T17:00:45", NOW), datetime(2026, 3, 5, 17, 0))

    def test_deadline_now_or_in_the_past_is_rejected(self):
        for raw in ["2026-03-01T10:00", "2026-02-28T09:00"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_deadline(raw, NOW)

    def test_garbage_time_zone_and_too_far_ahead_are_rejected(self):
        for raw in ["", "tomorrow", "2026-13-45T10:00", "2026-03-05T17:00+07:00", "2027-12-31T17:00", None]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_deadline(raw, NOW)

    def test_an_unchanged_past_deadline_is_allowed_when_editing(self):
        past = datetime(2026, 2, 20, 17, 0)
        self.assertEqual(validation.parse_deadline("2026-02-20T17:00", NOW, unchanged_from=past), past)
        with self.assertRaises(ValidationError):  # a different past time is still wrong
            validation.parse_deadline("2026-02-21T17:00", NOW, unchanged_from=past)


class TextFieldTests(unittest.TestCase):
    def test_names_are_trimmed_and_symbols_are_rejected(self):
        self.assertEqual(validation.clean_full_name("  Sari   Wulandari "), "Sari Wulandari")
        for raw in ["", "   ", "=1+1", "<script>", "x" * (rules.MAX_FULL_NAME_LENGTH + 1), None]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.clean_full_name(raw)

    def test_po_and_item_names_allow_common_punctuation(self):
        self.assertEqual(validation.clean_po_name("PO Brownies (Batch #3) - Lebaran"), "PO Brownies (Batch #3) - Lebaran")
        self.assertEqual(validation.clean_item_name("Mac & Cheese"), "Mac & Cheese")
        for clean in (validation.clean_po_name, validation.clean_item_name):
            with self.subTest(clean=clean.__name__):
                with self.assertRaises(ValidationError):
                    clean("<b>bold</b>")

    def test_optional_text_fields_return_none_when_blank_and_enforce_length(self):
        for clean, limit in [(validation.clean_note, rules.MAX_NOTE_LENGTH),
                             (validation.clean_description, rules.MAX_DESCRIPTION_LENGTH),
                             (validation.clean_payment_info, rules.MAX_PAYMENT_INFO_LENGTH)]:
            with self.subTest(clean=clean.__name__):
                self.assertIsNone(clean("   "))
                self.assertEqual(clean("a  b"), "a b")
                with self.assertRaises(ValidationError):
                    clean("x" * (limit + 1))

    def test_phone_is_optional_but_checked_when_given(self):
        self.assertIsNone(validation.clean_phone(""))
        self.assertEqual(validation.clean_phone("0812-3456 7890"), "081234567890")
        for raw in ["12345", "abcdefghij", "0812345678901234567"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.clean_phone(raw)

    def test_username_password_and_payment_method(self):
        self.assertEqual(validation.clean_username(" Sari_1 "), "sari_1")
        with self.assertRaises(ValidationError):
            validation.clean_username("a b")
        with self.assertRaises(ValidationError):
            validation.check_password("short")
        self.assertEqual(validation.parse_payment_method("QRIS"), "QRIS")
        for raw in ["", "CASH", "qris", None]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    validation.parse_payment_method(raw)


if __name__ == "__main__":
    unittest.main()
