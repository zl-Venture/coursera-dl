---
name: talkpal-dl
description: Download course material (word-mode words, sentence-mode and dialogue lines, example sentences, audio, images, cover art) from the TalkPal language-learning platform (app.talkpal.ai) via its API. Use this whenever the user wants to download, save, fetch, archive or batch-grab anything from TalkPal, pastes an app.talkpal.ai URL, mentions a TalkPal course/unit/deck/exercise, wants to set up or refresh their TalkPal access token, or hits a 401/403 from api.talkpal.ai. Also use it when they just say "下载这门课" and the course is on TalkPal.
---

# talkpal-dl

Downloads material from TalkPal (https://app.talkpal.ai) through its private
JSON API. TalkPal is not Coursera; this is a separate tool in the same repo.

`$SKILL_DIR` is the directory holding this SKILL.md. Scripts in `$SKILL_DIR/scripts/`:

| Script | Purpose |
|---|---|
| `run.sh ARGS...` | Run talkpal-dl with the stored credentials injected via the environment. Use for every call. Needs only `python3`. |
| `session.sh set\|status\|clear` | Store the long-lived Auth.js **session cookie** (recommended — enables auto-refresh). |
| `token.sh set\|status\|clear` | Store a short-lived access token (optional fallback if no session cookie). |
| `talkpal_dl.py` | The downloader (standard library only). `run.sh` calls it. |

## Auth

TalkPal uses two credentials:

- **accessToken** — the `Authorization: Bearer <...>` sent to `api.talkpal.ai`
  (plus `source: web` / `source-device: web`). Short-lived JWT: **~1 hour**
  (`exp - iat = 3600`), then every call 401s with `jwt expired`. The web app
  keeps it in `sessionStorage` under `accessToken`.
- **session cookie** — `__Secure-authjs.session-token`, the long-lived (Auth.js,
  ~30 days) login credential. POST it to `https://app.talkpal.ai/api/auth/refresh`
  and the response body is `{"accessToken": "<fresh 1h token>"}`. The refresh
  does not rotate the cookie (no `Set-Cookie`), so storing it once is enough.

**Preferred setup: store the session cookie** (`session.sh set`). The tool then
mints access tokens itself and, when one expires mid-run, auto-refreshes and
retries transparently (`(token refreshed)` on stderr) — a full multi-hour
download never stops for a stale JWT. A bare access token (`token.sh set`) still
works but dies after an hour. `run.sh` injects whichever is stored; if both are,
the session cookie drives refresh.

Both are full login credentials: never echo them, never write them into the
repo/commit/memory, never quote them in errors.

## Endpoints and the word-mode flow

Base `https://api.talkpal.ai/api/v1`. Each exercise in `/mode/courses` has a
`type` of `WORD`, `SENTENCE` or `DIALOGUE`, all three supported:

| Call | Returns |
|---|---|
| `GET /mode/courses` | courses → `units[]` → `exercises[]` (`id`, `type`, `exerciseId`, `exerciseVariant`, `coverPhoto`) |
| `GET /mode/list/word` | per-unit word `decks[]` (`id`, `deckOrder`, `exerciseVariant`, `coverImg`) |
| `POST /chat/initialize` | body `{"modeType":<word|sentence-mode|dialogue>,"categoryId":<exercise.id>,"exerciseId":<exercise.exerciseId>}` → `{"chatId": "..."}` (dialogue also wants `"chatApiType":"standard"`) |
| `GET /sentences/word-mode/{chatId}` | `{"contents":[{id, word, sentence, images:[{image,correct}], wordSpeechPath, sentenceSpeechPath}]}` |
| `GET /sentences/sentence-mode/{chatId}` | `{"sentences":[{id, content, role, speechPath}]}` |
| `GET /sentences/dialogue/{exercise.id}` | `{"sentences":[{id, content, role, speechPath}]}` — read-only, **no chat init** |

How each type is fetched:

- **WORD** — POST `/chat/initialize` (`modeType:"word"`) → `chatId` → GET
  `/sentences/word-mode/{chatId}`. Content: target word, example sentence, four
  candidate images (one `correct`), word audio and sentence audio.
- **SENTENCE** — POST `/chat/initialize` (`modeType:"sentence-mode"`) → `chatId`
  → GET `/sentences/sentence-mode/{chatId}`. Content: sentences with `role` and
  `speechPath` audio.
- **DIALOGUE** — GET `/sentences/dialogue/{exercise.id}` **directly**; no init,
  no chat id. Content: alternating `assistant`/`user` lines with audio.

Key gotcha: `/sentences/word-mode/{id}` and `/sentences/sentence-mode/{id}` take
a **chat id**, not an exercise id (an exercise/deck id returns HTTP 500 "Chat
with ID ... not found"). The tool mints one per exercise via `/chat/initialize`,
which is the same write the app makes when you open a lesson, so it runs only
during a real download, never during `--list`/`--covers`. Dialogue needs no such
write. Audio is `.mp3`, images are `.webp`.

## Workflow

### 1. Store a credential

```bash
bash "$SKILL_DIR/scripts/session.sh" status   # preferred
bash "$SKILL_DIR/scripts/token.sh" status     # fallback
```

If neither is stored, ask the user to store the **session cookie** themselves so
it never enters the chat (recommended — it enables auto-refresh):

> Log in to TalkPal, open DevTools → Application → Storage → **Cookies** →
> `https://app.talkpal.ai`, copy the **value** of `__Secure-authjs.session-token`
> (it is HttpOnly, so it is not in `document.cookie`/sessionStorage — copy it from
> the Cookies panel), then run `bash <SKILL_DIR>/scripts/session.sh set` and paste
> it (input hidden). In Claude Code, prefix the command with `!`.
> (中文:登录后 DevTools → Application → Cookies → app.talkpal.ai,复制
> `__Secure-authjs.session-token` 的 Value,运行 `session.sh set` 粘贴。)

Quick fallback (one hour, no auto-refresh): copy a Bearer access token instead —
from `sessionStorage.accessToken` or any `api.talkpal.ai` request's
`authorization` header — and run `token.sh set`.

Give the full absolute path. With a session cookie stored, a stale access token
fixes itself; a 401/403 that persists *after* `(token refreshed)` means the
session cookie itself is stale — ask for a fresh one.

### 2. Browse

```bash
bash "$SKILL_DIR/scripts/run.sh" --list            # courses, ids, levels, WORD counts
bash "$SKILL_DIR/scripts/run.sh" --list -v         # + units and exercises
bash "$SKILL_DIR/scripts/run.sh" --list-decks -v   # word-mode decks per unit
```

### 3. Download

```bash
# every exercise (word + sentence + dialogue) in every course -> ~/TalkPal
bash "$SKILL_DIR/scripts/run.sh" --path ~/TalkPal

# one course (use the id from --list)
bash "$SKILL_DIR/scripts/run.sh" --course <courseId> --path ~/TalkPal

# one exercise
bash "$SKILL_DIR/scripts/run.sh" --exercise <exerciseId> --path ~/TalkPal

# only some types
bash "$SKILL_DIR/scripts/run.sh" --types dialogue --path ~/TalkPal

# just cover art, no lesson content
bash "$SKILL_DIR/scripts/run.sh" --covers --path ~/TalkPal
```

Useful options (full list: `run.sh --help`):

| Need | Option |
|---|---|
| Save location | `--path DIR` (default `~/TalkPal`) |
| One course / one exercise | `--course <id>` / `--exercise <id>` |
| Limit exercise types | `--types word,sentence,dialogue` (default: all three) |
| Save every option image, not just the correct one | `--all-images` |
| Re-download exercises already finished | `--force` |
| Skip audio, keep transcripts/images/JSON | `--no-audio` |
| One word deck by an already-live chat id | `--chat <chatId> --name <label>` |
| Throttle between exercises | `--delay <seconds>` (default 0.3) |

Output layout:

```
<path>/courses.json
<path>/<course>/<NN_unit>/<NN_type[_variant]>/
    word-mode.json | sentences.json    raw response
    transcript.txt                     word/line text per item (role-prefixed
                                        for sentence & dialogue)
    NN_<word>_word.mp3                 WORD: the word, spoken
    NN_<word>_sentence.mp3             WORD: the example sentence, spoken
    NN_<word>.webp                     WORD: the correct image (--all-images = 4)
    NN_<role>_<text>.mp3               SENTENCE/DIALOGUE: each line, spoken
```

Default save location is the user's home (`~/TalkPal`), not inside the repo, so
downloads do not pollute `git status`.

### Resume after an interruption

Downloads are resumable, so a crash, a 401, or Ctrl-C costs almost nothing to
recover from — just run the same command again.

- **Per file**: each audio/image download retries up to 4 times with backoff on
  a transient network error (connection reset, timeout, closed connection), so a
  blip recovers within the same run; a 4xx (missing/forbidden asset) is not
  retried. The file is written to a `.part` temp file and renamed atomically; an
  existing non-empty file is skipped. No half files, no re-fetch of media already
  on disk. A file that still fails after all retries is left missing (not marked
  done), so the next run picks it up.
- **Per exercise**: when an exercise downloads with *every* file succeeding, a
  `.done` marker (JSON: time + counts) is written in its folder. On the next run
  that exercise is skipped entirely — no `/chat/initialize`, no re-fetch (shown
  as `= resume ... (already complete)`). An exercise that finished only
  partially has no marker, so it re-runs and the per-file skip fills the gaps.
- `--force` ignores the markers and re-downloads everything.

The summary line reports resumed vs. skipped: `N resumed` = finished on an
earlier run, `N skipped` = locked/paid or excluded by `--types`.

### 4. Report what happened

Check the output before claiming success. The run prints per-exercise and total
counts of exercises, sentences, audio files and images, plus how many were
skipped. A skip usually means locked/paid content (HTTP 402/403 on that item) or
a type excluded by `--types`. A 401 on *everything* is a stale token, not locked
content.

## Notes

- `/chat/initialize` creates a chat session per WORD/SENTENCE exercise on the
  user's account. That is normal (it is what opening a lesson does), but it is a
  write, so the tool does it only during a real download, never during
  `--list`/`--covers`. DIALOGUE needs no such write.
- Content has no translation field; it provides target-language text and audio.
  WORD adds four candidate images (one `correct`). `transcript.txt` captures the
  text (role-prefixed for sentence and dialogue).
