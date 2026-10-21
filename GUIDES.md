# Visiting guides

Each statue page can carry an optional **Visiting** section (`/<page>/#visiting`).
It is rendered by `build.py` (`visit_html`) from an optional `visit` object on the
statue in `statues.json`. Statues without one render no section, no map-card link
and no extra JSON-LD. Never hand-edit the generated pages: edit `statues.json` and run
`BUILD_DATE=YYYY-MM-DD python3 build.py`, then `python3 build.py --check`.

## Writing a guide in markdown → statues.json fields

Write the guide as markdown with these headings, then copy each section into the field:

| Markdown heading        | `statues.json` field         | Format |
|-------------------------|------------------------------|--------|
| `## Getting there`      | `visit.getting_there`        | plain text; blank line = new paragraph |
| `## Exact spot`         | `visit.exact_spot`           | plain text |
| `## Photo tip`          | `visit.photo_tip`            | plain text |
| `## Hours & access`     | `visit.hours_access`         | plain text. Omit to reuse the statue's existing `access` + `accessSource` |
| `## Nearby (BTC Map)` bullets `- [Name](https://btcmap.org/merchant/…) – note` | `visit.nearby` | `[{"name": "Name", "url": "https://btcmap.org/merchant/…", "note": "note"}]` |
| `## Sources` bullets `- [Label](url)` | `visit.sources` | `[{"label": "Label", "url": "url"}]` |
| front matter `updated: YYYY-MM-DD` | `visit.updated` | date; sets the statue page's sitemap `<lastmod>` (max of this and BUILD_DATE) |
| front matter `public_access: true/false` | `visit.public_access` | optional bool → JSON-LD `publicAccess`, only emitted when `visit.sources` is non-empty |
| front matter `free: true/false` | `visit.free` | optional bool → JSON-LD `isAccessibleForFree`, only emitted when `visit.sources` is non-empty |

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
