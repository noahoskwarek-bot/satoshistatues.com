# Visiting guides

Each statue page can carry an optional **Visiting** section (`/<page>/#visiting`).
It is rendered by `build.py` (`visit_html`) from an optional `visit` object on the
statue in `statues.json`. Statues without one render no section, no map-card link
and no extra JSON-LD. Never hand-edit the generated pages: edit `statues.json` and run
`BUILD_DATE=YYYY-MM-DD python3 build.py`, then `python3 build.py --check`.

## Writing a guide in markdown → statues.json fields

Write one file per statue named `<page>.md` (the statue's `page` in `statues.json`, e.g. `miami-bull.md`),
then import it with `python3 tools/import_guide.py <page>.md [...]`, which fills `visit` for that statue.
Input format (exactly what the importer reads):

```markdown
---
updated: 2026-10-21
public_access: true      # optional, only when a source says so
free: true               # optional, only when a source says so
---

# Any title (ignored)

## Getting there
Plain text. Blank line = new paragraph.

## Exact spot
## Photo tip
## Hours & access

## Nearby Bitcoin places
Name | https://btcmap.org/merchant/123 | note

Another place | https://btcmap.org/merchant/456 | note
(a line without " | URL" is kept as a note, e.g. "None within 1 km on BTC Map (checked 2026-10-21).")

## Sources
Label | https://example.com/article

## Intro and FAQ (optional)
Everything from this heading on is ignored.
```

| Markdown                | `statues.json` field         | Format |
|-------------------------|------------------------------|--------|
| `## Getting there`      | `visit.getting_there`        | plain text; blank line = new paragraph |
| `## Exact spot`         | `visit.exact_spot`           | plain text |
| `## Photo tip`          | `visit.photo_tip`            | plain text. Unsourced advice starts with "Generic tip (not from a source):" |
| `## Hours & access`     | `visit.hours_access`         | plain text. Omit to reuse the statue's existing `access` + `accessSource` |
| `## Nearby Bitcoin places` lines `Name \| URL \| note` | `visit.nearby` | `[{"name": "Name", "url": "https://btcmap.org/merchant/…", "note": "note"}]` |
| other text in that section | `visit.nearby_note` | plain text shown under the nearby heading |
| `## Sources` lines `Label \| URL` | `visit.sources` | `[{"label": "Label", "url": "url"}]` |
| front matter `updated: YYYY-MM-DD` | `visit.updated` | date; sets the statue page's sitemap `<lastmod>` (max of this and BUILD_DATE) |
| front matter `public_access: true/false` | `visit.public_access` | optional bool → JSON-LD `publicAccess`, only emitted when `visit.sources` is non-empty |
| front matter `free: true/false` | `visit.free` | optional bool → JSON-LD `isAccessibleForFree`, only emitted when `visit.sources` is non-empty |

The older bullet style (`## Nearby (BTC Map)` with `- [Name](url) – note`, `- [Label](url)`) is still accepted.

Text is HTML-escaped (no markdown links inside paragraphs; put links in `nearby`/`sources`).
Only state facts the cited sources support.

Example:

```json
"visit": {
  "updated": "2026-11-01",
  "getting_there": "U2 to Donaumarina, then a 5-minute walk …",
  "exact_spot": "On the lakehead next to …",
  "photo_tip": "Morning light from the east side …",
  "nearby": [{"name": "Café X", "url": "https://btcmap.org/merchant/node:123", "note": "Lightning accepted"}],
  "sources": [{"label": "Viertel Zwei", "url": "https://…"}],
  "public_access": true,
  "free": true
}
```

The section appears when at least one of `getting_there`, `exact_spot`, `photo_tip`,
`hours_access` or `nearby` is present. The home map card then shows a "🧭 Visiting guide" link
to `/<page>/#visiting`. HowTo JSON-LD is deliberately not used (Google retired HowTo rich results).

## Approximate pins

Set `"pin_approx": true` on a statue (next to `lat`/`lng`) when the coordinates are a best estimate
(third-party listing, or a spot described in words but not pinned). The map card and statue page then show
"📍 Approximate location". The check-in geofence (150 m) still uses the same coordinates, so after changing
any `lat`/`lng` run `python3 build.py --worker` and redeploy the leaderboard Worker.
