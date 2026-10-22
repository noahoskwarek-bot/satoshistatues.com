# Upcoming Bitcoin events (events.json)

Statue pages show an **Upcoming Bitcoin events nearby** section built from `events.json`.
Edit `events.json`, then run `python3 build.py` and `python3 build.py --check`, and commit.

## Format

```json
{
  "events": [
    {
      "name": "BTC Prague 2027",
      "start_date": "2027-05-06",
      "end_date": "2027-05-08",
      "city": "Prague",
      "country": "Czech Republic",
      "lat": 50.0755,
      "lng": 14.4378,
      "url": "https://btcprague.com/",
      "statue": "vienna",
      "source_url": "https://btcprague.com/",
      "verified": "2026-10-21"
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Event name including the edition year. |
| `start_date` | yes | `YYYY-MM-DD`. |
| `end_date` | no | `YYYY-MM-DD`; omit for one-day events. |
| `city`, `country` | yes | Shown on the page and used in the Event JSON-LD. |
| `lat`, `lng` | no (recommended) | Venue or city centre. When present the build checks the event is within 300 km of its statue and shows "about N km away" if it's 25 km or more. |
| `url` | yes | The event's official website (linked, opens in a new tab). |
| `statue` | yes | The nearest statue's `page` slug in `statues.json` (straight-line distance, max ~300 km). |
| `source_url` | yes | The official page where the dates were confirmed. |
| `verified` | yes | `YYYY-MM-DD` you last checked the dates. |

## Rules

- Only add an event after confirming its dates on the **official** event site. Never infer dates from past editions or third-party listings.
- Skip events farther than ~300 km from any statue, and don't assign events to statues that are only planned.
- Past events disappear automatically: the build drops events whose end date is before `BUILD_DATE`, and a tiny script on each page hides any that have ended since the page was built (and the whole section if none are left).
- A statue with no upcoming events gets no section at all.
- Each listed event also gets schema.org `Event` JSON-LD (name, dates, city/country, official URL).

## Checked 2026-10-21 and not added

- **Bitcoin 2027 (BTC Inc)**: Nashville, Jul 15–17, 2027 (conference.b.tc). Not Miami; nearest statue (New York) is ~1,220 km away.
- **Bitcoin Amsterdam 2026**: Nov 5–6, 2026 (bitcoin.amsterdam). ~770 km from the nearest statue (Lugano).
- **Adopting Bitcoin**: official site shows no upcoming El Salvador edition (archive lists El Salvador through 2025).
- **Bitcoin Histórico (San Salvador)**: official site bitcoinhistorico.com was unavailable (503), so dates not confirmed.
- **Budapest Bitcoin**: official site shows no dates for an upcoming edition.
- **Consensus Miami 2027 / WebX 2027 (Tokyo)**: broad crypto/Web3 conferences, not Bitcoin events.
- **BTC Balkans (Sofia)**: ~640 km from Budapest.

## Checked 2026-10-22 and not added

- **Bitcoin Treasuries Conference 2027 (New York)**: Sep 28, 2027 appears only on the organizer's Luma page; bitcointreasuries.net/conference still shows the 2026 event, so the dates aren't confirmed on the official site yet.
- **The Sovereign Summit (Miami Beach, Feb 4–7, 2027)**: not Bitcoin-only (covers AI, energy and money).
- **TOKEN2049 New York, Digital Assets Week NY, Blockchain Week UNGA, Vienna Blockchain Week 2027**: broad crypto, not Bitcoin events.
- **Adopting Bitcoin Arnhem 2027 (May 28–29)**: ~700+ km from the nearest statue.
- **Bitcoin Hanoi meetups**: small monthly meetups, location shared by DM only; not a conference.

Note (2026-10-22): the asia.b.tc header still reads "Aug 27–28", but its 2027 section says August 26–27, 2027, so the Bitcoin Asia 2027 listing stays as is.

Added 2026-10-22: **Miami Bitcoin Summit 2027** (Fri Feb 5, 2027, Fontainebleau Miami Beach, 4441 Collins Ave; Bitcoin-only; confirmed on miamibitcoinsummit.com), ~8 km from the Miami Bitcoin Bull.

