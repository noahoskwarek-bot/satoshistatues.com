# Satoshi Fountain (reverse fountain) — site side

Off by default. `fountain.json` → `"enabled": false` keeps the build byte-identical to one without the feature: there is no widget, no `/terms/` page, no privacy section, no footer link and no sitemap entry. The giveaway amount, budget and limits live in the leaderboard Worker (`/workspace/leaderboard`, see its `FOUNTAIN.md`), not in the site. In live mode the Worker talks to Noah's Coinos wallet over Nostr Wallet Connect (NIP-47, one budget-capped `NWC_URL` secret): payouts use `pay_invoice` and tips use `make_invoice` + `lookup_invoice` (or a Lightning address with LUD-21 verify, `TIP_MODE=lnaddress`). The site's terms and privacy copy only say "our Lightning payment provider", so they didn't change.

When `enabled` is true:
- Pilot statue pages (`statues`) get a "⛲ Satoshi Fountain" widget under the check-in box. It shows giveaway sats left, sats tipped here and recent activity (masked addresses), plus a claim form after a verified check-in and "Support the map" tip buttons. The logic is in `fountain.js`. It wraps `lbPost` from `checkin.js` to pick up the claim token, so `checkin.js` itself is unchanged.
- `/terms/` is generated, the privacy page gets a "Satoshi Fountain giveaway and tips" section, and the footer links to Terms.
- `api` overrides the API base. Empty means `statues.json` `config.leaderboard_api`.

Wording rules: `python3 tools/check_fountain_words.py [built dir] --worker /workspace/leaderboard/src` fails on pool / "your sats" / "fountain balance" / refill / donation / winner.

## Widget states added for NWC
- A payout the wallet hasn't confirmed shows the Worker's message ("The payout wasn't confirmed yet…") and the form stays locked, so it can't be paid twice.
- In `TIP_MODE=lnaddress` without a LUD-21 verify URL, the tip invoice shows "This tip can't be confirmed automatically, so it won't show in the sats tipped count" and isn't polled.
- Tip status polling is every 5 s (the Worker checks the wallet at most every 10 s per tip).

## Home-map callouts
When fountain.json is enabled, statues listed there get `giveaway: true` in the home-page map data. The map popup
(and the mobile detail sheet) shows a "⚡ Sats giveaway" callout linking to the statue page's `#giveaway` section, and
the sidebar card shows a small "⚡ 21-sat giveaway" badge. The amount comes from `/api/fountain?slug=` (Worker
PAYOUT_SATS); until the API answers, or if it fails, a neutral label without an amount is shown. "Giveaway paused"
when paused; hidden when the giveaway is disabled or the budget is below one payout. CSS/JS live in build.py
(GIVEAWAY_HOME_CSS / GIVEAWAY_HOME_JS) and are only emitted when the fountain is on.
`tools/check_fountain_words.py` also runs a stricter word list over this copy, fountain.js, the terms page and the
statue-page fountain sections.

## Random amounts (branch `fountain-random`)
Noah asked for "Random 1–100 sats with a rare 210-sat jackpot, averaging about 21". The site copy says **Lucky 210** / rare bonus.
- `fountain.json` → `payout` mirrors the Worker's payout vars and **must match them**: `mode` (`fixed`|`random`), `fixed_sats`,
  `tiers` (`[lo, hi, weight]`), `bonus_sats`, `bonus_weight`, `cap_sats_day`. build.py computes the exact odds and mean
  from it (`payout_info`, with `Fraction`) for the static copy and the **Official Rules** page at `/rules/` (generated only
  in random mode; also in the sitemap and linked from the widget, the terms page and the map popup).
  Defaults: 1–10 (440/1000), 11–25 (313), 26–50 (170), 51–100 (72), 210 (5 = 1 in 200). Expected amount: exactly 21 sats.
- The widget reads the live rules from `/api/fountain` (`payout_mode`, `payout_min`, `payout_max`, `bonus_sats`) and works
  with a fixed-mode Worker too (then it shows the fixed amount as before).
- Next to the Send button: "Free to play. No purchase or tip necessary. A tip won’t improve your odds. 18+. Official Rules".
- Success screen: an odometer counter rolls each digit for 1.5 s and stops on the amount the server already paid (`j.sats`);
  it's decoration only. Headline "You got 37 sats!", or "Lucky 210! You got 210 sats!" with a glow and a small CSS
  confetti burst (28 spans, no library). `prefers-reduced-motion` shows the final amount at once, no confetti. No reels,
  levers or slot-machine look. The "Support the map" tip section is hidden while the success screen shows.
- Recent activity: "⚡ 37 giveaway sats sent to al…@e….com", bonus entries "⚡ Lucky 210! 210 sats sent to …".
- Home map: popup "⚡ Sats giveaway: 1–100 sats per verified check-in, with a rare 210 bonus, while the giveaway budget lasts.",
  badge "⚡ Sats giveaway".
- Word check: global list adds jackpot, lottery, spin, slot, casino, gamble; the strict giveaway-copy list adds those plus
  prize pool and bet, and now also scans `/rules/` (two factual phrases about the random amount are allowed there only).

## Temporary test statue page (`/test-noah/`)
`fountain.json` → `test_page: {"slug": "test-noah", "name": "Test statue"}` builds one private page for the live end-to-end
test. It is not in `statues.json`, so it is not on the map, sitemap, feed, passport, leaderboard, statue lists or embeds,
and it is `noindex, nofollow`. The page has no coordinates: the Worker checks the GPS fix against the location in its
D1 row (`fountain_test_statue`), and the check-in isn't recorded or stamped. The giveaway box is the normal one without
the tip section. While the Worker's test statue is off, the box stays hidden and a check-in says the statue isn't installed.
Remove after the test: delete `test_page` and `_test_page_help` from `fountain.json`, `git rm -r test-noah`, rebuild.
