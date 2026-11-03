---
name: coursera-dl
description: Download Coursera course material (lecture videos, subtitles, PDFs, quizzes) with the patched coursera-dl command-line tool. Use this whenever the user wants to download, save, fetch, archive or batch-grab anything from Coursera, pastes a coursera.org/learn/... URL, mentions a course slug like "french-elementary", asks which Coursera courses they are enrolled in, wants to set up or refresh their Coursera CAUTH cookie, or hits a coursera-dl error (JSONDecodeError, 403 Not Authorized, distutils, API Route Does Not Exist). Also use it when they just say "下载这门课" and the course is on Coursera.
---

# coursera-dl

This skill drives a patched fork of coursera-dl. Upstream is unmaintained; the
fork fixes Python 3.12+ breakage and Coursera's retired v1 API, so always use
the fork's checkout, never `pip install coursera-dl`.

`$SKILL_DIR` below means the directory holding this SKILL.md. Three helper
scripts live in `$SKILL_DIR/scripts/`:

| Script | Purpose |
|---|---|
| `run.sh ARGS...` | Run coursera-dl. Locates the checkout and venv (via `setup.sh`), injects the stored CAUTH cookie. Use this for every download. |
| `cauth.sh set\|status\|clear` | Store the Coursera login cookie in the macOS Keychain (or a mode-600 file elsewhere). |
| `syllabus_tree.py FILE` | Print module/section/lecture slugs from a cached syllabus, for building filters. |

`run.sh` takes care of `setup.sh` (find or clone the repo, create the venv,
install requirements) on every call, so there is no separate setup step.

## Workflow

### 1. Make sure a cookie is stored

```bash
bash "$SKILL_DIR/scripts/cauth.sh" status
```

Username/password login no longer works; the tool authenticates with the
browser's `CAUTH` cookie. If status says `not stored`, ask the user to store it
themselves, in their own terminal, so the value never goes through the chat:

> Log in to Coursera in the browser, open developer tools → Application
> (Chrome) or Storage (Firefox) → Cookies → `https://www.coursera.org`, copy
> the value of `CAUTH`, then run
> `bash <SKILL_DIR>/scripts/cauth.sh set` and paste it (input is hidden).
> In Claude Code, prefix the command with `!` to run it in this session.
> (中文:登录 Coursera 后打开开发者工具 → Application/Storage → Cookies →
> coursera.org,复制 `CAUTH` 的值,运行 `cauth.sh set` 粘贴即可。)

Give the full absolute path of `cauth.sh` in that instruction. Only if the user
insists on pasting the value into the chat, store it with
`printf '%s' '<value>' | bash "$SKILL_DIR/scripts/cauth.sh" set`.

The cookie is a full login credential. Never echo it in a reply, never write
it into the repo, a commit message, memory or a config file, and never quote it
when reporting errors. Refer to it as "the cookie". It expires after a while:
a run that fails with 401/403 on everything, or `--list-courses` returning
nothing, means a stale cookie. Ask the user to run `cauth.sh set` again.

### 2. Get the course slug
The slug is the path segment after `/learn/` in the course URL:
`https://www.coursera.org/learn/french-elementary` → `french-elementary`.
Specialization URLs look like `/specializations/<slug>`; pass that slug with
`--specialization` to download every course in it.

If the user only knows the course title, list what they are enrolled in:

```bash
bash "$SKILL_DIR/scripts/run.sh" --list-courses
```

### 3. Run the download
Default to saving under the user's home, not inside the repo (course folders
are not git-ignored and pollute `git status`):

```bash
bash "$SKILL_DIR/scripts/run.sh" --path ~/Coursera -sl en --resume <slug>
```

Useful options (full list: `run.sh --help`):

| Need | Option |
|---|---|
| Save location | `--path DIR` |
| Subtitle languages | `-sl en,fr` (default `all`; `en,zh-CN\|zh-TW` means fallback) |
| Video quality | `--video-resolution 720p` |
| Quizzes / notebooks | `--download-quizzes`, `--download-notebooks` |
| Only some file types | `-f "mp4,pdf"` / `--ignore-formats "srt,txt"` |
| Only part of the course | `-sf <regex>` (section), `-lf <regex>` (lecture), see below |
| Parallel downloads | `--jobs 4` |
| Continue a partial run | `--resume` |
| Inspect without downloading | `--only-syllabus --cache-syllabus` |

A full course takes a few minutes to parse plus the download time. Run it in
the background with output going to a log file, then summarize the log.

### 4. Filters match slugs, not display names
`-sf` is matched against **section** slugs (Coursera calls them lessons, e.g.
`avant-de-commencer`), not module/week slugs. `-lf` matches lecture slugs.
Module names like `connexions` match nothing in `-sf` and the run silently
downloads zero files. To see the real slugs before filtering, dump the
syllabus and print the tree:

```bash
cd ~/Coursera
bash "$SKILL_DIR/scripts/run.sh" --only-syllabus --cache-syllabus <slug>
python3 "$SKILL_DIR/scripts/syllabus_tree.py" <slug>-syllabus-parsed.json
```

`<slug>-syllabus-parsed.json` is written to the current directory; delete it
afterwards.

### 5. Report what happened
Check the log and the output directory before telling the user it worked.
Report counts of files per type and explain anything skipped. Output layout is
`<path>/<slug>/NN_<module>/NN_<section>/NN_<lecture>.<ext>`.

## Reading the log

These messages are normal and not errors:

- `Skipping locked lecture "..." (reason: PAID_ITEM)` — the user is auditing
  the course for free; that item needs payment. Tell the user how many items
  were skipped for this reason. Nothing can be done without paying.
- `Unsupported typename "coach"/"discussionPrompt"/"staffGraded"/
  "ungradedAssignment"` — interactive items with nothing to download.
- `The following classes had errors during the syllabus parsing stage` —
  printed whenever any single item failed; check the log for the actual
  failures before calling the run a failure. Videos usually downloaded fine.

Real problems:

| Symptom | Cause | Fix |
|---|---|---|
| `No CAUTH cookie stored` | Nothing stored yet | Step 1 |
| `403 Not Authorized` on items that are **not** locked, or on everything | Expired cookie, or not enrolled | `cauth.sh set` with a fresh cookie; enroll (audit) on the website and accept the honor code |
| `JSONDecodeError` right after "Parsing syllabus" | Coursera retired an API endpoint; the body is an HTML "API Route Does Not Exist" page | `onDemandCourseMaterials.v1` is already handled in the fork. For a new one, probe the URL with `requests` and the cookie, find the v2 equivalent, patch `coursera/define.py` |
| `No module named 'distutils'` / `HTMLParser has no attribute 'unescape'` | Old checkout (upstream) or wrong Python | Use the fork via `run.sh`; `git pull` in the checkout |
| `No module named requests` | System python instead of the venv | `run.sh` recreates the venv; or `venv/bin/pip install -r requirements.txt` |
| Zero files downloaded, no errors | Filters matched nothing | See section 4 |

To use a different checkout, set `COURSERA_DL_HOME=/path/to/repo`. To use a
one-off cookie without storing it, set `COURSERA_CAUTH` in the environment.

When you hit a new API breakage, the pattern that has worked: call the failing
URL directly with a `requests.Session` carrying the `CAUTH` cookie, look at the
status and the first 300 characters of the body, compare with the request the
Coursera web app makes, and update the URL template in `coursera/define.py`.
Keep fixes small and commit them in the repo so the next run benefits.
