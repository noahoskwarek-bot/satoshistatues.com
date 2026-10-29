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
