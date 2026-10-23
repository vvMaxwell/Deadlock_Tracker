# Site audit — October 23, 2026

Changes are in the local checkout. Production deployment was not performed.

## API review

Reviewed the live [OpenAPI contract](https://api.deadlock-api.com/openapi.json), live rank assets, and upstream implementations of [player hero statistics](https://github.com/deadlock-api/deadlock-api/blob/master/api/src/routes/v1/players/hero_stats.rs), [history](https://github.com/deadlock-api/deadlock-api/blob/master/api/src/routes/v1/players/match_history.rs), [rank](https://github.com/deadlock-api/deadlock-api/blob/master/api/src/routes/v1/players/rank.rs), and badge distribution.

Compared with the repository's API snapshot, the live schema adds ability-order-tree, ability-max-first-stats, and the patron bot-friend endpoint; removes player card/account-stats endpoints; replaces history's team_abandoned field with low_pri_pool; and adds bucket_matches_since_first_day to hero analytics. This app does not depend on the removed fields or endpoints. Existing gold-source/convar/rank compatibility remains covered by tests.

The single-player hero-stat URL used by this client is absent from the current public contract. The client now uses the documented batch endpoint with an explicit account and normal ranked/unranked scope. Hero analytics no longer accepts min_matches; that display threshold is enforced locally against returned match counts.

## Fixed

- Profiles now show API tracked hero totals rather than calculating everything from 50 recent matches. Partial fallbacks are labeled, and missing history/rank/assets no longer hide otherwise available totals.
- Rank names and filter labels agree with current assets: Acolyte, Sentinel, Mystic, Ritualist, and Emissary occupy tiers 3–7.
- Canonical redirects occur before summary loading and force refresh, avoiding duplicate refresh operations. Rank is fetched after history refresh.
- History is sorted newest first and deduplicated before applying the limit.
- Numeric Steam64 IDs normalize to account IDs; invalid ranges and misleading profile hosts are rejected. Vanity URLs resolve Steam identity rather than guessing from display names.
- Unknown match results, KDA components, souls, and last hits remain unavailable instead of being presented as losses or zeros.
- Hero minimum-match filtering now works. The selection-share metric is labeled Pick Share, with its denominator explained.
- Recent match detail requests use bounded concurrency of three instead of ten serial requests.
- External Steam/forum text requests never receive the API key. Invalid JSON gets a controlled API error.
- Search suggestions cancel stale requests, including when the query becomes too short.
- Closed mobile navigation is inert and hidden from accessibility navigation. Open navigation contains keyboard focus, and closing restores focus to its toggle.
- Built distributions include branding images, favicons, and hero signature assets.

## Verification

- `python -m pytest -q`: **162 passed**. Regression coverage includes current endpoint/query selection, totals versus recent samples, outage fallback, Steam identity, rank labels, minimum-match filtering, sorting/deduplication, refresh redirects, and external-request credential isolation.
- Live API checks succeeded for hero/item assets, rank, player history, player hero totals, hero analytics, and rank distribution.
- A real `force_refetch=true` request succeeded for public sample account 18373975, returning 50 matches in approximately one second. Public checks used no API key.
- Sample account: **171 tracked matches across nine heroes**, versus the loaded 50-match history sample. Top hero: 58 games, 34 wins, 58.6% win rate; totals rendered correctly in the browser.
- Thirty representative routes returned HTTP 200 after redirects with live upstream data: home; FAQ/about/privacy/credits/disclaimers/bot pages; robots, manifest and favicon; hero/item directories and details; hero items/matchups/rank distribution; builds; best heroes/items; Street Brawl; patch archive; player search/profile/match detail; region and hero leaderboards; rank distribution.
- Browser search submitted successfully to a populated canonical profile. Desktop and 390×844 mobile profile layouts were inspected. Mobile page width fit its viewport; no loaded image failures were found. Mobile menu open/close behavior and accessibility state were verified.
- Final checks also passed for numeric Steam64 lookup, a 5,000-match hero threshold, Street Brawl hero/item filters, Europe/Asia/South America/Oceania leaderboards, and sitemap generation. Live profile HTML assertions confirmed the API's 58 games, 34 wins, and 58.6% top-hero win rate.
- Wheel build succeeded; archive inspection confirmed 11 branding assets and seven hero signatures, including favicon-48.png and yamato.svg.
- `git diff --check` passed.

## Limits

This is a live-data sample audit, not proof that every player, historical match, filter combination, network failure, or browser works. Authenticated API quotas, Discord delivery, advertising, VPS deployment, CloudPanel, TLS, and CDN behavior were not exercised.

The app reads third-party tracked data; it has no persistent match database or background ingestion service. Private/untracked games may be absent. Aggregate stats may lag refreshed history. Per-hero rank distribution still uses the upstream deprecated endpoint because the current account-wide replacement has no hero filter; its live sample succeeded, but future removal will require a product/API change.

One dependency warning remains: the installed Starlette release deprecates httpx-based TestClient in favor of httpx2. Tests currently pass.
