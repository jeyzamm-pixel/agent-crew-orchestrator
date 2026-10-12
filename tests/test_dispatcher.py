import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crew import dispatcher as d  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REG = d.wczytaj_rejestr(ROOT / "registry" / "agents.yaml")
FAKE_ENV = {"PATH": "x", "CREW_KEY_SEDZIA": "a", "CREW_KEY_REDAKTOR": "b", "CREW_KEY_ZAMOWIENIA": "c"}


def t(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def test_agent_widzi_tylko_wlasny_klucz():
    env = d.srodowisko("sedzia", REG, FAKE_ENV)
    assert "CREW_KEY_SEDZIA" in env
    assert "CREW_KEY_REDAKTOR" not in env and "CREW_KEY_ZAMOWIENIA" not in env
    assert env["PATH"] == "x"


def test_agent_regulowy_nie_dostaje_zadnego_klucza():
    env = d.srodowisko("straznik-pieca", REG, FAKE_ENV)
    assert not [k for k in env if k.startswith("CREW_KEY_")]


def test_slot_nadchodzi_i_nie_odpala_sie_dwa_razy():
    chwila = t("2026-10-12 09:05")
    assert d.sloty_do_odpalenia(["09:00"], None, {}, chwila) == ["09:00"]
    assert d.sloty_do_odpalenia(["09:00"], None, {"09:00": "2026-10-12 09:00"}, chwila) == []


def test_nadrabianie_do_trzech_godzin():
    assert d.sloty_do_odpalenia(["09:00"], None, {}, t("2026-10-12 11:55")) == ["09:00"]
    assert d.sloty_do_odpalenia(["09:00"], None, {}, t("2026-10-12 12:05")) == []


def test_slot_z_przyszlosci_nie_rusza():
    assert d.sloty_do_odpalenia(["15:00"], None, {}, t("2026-10-12 09:05")) == []


def test_dni_tygodnia():
    # 2026-10-17 to sobota, prasówka chodzi pn-pt
    assert d.sloty_do_odpalenia(["06:30"], [0, 1, 2, 3, 4], {}, t("2026-10-17 06:35")) == []
    assert d.sloty_do_odpalenia(["06:30"], [0, 1, 2, 3, 4], {}, t("2026-10-12 06:35")) == ["06:30"]


def test_progi_budzetu():
    assert d.stan_budzetu(34.9, REG) == "ok"
    assert d.stan_budzetu(35.0, REG) == "alarm"
    assert d.stan_budzetu(45.0, REG) == "sen"


def test_przy_snie_niekrytyczny_nie_pracuje_a_krytyczny_tak():
    assert d.czy_wolno(REG["agenci"]["sedzia"], "sen")[0] is False
    assert d.czy_wolno(REG["agenci"]["straznik-pieca"], "sen")[0] is True
    assert d.czy_wolno(REG["agenci"]["tajemniczy-klient"], "ok")[0] is False  # uśpiony w rejestrze


def test_pelny_przebieg_blad_agenta_staje_sie_raportem(tmp_path):
    stan = d.Stan(tmp_path)
    zd = d.przebieg(REG, stan, t("2026-10-12 10:05"), korzen=ROOT, baza_env=FAKE_ENV)
    bledy = [z for z in zd if z["typ"] == "blad"]
    assert [b["agent"] for b in bledy] == ["kontrola-cen"]
    assert "niedostępne" in bledy[0]["wyjscie"]
    assert any(r["typ"] == "blad" for r in stan.raporty())
    assert (tmp_path / "puls.json").exists()


def test_ten_sam_slot_nie_odpala_sie_drugi_raz(tmp_path):
    stan = d.Stan(tmp_path)
    d.przebieg(REG, stan, t("2026-10-12 09:05"), korzen=ROOT, baza_env=FAKE_ENV)
    drugi = d.przebieg(REG, stan, t("2026-10-12 09:10"), korzen=ROOT, baza_env=FAKE_ENV)
    assert not [z for z in drugi if z["typ"] in ("ok", "blad")]


def test_raport_dobowy_wymienia_kto_milczal(tmp_path):
    stan = d.Stan(tmp_path)
    # nic nie uruchomiono, a jest południe: aktywni agenci ze slotami do 12:00 milczeli
    brak = d.raport_dobowy(REG, stan, t("2026-10-12 00:00"), t("2026-10-12 12:00"))
    nazwy = {n for n, _ in brak}
    assert "straznik-pieca" in nazwy and "sedzia" in nazwy
    assert "tajemniczy-klient" not in nazwy  # uśpiony, nie liczy się
