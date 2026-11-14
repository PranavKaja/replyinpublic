# TikTok source

Use EnsembleData. Do not use davidteather/TikTok-Api. That library needs a TikTok login cookie and residential proxies. There is no TikTok account, and a Vultr address will not stay reliable.

Free tier: 50 units a day, reset 00:00 UTC, no card. Too small to poll. Two pulls only.

- Saturday evening, to fill the dashboard.
- Sunday 7:00 AM Eastern, for fresh comments before judging.

TikTok units: 1 unit returns 10 posts for a username. 1 unit returns 30 comments on one post.

For the five focus brands, one pull is 5 post lists plus 2 comment pages each: 15 units. The same shape runs again after the daily reset.

Put the token in `.env` as `ENSEMBLEDATA_API_KEY`. It is not on this machine yet.
