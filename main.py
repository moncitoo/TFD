"""Telegram -> Jellyfin: cerca, descàrrega, descompressió i organització."""
import asyncio
import html
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from itertools import count
from typing import Dict, List, Optional

from telethon import Button, TelegramClient, events
from telethon.errors import FloodWaitError, MessageNotModifiedError

import config
import fileops
from parsing import Ep, in_range, parse_episode, parse_range

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tgjf")

config.SESSION_DIR.mkdir(parents=True, exist_ok=True)
config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

user = TelegramClient(str(config.SESSION_DIR / "user"), config.API_ID, config.API_HASH)
bot = TelegramClient(str(config.SESSION_DIR / "bot"), config.API_ID, config.API_HASH)

PROCESS_LOCK = asyncio.Lock()  # un sol lot descarregant alhora
_ids = count(1)


@dataclass
class Item:
    msg_id: int
    name: str
    ext: str
    size: int
    ep: Ep


@dataclass
class Job:
    id: int
    chat: object
    items: List[Item]
    series: str = ""
    season_off: int = 0
    ep_off: int = 0
    folders: List[str] = field(default_factory=list)
    running: bool = False

    def numbers(self, ep: Ep) -> Ep:
        return max(ep[0] + self.season_off, 0), max(ep[1] + self.ep_off, 0)


JOBS: Dict[int, Job] = {}
AWAITING_NAME: Dict[int, int] = {}  # user_id -> job_id


def esc(s) -> str:
    return html.escape(str(s))


# ---------- Cerca ----------

async def search_chat(chat, start: Ep, end: Ep, keyword: Optional[str]) -> List[Item]:
    found: Dict[Ep, Item] = {}
    kw = keyword.lower() if keyword else None
    async for msg in user.iter_messages(chat):
        f = msg.file
        if not f or not f.ext:
            continue
        ext = f.ext.lower()
        if ext not in config.VIDEO_EXT | config.ARCHIVE_EXT:
            continue
        name = f.name or f"{msg.id}{ext}"
        haystack = f"{name} {msg.message or ''}"
        if kw and kw not in haystack.lower():
            continue
        ep = parse_episode(haystack)
        if ep and in_range(ep, start, end) and ep not in found:
            found[ep] = Item(msg.id, name, ext, f.size or 0, ep)
    return [found[k] for k in sorted(found)]


# ---------- Menú ----------

def render(job: Job):
    first = job.items[0]
    s, e = job.numbers(first.ep)
    series = job.series or "⟨sense nom⟩"
    path = (fileops.final_path(job.series, s, e, first.ext if first.ext not in config.ARCHIVE_EXT else ".mkv")
            if job.series else "—")
    total = sum(i.size for i in job.items) / 1024 ** 3
    text = (
        f"📺 <b>Lot #{job.id}</b>: {len(job.items)} episodis ({total:.2f} GB)\n"
        f"Del {first.ep[0]:02d}x{first.ep[1]:02d} al "
        f"{job.items[-1].ep[0]:02d}x{job.items[-1].ep[1]:02d}\n\n"
        f"<b>Sèrie:</b> {esc(series)}\n"
        f"<b>Offset temporada:</b> {job.season_off:+d}   <b>Offset episodi:</b> {job.ep_off:+d}\n\n"
        f"<b>Vista prèvia (1r episodi):</b>\n<code>{esc(path)}</code>"
    )
    j = job.id
    rows = []
    row = []
    for idx, name in enumerate(job.folders[:30]):
        row.append(Button.inline(name[:28], f"ser:{j}:{idx}".encode()))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([Button.inline("✏️ Nova sèrie", f"new:{j}".encode())])
    rows.append([Button.inline("Temp −", f"adj:{j}:s:-1".encode()),
                 Button.inline("Temp +", f"adj:{j}:s:1".encode()),
                 Button.inline("Ep −", f"adj:{j}:e:-1".encode()),
                 Button.inline("Ep +", f"adj:{j}:e:1".encode())])
    rows.append([Button.inline("✅ Confirmar i Processar", f"go:{j}".encode()),
                 Button.inline("❌ Cancel·lar", f"cancel:{j}".encode())])
    return text, rows


async def refresh_menu(event_or_msg, job: Job, via_event=True):
    text, rows = render(job)
    try:
        if via_event:
            await event_or_msg.edit(text, buttons=rows, parse_mode="html")
        else:
            await bot.edit_message(event_or_msg, text, buttons=rows, parse_mode="html")
    except MessageNotModifiedError:
        pass


# ---------- Processament ----------

async def download_item(job: Job, item: Item, workdir, status):
    msg = await user.get_messages(job.chat, ids=item.msg_id)
    last = [0.0]

    async def progress(done, total):
        if time.monotonic() - last[0] > 8:
            last[0] = time.monotonic()
            try:
                await status.edit(f"⬇️ {esc(item.name)}\n{done / 1024 ** 2:.0f}/{total / 1024 ** 2:.0f} MB",
                                  parse_mode="html")
            except Exception:
                pass

    while True:
        try:
            return await user.download_media(msg, file=str(workdir) + "/", progress_callback=progress)
        except FloodWaitError as e:
            log.warning("FloodWait %ss", e.seconds)
            await asyncio.sleep(e.seconds + 1)


def place_files(job: Job, item: Item, workdir) -> List[str]:
    """Mou vídeos i subtítols del directori de treball a Jellyfin."""
    videos = fileops.collect(workdir, config.VIDEO_EXT)
    subs = fileops.collect(workdir, config.SUB_EXT)
    out: List[str] = []
    for v in videos:
        ep = item.ep if len(videos) == 1 else (parse_episode(v.name) or None)
        if not ep:
            out.append(f"⚠️ Sense número detectable: {v.name}")
            continue
        s, e = job.numbers(ep)
        dest = fileops.move_unique(v, fileops.final_path(job.series, s, e, v.suffix.lower()), True)
        out.append(f"✔️ {dest.name}")
        for sub in subs:
            sub_ep = ep if len(videos) == 1 else parse_episode(sub.name)
            if sub_ep == ep and sub.exists():
                fileops.move_unique(sub, dest.with_suffix(sub.suffix.lower()), False)
    return out


async def run_job(job: Job, status):
    report: List[str] = []
    async with PROCESS_LOCK:
        for n, item in enumerate(job.items, 1):
            workdir = config.DOWNLOAD_DIR / f"{job.id}_{item.msg_id}"
            workdir.mkdir(parents=True, exist_ok=True)
            try:
                await status.edit(f"⬇️ [{n}/{len(job.items)}] {esc(item.name)}", parse_mode="html")
                path = await download_item(job, item, workdir, status)
                if not path:
                    raise RuntimeError("descàrrega buida")
                from pathlib import Path
                p = Path(path)
                if p.suffix.lower() in config.ARCHIVE_EXT:
                    await status.edit(f"📦 Descomprimint {esc(p.name)}", parse_mode="html")
                    ok = await asyncio.to_thread(fileops.extract_archive, p, workdir)
                    if not ok:
                        raise RuntimeError("error descomprimint (veure logs)")
                report += await asyncio.to_thread(place_files, job, item, workdir)
            except Exception as e:
                log.exception("Error amb %s", item.name)
                report.append(f"❌ {item.name}: {e}")
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        refreshed = await fileops.refresh_jellyfin()
    summary = "\n".join(report)[-3500:]
    await status.edit(
        f"🏁 Lot #{job.id} acabat.\n{esc(summary)}\n\n"
        f"Jellyfin: {'biblioteca actualitzada ✅' if refreshed else 'no actualitzat ⚠️'}",
        parse_mode="html")
    JOBS.pop(job.id, None)


# ---------- Handlers del bot ----------

admin = events.NewMessage(from_users=config.ADMIN_USER_ID)


@bot.on(events.NewMessage(pattern=r"^/start", from_users=config.ADMIN_USER_ID))
async def h_start(event):
    await event.respond("Ús: <code>/buscar &lt;chat&gt; &lt;01x01-03x15&gt; [paraula clau]</code>",
                        parse_mode="html")


@bot.on(events.NewMessage(pattern=r"^/buscar(?:@\w+)?\s+(.+)", from_users=config.ADMIN_USER_ID))
async def h_search(event):
    parts = event.pattern_match.group(1).split(maxsplit=2)
    if len(parts) < 2:
        return await event.respond("Ús: /buscar <chat> <01x01-03x15> [paraula clau]")
    chat_raw, rng = parts[0], parts[1]
    keyword = parts[2].strip() if len(parts) > 2 else None
    try:
        start, end = parse_range(rng)
    except ValueError as e:
        return await event.respond(str(e))
    try:
        chat = int(chat_raw) if chat_raw.lstrip("-").isdigit() else chat_raw
        entity = await user.get_entity(chat)
    except Exception as e:
        return await event.respond(f"No puc accedir al xat: {esc(e)}")
    status = await event.respond("🔎 Cercant a l'historial…")
    try:
        items = await search_chat(entity, start, end, keyword)
    except Exception as e:
        log.exception("Error cercant")
        return await status.edit(f"Error cercant: {esc(e)}")
    if not items:
        return await status.edit("No s'ha trobat cap episodi en aquest rang.")
    job = Job(id=next(_ids), chat=entity, items=items, series=keyword or "",
              folders=fileops.list_series_folders())
    JOBS[job.id] = job
    await refresh_menu(status, job)


@bot.on(events.NewMessage(pattern=r"^/desinstalar", from_users=config.ADMIN_USER_ID))
async def h_uninstall(event):
    await event.respond(
        "⚠️ <b>Desinstal·lar tot?</b>\nS'esborraran el programa, la configuració, les sessions de "
        "Telegram i els paquets que va instal·lar l'instal·lador. Els episodis de Jellyfin es conserven.",
        buttons=[[Button.inline("🗑 Sí, esborra-ho tot", b"unin:yes"),
                  Button.inline("Cancel·lar", b"unin:no")]],
        parse_mode="html")


@bot.on(events.CallbackQuery(pattern=rb"^unin:", func=lambda e: e.sender_id == config.ADMIN_USER_ID))
async def h_uninstall_cb(event):
    if event.data != b"unin:yes":
        return await event.edit("Desinstal·lació cancel·lada.")
    script = config.BASE_DIR / "uninstall.sh"
    if not script.is_file():
        return await event.edit("No trobo uninstall.sh.")
    if any(j.running for j in JOBS.values()):
        return await event.answer("Hi ha un lot en curs. Espera que acabi.", alert=True)
    await event.edit("🗑 Desinstal·lant… rebràs un missatge quan acabi.")
    try:
        await user.log_out()  # tanca la sessió d'usuari a Telegram
    except Exception:
        log.exception("No s'ha pogut tancar la sessió d'usuari")
    # systemd-run: el procés sobreviu a l'aturada del servei (que mata el seu cgroup)
    cmd = ["bash", str(script), "--yes"]
    if shutil.which("systemd-run"):
        cmd = ["systemd-run", "--no-block", "--collect", *cmd]
    subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@bot.on(events.CallbackQuery(func=lambda e: e.sender_id == config.ADMIN_USER_ID
                             and not e.data.startswith(b"unin:")))
async def h_cb(event):
    parts = event.data.decode().split(":")
    action, job = parts[0], JOBS.get(int(parts[1]))
    if not job:
        return await event.answer("Lot caducat.", alert=True)
    if job.running:
        return await event.answer("Ja s'està processant.")
    if action == "ser":
        job.series = job.folders[int(parts[2])]
    elif action == "new":
        AWAITING_NAME[event.sender_id] = job.id
        return await event.answer("Escriu el nom de la sèrie al xat.", alert=True)
    elif action == "adj":
        d = int(parts[3])
        if parts[2] == "s":
            job.season_off += d
        else:
            job.ep_off += d
    elif action == "cancel":
        JOBS.pop(job.id, None)
        return await event.edit("Lot cancel·lat.")
    elif action == "go":
        if not job.series:
            return await event.answer("Tria o escriu primer el nom de la sèrie.", alert=True)
        job.running = True
        await event.edit(f"⏳ Lot #{job.id} a la cua…")
        msg = await event.get_message()
        asyncio.create_task(run_job(job, msg))
        return
    await refresh_menu(event, job)


@bot.on(events.NewMessage(from_users=config.ADMIN_USER_ID,
                          func=lambda e: e.raw_text and not e.raw_text.startswith("/")))
async def h_text(event):
    job_id = AWAITING_NAME.pop(event.sender_id, None)
    job = JOBS.get(job_id) if job_id else None
    if not job:
        return
    job.series = fileops.sanitize(event.raw_text)
    sent = await event.respond("Nom actualitzat.")
    text, rows = render(job)
    await sent.edit(text, buttons=rows, parse_mode="html")


async def main():
    await user.start()  # primer cop: demana telèfon i codi (executar-ho interactivament)
    await bot.start(bot_token=config.BOT_TOKEN)
    await bot.send_message(config.ADMIN_USER_ID, "🤖 Bot actiu. Usa /buscar.")
    log.info("Llest.")
    await asyncio.gather(user.run_until_disconnected(), bot.run_until_disconnected())


if __name__ == "__main__":
    asyncio.run(main())
