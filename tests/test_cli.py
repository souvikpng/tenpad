import unittest

from evdev import ecodes

from tenpad.cli import output_for_key_event


class OutputForKeyEventTest(unittest.TestCase):
    def test_active_unmapped_repeat_falls_back_to_original_key(self) -> None:
        held_outputs: dict[tuple[int, int], int] = {}

        output_code = output_for_key_event(
            ecodes.KEY_A,
            2,
            True,
            (1, ecodes.KEY_A),
            {ecodes.KEY_Y: ecodes.KEY_KP7},
            held_outputs,
        )

        self.assertEqual(output_code, ecodes.KEY_A)

    def test_release_uses_pressed_output_after_toggle_change(self) -> None:
        held_outputs: dict[tuple[int, int], int] = {}
        key_id = (1, ecodes.KEY_Y)

        down_code = output_for_key_event(
            ecodes.KEY_Y,
            1,
            True,
            key_id,
            {ecodes.KEY_Y: ecodes.KEY_KP7},
            held_outputs,
        )
        up_code = output_for_key_event(
            ecodes.KEY_Y,
            0,
            False,
            key_id,
            {ecodes.KEY_Y: ecodes.KEY_KP7},
            held_outputs,
        )

        self.assertEqual(down_code, ecodes.KEY_KP7)
        self.assertEqual(up_code, ecodes.KEY_KP7)


if __name__ == "__main__":
    unittest.main()
