# Phone Vault — handoff

Read this first. Keep it current: update **Next steps** and add a line to the **Session log** (newest first) at the end of every work session. Bump the version and add a CHANGELOG entry for every change that ships.

## Next steps (top = next)

1. **v0.2.0 — Back up (copy to the PC).** This is the core feature still missing.
   - Settings: backup root folder (default `~/Phone Vault/<device label>/`).
   - Archive layout: `<root>/<Group>/<Category>/<YYYY>/<MM>/<filename>`, e.g. `Yours/Camera photos/2026/11/PXL_….jpg`. Make the layout a setting (by category, by date, or keep phone folders).
   - Copy engine in `core/backup.py` (Qt-free): ADB `pull -a` or file copy for folders, written to `*.part` then renamed. Keep mtime. Run in a worker thread with progress and cancel, like `ScanThread`.
   - Index: SQLite at `<root>/.phonevault/index.sqlite` with rel_path, size, mtime, sha256, dest_path, category, backed_up_at, device. Incremental runs skip files whose (rel_path, size, mtime) is already in the index.
   - Verify: hash the copy and compare it with the size (and hash when it's cheap). Only files that pass verification count as backed up.
   - Name collisions: add `-1`, `-2`… and never overwrite.
   - UI: a **Back up** primary button next to Scan, a "Backed up" badge on cards, and a sidebar section *BACKUP: New / Backed up*.
2. **v0.3.0 — Safe to delete.** Add a view of files that are verified in the archive. *Remove from phone* asks for confirmation and deletes only verified files (ADB: `adb shell rm -- <quoted path>`; folders: `os.remove`). Write a log of deleted files. Never delete anything that isn't verified.
3. **v0.4.0 — Duplicates.** Exact duplicates by size, then sha256. WhatsApp `Sent/` copies matched to the camera originals by date and perceptual hash (`imagehash` dHash). Add an option to skip backing up sent copies.
4. **v0.5.0 — Video and audio metadata.** Use `ffprobe` for the date taken, duration and camera on videos, and `ffmpeg` for video thumbnails (one frame at 1 s). Both are optional and the app degrades if they're missing.
5. **v0.6.0 — Automatic backups.** Watch for the phone (`adb track-devices`, gvfs mount events). Offer "Back up when connected" and a tray/notification summary.
6. **v0.7.0 — Archive browser.** Open an existing archive without a phone, using the same grid, list and details views.
7. **Packaging.** `.deb` or Flatpak, app ID `io.github.ozzy-apps.PhoneVault`, AppStream metainfo.

## What it is

A Linux desktop app (Zorin OS first) that connects to an Android phone, scans all files and sorts them into categories (camera photos, screenshots, chat media, received photos, downloads, documents…). The goal is sporadic, incremental backups to the PC so the phone can be cleared safely. The UI follows the user's **Inca** 3D app: near-black neutral panels, amber accent, uppercase section labels, monospace counts, segmented pill toggles, a library-style card grid and a right-hand inspector.

## Tech stack

- Python 3.10+ (Zorin 17 ships 3.10)
- PySide6 (Qt 6 Widgets, Fusion style + generated QSS)
- Pillow for EXIF and size probing (optional `pillow-heif`)
- `adb` (Ubuntu package `adb`) for USB debugging, gvfs MTP mounts for File transfer
- pytest for tests
- Semantic Versioning; the version is in `phonevault/__init__.py` and `pyproject.toml` reads it from there

## Architecture

```
core/ (no Qt)                              ui/ (PySide6)
  sources/  Source ABC                       main_window.py   assembles everything, menus, scan flow
    adb.py     find+stat listing, head -c,   category_panel.py NavList: sidebar sections, categories, match filter
               pull, getprop/wm size         grid_view.py     card grid (delegate) + justified cells
    folder.py  os.walk (MTP mounts, dirs)    file_view.py     table model, filter proxy (category/match/text)
    discovery.py adb devices + gvfs mounts   thumbnails.py    lazy LIFO thumbnail loader, disk cache
  scanner.py  run_scan() pipeline            details_panel.py inspector + async preview
  classifier.py rules → category/origin/     settings_dialog.py live-applied preferences
              reason/confidence, dates        themes.py        built-in + JSON user themes
  metadata.py  EXIF probe from 128 KB         style.py         palette + QSS from a Theme
  models.py    MediaFile, Category, etc.      widgets.py       Segmented, DevicePill
  settings.py  JSON settings, XDG paths       workers.py       ScanThread, run_task, local_copy, previews
```

Scan pipeline (`core/scanner.py`): list files (with skip rules) → first sort pass → choose which files to probe (*smart*: the ones where EXIF would change the answer, plus up to 24 camera and 12 screenshot samples) → probe in a thread pool → learn the phone's cameras and screen sizes → final sort pass. Changing *Your cameras* in Settings re-sorts the scan in place without rescanning.

Paths are always POSIX and relative to the storage root (`/storage/emulated/0` over ADB).

## What's built (v0.1.0)

- Connect: ADB devices (USB/Wi-Fi) with state notes, MTP/PTP mounts, any folder, recent folders.
- Scan: progress per phase, cancel, skip patterns, hidden-file toggle. Measured on the sample phone: 180 files in 0.1 s, the same result over a fake adb.
- Sort: 16 categories, the rules in the README table, reasons and match levels, received-photo detection via EXIF, screenshot detection via screen size, dates.
- UI: Inca-style top bar with menus and device pill, sidebar (Library / Yours / Chats / Received / Files / Match), grid (S/M/L, lazy thumbnails) and list views, search, sort, storage bar, details inspector with preview, open file, show in folder, CSV export.
- Customisation: 4 built-in themes, JSON user themes (`~/.config/phone-vault/themes/`), accent override, interface size 80–150 %, density, view settings remembered.
- Tooling: `run.sh`, `install.sh`, `tools/make_sample_phone.py`, `tools/capture_screenshots.py`, 46 passing tests.

## Conventions and preferences

- No filler text in the UI: only functional labels and hints.
- No green UI themes. A test checks that no built-in accent hue falls in the green range.
- Neutral dark grey base. The default accent is Inca amber, and blue is available through *Inca Blue* / *Graphite*.
- Every new UI element must take its colours from `Theme`. Never hard-code colours in widgets (category colours in `models.CATEGORY_INFO` are the exception).
- Keep `core/` free of Qt so it stays testable.
- Update README screenshots with `tools/capture_screenshots.py` when the UI changes.

## Known gaps and risks

- No copying or deleting yet (v0.2/v0.3).
- Video files have no thumbnails and no date from metadata (v0.5).
- EXIF thumbnails over ADB ignore orientation, so some can show sideways in the grid. Full previews are rotated correctly.
- The Android 11+ `Android/data` and `Android/obb` folders are unreadable over ADB/MTP and are skipped on purpose.
- MTP mounts are slow (gvfs). The UI recommends ADB.
- ADB listing relies on toybox `find -exec stat -c` (Android 6+). On older devices it fails with an error message.
- The repo isn't on GitHub yet. Create the private repo `ozzy-apps/phone-vault` and push (see the README).

## Running

```bash
./run.sh                    # creates .venv on first run
python3 -m pytest           # tests
python3 tools/make_sample_phone.py /tmp/sample-phone
```

## Session log (newest first)

- **2026-11-19 — v0.1.0.** Project created: core engine, ADB/MTP/folder sources, sorting rules, Inca-style UI, themes, tests, README with screenshots. The repo is packaged locally with the tag `v0.1.0`. It's not pushed yet because repo creation wasn't available from the build session.
