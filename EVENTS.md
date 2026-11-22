# Upcoming Bitcoin events (events.json)

Statue pages show an **Upcoming Bitcoin events nearby** section built from `events.json`.
The home map uses the same list for its **Events** layer (on by default): only upcoming, verified events with coordinates are pinned, and past ones are hidden at build time and again in the browser.
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
| `source_url` | yes | The official page where the dates were confirmed (organizer site or blog, X post, or organizer-posted ticketing page). |
| `verified` | yes | `YYYY-MM-DD` you last checked the dates. |

## Rules

- Only add an event after confirming its dates on an **official** source. An announcement on the organizer's own blog, X account, or ticketing page (Satlantis, Luma, Eventbrite, Meetup) counts as official when the organizer posted it. Never infer dates from past editions or from third-party listings the organizer did not post.
- Local meetups and community events are in scope if they have an organizer-posted page with confirmed dates.
- Skip events farther than ~300 km from any statue, and don't assign events to statues that are only planned.
- Each week, sweep the statue-city communities directly: Bitcoin Beach, Bitcoin Berlín SV, TBB Tokyo (Tokyo Bitcoin Base), Lugano Plan ₿, Bitcoin Office SV, plus local meetups within 300 km of each statue.
- Check local news roundups such as ia.sv and investsalvador for multi-event weeks. Use those to find candidates, then confirm dates on an official (organizer-posted) source before adding.
- Past events disappear automatically: the build drops events whose end date is before `BUILD_DATE`, and a tiny script on each page hides any that have ended since the page was built (and the whole section if none are left).
- A statue with no upcoming events gets no section at all.
- Each listed event also gets schema.org `Event` JSON-LD (name, dates, city/country, official URL).

## Checked 2026-10-21 and not added

- **Bitcoin 2027 (BTC Inc)**: Nashville, Jul 15–17, 2027 (conference.b.tc). Not Miami; nearest statue (New York) is ~1,220 km away.
- **Bitcoin Amsterdam 2026**: Nov 5–6, 2026 (bitcoin.amsterdam). ~770 km from the nearest statue (Lugano).
- **Adopting Bitcoin**: official site shows no upcoming El Salvador edition (archive lists El Salvador through 2025).
- **Budapest Bitcoin**: official site shows no dates for an upcoming edition.
- **Consensus Miami 2027 / WebX 2027 (Tokyo)**: broad crypto/Web3 conferences, not Bitcoin events.
- **BTC Balkans (Sofia)**: ~640 km from Budapest.

## Checked 2026-10-22 and not added

- **Bitcoin Treasuries Conference 2027 (New York)**: Sep 28, 2027 appeared on the organizer's Luma page on 2026-10-22, while bitcointreasuries.net/conference still showed the 2026 event. It was skipped then because the dates weren't on the main official site. Under the updated sourcing policy, an organizer-posted Luma page counts as official; re-check on the next weekly refresh before adding.
- **The Sovereign Summit (Miami Beach, Feb 4–7, 2027)**: not Bitcoin-only (covers AI, energy and money).
- **TOKEN2049 New York, Digital Assets Week NY, Blockchain Week UNGA, Vienna Blockchain Week 2027**: broad crypto, not Bitcoin events.
- **Adopting Bitcoin Arnhem 2027 (May 28–29)**: ~700+ km from the nearest statue.
- **Bitcoin Hanoi meetups**: not added. Location was shared by DM only, with no public organizer-posted page confirming dates and venue. Meetups and community events are in scope when the organizer has published those details.

Note (2026-10-22): the asia.b.tc header still reads "Aug 27–28", but its 2027 section says August 26–27, 2027, so the Bitcoin Asia 2027 listing stays as is.

Added 2026-10-22: **Miami Bitcoin Summit 2027** (Fri Feb 5, 2027, Fontainebleau Miami Beach, 4441 Collins Ave; Bitcoin-only; confirmed on miamibitcoinsummit.com), ~8 km from the Miami Bitcoin Bull.

## Checked 2026-10-29

Added 2026-10-29: **Bitcoin Histórico 2026** (Nov 11–12, 2026, Centro Histórico, San Salvador: National Palace main stage, live-streamed on Plaza Gerardo Barrios; a conference by the National Bitcoin Office of El Salvador; confirmed on bitcoinhistorico.com, which was down on 2026-10-21), ~40 km from the El Zonte statue.

Added 2026-10-29: **Le Paradigme Bitcoin 2027** (Jun 25–26, 2027, Coworking Blockchain Neuchâtel, rue St-Maurice 9, 2000 Neuchâtel; Bitcoin community event for French-speaking Switzerland; confirmed on leparadigmebitcoin.ch), ~190 km from the Lugano statue.

- **Budapest Bitcoin**: still not added. The official site (budapestbitcoin.com) now shows a formal postponement notice with no new dates: "We've made the tough decision to postpone the Budapest Bitcoin Conference originally planned for 8-9, August. Please stay connected with us by following our social channels — we'll be sharing all updates there, including our next steps and future plans."

## Checked 2026-11-05 (weekly)

- **Miami Bitcoin Summit 2027**: REMOVED. Official site miamibitcoinsummit.com shows a banner: "Sample website Nothing on this site is accurate. Used as an example only." Dates are not confirmed.
- **BitcoinDay Naples 2027**: KEPT as Sat Jan 16, 2027. Confirmed on bitcoinday.io published content (`api/content.js` editions kicker "Sat · Jan 16 · 2027 — ~200 seats" and SEO description "Sat Jan 16, 2027"); the Jan 15 Carnivore Dinner is a separate side-event ticket, not the main conference. Buy-tickets path 404; homepage draft flag exists but is hidden while published content is served.

## Checked 2026-11-12

Added 2026-11-12: **Bitcoin Österreich 2027** (formerly Bitcoin Burgenland; Apr 16–17, 2027, Neufeldersee-Restaurant, Neufeldersee (Burgenland), Austria; organizer RETTE DEIN GELD; confirmed on rettedeingeld.at/bitcoin-oesterreich-2027/), ~39 km south of the Vienna statue.

- **Bitcoin Zitadelle 2027** (Aug 5–8, 2027, Frankenfels, bitcoin-zitadelle.at) NOT added because ticket sales are invite-only/not public.
- **Miami Bitcoin Summit** still NOT added because its site still shows the 'Sample website' banner.
- **BTC Prague 2027** unchanged, May 6–8, 2027 in Prague (the venue is reportedly moving to Průmyslový palác, but city and dates are the same).

## Added 2026-11-19

Added 2026-11-19: **Anti-Fragile Bitcoin 2026** (Sun Nov 29, 2026, 13:00–17:00 JST, Tokyo Bitcoin Base, Yotsuya; official side event of Bitcoin Japan 2026; free entry). Name, date, time and venue confirmed on the organizer's X post and attached flyer (https://x.com/TBB_EN/status/2123364185639960866, Tokyo Bitcoin Base / @TBB_EN). Registration is the organizer-posted Luma page linked on the flyer (https://luma.com/i1ghcdwz). Coordinates are the OpenStreetMap pin already used for the Tokyo statue's exact spot (35.68897, 139.72854), at the venue itself.

Added 2026-11-19: **Global Bitcoin Circular Economies Summit 2026** (Nov 19–20, 2026, El Zonte, El Salvador; organized by Bitcoin Beach and the Federation of Bitcoin Circular Economies; first time public, limited seats). Dates and El Zonte location confirmed on the organizer's blog (https://www.bitcoinbeach.com/summit-blog/bitcoin-circular-economies-summit-2026) and on the organizer-posted Satlantis registration page (https://www.satlantis.io/events/2311/global-bitcoin-circular-economies-summit). Coordinates are the Open Location Code center of short code FHW5+Q7X recovered against the El Zonte statue (full code 765GFHW5+Q7X → 13.49699, -89.44177, about 190 m from the statue), which third-party listings give as El Zonte Community Centre. The official blog and Satlantis page name El Zonte but do not themselves name the Community Centre or the plus code.

Sourcing policy updated the same day so the weekly refresh can catch events like this (no standalone conference site required when the organizer posts an announcement on their blog, X account, or a ticketing page). Weekly sweeps now include statue-city communities (Bitcoin Beach, Bitcoin Berlín SV, TBB Tokyo, Lugano Plan ₿, Bitcoin Office SV, and local meetups within 300 km of each statue) and local news roundups such as ia.sv and investsalvador.

- **Women in Bitcoin at Bitcoin Beach, Nov 21, 2026**: NOT added. No official organizer page was found confirming this event or its dates and venue (Bitcoin Beach blog and events page, Bitcoin Beach's Luma account, Satlantis, Eventbrite, Meetup, and local roundups ia.sv / investsalvador). Bitcoin Beach's own November list names the Summit on Nov 19–20 and does not mention Women in Bitcoin. A January 24, 2026 Women Bitcoin meetup in El Zonte is a different, earlier event. Third-party coverage of Festival Bitcoin Beach (Nov 21–22) is not an organizer-posted Women in Bitcoin listing and was not added.

## Added 2026-11-21

Added 2026-11-21: **21MEETUP | Noviembre 2026** (Sat Nov 21, 2026, 20:00–22:30 America/Argentina/Buenos_Aires, Ronda at DOT Baires, Vedia 3600, Buenos Aires; hosted by ONG Bitcoin Argentina; free with registration; includes a visit to the El Génesis de Satoshi Nakamoto monument). Name, date, time and venue confirmed on the organizer-posted Luma page (https://luma.com/mitj8wxn) and on the organizer's X post and attached flyer (https://x.com/BitcoinAR/status/2123519708531970130, ONG Bitcoin Argentina / @BitcoinAR). Coordinates are the Luma venue pin for Ronda (−34.54648, −58.48785), about 180 m from the Buenos Aires statue; OpenStreetMap places the Dot Baires mall at Vedia 3600 at −34.54626, −58.48820.

Added 2026-11-21: **Bitcoin Maribor Meetup #35 2026** (Thu Nov 26, 2026, 19:00–20:00 Europe/Ljubljana, Hotel Betnava café, Ulica Eve Lovše 15, Maribor, Slovenia). Name, date, time and venue confirmed on the organizer-posted Meetup page (https://www.meetup.com/bitcoin-maribor/events/317510939/). Coordinates are the OpenStreetMap pin for Hotel Betnava (46.53778, 15.64122), about 104 km from the Kranj statue (within the 300 km events radius).

## Added 2026-11-22

Added 2026-11-22: **秋の夜長に、ビットコイン関連の“何か”を作っている人たちのお月見座談会 2026** (Sat Nov 28, 2026, 19:30–21:00 JST, Tokyo Bitcoin Base, 2-8 Yotsuya-Honshiocho, Shinjuku-ku, Tokyo). A builders' roundtable / moon-viewing talk, co-hosted by むらぴぃ (@mura0306) and Tokyo Bitcoin Base, after day two of Bitcoin Japan 2026. Name, date, venue and registration confirmed on the organizer's X announcement (https://x.com/mura0306/status/2122963839042109758) and the organizer-posted Luma page linked from that post (https://luma.com/d67mvqbg; eventStatus EventScheduled, not cancelled). The announcement first said 19:00 JST; the organizer's follow-up the same day (https://x.com/mura0306/status/2123042540291330290) moved the start back 30 minutes to 19:30, which matches the Luma start/end (19:30–21:00 Asia/Tokyo). Coordinates are the OpenStreetMap pin already used for the Tokyo statue and for Anti-Fragile Bitcoin (35.68897, 139.72854), at the venue itself. Official venue address: 2-8 Yotsuya-Honshiocho, Shinjuku-ku, Tokyo 160-0003 (tokyobitcoin.space and the Luma location).

Removed 2026-11-22: **21MEETUP | Noviembre 2026** (one-day event on Nov 21, 2026; end date before today). The Global Bitcoin Circular Economies Summit (ended Nov 20) had already been removed in 5e86c0f.
