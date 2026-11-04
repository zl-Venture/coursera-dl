#!/usr/bin/env python3
"""
talkpal-dl -- download course material from TalkPal (app.talkpal.ai).

Standard library only (urllib). Authentication is a Bearer access token read
from the TALKPAL_TOKEN environment variable (run.sh injects it from the macOS
Keychain). Nothing is printed that would reveal the token.

Verified endpoints (base https://api.talkpal.ai/api/v1):
  GET  /mode/courses              courses -> units -> exercises
  GET  /mode/list/word            word-mode decks per unit (ids, covers)
  POST /chat/initialize           {modeType,categoryId,exerciseId} -> {chatId}
  GET  /sentences/word-mode/{id}  the deck content for that chat id

Word-mode flow (what this tool automates): each WORD exercise is "started" by
POSTing to /chat/initialize with
    {"modeType":"word","categoryId":<exercise.id>,"exerciseId":<exercise.exerciseId>}
which returns a fresh chatId; then GET /sentences/word-mode/{chatId} returns
  {"contents":[{id, word, sentence, sentenceId,
                images:[{image, correct}], wordSpeechPath, sentenceSpeechPath}]}
word/sentence audio are .mp3, images are .webp.

The JSON is tolerated loosely and the raw response is always saved too.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.talkpal.ai/api/v1"
REFRESH_URL = "https://app.talkpal.ai/api/auth/refresh"
UA = "talkpal-dl/0.3 (standard-library urllib)"

# accessToken currently in use; refreshed in place from the session cookie when
# it expires, so a long download survives the ~1h token lifetime untouched.
_CURRENT_TOKEN = None


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------


def _strip_bearer(tok):
    tok = (tok or "").strip()
    return tok[7:].strip() if tok.lower().startswith("bearer ") else tok


def _session():
    return os.environ.get("TALKPAL_SESSION", "").strip()


def refresh_token():
    """Mint a fresh accessToken from the Auth.js session cookie. Returns True on
    success and updates _CURRENT_TOKEN in place."""
    global _CURRENT_TOKEN
    sess = _session()
    if not sess:
        return False
    req = urllib.request.Request(
        REFRESH_URL, method="POST",
        headers={
            "Accept": "application/json",
            "User-Agent": UA,
            "Origin": "https://app.talkpal.ai",
            "Referer": "https://app.talkpal.ai/",
            "Cookie": "__Secure-authjs.session-token=" + sess,
        })
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False
    at = _strip_bearer((d or {}).get("accessToken"))
    if not at:
        return False
    _CURRENT_TOKEN = at
    return True


def _token():
    global _CURRENT_TOKEN
    if _CURRENT_TOKEN:
        return _CURRENT_TOKEN
    tok = _strip_bearer(os.environ.get("TALKPAL_TOKEN"))
    if tok:
        _CURRENT_TOKEN = tok
        return tok
    # No static token supplied: mint one from the session cookie if we have it.
    if refresh_token():
        return _CURRENT_TOKEN
    sys.exit("No credential: set a session cookie (session.sh set) or an access "
             "token (token.sh set).")


def _headers(json_body=False):
    h = {
        "Authorization": "Bearer " + _token(),
        "Accept": "application/json",
        "source": "web",
        "source-device": "web",
        "User-Agent": UA,
        "Origin": "https://app.talkpal.ai",
        "Referer": "https://app.talkpal.ai/",
    }
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def api(path, body=None, method=None, retries=3):
    """Call the API. body=dict -> POST JSON. Returns parsed JSON."""
    url = path if path.startswith("http") else API_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    method = method or ("POST" if data is not None else "GET")
    last = None
    refreshed = False
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data,
                                     headers=_headers(json_body=data is not None),
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403):
                # Token expired mid-run: swap in a fresh one from the session
                # cookie and retry once, transparently.
                if not refreshed and refresh_token():
                    refreshed = True
                    print("    (token refreshed)", file=sys.stderr)
                    continue
                if _session():
                    sys.exit(
                        "Auth failed (%d) for %s even after refresh. The session "
                        "cookie is stale. Log in again at app.talkpal.ai, copy a "
                        "fresh __Secure-authjs.session-token, run session.sh set."
                        "\nServer said: %s" % (e.code, path, txt))
                sys.exit(
                    "Auth failed (%d) for %s. The token is stale.\nStore a "
                    "session cookie for auto-refresh (session.sh set), or copy a "
                    "fresh access token and run token.sh set.\nServer said: %s"
                    % (e.code, path, txt))
            if e.code == 500 and "Chat with ID" in txt:
                raise ChatNotFound(txt)
            if e.code in (400, 402, 404):
                raise ApiError(e.code, txt)
            if e.code == 429 or 500 <= e.code < 600:
                last = "%d %s" % (e.code, txt)
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(e.code, txt)
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
            time.sleep(2 * (attempt + 1))
    raise ApiError(0, "failed after %d tries: %s" % (retries, last))


class ChatNotFound(Exception):
    pass


class ApiError(Exception):
    def __init__(self, code, text):
        super().__init__("HTTP %s: %s" % (code, text))
        self.code = code
        self.text = text


def download_file(url, dest, retries=4):
    if not url:
        return False
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, dest)
            return True
        except urllib.error.HTTPError as e:
            # 4xx (missing/forbidden asset) will not fix itself; do not retry.
            last = e
            if 400 <= e.code < 500:
                break
        except Exception as e:  # noqa: BLE001  (reset, timeout, incomplete read)
            last = e
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    print("    ! download failed %s (%s)" % (url, last), file=sys.stderr)
    return False


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def first(d, *keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in list(keys) + ["data", "results", "items", "contents"]:
            v = obj.get(k)
            if isinstance(v, list):
                return v
    return []


def slugify(text, maxlen=60):
    text = str(text or "").strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-.]", "", text, flags=re.UNICODE)
    return (text.strip("_.") or "item")[:maxlen]


def ext_of(url, default=".mp3"):
    base = os.path.basename(url.split("?")[0])
    e = os.path.splitext(base)[1]
    return e if e else default


def dump_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def collect_media(obj):
    out = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and o.startswith("http"):
            low = o.split("?")[0].lower()
            if low.endswith((".mp3", ".m4a", ".ogg", ".wav", ".webp", ".png",
                             ".jpg", ".jpeg", ".gif")):
                out.append(o)
    walk(obj)
    return list(dict.fromkeys(out))


# ----------------------------------------------------------------------------
# word-mode core
# ----------------------------------------------------------------------------


def init_chat(mode_type, category_id, exercise_id, extra=None):
    """Start a lesson of the given modeType, returning its fresh chatId."""
    body = {
        "modeType": mode_type,
        "categoryId": category_id,
        "exerciseId": exercise_id,
    }
    if extra:
        body.update(extra)
    resp = api("/chat/initialize", body=body)
    return first(resp, "chatId", "id", "_id")


def save_word_mode(data, dest, all_images=False, want_audio=True):
    """Save a /sentences/word-mode response into dest. Returns counts dict."""
    os.makedirs(dest, exist_ok=True)
    dump_json(data, os.path.join(dest, "word-mode.json"))
    items = as_list(data, "contents")
    n_audio = n_img = 0
    ok = True
    lines = []
    for i, it in enumerate(items, 1):
        word = first(it, "word", "text", default="")
        sentence = first(it, "sentence", default="")
        if word or sentence:
            lines.append("%02d. %s" % (i, word) + (
                "\n    %s" % sentence if sentence else ""))
        tag = "%02d_%s" % (i, slugify(word, 30) or "item")
        if want_audio:
            wsp = first(it, "wordSpeechPath")
            ssp = first(it, "sentenceSpeechPath")
            if wsp:
                if download_file(wsp, os.path.join(dest, tag + "_word" + ext_of(wsp))):
                    n_audio += 1
                else:
                    ok = False
            if ssp:
                if download_file(ssp, os.path.join(dest, tag + "_sentence" + ext_of(ssp))):
                    n_audio += 1
                else:
                    ok = False
        imgs = as_list(it, "images")
        chosen = imgs if all_images else [im for im in imgs if im.get("correct")]
        for j, im in enumerate(chosen, 1):
            url = first(im, "image", "url")
            if not url:
                continue
            suffix = "" if (len(chosen) == 1 and not all_images) else "_%d" % j
            if download_file(url, os.path.join(dest, tag + suffix + ext_of(url, ".webp"))):
                n_img += 1
            else:
                ok = False
    if lines:
        with open(os.path.join(dest, "transcript.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return {"sentences": len(items), "audio": n_audio, "images": n_img, "complete": ok}


def save_sentence_list(data, dest, want_audio=True):
    """Save a sentence-mode / dialogue response: {"sentences":[{content,role,
    speechPath}]}. Returns counts dict."""
    os.makedirs(dest, exist_ok=True)
    dump_json(data, os.path.join(dest, "sentences.json"))
    items = as_list(data, "sentences")
    n_audio = 0
    ok = True
    lines = []
    for i, it in enumerate(items, 1):
        content = first(it, "content", "text", "sentence", default="")
        role = first(it, "role", default="")
        prefix = ("%s: " % role) if role else ""
        if content:
            lines.append("%02d. %s%s" % (i, prefix, content))
        if want_audio:
            sp = first(it, "speechPath", "sound", "audio")
            tag = "%02d_%s%s" % (i, (role + "_") if role else "",
                                 slugify(content, 30) or "line")
            if sp:
                if download_file(sp, os.path.join(dest, tag + ext_of(sp))):
                    n_audio += 1
                else:
                    ok = False
    if lines:
        with open(os.path.join(dest, "transcript.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    return {"sentences": len(items), "audio": n_audio, "images": 0, "complete": ok}


def download_word_exercise(ex, dest, all_images=False, want_audio=True):
    """WORD: init chat -> fetch -> save."""
    cat, exid = first(ex, "id"), first(ex, "exerciseId")
    if not cat or not exid:
        raise ApiError(0, "exercise missing id/exerciseId")
    chat_id = init_chat("word", cat, exid)
    if not chat_id:
        raise ApiError(0, "no chatId returned by /chat/initialize")
    data = api("/sentences/word-mode/%s" % chat_id)
    return save_word_mode(data, dest, all_images=all_images, want_audio=want_audio)


def download_sentence_exercise(ex, dest, want_audio=True):
    """SENTENCE: init sentence-mode chat -> fetch -> save."""
    cat, exid = first(ex, "id"), first(ex, "exerciseId")
    if not cat or not exid:
        raise ApiError(0, "exercise missing id/exerciseId")
    chat_id = init_chat("sentence-mode", cat, exid)
    if not chat_id:
        raise ApiError(0, "no chatId returned by /chat/initialize")
    data = api("/sentences/sentence-mode/%s" % chat_id)
    return save_sentence_list(data, dest, want_audio=want_audio)


def download_dialogue_exercise(ex, dest, want_audio=True):
    """DIALOGUE: read-only GET by the exercise id (categoryId). No init needed."""
    cat = first(ex, "id")
    if not cat:
        raise ApiError(0, "exercise missing id")
    data = api("/sentences/dialogue/%s" % cat)
    return save_sentence_list(data, dest, want_audio=want_audio)


# ----------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------


def cmd_list(args):
    courses = as_list(api("/mode/courses"))
    for c in courses:
        n_units = len(as_list(c, "units"))
        n_ex = sum(len(as_list(u, "exercises")) for u in as_list(c, "units"))
        n_word = sum(1 for u in as_list(c, "units")
                     for e in as_list(u, "exercises")
                     if first(e, "type") == "WORD")
        print("- %s  [%s]" % (first(c, "name", default="course"),
                              first(c, "level", default="")))
        print("    id=%s  units=%d  exercises=%d  (WORD=%d)"
              % (first(c, "id"), n_units, n_ex, n_word))
        if args.verbose:
            for u in as_list(c, "units"):
                print("    unit %s: %s" % (first(u, "order"), first(u, "name", default="")))
                for ex in as_list(u, "exercises"):
                    print("        [%s/%s] id=%s exerciseId=%s"
                          % (first(ex, "type", default="?"),
                             first(ex, "exerciseVariant", default=""),
                             first(ex, "id"), first(ex, "exerciseId")))


def cmd_list_decks(args):
    units = as_list(api("/mode/list/word"))
    for u in units:
        decks = as_list(u, "decks")
        print("unit %s: %d decks  (%s/%s complete)"
              % (first(u, "unitIndex"), len(decks),
                 first(u, "completedCount", default=0),
                 first(u, "totalCount", default=0)))
        if args.verbose:
            for d in decks:
                print("    deck %s id=%s variant=%s"
                      % (first(d, "deckOrder"), first(d, "id"),
                         first(d, "exerciseVariant", default="")))


def cmd_chat(args):
    """Download one word-mode deck by a known chat id."""
    try:
        data = api("/sentences/word-mode/%s" % args.chat)
    except ChatNotFound:
        sys.exit("That id is not a live chat id. Use the full download, which "
                 "creates chat ids via /chat/initialize, or pass a chat id seen "
                 "in DevTools.")
    dest = os.path.join(args.path, slugify(args.name or args.chat))
    c = save_word_mode(data, dest, all_images=args.all_images,
                       want_audio=not args.no_audio)
    print("Saved %s: %d sentences, %d audio, %d images -> %s"
          % (args.name or args.chat, c["sentences"], c["audio"], c["images"], dest))


def cmd_covers(args):
    courses = api("/mode/courses")
    decks = api("/mode/list/word")
    dump_json(courses, os.path.join(args.path, "courses.json"))
    dump_json(decks, os.path.join(args.path, "word-decks.json"))
    urls = set(collect_media(courses)) | set(collect_media(decks))
    cover_dir = os.path.join(args.path, "_covers")
    n = sum(download_file(u, os.path.join(cover_dir, slugify(
        os.path.basename(u.split("?")[0]), 80))) for u in sorted(urls))
    print("Downloaded %d cover images to %s" % (n, cover_dir))


DISPATCH = {
    "WORD": lambda ex, d, a: download_word_exercise(
        ex, d, all_images=a.all_images, want_audio=not a.no_audio),
    "SENTENCE": lambda ex, d, a: download_sentence_exercise(
        ex, d, want_audio=not a.no_audio),
    "DIALOGUE": lambda ex, d, a: download_dialogue_exercise(
        ex, d, want_audio=not a.no_audio),
}


def cmd_download(args):
    """Download every exercise (WORD/SENTENCE/DIALOGUE) in all courses or one."""
    out = args.path
    wanted = {t.strip().upper() for t in args.types.split(",") if t.strip()}
    courses = as_list(api("/mode/courses"))
    dump_json(courses, os.path.join(out, "courses.json"))
    tot = {"ex": 0, "sent": 0, "audio": 0, "img": 0, "skip": 0, "done": 0}
    for c in courses:
        cid = first(c, "id")
        if args.course and str(cid) != str(args.course):
            continue
        cdir = os.path.join(out, slugify(first(c, "name", default=cid)))
        print("Course: %s [%s]" % (first(c, "name"), first(c, "level", default="")))
        for ui, u in enumerate(as_list(c, "units"), 1):
            udir = os.path.join(cdir, "%02d_%s" % (ui, slugify(first(u, "name", default="unit"), 40)))
            for ei, ex in enumerate(as_list(u, "exercises"), 1):
                etype = first(ex, "type", default="")
                if etype not in wanted or etype not in DISPATCH:
                    continue
                if args.exercise and str(first(ex, "exerciseId")) != str(args.exercise):
                    continue
                variant = first(ex, "exerciseVariant")
                label = "%02d_%s" % (ei, etype.lower())
                if variant:
                    label += "_" + slugify(variant, 24)
                edir = os.path.join(udir, label)
                done_marker = os.path.join(edir, ".done")
                if os.path.exists(done_marker) and not args.force:
                    tot["done"] += 1
                    print("    = resume %s (already complete)" % label)
                    continue
                try:
                    r = DISPATCH[etype](ex, edir, args)
                except ChatNotFound as e:
                    print("    ! chat vanished for %s (%s)" % (label, e), file=sys.stderr)
                    tot["skip"] += 1
                    continue
                except ApiError as e:
                    # 402/403 => locked/paid; 400 => unsupported; keep going
                    print("    - skip %s (%s)" % (label, e), file=sys.stderr)
                    tot["skip"] += 1
                    continue
                tot["ex"] += 1
                tot["sent"] += r["sentences"]
                tot["audio"] += r["audio"]
                tot["img"] += r["images"]
                if r.get("complete"):
                    try:
                        with open(done_marker, "w", encoding="utf-8") as fh:
                            json.dump({"at": int(time.time()),
                                       "sentences": r["sentences"],
                                       "audio": r["audio"],
                                       "images": r["images"]}, fh)
                    except OSError:
                        pass
                    status = ""
                else:
                    status = "  (incomplete, will retry next run)"
                print("    %s: %d sentences, %d audio, %d images%s"
                      % (label, r["sentences"], r["audio"], r["images"], status))
                time.sleep(args.delay)
    print("\nDone: %d exercises, %d sentences, %d audio, %d images, "
          "%d resumed, %d skipped -> %s"
          % (tot["ex"], tot["sent"], tot["audio"], tot["img"],
             tot["done"], tot["skip"], out))


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(
        prog="talkpal-dl",
        description="Download TalkPal (app.talkpal.ai) word-mode material.")
    p.add_argument("--path", default=os.path.expanduser("~/TalkPal"),
                   help="output directory (default: ~/TalkPal)")
    p.add_argument("--list", action="store_true",
                   help="list courses -> units -> exercises and exit")
    p.add_argument("--list-decks", action="store_true",
                   help="list word-mode decks per unit and exit")
    p.add_argument("--covers", action="store_true",
                   help="download course/deck cover images and exit")
    p.add_argument("--chat", default=None, metavar="CHAT_ID",
                   help="download one deck by an already-live chat id")
    p.add_argument("--course", default=None, metavar="COURSE_ID",
                   help="restrict the full download to this course id")
    p.add_argument("--exercise", default=None, metavar="EXERCISE_ID",
                   help="restrict the full download to this exerciseId")
    p.add_argument("--types", default="word,sentence,dialogue",
                   help="comma list of exercise types to download "
                        "(default: word,sentence,dialogue)")
    p.add_argument("--all-images", action="store_true",
                   help="save every option image, not just the correct one")
    p.add_argument("--force", action="store_true",
                   help="re-download exercises already marked complete (.done)")
    p.add_argument("--no-audio", action="store_true",
                   help="skip audio, keep transcripts/images/JSON")
    p.add_argument("--name", default=None, help="folder label for --chat")
    p.add_argument("--delay", type=float, default=0.3,
                   help="seconds between exercises (default 0.3)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="with --list / --list-decks, show nested items")
    args = p.parse_args()

    if args.list:
        cmd_list(args)
    elif args.list_decks:
        cmd_list_decks(args)
    elif args.covers:
        cmd_covers(args)
    elif args.chat:
        cmd_chat(args)
    else:
        cmd_download(args)


if __name__ == "__main__":
    main()
