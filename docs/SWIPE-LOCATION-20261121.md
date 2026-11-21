# Swipe deck and location review — 2026-11-21

Release prepared for production deployment; deployment evidence is recorded in docs/DEPLOY-20261121-DECK.md.

- Restaurant deck with decorative backing sheets, circular actions, persistent left/right guide. Real-photo rules unchanged; preview uses existing example fixture, not a real recommendation.
- Automatic location stays primary. Fast attempt escalates once to a fresh high-accuracy attempt on timeout/unavailability or accuracy >500m. Explicit retry uses high accuracy and maximumAge=0. Both attempts have bounded timers. Permission denial does not retry automatically.
- Accuracy stays visible; >500m results explain approximate location. Errors show permission/settings or timeout help. Existing selected location is explicitly retained on failed refresh.
- Weather no longer holds location controls busy. Manual selection immediately cancels a pending GPS attempt. Stale callbacks are ignored; coarse background updates cannot overwrite a precise fix.
- Nested gesture busy calls preserve the original action label.

Validation: syntax, location UI, swipe, photo state, repeat UI and diff checks passed. Extended tests cover precise retry, stale attempt callbacks, cached-position warning, pending weather, cancellation, degraded watch accuracy and repeated busy label restoration.

Production observation: HTTPS 200, no response Permissions-Policy blocking geolocation; browser automatic location timed out. This does not establish the user's handset permission or GPS state. Browser manual landmark search checked separately. Actual handset GPS must still be tested after deployment.

Reference: https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition
UI process informed by unslop, Damir Sokolovsky (@heydamir), CC BY 4.0.


## Expanded pre-deploy regression
38 checks passed after two fixture corrections. The deletion test used a fixed October creation date, causing intended review-expiry rejection in November; its pending fixture now uses the current creation time. Persistence test now isolates local admin/provider settings and requires the actual no-store cache contract. These corrections do not weaken production authentication or expiry behavior.
Coverage: 18 UI/cache/auth checks and 20 backend checks including receipt review/settlement, identity, beta limits, payouts, wallet, deletion guards, storage restart/merge/restore, search/matching and acquisition.
