"""Symuluje dzień pracy załogi firmy fikcyjnej i zapisuje demo/report.html (jeden plik, bez serwera).

Uruchom: python demo/make_demo.py
"""
import html
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crew import dispatcher as d  # noqa: E402

DEMO_ENV = {"PATH": "x", "CREW_KEY_ZAMOWIENIA": "demo-1", "CREW_KEY_REDAKTOR": "demo-2",
            "CREW_KEY_SEDZIA": "demo-3", "CREW_KEY_PRASOWKA": "demo-4", "CREW_KEY_KLIENT": "demo-5"}


def t(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def symuluj():
    reg = d.wczytaj_rejestr(ROOT / "registry" / "agents.yaml")
    stan = d.Stan(tempfile.mkdtemp())
    stan.ustaw_wydano(18.0)
    # dyspozytor tyka co 5 minut, ale demo pokazuje tylko momenty, w których coś się dzieje
    kroki = ["06:05", "07:05", "08:05", "09:05", "10:05", "11:05"]
    for k in kroki:
        d.przebieg(reg, stan, t(f"2026-10-12 {k}"), korzen=ROOT, baza_env=DEMO_ENV)
    # budżet skacze do 92%: od teraz niekrytyczni śpią
    stan.ustaw_wydano(46.0)
    for k in ["12:05", "14:05"]:
        d.przebieg(reg, stan, t(f"2026-10-12 {k}"), korzen=ROOT, baza_env=DEMO_ENV)
    brak = d.raport_dobowy(reg, stan, t("2026-10-12 00:00"), t("2026-10-12 14:30"))
    return reg, stan, brak


ETYKIETA = {"ok": ("ok", "Zrobione"), "blad": ("bl", "Błąd"), "pominiety": ("sk", "Pominięty")}


def strona(reg, stan, brak):
    wiersze = []
    for r in stan.raporty():
        if r["typ"] == "budzet":
            continue
        klasa, nazwa = ETYKIETA[r["typ"]]
        opis = r.get("wyjscie") or r.get("powod") or ""
        wiersze.append(
            f"<tr><td>{r['czas'][11:16]}</td><td>{html.escape(r['agent'])}</td>"
            f"<td>{r['slot']}</td><td><span class='b {klasa}'>{nazwa}</span></td>"
            f"<td class='o'>{html.escape(opis)}</td></tr>")
    karty = []
    for n, c in reg["agenci"].items():
        karty.append(
            f"<div class='k'><b>{html.escape(n)}</b><small>{c['budynek']}</small>"
            f"<small>{'model: ' + html.escape(str(c['model'])) if c.get('model') else 'reguły, bez modelu'}</small>"
            f"<small>{c['stan']}{' · krytyczny' if c.get('krytyczny') else ''}</small></div>")
    ciszej = "".join(f"<li>{html.escape(n)} o {g}</li>" for n, g in brak) or "<li>nikt</li>"
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Załoga: dzień pracy</title>
<style>
:root{{--n:#0A95C9;--o:#FC6E08;--g:#021836;--bg:#f5f8fb;--card:#fff;--line:#dbe4ec}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--g)}}
main{{max-width:1100px;margin:0 auto;padding:28px 20px 40px}}
h1{{font-size:26px;margin:0 0 4px}}p.s{{margin:0 0 22px;color:#476}}
.bar{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:22px}}
.st{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;min-width:170px}}
.st b{{display:block;font-size:26px}}.st.w b{{color:var(--o)}}
.meter{{height:10px;border-radius:6px;background:#e3ebf2;overflow:hidden;margin-top:8px}}
.meter i{{display:block;height:100%;width:92%;background:var(--o)}}
h2{{font-size:16px;margin:26px 0 10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}}
.k{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;display:flex;flex-direction:column}}
.k small{{color:#58708a}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
th{{background:#eaf3f9;font-size:13px}}td.o{{color:#476;font-size:13px}}
.b{{padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;color:#fff}}
.ok{{background:var(--n)}}.bl{{background:#c2410c}}.sk{{background:#7a8a99}}
.al{{background:#fff4ec;border:1px solid #f9c9a3;border-radius:12px;padding:10px 18px}}
</style></head><body><main>
<h1>Załoga Piekarni Przykładowej</h1>
<p class="s">Symulacja jednego dnia (12.10.2026). Dyspozytor budzi agentów według rejestru, pilnuje budżetu i zgłasza ciszę.</p>
<div class="bar">
 <div class="st"><span>Agentów w rejestrze</span><b>{len(reg['agenci'])}</b></div>
 <div class="st"><span>Uruchomień</span><b>{sum(r['typ'] in ('ok','blad') for r in stan.raporty())}</b></div>
 <div class="st w"><span>Błędy zgłoszone</span><b>{sum(r['typ']=='blad' for r in stan.raporty())}</b></div>
 <div class="st w"><span>Budżet miesiąca</span><b>92%</b><div class="meter"><i></i></div></div>
</div>
<h2>Przebiegi</h2>
<table><tr><th>Czas</th><th>Agent</th><th>Slot</th><th>Wynik</th><th>Szczegóły</th></tr>{''.join(wiersze)}</table>
<h2>Cisza: kto miał slot i nie pracował (raport dobowy)</h2>
<div class="al"><ul>{ciszej}</ul></div>
<h2>Rejestr</h2><div class="grid">{''.join(karty)}</div>
</main></body></html>"""


if __name__ == "__main__":
    reg, stan, brak = symuluj()
    out = ROOT / "demo" / "report.html"
    out.write_text(strona(reg, stan, brak), encoding="utf-8")
    print("zapisano", out.relative_to(ROOT))
