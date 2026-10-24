"""Comandi da terminale: `python -m livescore` (oppure `bot.cmd` su Windows).

Senza argomenti apre un menu. Con argomenti:

    python -m livescore run                    avvia il live (come fa GitHub Actions)
    python -m livescore keepalive              rinnova solo il token Canva
    python -m livescore sync-logos             scarica i loghi FCLogo
    python -m livescore schedule-check         controlla se c'e' una partita (scheduler)
    python -m livescore simulate <event_id>    simula una partita su Bot JR (finita: replay, in corso: live)
    python -m livescore config                 mostra i parametri regolabili
    python -m livescore config set poll_seconds 5
    python -m livescore config reset poll_seconds
    python -m livescore team list [testo]      cerca nelle traduzioni squadra
    python -m livescore team set "Inter Milan" Inter Inter
    python -m livescore team remove "Inter Milan"
    python -m livescore league list [testo]    cerca nelle leghe (emoji)
    python -m livescore league set ita.1 "🇮🇹"
    python -m livescore league remove ita.1
    python -m livescore push ["messaggio"]     pubblica le modifiche su GitHub (add + commit + push)
    python -m livescore pull                   scarica gli aggiornamenti da GitHub
    python -m livescore connect [url]          collega questa cartella al repo GitHub (una volta sola)
    python -m livescore test [filtro]          esegue i test
    python -m livescore doctor                 controlla che tutto sia a posto

Le modifiche a `config`, `team` e `league` scrivono nei file di `data/`: nessun codice da toccare.
Aggiungendo `--push` a un comando di modifica (o `push` dopo) la cartella su GitHub si aggiorna subito.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from livescore import settings
from livescore.paths import DATA_DIR, ROOT, SETTINGS_FILE

TEAMS_FILE = DATA_DIR / "teams.json"
LEAGUES_FILE = DATA_DIR / "leagues.json"


# ───────────────────────────── file JSON ─────────────────────────────
def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, data: dict) -> None:
    """Scrive in modo atomico: un file a meta' non puo' rompere il bot."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_leagues(leagues: dict) -> None:
    """Una lega per riga (come il file originale), cosi' le modifiche si leggono bene."""
    rows = [f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}' for k, v in leagues.items()]
    tmp = LEAGUES_FILE.with_suffix(".json.tmp")
    tmp.write_text("{\n" + ",\n".join(rows) + "\n}\n", encoding="utf-8")
    os.replace(tmp, LEAGUES_FILE)


# ───────────────────────────── config ─────────────────────────────
def cmd_config(args) -> int:
    action = args.action or "show"
    if action == "show":
        stored = settings.load_file()
        print(f"{'parametro':<24}{'valore':>8}  {'default':>8}  descrizione")
        for key, spec in settings.TUNABLES.items():
            value = settings.tunable(key)
            mark = "" if value == spec.default else "  *"
            print(f"{key:<24}{value:>8}  {spec.default:>8}  {spec.description}"
                  f" [{spec.minimum}-{spec.maximum}]{mark}")
        extra = sorted(set(stored) - set(settings.TUNABLES))
        if extra:
            print(f"\nChiavi sconosciute in {SETTINGS_FILE.name}: {', '.join(extra)}")
        print("\n* = diverso dal default.  Cambia con: config set <parametro> <valore>")
        return 0
    if action in ("set", "reset"):
        key = args.key
        if key not in settings.TUNABLES:
            print(f"Parametro sconosciuto: {key!r}. Disponibili: {', '.join(settings.TUNABLES)}")
            return 2
        data = settings.load_file()
        if action == "reset":
            data.pop(key, None)
        else:
            spec = settings.TUNABLES[key]
            try:
                value = int(args.value)
            except (TypeError, ValueError):
                print("Il valore deve essere un numero intero.")
                return 2
            if not spec.minimum <= value <= spec.maximum:
                print(f"{key} deve stare tra {spec.minimum} e {spec.maximum}.")
                return 2
            data[key] = value
        _write_json(SETTINGS_FILE, data)
        print(f"{key} = {data.get(key, settings.TUNABLES[key].default)}"
              f"{' (default)' if key not in data else ''}")
        return 0
    return 2


# ───────────────────────────── squadre ─────────────────────────────
def cmd_team(args) -> int:
    teams = _read_json(TEAMS_FILE)
    if args.action == "list":
        needle = (args.name or "").lower()
        rows = [(k, v) for k, v in teams.items()
                if not needle or needle in k.lower() or needle in v[0].lower()]
        for name, (italian, tag) in rows:
            print(f"{name:<34} → {italian:<28} #{tag}")
        print(f"\n{len(rows)} squadre" + ("" if needle else f" (su {len(teams)})"))
        return 0
    if args.action == "set":
        if not (args.name and args.italian):
            print("Uso: team set <nome ESPN> <nome italiano> [hashtag]")
            return 2
        tag = args.hashtag or args.italian.replace(" ", "")
        existed = args.name in teams
        teams[args.name] = [args.italian, tag]
        _write_json(TEAMS_FILE, teams)
        print(f"{'Aggiornata' if existed else 'Aggiunta'}: {args.name} → {args.italian} #{tag}")
        return 0
    if args.action == "remove":
        if args.name not in teams:
            print(f"Squadra non trovata: {args.name!r}")
            return 1
        del teams[args.name]
        _write_json(TEAMS_FILE, teams)
        print(f"Rimossa: {args.name}")
        return 0
    return 2


# ───────────────────────────── leghe ─────────────────────────────
def cmd_league(args) -> int:
    leagues = _read_json(LEAGUES_FILE)
    if args.action == "list":
        needle = (args.slug or "").lower()
        shown = 0
        for slug, cfg in leagues.items():
            if slug.startswith("--") or (needle and needle not in slug.lower()):
                continue
            extra = {k: v for k, v in cfg.items() if k != "emoji"}
            print(f"{slug:<34} {cfg.get('emoji', ''):<4} {extra if extra else ''}")
            shown += 1
        print(f"\n{shown} leghe")
        return 0
    if args.action == "set":
        if not (args.slug and args.emoji):
            print("Uso: league set <slug ESPN> <emoji>")
            return 2
        cfg = leagues.setdefault(args.slug, {})
        cfg["emoji"] = args.emoji
        _write_leagues(leagues)
        print(f"{args.slug} → {args.emoji}")
        return 0
    if args.action == "remove":
        if args.slug not in leagues:
            print(f"Lega non trovata: {args.slug!r}")
            return 1
        del leagues[args.slug]
        _write_leagues(leagues)
        print(f"Rimossa: {args.slug}")
        return 0
    return 2


# ───────────────────────────── git: aggiornare la cartella senza passaggi manuali ─────────────────────────────
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def _git_live(*args: str) -> int:
    """Passi che usano la rete: l'output di git (login, avanzamento) resta visibile in tempo reale."""
    return subprocess.call(["git", *args], cwd=ROOT)


def _git_ready() -> bool:
    try:
        probe = _git("rev-parse", "--is-inside-work-tree")
    except FileNotFoundError:
        print("Git non e' installato: scaricalo da https://git-scm.com e riprova.")
        return False
    if probe.returncode != 0:
        print("Questa cartella non e' ancora collegata a GitHub (manca .git).\n"
              "Collegala una volta sola con:  python -m livescore connect")
        return False
    return True


def publish(message: str | None = None) -> int:
    """add + commit + pull --rebase + push, con messaggi chiari se qualcosa non va."""
    if not _git_ready():
        return 1
    _git("add", "-A")
    if _git("diff", "--cached", "--quiet").returncode == 0:
        print("Nessuna modifica da pubblicare.")
        return 0
    changed = _git("diff", "--cached", "--name-status").stdout.strip()
    print(changed)
    commit = _git("commit", "-m", message or "Aggiornamento da CMD")
    if commit.returncode != 0:
        print(commit.stderr.strip() or commit.stdout.strip())
        return 1
    print("Sincronizzo con GitHub...")
    if _git_live("pull", "--rebase", "--autostash") != 0:
        print("Impossibile unire con GitHub (conflitto?). Annullo l'unione: i tuoi file non sono stati toccati.")
        _git("rebase", "--abort")
        return 1
    print("Invio a GitHub...")
    if _git_live("push") != 0:
        print("Push non riuscito (vedi sopra).")
        return 1
    print("Pubblicato su GitHub.")
    return 0


DEFAULT_REPO_URL = "https://github.com/Tommaso20BW/LiveScore_JR.git"


def connect(url: str | None = None) -> int:
    """Collega la cartella al repo GitHub SENZA toccare i file e SENZA pubblicare nulla.

    Dopo `connect`, `git status` mostra le differenze tra questa cartella e GitHub
    (qui: la nuova struttura). Si pubblicano poi con `push`.
    """
    url = url or DEFAULT_REPO_URL
    try:
        _git("--version")
    except FileNotFoundError:
        print("Git non e' installato: scaricalo da https://git-scm.com e riprova.")
        return 1
    if _git("rev-parse", "--is-inside-work-tree").returncode == 0:
        print("Questa cartella e' gia' un repository git:", _git("remote", "-v").stdout.strip() or "(senza remote)")
        return 0
    for args, label in ((["init", "-q"], "git init"), (["remote", "add", "origin", url], "indirizzo " + url)):
        result = _git(*args)
        if result.returncode != 0:
            print(f"Non riuscito ({label}):\n{(result.stderr or result.stdout).strip()}")
            return 1
        print(f"OK  {label}")
    print("Scarico la cronologia da GitHub... (se compare una finestra di login, completala: "
          "puo' essere dietro al terminale)")
    if _git_live("fetch", "origin") != 0:
        print("Download non riuscito. Controlla l'indirizzo, la connessione e il login a GitHub, poi riprova "
              "(se e' rimasta una cartella .git a meta', cancellala).")
        return 1
    print("OK  cronologia scaricata")
    _git("remote", "set-head", "origin", "-a")
    head = _git("symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip()   # es. origin/main
    if not head:
        branches = _git("branch", "-r").stdout.split()
        head = next((b for b in ("origin/main", "origin/master") if b in branches), "")
    if not head:
        print("Non trovo il ramo principale del repo: controlla l'indirizzo.")
        return 1
    branch = head.split("/", 1)[1]
    # reset "mixed": il ramo punta a GitHub, i file della cartella restano com'erano
    if _git("reset", "-q", head).returncode != 0 or _git("checkout", "-q", "-B", branch).returncode != 0:
        print("Collegamento non riuscito durante il reset.")
        return 1
    _git("branch", "--set-upstream-to", head, branch)
    changes = _git("status", "--short").stdout.strip().splitlines()
    print(f"\nCollegata al ramo '{branch}'. Differenze rispetto a GitHub: {len(changes)} file.")
    print("Nulla e' stato pubblicato. Per pubblicare:  python -m livescore push \"Nuova struttura\"")
    return 0


def cmd_connect(args) -> int:
    return connect(args.url)


def cmd_push(args) -> int:
    return publish(args.message)


def cmd_pull(_args) -> int:
    if not _git_ready():
        return 1
    return _git_live("pull", "--rebase", "--autostash")


# ───────────────────────────── test e controlli ─────────────────────────────
def cmd_test(args) -> int:
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    if args.pattern:
        cmd += ["-k", args.pattern]
    return subprocess.call(cmd, cwd=ROOT)


def cmd_doctor(_args) -> int:
    problems = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal problems
        problems += 0 if ok else 1
        print(f"  {'OK ' if ok else 'ERR'}  {label}{f'  ({detail})' if detail else ''}")

    print("Dati")
    for path in (TEAMS_FILE, LEAGUES_FILE, DATA_DIR / "goal_players.json", DATA_DIR / "fclogo_manifest.json",
                 SETTINGS_FILE):
        try:
            data = _read_json(path)
            check(path.name, isinstance(data, dict), f"{len(data)} voci")
        except (OSError, ValueError) as exc:
            check(path.name, False, str(exc))

    print("Parametri")
    stored = settings.load_file()
    for key in stored:
        check(f"settings.json: {key}", key in settings.TUNABLES, "" if key in settings.TUNABLES else "sconosciuto")

    print("Moduli")
    import importlib
    import pkgutil

    import livescore
    for info in pkgutil.walk_packages(livescore.__path__, "livescore."):
        if info.name.endswith("__main__"):
            continue
        try:
            importlib.import_module(info.name)
        except Exception as exc:   # noqa: BLE001 - e' proprio il punto del controllo
            check(info.name, False, f"{type(exc).__name__}: {exc}")
    check("tutti i moduli si importano", problems == 0)

    print("Segreti (ambiente)")
    for name in ("TELEGRAM_TOKEN", "TELEGRAM_TO", "TELEGRAM_TO_BOT", "GH_PAT", "GIST_ID"):
        print(f"  {'si ' if os.getenv(name) else 'no '}  {name}")
    print("\n" + ("Tutto a posto." if problems == 0 else f"{problems} problema/i da guardare."))
    return 0 if problems == 0 else 1


# ───────────────────────────── servizi (usati dai workflow) ─────────────────────────────
def cmd_run(_args) -> int:
    from livescore import runner
    runner.main()
    return 0


def cmd_keepalive(_args) -> int:
    os.environ["ONLY_REFRESH_TOKEN"] = "true"
    from livescore.match import session
    session.main()
    return 0


def cmd_sync_logos(args) -> int:
    from livescore.graphics import logos
    sys.argv = ["sync-logos"] + (["--output-dir", args.output_dir] if args.output_dir else [])
    return logos.main()


def cmd_simulate(args) -> int:
    from livescore import simulate
    return simulate.run(
        args.event_id,
        dry_run=args.dry_run,
        interval=args.interval,
        delete_after=args.delete_after,
        allow_canva=not args.no_canva,
        output=args.output,
        mode=args.mode,
    )


def cmd_simulate_cleanup(args) -> int:
    from livescore import simulate
    simulate.delete_pending(args.output)
    return 0


def cmd_schedule_check(_args) -> int:
    from livescore import scheduler
    scheduler.main()
    return 0


# ───────────────────────────── menu ─────────────────────────────
def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return "0"


def _offer_publish() -> None:
    if _ask("Pubblicare subito su GitHub? (s/N) ").lower() == "s":
        publish("Modifica da menu")


def _menu() -> int:
    items = [
        ("Parametri (velocita', attese...)", "config"),
        ("Squadre: cerca / aggiungi / modifica", "team"),
        ("Leghe: cerca / cambia emoji", "league"),
        ("Controlla che tutto sia a posto", "doctor"),
        ("Esegui i test", "test"),
        ("Collega la cartella a GitHub (una volta sola)", "connect"),
        ("Pubblica le modifiche su GitHub", "push"),
        ("Scarica gli aggiornamenti da GitHub", "pull"),
        ("Avvia il live", "run"),
    ]
    while True:
        print("\n=== LiveScore JR ===")
        for i, (label, _) in enumerate(items, 1):
            print(f"  {i}. {label}")
        print("  0. Esci")
        choice = _ask("> ")
        if choice in ("0", "q", ""):
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(items):
            continue
        name = items[int(choice) - 1][1]
        if name == "config":
            main(["config"])
            key = _ask("Parametro da cambiare (invio per tornare): ")
            if key:
                if main(["config", "set", key, _ask("Nuovo valore: ")]) == 0:
                    _offer_publish()
        elif name == "team":
            needle = _ask("Cerca squadra (invio = tutte): ")
            main(["team", "list"] + ([needle] if needle else []))
            if _ask("Aggiungere/modificare una squadra? (s/N) ").lower() == "s":
                espn = _ask("Nome ESPN (es. Inter Milan): ")
                ita = _ask("Nome italiano: ")
                tag = _ask("Hashtag (invio = automatico): ")
                if main(["team", "set", espn, ita] + ([tag] if tag else [])) == 0:
                    _offer_publish()
        elif name == "league":
            needle = _ask("Cerca lega (es. ita, uefa): ")
            main(["league", "list"] + ([needle] if needle else []))
            if _ask("Cambiare un'emoji? (s/N) ").lower() == "s":
                if main(["league", "set", _ask("Slug: "), _ask("Emoji: ")]) == 0:
                    _offer_publish()
        elif name == "connect":
            url = _ask(f"Indirizzo del repo (invio = {DEFAULT_REPO_URL}): ")
            main(["connect"] + ([url] if url else []))
        elif name == "push":
            main(["push"])
        elif name == "test":
            main(["test"])
        elif name == "run":
            if _ask("Avviare davvero il live? (s/N) ").lower() == "s":
                main(["run"])
        else:
            main([name])


# ───────────────────────────── parser ─────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="livescore", description="LiveScore JR - comandi rapidi",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="avvia il live").set_defaults(func=cmd_run)
    sub.add_parser("keepalive", help="rinnova il token Canva").set_defaults(func=cmd_keepalive)
    p = sub.add_parser("sync-logos", help="scarica i loghi FCLogo")
    p.add_argument("--output-dir")
    p.set_defaults(func=cmd_sync_logos)
    sub.add_parser("schedule-check", help="controllo scheduler").set_defaults(func=cmd_schedule_check)
    p = sub.add_parser("simulate", help="simula una partita ESPN (finita: replay; in corso: live vero)")
    p.add_argument("event_id", help="ID ESPN della partita")
    p.add_argument("--dry-run", action="store_true", help="nessun invio: solo log e report")
    p.add_argument("--mode", choices=("auto", "replay", "live"), default="auto",
                   help="auto: replay se la partita e' finita, live se in corso o da giocare")
    p.add_argument("--interval", type=float, default=None,
                   help="secondi tra un messaggio e l'altro (default: 20 replay, 3 live)")
    p.add_argument("--delete-after", type=float, default=300.0, help="secondi prima di cancellare tutto")
    p.add_argument("--no-canva", action="store_true", help="niente export Canva (HT/FT senza sfondo)")
    p.add_argument("--output", default="sim_output", help="cartella del report e delle immagini")
    p.set_defaults(func=cmd_simulate)
    p = sub.add_parser("simulate-cleanup", help="cancella i messaggi rimasti di una simulazione")
    p.add_argument("--output", default="sim_output", help="cartella della simulazione")
    p.set_defaults(func=cmd_simulate_cleanup)

    p = sub.add_parser("config", help="parametri regolabili")
    p.add_argument("action", nargs="?", choices=["show", "set", "reset"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.add_argument("--push", action="store_true", help="dopo la modifica pubblica subito su GitHub")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("team", help="traduzioni squadre")
    p.add_argument("action", choices=["list", "set", "remove"])
    p.add_argument("name", nargs="?")
    p.add_argument("italian", nargs="?")
    p.add_argument("hashtag", nargs="?")
    p.add_argument("--push", action="store_true", help="dopo la modifica pubblica subito su GitHub")
    p.set_defaults(func=cmd_team)

    p = sub.add_parser("league", help="leghe ed emoji")
    p.add_argument("action", choices=["list", "set", "remove"])
    p.add_argument("slug", nargs="?")
    p.add_argument("emoji", nargs="?")
    p.add_argument("--push", action="store_true", help="dopo la modifica pubblica subito su GitHub")
    p.set_defaults(func=cmd_league)

    p = sub.add_parser("test", help="esegue i test")
    p.add_argument("pattern", nargs="?")
    p.set_defaults(func=cmd_test)
    p = sub.add_parser("push", help="pubblica le modifiche su GitHub")
    p.add_argument("message", nargs="?")
    p.set_defaults(func=cmd_push)
    p = sub.add_parser("connect", help="collega la cartella a GitHub (una volta sola)")
    p.add_argument("url", nargs="?")
    p.set_defaults(func=cmd_connect)
    sub.add_parser("pull", help="scarica gli aggiornamenti da GitHub").set_defaults(func=cmd_pull)
    sub.add_parser("doctor", help="controllo generale").set_defaults(func=cmd_doctor)
    sub.add_parser("menu", help="menu interattivo").set_defaults(func=lambda _a: _menu())
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):          # emoji e accenti anche nel CMD di Windows
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        return _menu()
    code = int(args.func(args) or 0)
    modifies = getattr(args, "action", None) in ("set", "reset", "remove")
    if code == 0 and modifies and getattr(args, "push", False):
        target = next((v for v in (getattr(args, n, None) for n in ("key", "name", "slug")) if v), "")
        code = publish(f"{args.command} {args.action} {target}".strip())
    return code


if __name__ == "__main__":
    sys.exit(main())
