from __future__ import annotations

import unittest

from buddy_parallel.cli import build_parser


class CliParserTests(unittest.TestCase):
    def test_parser_accepts_setup_and_flash_board_commands(self) -> None:
        parser = build_parser()

        setup_args = parser.parse_args(["setup"])
        flash_args = parser.parse_args(["flash-board", "--port", "COM7", "--firmware-dir", "firmware", "--erase"])

        self.assertEqual(setup_args.command, "setup")
        self.assertEqual(flash_args.command, "flash-board")
        self.assertEqual(flash_args.port, "COM7")
        self.assertEqual(flash_args.firmware_dir, "firmware")
        self.assertTrue(flash_args.erase)


if __name__ == "__main__":
    unittest.main()
