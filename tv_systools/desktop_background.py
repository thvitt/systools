import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from .util import run_pipe

logger = logging.getLogger(__name__)

# Re-use regex from monitor_switch.py for consistency
output_re = re.compile(
    r"^(?P<output>\S+) (?P<connected>connected|disconnected) (?P<primary>primary *)?(?:(?P<width>\d+)x(?P<height>\d+)\+(?P<x>\d+)\+(?P<y>\d+))?.*?(?:(?P<physx>\d+)mm x (?P<physy>\d+)mm)?$"
)


def get_connected_monitors() -> list[str]:
    """
    Returns a list of names for monitors that are currently connected and active (have a resolution/position).
    """
    try:
        output = run_pipe("xrandr", "--query")
        monitors = []
        for line in output.splitlines():
            match = output_re.match(line)
            if match:
                groups = match.groupdict()
                # A monitor is active if it's connected and has a position (x is not None)
                if groups["connected"] == "connected" and groups["x"] is not None:
                    monitors.append(groups["output"])
        return monitors
    except Exception as e:
        logger.error(f"Failed to query monitors via xrandr: {e}")
        return []


def set_screens_background(*image_paths: str | Path):
    """
    Sets the desktop background for each active screen.
    Uses 'feh --bg-fill'.

    If multiple images are provided, they are assigned to monitors in the order
    reported by xrandr. If fewer images are provided than monitors, the last image
    may be repeated or behaviors may vary by feh version; it is recommended to
    provide one image per screen.
    """
    if not image_paths:
        logger.warning("No image paths provided to set_screens_background.")
        return

    feh = shutil.which("feh")
    if not feh:
        logger.error("feh is not installed. Background cannot be set.")
        return

    cmd = [feh, "--bg-fill"]
    for img in image_paths:
        path = Path(img).expanduser().resolve()
        if not path.exists():
            logger.warning(f"Background image not found: {path}")
            continue
        cmd.append(str(path))

    if len(cmd) <= 2:
        logger.error("No valid background images found.")
        return

    try:
        subprocess.run(cmd, check=True)
        logger.info(f"Successfully set background using {len(cmd)-2} images.")
    except subprocess.CalledProcessError as e:
        logger.error(f"feh failed to set background: {e}")


def set_lock_screen_background(image_path: str | Path):
    """
    Sets the lock screen background.
    Primary method: betterlockscreen -u <image>
    Also logs instructions for LightDM GTK Greeter.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        logger.error(f"Lock screen image not found: {path}")
        return

    # 1. betterlockscreen (common on Qtile/i3 setups)
    betterlockscreen = shutil.which("betterlockscreen")
    if betterlockscreen:
        try:
            logger.info(f"Updating betterlockscreen cache with {path}...")
            # -u updates the cache, which is what's needed for the background to change
            subprocess.run([betterlockscreen, "-u", str(path)], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"betterlockscreen update failed: {e}")
    else:
        logger.debug("betterlockscreen not found in PATH.")

    # 2. LightDM GTK Greeter
    greeter_conf = Path("/etc/lightdm/lightdm-gtk-greeter.conf")
    if greeter_conf.exists():
        logger.info(
            "To update LightDM background permanently, ensure the following is in [greeter] section of %s:",
            greeter_conf,
        )
        logger.info("background = %s", path)
        # Note: Writing to /etc/lightdm requires root privileges.
    else:
        logger.debug("LightDM GTK Greeter config not found at expected location.")


def get_theme_mode() -> Literal["dark", "light", "unknown"]:
    """
    Detects whether the system is using a dark or light theme.
    Returns 'dark', 'light', or 'unknown'.
    """
    # Priority 1: XDG Portal (modern, cross-desktop standard)
    try:
        # Appearance color-scheme: 0: No preference, 1: Prefer dark, 2: Prefer light
        cmd = [
            "dbus-send",
            "--session",
            "--print-reply",
            "--dest=org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings.Read",
            "string:org.freedesktop.appearance",
            "string:color-scheme",
        ]
        res = run_pipe(*cmd)
        if "uint32 1" in res:
            return "dark"
        if "uint32 2" in res:
            return "light"
    except Exception:
        pass

    # Priority 2: GSettings color-scheme (GNOME/GTK specific)
    try:
        res = run_pipe(
            "gsettings",
            "get",
            "org.gnome.desktop.interface",
            "color-scheme",
            strip=True,
        )
        if "dark" in res.lower():
            return "dark"
        if "light" in res.lower():
            return "light"
    except Exception:
        pass

    # Priority 3: GTK theme name (heuristic)
    try:
        res = run_pipe(
            "gsettings", "get", "org.gnome.desktop.interface", "gtk-theme", strip=True
        )
        if "dark" in res.lower():
            return "dark"
    except Exception:
        pass

    return "unknown"
