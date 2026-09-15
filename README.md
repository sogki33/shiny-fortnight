# Threads × Coupang connection setup

Status: Threads profile and Coupang product-search connections verified from GitHub Actions on 2026-09-16 KST. Scheduled publishing is NOT enabled.
Target Threads account: `jamestv1007`.

Verification: https://github.com/sogki33/shiny-fortnight/actions/runs/34988379625
All four required repository secrets are registered. No live post has been published.

The initial bot is preserved, but its Korean-food-only selection and publishing flow still need to be adapted to the agreed broader product concept and a reviewed content queue. Do not run `bot.py` for live publishing yet.

## Connect

Add repository Actions secrets: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`, `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY`. Use the Coupang Partners API keys, not seller WING keys. Do not commit credentials.

Run **Check connections (no publishing)** from Actions. This verifies the intended Threads account and makes one Coupang product search. It does not publish. Missing secrets cause a failed check with only the missing names printed.

After connection, finish content/image preparation and update the publishing flow before enabling the intended KST 08:30 / 12:30 / 20:30 schedules. Token refresh and secure secret rotation also remain to be configured.
