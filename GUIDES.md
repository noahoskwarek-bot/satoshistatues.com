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
(optional: only for a note worth adding to a BTC Map place, e.g. opening days. The list itself is automatic, see below.)

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
| `## Nearby Bitcoin places` lines `Name \| URL \| note` | `visit.nearby` | optional curated notes `[{"name", "url", "note"}]`. A note for a place in the automatic list is appended to it; other entries appear under "Also noted in our guide" |
| (no markdown) | `visit.merchants` | `false` hides the automatic list (statue not installed yet) |
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

## Nearby places that accept bitcoin (automatic, BTC Map)

The list is no longer hand-written. `python3 tools/fetch_merchants.py` queries the BTC Map API
(`/v4/places/search/`, about 6 km) for every statue pin, re-checks each distance with haversine (the API radius is a
loose box), drops ATMs and unnamed entries, and caches counts plus the nearest 5 places in `merchants.json`.
It only rewrites the file when a list changed, and keeps a statue's cached entry if its fetch fails. `build.py`
reads the cache (builds stay offline) and renders, inside Visiting:

- up to 5 places within 1 km, with type, distance and BTC Map "last verified" month;
- a count line ("183 places within 1 km on BTC Map") when more than 5 are within 1 km;
- if none within 1 km: the nearest 3 within 5 km, with distances;
- if none within 5 km: "None listed within 5 km on BTC Map yet" with links to the BTC Map map at the pin and to
  https://btcmap.org/add-location.

A weekly GitHub Actions workflow (`.github/workflows/weekly-merchants.yml`) refreshes the cache, rebuilds text pages
with `python3 build.py --no-bin` and commits only when something changed. After moving a pin, re-run the fetch.

## The story (`story`)

Optional list on a statue, rendered as "📖 The story" between About and Visiting:

```json
"story": [
  {"label": "Artist", "text": "Valentina Picozzi (Satoshigallery).", "sources": [{"label": "Forbes", "url": "https://…"}]},
  {"label": "Commissioned by", "text": "… Who paid has not been stated.", "reported": true, "sources": [ … ]}
]
```

Use the labels Artist(s), Unveiled, Commissioned by, What the design means, Materials, Series, History (or a short
custom one such as "Where it is now"). Only sourced facts; leave unknowns out. Set `"reported": true` on items that are
only partly confirmed (shown with a "Reported" tag) and say in the text what is unconfirmed. Every item needs at least
one source; sources are shown under the item.

## Pin notes (`pin_note`)

`"pin_note": "Pin: unveiling location (20 Apr 2026)"` replaces the "Approximate location" label when the pin marks
something specific that is not the statue's confirmed current spot (Hong Kong). The header Access line falls back to
the first paragraph of `visit.hours_access` (with a link to Visiting) when a statue has no short `access` field.
