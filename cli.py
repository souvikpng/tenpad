from __future__ import annotations

import argparse
import contextlib
import select
import signal
import sys
from dataclasses import dataclass

from evdev import InputDevice, UInput, ecodes, list_devices


KEYMAP = {
    "KEY_Y": "KEY_KP7",
    "KEY_U": "KEY_KP8",
    "KEY_I": "KEY_KP9",
    "KEY_H": "KEY_KP4",
    "KEY_J": "KEY_KP5",
    "KEY_K": "KEY_KP6",
    "KEY_N": "KEY_KP1",
    "KEY_M": "KEY_KP2",
    "KEY_COMMA": "KEY_KP3",
    "KEY_B": "KEY_KP0",
}

NUMLOCK_COMBO_KEY = ecodes.KEY_N
NUMLOCK_OUTPUT_KEY = ecodes.KEY_NUMLOCK


@dataclass
class Keyboard:
    device: InputDevice
    grabbed: bool = False


def code_for(name: str) -> int:
    key = name.upper()
    if not key.startswith("KEY_"):
        key = f"KEY_{key}"
    try:
        code = ecodes.ecodes[key]
    except KeyError as error:
        raise argparse.ArgumentTypeError(f"unknown key name: {name}") from error
    return int(code)


def key_name(code: int) -> str:
    name = ecodes.KEY.get(code, str(code))
    if isinstance(name, list):
        return name[0]
    return str(name)


def find_keyboards() -> list[Keyboard]:
    keyboards: list[Keyboard] = []
    for path in list_devices():
        try:
            device = InputDevice(path)
            capabilities = device.capabilities()
            keys = set(capabilities.get(ecodes.EV_KEY, []))
        except OSError as error:
            print(f"Skipping {path}: {error}", file=sys.stderr)
            continue

        has_pointer_axes = ecodes.EV_REL in capabilities or ecodes.EV_ABS in capabilities
        has_mouse_buttons = bool(keys & {ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MOUSE})
        has_keyboard_keys = ecodes.KEY_A in keys and ecodes.KEY_SPACE in keys
        if has_keyboard_keys and not has_pointer_axes and not has_mouse_buttons:
            keyboards.append(Keyboard(device))
        else:
            device.close()
    return keyboards


def build_capabilities(keyboards: list[Keyboard]) -> dict[int, list[int]]:
    keys: set[int] = set()
    for keyboard in keyboards:
        keys.update(keyboard.device.capabilities().get(ecodes.EV_KEY, []))
    keys.update(ecodes.ecodes[name] for name in KEYMAP)
    keys.update(ecodes.ecodes[name] for name in KEYMAP.values())
    keys.add(NUMLOCK_OUTPUT_KEY)
    return {ecodes.EV_KEY: sorted(keys)}


def grab_keyboards(keyboards: list[Keyboard]) -> None:
    for keyboard in keyboards:
        try:
            keyboard.device.grab()
        except OSError as error:
            raise RuntimeError(f"failed to grab {keyboard.device.path}: {error}") from error
        keyboard.grabbed = True


def release_keyboards(keyboards: list[Keyboard]) -> None:
    for keyboard in keyboards:
        if keyboard.grabbed:
            with contextlib.suppress(OSError):
                keyboard.device.ungrab()
            keyboard.grabbed = False
        keyboard.device.close()


def release_held_outputs(
    ui: UInput, held_outputs: dict[tuple[int, int], int], fd: int | None = None
) -> None:
    released = False
    for key_id, output_code in list(held_outputs.items()):
        if fd is not None and key_id[0] != fd:
            continue
        ui.write(ecodes.EV_KEY, output_code, 0)
        del held_outputs[key_id]
        released = True
    if released:
        ui.syn()


def output_for_key_event(
    event_code: int,
    event_value: int,
    active: bool,
    key_id: tuple[int, int],
    mapped_keys: dict[int, int],
    held_outputs: dict[tuple[int, int], int],
) -> int:
    if event_value == 1:
        output_code = mapped_keys.get(event_code, event_code) if active else event_code
        held_outputs[key_id] = output_code
        return output_code
    if event_value == 0:
        return held_outputs.pop(key_id, event_code)
    return held_outputs.get(key_id) or (
        mapped_keys.get(event_code, event_code) if active else event_code
    )


def run(toggle_key: int) -> int:
    keyboards = find_keyboards()
    if not keyboards:
        print("No keyboards found.", file=sys.stderr)
        return 1

    mapped_keys = {ecodes.ecodes[src]: ecodes.ecodes[dst] for src, dst in KEYMAP.items()}
    active = False
    toggle_pressed = False
    toggle_combo_used = False
    numlock_combo_key_down = False
    held_outputs: dict[tuple[int, int], int] = {}
    stop = False

    def handle_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    ui: UInput | None = None
    try:
        ui = UInput(build_capabilities(keyboards), name="tenpad virtual keyboard")
        grab_keyboards(keyboards)
        print(f"Tenpad running. Toggle: {key_name(toggle_key)}. Press Ctrl+C to quit.")

        devices = {keyboard.device.fd: keyboard for keyboard in keyboards}
        while not stop:
            readable, _, _ = select.select(list(devices), [], [], 0.25)
            for fd in readable:
                keyboard = devices[fd]
                try:
                    events = keyboard.device.read()
                except OSError as error:
                    print(f"Lost keyboard {keyboard.device.path}: {error}", file=sys.stderr)
                    if keyboard.grabbed:
                        with contextlib.suppress(OSError):
                            keyboard.device.ungrab()
                        keyboard.grabbed = False
                    keyboard.device.close()
                    del devices[fd]
                    release_held_outputs(ui, held_outputs, fd)
                    if not devices:
                        print("No keyboards left.", file=sys.stderr)
                        stop = True
                    continue

                for event in events:
                    if event.type != ecodes.EV_KEY:
                        continue

                    if event.code == toggle_key:
                        if event.value == 1:
                            toggle_pressed = True
                            toggle_combo_used = False
                        elif event.value == 0:
                            if not toggle_combo_used:
                                active = not active
                                state = "on" if active else "off"
                                print(f"Tenpad {state}")
                            toggle_pressed = False
                            toggle_combo_used = False
                        continue

                    if event.code == NUMLOCK_COMBO_KEY and (
                        toggle_pressed or numlock_combo_key_down
                    ):
                        if event.value == 1 and toggle_pressed:
                            ui.write(ecodes.EV_KEY, NUMLOCK_OUTPUT_KEY, 1)
                            ui.write(ecodes.EV_KEY, NUMLOCK_OUTPUT_KEY, 0)
                            ui.syn()
                            toggle_combo_used = True
                            numlock_combo_key_down = True
                            print("Num Lock")
                        elif event.value == 0:
                            numlock_combo_key_down = False
                        continue

                    key_id = (fd, event.code)
                    output_code = output_for_key_event(
                        event.code,
                        event.value,
                        active,
                        key_id,
                        mapped_keys,
                        held_outputs,
                    )

                    ui.write(ecodes.EV_KEY, output_code, event.value)
                    ui.syn()
    finally:
        if ui is not None:
            release_held_outputs(ui, held_outputs)
        release_keyboards(keyboards)
        if ui is not None:
            ui.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Toggle YUI/HJK/NM,/B into numpad 789/456/123/0."
    )
    parser.add_argument(
        "--toggle-key",
        default="KEY_CAPSLOCK",
        type=code_for,
        help="key used to toggle Tenpad mode, such as KEY_CAPSLOCK or F12",
    )
    args = parser.parse_args()
    try:
        return run(args.toggle_key)
    except OSError as error:
        print(f"Tenpad failed: {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"Tenpad failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
