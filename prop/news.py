"""High-impact news blackout (Eightcap: no order executed within 10 minutes of high-impact news, closes included).
Source: the public weekly calendar feed used by Forex Factory (USD, impact High). Cached once per day.
If the calendar cannot be read and no cache exists, the bot treats 10:00 and 14:00 ET (most US high-impact releases
during the session) as blacked out - it misses a check rather than risk a rule breach."""
import datetime as dt
import json
import os
import urllib.request

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


class NewsCalendar:
    def __init__(self, home, et, opener=None, url=URL, before=11, after=11, currencies=("USD",)):
        self.path, self.et, self.url = os.path.join(home, "news.json"), et, url
        self.open = opener or urllib.request.urlopen
        self.before, self.after, self.cur = dt.timedelta(minutes=before), dt.timedelta(minutes=after), currencies
        self.events, self.loaded_on = None, None

    def _load(self, today):
        if self.loaded_on == today:
            return
        data = None
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with self.open(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            with open(self.path, "w") as f:
                json.dump(data, f)
        except Exception:  # noqa: BLE001 - fall back to the cache
            if os.path.exists(self.path):
                with open(self.path) as f:
                    data = json.load(f)
        self.events = None
        if data:
            ev = []
            for e in data:
                if str(e.get("impact")).lower() != "high" or e.get("country") not in self.cur:
                    continue
                try:
                    ev.append((dt.datetime.fromisoformat(e["date"]).astimezone(self.et), e.get("title", "")))
                except (KeyError, ValueError):
                    continue
            self.events = ev
        self.loaded_on = today

    def blocked(self, now):
        """(True, reason) when `now` is inside a news window."""
        now = now.astimezone(self.et)
        self._load(now.date())
        if self.events is None:
            for hh in (10, 14):
                t = now.replace(hour=hh, minute=0, second=0, microsecond=0)
                if now.weekday() < 5 and t - self.before <= now <= t + self.after:
                    return True, "news calendar unavailable - %d:00 blackout" % hh
            return False, ""
        for t, title in self.events:
            if t - self.before <= now <= t + self.after:
                return True, "news: %s at %s" % (title, t.strftime("%H:%M"))
        return False, ""
