from django.test import TestCase

from sports.services.lineup import validate_softball_lineup


class SoftballLineupValidationTests(TestCase):
    def test_requires_nine_field_positions(self):
        positions = [
            "pitcher",
            "catcher",
            "first_base",
            "second_base",
            "third_base",
            "shortstop",
            "left_field",
            "center_field",
        ]
        players = [
            {
                "player": i + 1,
                "is_starter": True,
                "position": pos,
                "batting_order": i + 1,
            }
            for i, pos in enumerate(positions)
        ]
        errors = validate_softball_lineup(players, lineup_size=9)
        self.assertTrue(any("9 posiciones" in e for e in errors))

    def test_valid_nine_player_lineup(self):
        positions = [
            "pitcher",
            "catcher",
            "first_base",
            "second_base",
            "third_base",
            "shortstop",
            "left_field",
            "center_field",
            "right_field",
        ]
        players = [
            {
                "player": i + 1,
                "is_starter": True,
                "position": pos,
                "batting_order": i + 1,
            }
            for i, pos in enumerate(positions)
        ]
        self.assertEqual(validate_softball_lineup(players, lineup_size=9), [])

    def test_ten_player_lineup_requires_dh(self):
        positions = [
            "pitcher",
            "catcher",
            "first_base",
            "second_base",
            "third_base",
            "shortstop",
            "left_field",
            "center_field",
            "right_field",
        ]
        players = [
            {
                "player": i + 1,
                "is_starter": True,
                "position": pos,
                "batting_order": i + 1,
            }
            for i, pos in enumerate(positions)
        ]
        errors = validate_softball_lineup(players, lineup_size=10)
        self.assertTrue(any("bateador designado" in e for e in errors))
