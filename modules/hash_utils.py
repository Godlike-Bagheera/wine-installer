"""SHA512 + буфер обмена."""
import hashlib
import subprocess
from modules import debug


def verify_sha512(file_path, expected_hex):
    if not expected_hex:
        return True, ""
    try:
        h = hashlib.sha512()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        actual = h.hexdigest().lower()
        return actual == expected_hex.lower(), actual
    except Exception as e:
        debug.dbg_exc(e, "verify_sha512")
        return False, ""


def copy_to_clipboard(text):
    for cmd in [
        ["xclip", "-selection", "clipboard"],
        ["wl-copy"],
        ["xsel", "--clipboard", "--input"],
    ]:
        try:
            r = subprocess.run(
                cmd, input=text.encode(), check=False, timeout=5,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if r.returncode == 0:
                return True
        except (FileNotFoundError, Exception):
            continue
    return False