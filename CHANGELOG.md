# Changelog

All notable changes to Phone Vault are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
