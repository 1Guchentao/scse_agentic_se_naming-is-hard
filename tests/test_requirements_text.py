"""Offline checks for the initial prose exercise; no model is called."""

import unittest

from brief_to_req import render_output, validate_text


TEXT = "\n".join(f"{number}. Requirement {number}." for number in range(1, 7))


class RequirementsTextTests(unittest.TestCase):
    def test_numbered_text_is_not_rewritten(self):
        self.assertEqual(validate_text(TEXT), TEXT)

    def test_missing_requirement_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_text("\n".join(TEXT.splitlines()[:-1]))

    def test_out_of_order_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_text(TEXT.replace("3. Requirement", "4. Requirement"))

    def test_json_is_not_a_prose_result(self):
        with self.assertRaises(ValueError):
            validate_text('{"goal": "fixture"}')

    def test_code_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_text(chr(96) * 3 + "python\n" + TEXT + "\n" + chr(96) * 3)

    def test_blank_reply_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_text(" ")

    def test_output_keeps_each_reply_verbatim(self):
        other = TEXT + "\n"
        self.assertEqual(render_output([TEXT, other]), "RUN 1\n" + TEXT + "\n\nRUN 2\n" + other + "\n")


if __name__ == "__main__":
    unittest.main()
