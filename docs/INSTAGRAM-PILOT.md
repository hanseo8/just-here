# Instagram detail pilot

Local implementation only. No approved branch mapping or post URLs yet.
Candidate supplied by the user: @galmaegi_makhoe.

Populate web/instagram-places.json only after matching the exact Kakao place ID
and address to the account. Do not match by approximate restaurant name.

Entry shape:
```json
{
  "place_id": "kakao_ACTUAL_ID",
  "username": "galmaegi_makhoe",
  "branch_verified": true,
  "posts": ["https://www.instagram.com/p/ACTUAL_SHORTCODE/"]
}
```

Replace placeholders with checked values; do not publish them. Up to three
curated public post/reel URLs. Profile-only entries provide an external link.
Never extract images from embed HTML for recommendation cards or story exports.

Details fetch the local catalog on demand. Instagram's external embed script
loads only after a visitor clicks the post button. Keep original links visible
for blocked/deleted/private posts. A loaded script does not prove media rendered.

Before activation verify Meta's current embed requirements (official docs returned
HTTP 429 during implementation), public embedding settings, logged-out rendering,
Kakao in-app browser, Safari and Chrome, narrow viewport overflow and modal focus.
Verify switching/closing details removes embedded media and stale responses.
Do not count this pilot as real-device QA or production deployment.
