# Changelog

All notable changes to Phone Vault are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-19

### Added
- Backups: copy files into `~/Phone Vault/<phone>/` (or any folder), sorted by category, by date or with the phone's own folders.
- Backups are incremental: an SQLite index per phone (`.phonevault/index.sqlite`) records every copy with its SHA-256, so later runs copy only new files.
- Verification: a size check plus a local SHA-256 by default, or the phone's own SHA-256 compared with the copy (*Checksum on the phone*).
- Backups are safe to interrupt: copies go to a staging folder and move into place only after they're verified; stopping leaves no partial files.
- Name collisions keep both files (`IMG-1.jpg`), and identical files already in the archive are recognised instead of copied twice.
- Batched `adb pull` for small files: far fewer adb calls on phones with thousands of photos.
- Backup dialog with new/already-backed-up/skipped counts, a free-space check, an example path, category selection and *skip sent chat copies*.
- Backed-up badges in the grid, a Backup column in the list, a Backup filter in the sidebar, a backup row and *Show backup* in the details panel, and *File → Open backup folder*.
- Automatic phone detection every 3 seconds, so there's no need to press Refresh after plugging in or allowing USB debugging.
- *Help → Connection check…* reads USB devices from `/sys` (ADB/MTP interfaces), adb state and gvfs mounts, explains the problem with copyable fixes, and has *Restart ADB* and *Copy report*.

### Changed
- An adb from the Android SDK is preferred over the distro package, which avoids two adb versions restarting each other's server.
- Android Studio emulators are labelled *(Emulator)* and never selected over a real phone.
- Every adb device state is now recognised (authorizing, connecting, recovery, …), with a note in the device pill.
- After the first scan, **Back up** becomes the primary button and Scan becomes secondary.

## [0.1.0] - 2026-11-19

### Added
- Phone sources: ADB (USB or Wi-Fi debugging), MTP/PTP mounts under gvfs, and any folder.
- Device discovery with state notes (unauthorized, offline, no USB permission).
- Scan pipeline: listing with exclusions, a first sort pass, metadata probing, learning the phone's own camera and screen size, and a final sort.
- Rule-based sorting into 16 categories with origin, reason and a Sure/Likely/Guess match level.
- EXIF reading from the first 128 KB of a file (camera make/model, date taken, software, size).
- Detection of received photos from camera metadata that doesn't match your phone, including WhatsApp send-as-document photos.
- Dates taken from EXIF, then the filename, then the modified time.
- Inca-style interface: sidebar with categories and a match filter, grid view with lazy thumbnails (EXIF thumbnails over ADB), list view, storage bar, details panel, CSV export.
- Themes: Inca (default), Inca Blue, Graphite and Light; custom JSON themes; accent override; interface size; density.
- Settings for metadata mode, own camera models, skip patterns, hidden files and the adb path.
- `run.sh`, `install.sh` (menu entry and icon), sample phone generator, headless screenshot tool, and a pytest suite.
