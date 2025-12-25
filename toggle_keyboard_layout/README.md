# Toggle Keyboard Layout (한/영 전환)

This project provides an AutoHotkey script to toggle the Korean/English keyboard layout using the `Shift + Space` shortcut.

This is a common customization for users who prefer using `Shift + Space` instead of the dedicated `한/영` (Han/Yeong) key on Korean keyboards.

## Prerequisites

- [AutoHotkey v2.0](https://www.autohotkey.com/) or later must be installed.

## Usage

1.  Install AutoHotkey.
2.  Run the `hangul_shift_space.ahk` script by double-clicking it.
3.  The script will run in the background.
4.  Press `Shift + Space` to toggle between the Hangul and English keyboard layouts.

## Script

The `hangul_shift_space.ahk` script contains the following code:

```ahk
#Requires AutoHotkey v2.0

; Send Han/Yeong toggle event when Shift + Space is pressed
+Space::
{
    ; Directly sends the scancode for the Han/Yeong key (SC1F2)
    Send "{vk15sc1F2}"
}
```
