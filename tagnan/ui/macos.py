"""What the window asks of macOS, through its C interfaces (ctypes: nothing to install).

Each call fails quietly: a missing symbol or a refusal leaves Tagnan as on any other system
(always welcome, no click seen elsewhere, an icon in the Dock).
"""

import ctypes
import logging
from collections.abc import Callable
from functools import cache
from typing import Any

logger = logging.getLogger(__name__)

CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
OBJC = "/usr/lib/libobjc.A.dylib"

COMBINED_SESSION_STATE = 0  # kCGEventSourceStateCombinedSessionState: every input device
LEFT_BUTTON, RIGHT_BUTTON = 0, 1  # kCGMouseButtonLeft, kCGMouseButtonRight
UTF8 = 0x08000100  # kCFStringEncodingUTF8
ACCESSORY = 1  # NSApplicationActivationPolicyAccessory: no Dock icon, no menu bar of its own
CAN_JOIN_ALL_SPACES = 1 << 0  # NSWindowCollectionBehaviorCanJoinAllSpaces


@cache
def _graphics() -> ctypes.CDLL:
    library = ctypes.CDLL(CORE_GRAPHICS)
    library.CGEventSourceButtonState.restype = ctypes.c_bool
    library.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]
    library.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
    library.CGSessionCopyCurrentDictionary.argtypes = []
    return library


@cache
def _foundation() -> ctypes.CDLL:
    library = ctypes.CDLL(CORE_FOUNDATION)
    library.CFStringCreateWithCString.restype = ctypes.c_void_p
    library.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    library.CFDictionaryGetValue.restype = ctypes.c_void_p
    library.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    library.CFRelease.restype = None
    library.CFRelease.argtypes = [ctypes.c_void_p]
    return library


def mouse_down() -> bool:
    """Whether a mouse button is down now, wherever the pointer is."""
    try:
        state = _graphics().CGEventSourceButtonState
        return bool(
            state(COMBINED_SESSION_STATE, LEFT_BUTTON)
            or state(COMBINED_SESSION_STATE, RIGHT_BUTTON)
        )
    except (OSError, AttributeError):
        return False


def screen_locked() -> bool:
    """Whether the session's screen is locked."""
    try:
        graphics, foundation = _graphics(), _foundation()
        session = graphics.CGSessionCopyCurrentDictionary()
        if not session:
            return False  # nothing to tell: welcome, as elsewhere
        key = foundation.CFStringCreateWithCString(None, b"CGSSessionScreenIsLocked", UTF8)
        try:
            value = foundation.CFDictionaryGetValue(session, key)
            true = ctypes.c_void_p.in_dll(foundation, "kCFBooleanTrue").value
            return bool(value) and value == true
        finally:
            foundation.CFRelease(key)
            foundation.CFRelease(session)
    except (OSError, AttributeError, ValueError):
        return False


@cache
def _objc() -> tuple[ctypes.CDLL, Callable[..., Any], Callable[..., Any]]:
    """The Objective-C runtime, and objc_msgSend as two prototypes (it takes the method's own
    signature): one argument-less call returning an object, one with an integer argument."""
    objc = ctypes.CDLL(OBJC)
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    send = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
        ("objc_msgSend", objc)
    )
    send_long = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(
        ("objc_msgSend", objc)
    )
    return objc, send, send_long


def hide_from_dock() -> None:
    """No icon in the Dock: he lives on the desktop and in the menu bar, as on Windows he stays
    out of the taskbar. To call once the QApplication exists."""
    try:
        objc, send, send_long = _objc()
        application = send(
            objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication")
        )
        if application:
            send_long(application, objc.sel_registerName(b"setActivationPolicy:"), ACCESSORY)
    except (OSError, AttributeError) as error:
        logger.warning("could not leave the Dock: %s", error)


def join_all_spaces(view: int) -> None:
    """The window of this NSView (a QWindow's winId) shows on every desktop (Spaces): he stays at
    hand whichever one is in front."""
    try:
        objc, send, send_long = _objc()
        window = send(view, objc.sel_registerName(b"window"))
        if window:
            send_long(window, objc.sel_registerName(b"setCollectionBehavior:"), CAN_JOIN_ALL_SPACES)
    except (OSError, AttributeError) as error:
        logger.warning("could not join every desktop: %s", error)
