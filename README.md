# iphone-ringtone-usb

Turn any audio file into an iPhone ringtone or alarm sound and install it over USB
from one command. You don't need iTunes, GarageBand or a jailbreak.

```
python add_ringtone.py "some song.mp3" --start 1:10 --name "Wake Up" --restart
```

After the phone restarts, the tone appears under **Ringtones** in every sound picker:
Clock → Alarms → Sound, Settings → Sounds & Haptics, and per-contact tones.

## Why

Apple's Windows "Apple Devices" app can't sync ringtones. The usual workarounds are
iTunes or a multi-step GarageBand export on the phone. This script does what an iTunes
tone sync does, directly:

1. It cuts the clip with ffmpeg into AAC `.m4r`, capped at 39 seconds because iOS tones top out at 40.
2. It copies the clip into the phone's `/iTunes_Control/Ringtones/` over Apple's file
   service (AFC), using [pymobiledevice3](https://github.com/doronz88/pymobiledevice3).
3. It registers the clip in `/iTunes_Control/iTunes/Ringtones.plist`, the list iOS reads its
   custom tones from.
4. It restarts the phone (`--restart`), since iOS only rereads that list on boot.

Tested on an iPhone 15 Pro running iOS 18.7, from Windows 10.

## Setup

- Python 3.9 or newer
- `pip install pymobiledevice3`
- [ffmpeg](https://ffmpeg.org/) and ffprobe on your PATH. You only need them for cutting;
  installing a ready-made `.m4r` works without them.
- **Windows:** install Apple's "Apple Devices" app or iTunes. It supplies the USB
  driver and the Apple Mobile Device service that pymobiledevice3 talks to.
- **macOS:** works out of the box. **Linux:** install `usbmuxd`.

Plug the phone in, unlock it and tap **Trust** when it asks.

## Usage

| Command | What it does |
|---|---|
| `add_ringtone.py song.mp3` | Cuts 0:00–0:39 and installs it, named after the file |
| `add_ringtone.py song.mp3 --start 2:30 --name "Peak"` | Cuts from 2:30 with a custom name |
| `add_ringtone.py tone.m4r` | Installs a ready-made tone as is |
| `add_ringtone.py song.mp3 --output tone.m4r` | Only cuts; doesn't touch the phone |
| `add_ringtone.py --list` | Lists the custom tones on the phone |
| `add_ringtone.py --remove "Peak"` | Removes a custom tone |
| add `--restart` | Restarts the phone afterwards so the change shows up |

Each cut gets a 3-second fade-out, plus a 1-second fade-in when it starts mid-track.
If a tone with the same name is already on the phone, it gets replaced. Your source
audio file is never changed.

## Safety

- Before every write, the script saves the phone's existing `Ringtones.plist` to
  `./backups/`. To roll back, push a backup to `/iTunes_Control/iTunes/Ringtones.plist`
  (for example with `pymobiledevice3 afc push`).
- It only touches the custom-tone folder and its list. It doesn't change system tones,
  music or other data.
- Use audio you have the right to use.

## WSL

USB devices aren't visible inside WSL. Run the script with Windows Python
(`python.exe add_ringtone.py ...`), or cut the tone in WSL with `--output` and install
the `.m4r` from Windows.

## License

MIT
