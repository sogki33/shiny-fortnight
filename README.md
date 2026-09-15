# Threads × Coupang

Target: jamestv1007. Real Threads identity and Coupang search verified 2026-09-16 KST. First live post published successfully; see LIVE_POST.md.

GitHub Actions runs around KST 08:30, 12:30, 20:30; delays are possible. It renews the token when 27 days old, discovers products, and publishes at most one reviewed queue entry. Four additional reviewed posts are scheduled; see LAUNCH_PLAN.md. Each waits until its not_before time.

## Content

- CONTENT_PREVIEW.md: actual first product, generated image and caption.
- data/product-drafts.json: unpublished product drafts.
- data/queue.json: reviewed publishing queue. Begin with an introduction before advertising.
- assets/intro-kitchen.png: original AI introduction image.
- assets/steam-iron-lifestyle.png: AI staged scene based on the product reference, not a personal-use photo.

Images and copy are prepared in Codex. Actions does not generate fresh AI images or AI copy. It discovers candidates and publishes prepared entries only. Research of 100 qualifying affiliate posts and comments is not complete.

## Operations

Workflow commands: discover, preview (validation without posting), publish, refresh. Reviewed entries require unique id, approved status, reviewer, text, HTTPS media URL and source information. Affiliate disclosure and link must appear in the main text. Missing images block posting. Uncertain publication outcomes block retries until data/publication.json is reconciled.

Secrets: THREADS_ACCESS_TOKEN, THREADS_USER_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY, TOKEN_ENCRYPTION_KEY. Renewed tokens are encrypted in the repository; the encryption key remains in Secrets. Connection checks use the renewed token when available.

Tests: python -m unittest discover -v. Use automation.py, not the preserved legacy bot.py, to publish.
