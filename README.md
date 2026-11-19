# Phone Vault

Back up the files on your Android phone to your Linux PC, sorted by what they actually are: photos you took, screenshots, chat media, things people sent you, and downloads. Built for Zorin OS. Works on any GNOME- or Ubuntu-based desktop.

![Library in grid view](docs/screenshots/library-grid.png)

> **Status: v0.2.0.** Phone Vault connects, sorts, and backs up to your drive: verified and incremental, so later runs only copy what's new. Clearing the backed-up files off the phone is the next milestone (see [handoff.md](handoff.md)).

## Features

- **Three ways to connect:** USB debugging (ADB, fastest), File transfer (MTP mounts that Zorin creates automatically), or any folder.
- **Picks up phones by itself** when they're plugged in or allowed, and never picks an Android Studio emulator over your phone.
- **Connection check** (*Help → Connection check…*): reads the USB bus and adb, and tells you exactly what to fix, such as a charge-only cable, USB debugging not yet allowed, missing permissions, or two adb versions fighting.
- **Incremental, verified backups** into a sorted folder: each file is copied, checked, fingerprinted (SHA-256) and recorded, and the next run copies only new files.
- **Automatic sorting** into 16 categories in four groups:
  - **Yours:** Camera photos, Camera videos, Edited photos, Screenshots, Screen recordings
  - **Chats:** Chat images, Chat videos, Voice notes, Stickers & GIFs (WhatsApp, WhatsApp Business, Telegram, Signal, Messenger, Viber, Discord)
  - **Received:** Received photos, Downloads & saved
  - **Files:** Documents, Audio, Other images, Other videos, Other files
- **Shows why each file was sorted where it is**, with a match level of *Sure*, *Likely* or *Guess*. Filter on *Guess* to review the uncertain ones.
- **Tells your photos from other people's** by comparing camera metadata with your phone's own camera, which Phone Vault learns from your camera folder.
- **Grid view with lazy thumbnails.** Over ADB it uses the photo's embedded thumbnail, so whole files aren't copied just to preview them.
- **List view** with sortable columns, and search across names, folders, apps, cameras and reasons.
- **Storage bar** showing what takes up space on the phone. Click a segment to filter to that category.
- **Details panel** with a preview, the reason for the category, origin, date and where it came from, camera, size and path on the phone.
- **Export to CSV** of whatever is currently shown.
- **Backed-up badges** on cards, a *Backup* filter in the sidebar, and *Show backup* for any file.

## How sorting works

Each file is checked against these signals, strongest first:

| Signal | Example | Result |
|---|---|---|
| App media folder | `Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images/` | Chat images (`Sent/` = your own compressed copies) |
| Screenshot folder or name | `Pictures/Screenshots/`, `Screenshot_20261118-101010_Chrome.jpg` | Screenshots (Samsung names also give the app) |
| Camera folder | `DCIM/Camera/PXL_20261118_101010123.jpg` | Camera photos / videos |
| Camera metadata (EXIF) | Make `Apple`, Model `iPhone 15 Pro` in your Downloads | Received photos, because it isn't your camera |
| Pixel size | 1080 × 2400 with no camera data | Screenshot (*Likely*) |
| Folder fallbacks | `Download/`, `Recordings/`, `Music/`, `Documents/` | Downloads, Audio, Documents… |

**What about photos sent through WhatsApp?** A photo sent the normal way is recompressed and its camera metadata is removed, so it lands in *Chat images*. A photo sent **as a document** keeps the original file, including the sender's camera model. Phone Vault spots that the camera isn't yours and files it under *Received photos*.

Dates come from the photo metadata first, then the filename (`IMG_20261118_…`, `IMG-20261118-WA0001`), then the file's modified time.

## Backing up

Scan first, then press **Back up**. The dialog shows how many files are new, how much space they need and what's free, and an example of where a file will land.

- **Destination:** `~/Phone Vault` by default, or any folder or external drive. Each phone gets its own folder (`Google Pixel 8`). Keep that name the same between backups.
- **Layout:**
  - *By category:* `Yours/Camera photos/2026/11/…`, `Chats/Chat images/WhatsApp/2026/11/…`
  - *By date:* `2026/11/Camera photos/…`
  - *Same as phone:* `DCIM/Camera/…`
- **Verify:**
  - *Size check:* fast. Every copy still gets a SHA-256 fingerprint.
  - *Checksum on the phone:* the phone computes the SHA-256 too and the two must match. Slower, because every file is read twice.
- **Include:** untick categories you don't want, such as Stickers & GIFs. You can also skip your *sent* chat copies, which are compressed duplicates of your own photos.

How the copying works:
- Files go to `.phonevault/staging` first and are moved into place only after the check passes. A stopped or failed run leaves no half-written files.
- Each file keeps its original date.
- Two different files with the same name both survive (`IMG.jpg`, `IMG-1.jpg`).
- If the index is ever lost, identical files already in the archive are recognised instead of being copied again.
- Over ADB, small files are pulled in batches: 180 files took 23 `adb pull` calls in testing, not 180.

The record of what was copied lives in `<phone folder>/.phonevault/index.sqlite`. A file counts as backed up only while its copy still exists with the right size.

## Install (Zorin OS / Ubuntu)

```bash
sudo apt install python3-venv adb      # adb is only needed for USB debugging scans
git clone https://github.com/ozzy-apps/phone-vault.git
cd phone-vault
./install.sh                           # venv + app menu entry + icon
```

Or run it straight from the folder without installing. The first run sets up `.venv`:

```bash
./run.sh
```

Optional HEIC/HEIF support: `.venv/bin/pip install pillow-heif`

## Connecting your phone

**USB debugging (recommended)**
1. On the phone, open *Settings → About phone* and tap *Build number* 7 times.
2. Open *Settings → System → Developer options* and turn on *USB debugging*.
3. Connect the cable and allow this computer on the phone.
4. The phone shows up in the device pill at the top right. Press **Scan**.

### Phone doesn't show up?

Open **Help → Connection check…**. It looks at the USB connection, adb and File transfer mounts, and lists what to fix, with copyable commands. The usual causes:

| What you see | Fix |
|---|---|
| *No phone detected on USB* | Use a data cable (many only charge), plug it straight into the computer, unlock the phone. |
| *USB debugging isn't active on this connection* | Tap the USB notification on the phone and choose *File transfer*, then turn USB debugging off and on. On Xiaomi phones, also enable *USB debugging (Security settings)*. |
| *Allow USB debugging on the phone* | Unlock the phone and tap **Allow**. No prompt? *Developer options → Revoke USB debugging authorizations*, then replug. |
| *No permission to use the USB device* | `sudo apt install android-sdk-platform-tools-common`, `sudo usermod -aG plugdev $USER`, log out and in, replug. |
| *Two different adb versions are installed* | Android Studio and the system adb keep restarting each other. Phone Vault uses the Android SDK one; close Android Studio or set one adb in *Settings → Scanning*. |
| *ADB isn't installed* | `sudo apt install adb` |

**Restart ADB** in the same dialog fixes most *offline* states.

**File transfer (MTP):** set the phone's USB mode to *File transfer*. Once Zorin mounts it, it appears in the device list.

**Any folder:** use *File → Choose folder…*, for example a copy of your phone storage you made earlier.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| `F5` / `Esc` | Scan / stop scan |
| `Ctrl+R` | Refresh devices |
| `Ctrl+O` | Choose folder |
| `Ctrl+B` | Back up |
| `Ctrl+F` | Search |
| `Ctrl+1` / `Ctrl+2` | Grid / list view |
| `Ctrl+I` | Show or hide the details panel |
| `Ctrl+E` | Export the shown files as CSV |
| `Ctrl+,` | Settings |

## Customisation

Everything applies immediately and is saved in `~/.config/phone-vault/settings.json`.

- **Themes:** *Inca* (default, matching the Inca 3D app), *Inca Blue*, *Graphite* and *Light*.
- **Custom themes:** drop JSON files into `~/.config/phone-vault/themes/`. Any field you leave out falls back to the default theme, so this is already a complete theme:
  ```json
  { "name": "Mine", "accent": "#3d8bfd" }
  ```
  *Settings → New theme from current* writes a full template you can edit. The fields are `bg`, `surface`, `sidebar`, `field`, `surface_alt`, `raised`, `border`, `text`, `text_muted`, `accent`, `accent_text`, `sel_strong`, `sel_soft`, `warning` and `danger`.
- **Accent colour** override, **interface size** (80–150 %), and **density** (comfortable or compact).
- **Layout:** grid or list, thumbnail size S/M/L, sort by date, name or size, and the details panel on or off.
- **Sorting:** how much photo metadata to read (*Smart*, *All*, *Off*), plus your own camera models in case automatic detection misses one.
- **Scanning:** paths and patterns to skip, whether to include hidden files, and a custom `adb` location.

| | |
|---|---|
| ![Received photos in list view](docs/screenshots/received-list.png) | ![Screenshots, large grid](docs/screenshots/screenshots-grid.png) |
| *Received photos: the reason shows the sender's camera* | *A downloaded image recognised as a screenshot by its size* |
| ![Backup dialog](docs/screenshots/backup-dialog.png) | ![Connection check](docs/screenshots/connection-check.png) |
| *Back up: what's new, where it goes, space check* | *Connection check: what's wrong and how to fix it* |
| ![Light theme](docs/screenshots/theme-light.png) | ![Settings](docs/screenshots/settings.png) |
| *Light theme* | *Settings* |

## Project layout

```
phonevault/
  core/                 Qt-free logic, unit tested
    models.py           MediaFile, categories, confidence
    classifier.py       sorting rules and reasons
    backup.py           archive layout, SQLite index, verified incremental copying
    diagnostics.py      connection check (USB via /sys, adb, gvfs)
    metadata.py         EXIF/size probing from the first 128 KB of a file
    scanner.py          list → sort → probe → learn → sort
    settings.py         JSON settings, config/cache paths
    sources/            adb.py, folder.py (MTP/any folder), discovery.py
  ui/                   PySide6 interface (themes, style, views, panels)
tools/
  make_sample_phone.py  generates a fake phone for demos and tests
  capture_screenshots.py renders these README screenshots headlessly
tests/                  pytest suite
```

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
python3 tools/make_sample_phone.py /tmp/sample-phone       # then File → Choose folder…
QT_QPA_PLATFORM=offscreen python3 tools/capture_screenshots.py docs/screenshots
```

Versions follow [Semantic Versioning](https://semver.org). The version lives in `phonevault/__init__.py`, and changes are listed in [CHANGELOG.md](CHANGELOG.md). [handoff.md](handoff.md) holds the current state and the next steps.
