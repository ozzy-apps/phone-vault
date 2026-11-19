# Phone Vault — handoff

Read this first. Keep it current: update **Next steps** and add a line to the **Session log** (newest first) at the end of every work session. Bump the version and add a CHANGELOG entry for every change that ships.

## Next steps (top = next)

1. **Confirm on a real phone.** v0.2.0 was tested on a generated sample phone and a fake `adb`, not on hardware. When the user reports results, fix whatever their phone does differently (toybox `find`/`stat`/`sha256sum`, MTP timing, odd folder names).
2. **v0.3.0 — Safe to delete.**
   - Add a *Free up space* view: files that are backed up (`MediaFile.backed_up`, which means the index row exists and the copy is on disk with the right size). Optionally re-hash before deleting.
   - *Remove from phone* asks for confirmation (count, size, category breakdown) and deletes only verified files. ADB: batched `adb shell rm -f -- <quoted paths>`. Folders: `os.remove`.
   - Write a deletion log to `.phonevault/deleted-YYYYMMDD-HHMMSS.csv` and mark the rows in the index (`deleted_from_phone_at`).
   - After deleting over ADB, trigger a media rescan so the gallery updates: `adb shell cmd media_provider scan` or `am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE`. Check what works on Android 10+.
   - Never delete anything that isn't verified, and never delete with a scan older than the current device state (re-list first).
3. **v0.4.0 — Duplicates.** Exact duplicates via the SHA-256 already stored in the index. Match WhatsApp `Sent/` copies to camera originals by date and perceptual hash (`imagehash` dHash). Backups can already skip sent copies.
4. **v0.5.0 — Video and audio metadata.** Use `ffprobe` for the date taken, duration and camera on videos, and `ffmpeg` for video thumbnails (one frame at 1 s). Both are optional and the app degrades if they're missing.
5. **v0.6.0 — Automatic backups.** Detection already polls every 3 s (`MainWindow._poll_devices`). Add "Back up when this phone connects" per phone (`settings.device_folders` keys identify phones), plus a notification summary.
6. **v0.7.0 — Archive browser.** Open an existing archive without a phone, using the same grid, list and details views (read `index.sqlite` + files).
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
  backup.py   Archive (index.sqlite),       backup_dialog.py options, plan summary, space check
              plan_backup, run_backup        connection_dialog.py findings + Restart ADB
  diagnostics.py USB (/sys) + adb + gvfs    (BackupThread lives in workers.py)
              → findings with fixes
  classifier.py rules → category/origin/     settings_dialog.py live-applied preferences
              reason/confidence, dates        themes.py        built-in + JSON user themes
  metadata.py  EXIF probe from 128 KB         style.py         palette + QSS from a Theme
  models.py    MediaFile, Category, etc.      widgets.py       Segmented, DevicePill
  settings.py  JSON settings, XDG paths       workers.py       ScanThread, run_task, local_copy, previews
```

Scan pipeline (`core/scanner.py`): list files (with skip rules) → first sort pass → choose which files to probe (*smart*: the ones where EXIF would change the answer, plus up to 24 camera and 12 screenshot samples) → probe in a thread pool → learn the phone's cameras and screen sizes → final sort pass. Changing *Your cameras* in Settings re-sorts the scan in place without rescanning.

Paths are always POSIX and relative to the storage root (`/storage/emulated/0` over ADB).

## What's built (v0.2.0)

- Backups: `core/backup.py`.
  - Layouts: category (`Yours/Camera photos/YYYY/MM/`, chats get an app subfolder), date, or phone folders.
  - Staging under `.phonevault/staging`, then size check (or phone SHA-256 in checksum mode), local SHA-256, atomic move, and the phone file's mtime set on the copy.
  - Index row per file. Commits every 40 files. Collisions get `-1`. An identical existing file is reused.
  - Cancel happens between batches.
  - ADB `fetch_many` pulls up to 64 small files (each under 16 MB, 96 MB per batch, unique basenames) in one `adb pull`.
  - Incremental matching is on (rel_path, size) plus "copy still exists with that size". mtime is stored but not used for matching, because MTP and ADB can report different mtimes.
- Device folder name: `default_device_folder()` (`Google Pixel 8` from getprop, or the label without `(ADB · USB)` / `— storage`). It's remembered per source key in `settings.device_folders`, so the same phone over ADB and over MTP lands in the same folder when the names match.
- Detection: polls `discover_sources` every 3 s and updates the pill only when the signature changes. Emulators are flagged and never auto-picked. The SDK adb is preferred over `/usr/bin/adb`.
- Connection check: `core/diagnostics.py` + `ui/connection_dialog.py`.
- 63 tests, including a backup over a fake `adb` (batched pulls + `sha256sum`).

## What was built in v0.1.0

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

- No deleting from the phone yet (v0.3).
- Video files have no thumbnails and no date from metadata (v0.5).
- EXIF thumbnails over ADB ignore orientation, so some can show sideways in the grid. Full previews are rotated correctly.
- The Android 11+ `Android/data` and `Android/obb` folders are unreadable over ADB/MTP and are skipped on purpose.
- MTP mounts are slow (gvfs). The UI recommends ADB.
- ADB listing relies on toybox `find -exec stat -c` (Android 6+). On older devices it fails with an error message.

## Running

```bash
./run.sh                    # creates .venv on first run
python3 -m pytest           # tests
python3 tools/make_sample_phone.py /tmp/sample-phone
```

## Session log (newest first)

- **2026-11-19 — v0.2.0.** Backups (engine, dialog, badges, Backup filter, Show backup), automatic phone detection, Connection check, SDK-adb preference, emulator handling. The user reported that their phone wouldn't connect even with USB debugging on, and the cause isn't known yet. Most likely: the phone was plugged in after the app started (no polling in v0.1.0), the "Allow USB debugging" prompt wasn't accepted, or Android Studio's adb clashed with the system adb. All three are now handled or reported by the Connection check. Waiting for the user's `adb devices -l` output or Connection check report.

- **2026-11-19 — v0.1.0.** Project created: core engine, ADB/MTP/folder sources, sorting rules, Inca-style UI, themes, tests, README with screenshots. The repo is packaged locally with the tag `v0.1.0`. It's not pushed yet because repo creation wasn't available from the build session.
