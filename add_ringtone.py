#!/usr/bin/env python3
"""add_ringtone.py - cut an audio file into an iPhone tone and install it over USB.

No iTunes, no GarageBand, no jailbreak. The iPhone keeps custom tones in
/iTunes_Control/Ringtones/ and lists them in /iTunes_Control/iTunes/Ringtones.plist;
this script writes both over the phone's file service (AFC), the same way an iTunes
tone sync does. The tone appears under Ringtones in every sound picker (alarms,
ringtone, text tone) after the phone restarts.

  add_ringtone.py song.mp3                         cut 0:00-0:39, install as "song"
  add_ringtone.py song.mp3 --start 1:10 --name "Wake Up" --restart
  add_ringtone.py tone.m4r                         install a ready-made tone as is
  add_ringtone.py song.mp3 --output tone.m4r       cut only, touch no phone
  add_ringtone.py --list                           show the custom tones on the phone
  add_ringtone.py --remove "Wake Up"               remove a custom tone

Tones top out at 40 seconds, so cuts are capped at 39 s. A tone whose name is
already on the phone is replaced, not duplicated. Before every write the phone's
Ringtones.plist is saved to ./backups/.

Needs: Python 3.9+, `pip install pymobiledevice3`, and ffmpeg/ffprobe on PATH for
cutting (not for installing a ready .m4r). The phone must be plugged in, unlocked
and trusting this computer.
"""
import argparse
import asyncio
import inspect
import os
import pathlib
import plistlib
import random
import re
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import time

MAX_LEN = 39.0
PLIST = "/iTunes_Control/iTunes/Ringtones.plist"
TONES = "/iTunes_Control/Ringtones"
BACKUPS = pathlib.Path(__file__).resolve().parent / "backups"


# --- cutting -----------------------------------------------------------------

def seconds(s):
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m) * 60 + float(sec)
    return float(s)


def clean_name(path):
    n = path.stem
    n = re.sub(r"^[\w-]+\.(com|net|org|is|io)[_ -]+", "", n, flags=re.I)  # "site.com_-_" download prefixes
    n = re.sub(r"[_ -]*\d+[_ ]?kbps$", "", n, flags=re.I)
    n = re.sub(r"_+", " ", n).strip(" -")
    return n or "Custom Tone"


def duration(path):
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout)
    except ValueError:
        return None


def cut(src, out, start, length):
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not on PATH; install it, or pass a ready-made .m4r")
    fade = "afade=t=out:st=%.2f:d=3" % max(length - 3, 0)
    if start > 0:
        fade = "afade=t=in:d=1," + fade
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-t", str(length),
                    "-i", str(src), "-vn", "-af", fade, "-c:a", "aac", "-b:a", "192k",
                    "-f", "ipod", str(out)], check=True)
    dur = duration(out) or length
    if dur < 1:
        raise SystemExit("the cut came out %.1fs long; is --start past the end of the track?" % dur)
    return dur


# --- the phone -----------------------------------------------------------------

async def maybe(x):
    # pymobiledevice3 moved from sync to async APIs across versions; accept both
    return await x if inspect.isawaitable(x) else x


async def connect():
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService
    ld = await maybe(create_using_usbmux())
    return ld, await maybe(AfcService(ld))


async def read_list(afc):
    try:
        raw = await maybe(afc.get_file_contents(PLIST))
    except Exception:
        return None, {"Ringtones": {}}, plistlib.FMT_BINARY
    fmt = plistlib.FMT_BINARY if raw.startswith(b"bplist") else plistlib.FMT_XML
    d = plistlib.loads(raw)
    d.setdefault("Ringtones", {})
    return raw, d, fmt


def backup(raw):
    if raw is None:
        return
    BACKUPS.mkdir(exist_ok=True)
    stamp, n = time.strftime("Ringtones-%Y%m%d-%H%M%S"), 1
    path = BACKUPS / (stamp + ".plist")
    while path.exists():
        n += 1
        path = BACKUPS / ("%s-%d.plist" % (stamp, n))
    path.write_bytes(raw)
    print("backed up the phone's tone list to %s" % path)


def show(d):
    tones = sorted(d["Ringtones"].items(), key=lambda kv: kv[1].get("Name", ""))
    print("custom tones on the phone:" if tones else "no custom tones on the phone")
    for fn, t in tones:
        print("  %-40s %4ds  (%s)" % (t.get("Name", "?"), t.get("Total Time", 0) // 1000, fn))


async def install(local, name, ms, restart):
    ld, afc = await connect()
    raw, d, fmt = await read_list(afc)
    backup(raw)
    same = [fn for fn, t in d["Ringtones"].items() if t.get("Name") == name]
    if same:
        fn = same[0]
        print("replacing the tone already named %r" % name)
    else:
        fn = None
        while fn is None or fn in d["Ringtones"]:
            fn = "".join(random.choice(string.ascii_uppercase) for _ in range(4)) + ".m4r"
    await maybe(afc.set_file_contents(TONES + "/" + fn, pathlib.Path(local).read_bytes()))
    d["Ringtones"][fn] = {"Name": name, "GUID": secrets.token_hex(8).upper(),
                          "PID": random.randint(-2**63, 2**63 - 1), "Total Time": ms,
                          "Protected Content": False, "Artist": "", "Album": "", "Genre": ""}
    await maybe(afc.set_file_contents(PLIST, plistlib.dumps(d, fmt=fmt)))
    _, d, _ = await read_list(afc)
    print("installed %r" % name)
    show(d)
    await finish(ld, restart)


async def remove(name, restart):
    ld, afc = await connect()
    raw, d, fmt = await read_list(afc)
    hits = [fn for fn, t in d["Ringtones"].items() if t.get("Name") == name]
    if not hits:
        show(d)
        raise SystemExit("no custom tone named %r" % name)
    backup(raw)
    for fn in hits:
        del d["Ringtones"][fn]
        try:
            await maybe(afc.rm(TONES + "/" + fn))
        except Exception:
            pass
    await maybe(afc.set_file_contents(PLIST, plistlib.dumps(d, fmt=fmt)))
    print("removed %r" % name)
    show(d)
    await finish(ld, restart)


async def finish(ld, restart):
    if restart:
        from pymobiledevice3.services.diagnostics import DiagnosticsService
        await maybe(DiagnosticsService(ld).restart())
        print("phone restarting; the tone shows under Ringtones once it is back")
    else:
        print("restart the phone (or rerun with --restart) to see the change in the sound pickers")


async def list_tones():
    _, afc = await connect()
    _, d, _ = await read_list(afc)
    show(d)


# --- main ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", nargs="?", help="any audio file ffmpeg reads, or a ready .m4r")
    ap.add_argument("--start", default="0", help="where the cut starts: seconds or M:SS (default 0)")
    ap.add_argument("--length", type=float, default=MAX_LEN, help="cut length in seconds, max 39")
    ap.add_argument("--name", help="name shown in the sound picker (default: the file name)")
    ap.add_argument("--output", help="write the cut .m4r here and stop; no phone needed")
    ap.add_argument("--restart", action="store_true", help="restart the phone afterwards")
    ap.add_argument("--list", action="store_true", help="list the custom tones on the phone")
    ap.add_argument("--remove", metavar="NAME", help="remove the custom tone with this name")
    a = ap.parse_args()

    if a.list:
        return asyncio.run(list_tones())
    if a.remove:
        return asyncio.run(remove(a.remove, a.restart))
    if not a.audio:
        ap.error("give an audio file, or --list / --remove")
    src = pathlib.Path(a.audio).expanduser().resolve()
    if not src.is_file():
        raise SystemExit("no file at %s" % src)
    name = a.name or clean_name(src)

    if src.suffix.lower() == ".m4r" and a.start == "0" and not a.output:
        dur = duration(src)
        if dur and dur > 40:
            raise SystemExit("%s is %.0fs; tones top out at 40s" % (src.name, dur))
        return asyncio.run(install(src, name, int((dur or MAX_LEN) * 1000), a.restart))

    start, length = seconds(a.start), min(a.length, MAX_LEN)
    out = pathlib.Path(a.output).expanduser().resolve() if a.output else \
        pathlib.Path(tempfile.gettempdir()) / ("tone-%s.m4r" % secrets.token_hex(3))
    dur = cut(src, out, start, length)
    print("cut %.0fs from %s, starting at %.0fs" % (dur, src.name, start))
    if a.output:
        print("wrote %s" % out)
        return 0
    try:
        return asyncio.run(install(out, name, int(dur * 1000), a.restart))
    finally:
        out.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
