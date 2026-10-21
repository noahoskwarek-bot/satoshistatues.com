# Visitor photos, "Last confirmed" line and status alerts

## Adding a visitor photo
1. Photos arrive at photos@satoshistatues.com (or via @satoshistatue21 on X). Only use photos the sender agreed to publish
   (the mail template says so), and check that the photo really shows that statue.
2. Run, from the repo root:
   ```
   python3 tools/add_photo.py path/to/photo.jpg lugano --credit "Nickname" --month 2026-10
   ```
   - `slug` is the statue page slug (`lugano`, `vienna`, …). `--credit` defaults to `Anonymous`. `--month` is when it was taken.
   - The script applies orientation, resizes to max 1600 px (plus a 640 px `-sm.jpg` thumbnail), compresses the JPEG,
     strips **all** metadata (EXIF, GPS, XMP, IPTC, ICC), re-checks the output and aborts if anything remains.
   - It writes `photos/<slug>/<slug>-<month>-<n>.jpg`, adds an `approved: true` entry to `photos.json`, and moves that
     statue's `last_confirmed` to the photo month (source `visitor_photo`) if the photo is newer.
   - `--dry-run` processes and verifies without writing anything.
3. `python3 build.py && python3 build.py --check`, then commit `photos/`, `photos.json`, `statues.json` and the pages.

To hide a photo, set `"approved": false` in photos.json (or delete the entry and file) and rebuild.

## How the pages use it
- **Visitor photos** section on every statue page: approved entries only, newest first, lazy-loaded thumbnails, tap to
  enlarge (native `<dialog>`, no libraries). With no photos it shows the "Been here? Send your photo…" empty state.
  The address is assembled in JS from `config.photo_email_user` / `photo_email_domain` (never plain in the HTML).
- **📸 Photo-verified** badge next to the "Last confirmed" line when a statue has at least one approved photo.
- **Last confirmed line** under the title. build.py uses the newest approved photo if it is at least as new as
  `last_confirmed`, otherwise the statues.json fields:
  - `last_confirmed`: `YYYY-MM` · `last_confirmed_source`: `visitor_photo` | `gps_checkin` | `report`
    (shown as "Visitor photo", "GPS-verified check-in", "News/official report") · `last_confirmed_url`: link for the source.
  - `last_confirmed_kind: "reported"` says "Last reported" instead of "Last confirmed standing" (use it when the source
    does not show the statue standing in place, e.g. damaged, donated or not installed).
  - No date → "Not yet confirmed by a visitor · Send a photo".
  - Seeded values are news/official reports only (the latest dated source per statue). Never invent a date, and never
    mark a report as a visitor confirmation.
- **Status alert** (`alert`: null or `{type, title, text, date YYYY-MM-DD, source_url, source_label}`), shown as a banner
  near the top. Types styled: `damaged`, `donated`, `not_installed` (others fall back to the damaged colour). Use only
  facts from a source and link it.
