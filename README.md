# cfb

College football scores for a [TRMNL](https://usetrmnl.com) private plugin.

ESPN’s scoreboard is about 1MB, which is over TRMNL’s 100KB polling cap and can time out the 5-second serverless VM. GitHub Actions fetches ESPN every 30 minutes into `docs/schedule.json`. The transform prefers that payload and only hits ESPN as a short fallback.

## TRMNL setup

1. Private plugin → **Polling**
2. Polling URL: `https://raw.githubusercontent.com/mauser8/cfb/main/docs/schedule.json`
3. Serverless tab → Python, paste `src/transform.py`
4. Markup: `src/full.liquid` (and the half/quadrant files if you use mashups)
5. Refresh every **15 minutes**
6. If the plugin shows degraded / not refreshing: **Reset Health**, then **Force Refresh**

Local preview (needs Docker):

```bash
./start-trmnl.sh
```
