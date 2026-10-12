"""Dyspozytor: jeden wpis w cronie (co 5 minut), który budzi załogę według rejestru.

Co robi:
  1. czyta rejestr (agents.yaml),
  2. wylicza sloty, które nadeszły i jeszcze nie ruszyły (z nadrabianiem do 3 godzin),
  3. sprawdza budżet: alarm przy 70%, sen niekrytycznych przy 90%,
  4. uruchamia agenta w środowisku zawierającym wyłącznie jego własny klucz,
  5. niezerowy kod wyjścia zamienia w raport błędu w imieniu agenta,
  6. zapisuje puls, który sprawdza ktoś z zewnątrz.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

NADROBIENIE = timedelta(hours=3)
LIMIT_CZASU_S = 60


def wczytaj_rejestr(sciezka):
    with open(sciezka, encoding="utf-8") as f:
        return yaml.safe_load(f)


def srodowisko(agent, reg, baza=None):
    """Agent dostaje tylko własny klucz modelu: klucze pozostałych agentów znikają z jego środowiska."""
    baza = os.environ if baza is None else baza
    wlasny = reg["agenci"].get(agent, {}).get("klucz")
    cudze = {a.get("klucz") for n, a in reg["agenci"].items()
             if n != agent and (a.get("klucz") or "").startswith("CREW_KEY_")}
    return {k: v for k, v in baza.items() if k not in cudze or k == wlasny}


def sloty_do_odpalenia(harmonogram, dni, ostatnie, chwila):
    """Sloty z dziś, które już nadeszły (nie dawniej niż 3 h) i jeszcze nie ruszyły."""
    if dni is not None and chwila.weekday() not in dni:
        return []
    wynik = []
    for godz in harmonogram:
        h, m = map(int, godz.split(":"))
        slot = chwila.replace(hour=h, minute=m, second=0, microsecond=0)
        klucz = f"{slot.date().isoformat()} {godz}"
        if slot <= chwila < slot + NADROBIENIE and ostatnie.get(godz) != klucz:
            wynik.append(godz)
    return wynik


def stan_budzetu(wydano, reg):
    """Zwraca 'ok', 'alarm' (od 70%) albo 'sen' (od 90%)."""
    b = reg["budzet"]
    udzial = wydano / b["sufit"]
    if udzial >= b["sen"]:
        return "sen"
    if udzial >= b["alarm"]:
        return "alarm"
    return "ok"


def czy_wolno(agent_cfg, budzet):
    """Przy śnie budżetu pracują tylko agenci krytyczni."""
    if agent_cfg.get("stan") != "aktywny":
        return False, "uśpiony w rejestrze"
    if budzet == "sen" and not agent_cfg.get("krytyczny"):
        return False, "budżet 90%: niekrytyczny śpi"
    return True, ""


class Stan:
    """Pliki stanu w jednym katalogu: ostatnie sloty, wydatki, raporty, puls."""

    def __init__(self, katalog):
        self.k = Path(katalog)
        self.k.mkdir(parents=True, exist_ok=True)

    def _json(self, nazwa, domyslnie):
        p = self.k / nazwa
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else domyslnie

    def ostatnie(self):
        return self._json("ostatnie.json", {})

    def zapisz_ostatnie(self, dane):
        (self.k / "ostatnie.json").write_text(json.dumps(dane, indent=1), encoding="utf-8")

    def wydano(self):
        return float(self._json("wydatki.json", {"miesiac": 0.0})["miesiac"])

    def ustaw_wydano(self, kwota):
        (self.k / "wydatki.json").write_text(json.dumps({"miesiac": kwota}), encoding="utf-8")

    def raport(self, wpis):
        with open(self.k / "raporty.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(wpis, ensure_ascii=False) + "\n")

    def raporty(self):
        p = self.k / "raporty.jsonl"
        if not p.exists():
            return []
        return [json.loads(w) for w in p.read_text(encoding="utf-8").splitlines() if w.strip()]

    def puls(self, chwila, dane):
        (self.k / "puls.json").write_text(
            json.dumps({"czas": chwila.isoformat(), **dane}, indent=1), encoding="utf-8")


def uruchom_agenta(nazwa, cfg, reg, korzen, baza_env=None):
    """Uruchamia skrypt agenta w izolowanym środowisku. Zwraca (kod, wyjście)."""
    env = srodowisko(nazwa, reg, baza_env)
    env["CREW_AGENT"] = nazwa
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run([sys.executable, str(Path(korzen) / cfg["skrypt"])], env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=LIMIT_CZASU_S)
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "przekroczono limit czasu"


def przebieg(reg, stan, chwila, korzen=".", baza_env=None):
    """Jeden obrót dyspozytora. Zwraca listę zdarzeń."""
    ostatnie = stan.ostatnie()
    budzet = stan_budzetu(stan.wydano(), reg)
    zdarzenia = []
    if budzet != "ok":
        zdarzenia.append({"agent": "ekonom", "typ": "budzet", "stan": budzet})
    for nazwa, cfg in reg["agenci"].items():
        wlasne = ostatnie.setdefault(nazwa, {})
        for godz in sloty_do_odpalenia(cfg.get("harmonogram", []), cfg.get("dni"), wlasne, chwila):
            klucz_slotu = f"{chwila.date().isoformat()} {godz}"
            wolno, powod = czy_wolno(cfg, budzet)
            if not wolno:
                zdarzenia.append({"agent": nazwa, "slot": godz, "typ": "pominiety", "powod": powod})
                wlasne[godz] = klucz_slotu
                continue
            kod, wyjscie = uruchom_agenta(nazwa, cfg, reg, korzen, baza_env)
            wlasne[godz] = klucz_slotu
            if kod == 0:
                zdarzenia.append({"agent": nazwa, "slot": godz, "typ": "ok", "wyjscie": wyjscie})
            else:
                zdarzenia.append({"agent": nazwa, "slot": godz, "typ": "blad", "kod": kod,
                                  "wyjscie": wyjscie})
    for z in zdarzenia:
        stan.raport({"czas": chwila.isoformat(), **z})
    stan.zapisz_ostatnie(ostatnie)
    stan.puls(chwila, {"budzet": budzet,
                       "uruchomiono": sum(z["typ"] in ("ok", "blad") for z in zdarzenia)})
    return zdarzenia


def raport_dobowy(reg, stan, dzien, chwila):
    """Kto miał dziś slot, który już minął, i nie pracował (cisza nie udaje spokoju)."""
    ostatnie = stan.ostatnie()
    brakujace = []
    for nazwa, cfg in reg["agenci"].items():
        if cfg.get("stan") != "aktywny":
            continue
        if cfg.get("dni") is not None and dzien.weekday() not in cfg["dni"]:
            continue
        for godz in cfg.get("harmonogram", []):
            h, m = map(int, godz.split(":"))
            slot = dzien.replace(hour=h, minute=m, second=0, microsecond=0)
            if slot < chwila and ostatnie.get(nazwa, {}).get(godz) != f"{dzien.date().isoformat()} {godz}":
                brakujace.append((nazwa, godz))
    return brakujace


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--registry", default="registry/agents.yaml")
    ap.add_argument("--state", default="state")
    ap.add_argument("--now", help="RRRR-MM-DD GG:MM (domyślnie teraz)")
    a = ap.parse_args()
    chwila = datetime.strptime(a.now, "%Y-%m-%d %H:%M") if a.now else datetime.now()
    reg = wczytaj_rejestr(a.registry)
    korzen = Path(a.registry).resolve().parent.parent
    for z in przebieg(reg, Stan(a.state), chwila, korzen=korzen):
        print(z["typ"].upper().ljust(9), z["agent"], z.get("slot", ""), z.get("powod", ""))


if __name__ == "__main__":
    main()
