"""Agent poglądowy z modelem. Nie woła żadnego API: pokazuje, jakie klucze CREW_KEY_* widzi."""
import os

widzi = sorted(k for k in os.environ if k.startswith("CREW_KEY_"))
print(f"{os.environ.get('CREW_AGENT')} widzi klucze: {', '.join(widzi) or 'brak'}")
