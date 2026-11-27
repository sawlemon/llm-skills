# PHP2Shell explained: speaker notes

Deck: `C-paper-punch.html` (→ / ← to move, F for fullscreen). Slides 5 and 6 build up in 6 steps each.

Sources: [Wiz Research blog](https://www.wiz.io/blog/php2shell-php-rce) · PHP advisories [GHSA-w8hw-w9fx-j79w](https://github.com/php/php-src/security/advisories/GHSA-w8hw-w9fx-j79w) and [GHSA-6wmf-4rv5-p3rp](https://github.com/php/php-src/security/advisories/GHSA-6wmf-4rv5-p3rp) · [PHP Foundation post](https://thephp.foundation/blog/2026/10/21/todays-php-security-release-and-how-were-strengthening-php-security/)

---

## Slide 1: PHP2Shell (title)

- In October 2026, two critical bugs were found in **PHP itself**.
- Their nickname is **PHP2Shell**: going from a normal PHP website to a shell on the server.
- The two bugs are **CVE-2026-109618** and **CVE-2026-109619**.
- Both are rated **CVSS 9.2 out of 10**, which is critical.
- The cause sounds boring: **running out of memory**.

## Slide 2: What is PHP?

- PHP is the language running **behind** most websites.
- When you open a page, PHP builds it on the server and sends it to you.
- WordPress, Drupal, Joomla and Wikipedia (MediaWiki) all run on PHP.
- Wiz Research says about **70% of websites** run on PHP.
- The bug is in **PHP itself**, not in any one website. Even a perfectly written site can be hit, and even a simple "Hello World" page can be at risk.

## Slide 3: Think of PHP like a hotel

- A web request is a **guest**.
- A PHP **worker** is a **hotel room**.
- A server has only a few rooms (workers).
- Each room is **reused** guest after guest, because rebuilding the room every time would be slow.
- Between guests, **housekeeping** cleans the room. In PHP terms, the memory is reset.
- **Golden rule:** clean the room before the next guest checks in.
- Both bugs happen when that cleanup goes wrong.

## Slide 4: Out of memory? PHP stops dead

- Every request gets a **memory limit**, the `memory_limit` setting (often 128 MB).
- It's there so one visitor can't eat the whole server's memory.
- If a request goes over the limit, PHP **stops right there**.
- It doesn't finish the step it was on (technically, it jumps out with `longjmp()`).
- So some **cleanup never happens**.
- An attacker can **make this happen on purpose**. They send a huge, messy upload (thousands of headers, piles of empty file fields) that looks small on the network but gets huge once PHP unpacks it in memory.
- That way the attacker chooses **exactly when** memory runs out.

> **One line:** "When PHP runs out of memory, it stops mid-step and skips cleanup, and an attacker can trigger that whenever they want."

## Slide 5: Bug #1, the half-unpacked suitcase (CVE-2026-109618)

Press → for each step:

1. **Request 1 (attacker):** an earlier request leaves **junk** in memory. That memory later gets reused.
2. **Request 2 (attacker upload):** PHP starts **building data** on top of that memory, block by block.
3. **Memory runs out halfway.** PHP is in the middle of setting something up.
4. **PHP stops.** The data is **half-built**: one part is finished, and the rest still holds the old junk.
5. **Request 2 ends, cleanup runs.** Cleanup assumes everything is complete and **trusts all of it**.
6. Cleanup uses the junk, and **the attacker's code runs** on the server (as the web server user, `www-data`).

- The worst case is **Apache with `mod_php`**. All of this happens while PHP is still reading the upload, **before the website's own code runs**, with **default settings**.
- PHP-FPM was also confirmed to be exploitable, but only through certain application code paths.
- **The fix:** PHP no longer stops instantly. It now stops at the next **safe point**, and only force-kills the worker if memory goes way past the limit.

> **One line:** "PHP gets interrupted halfway, then later trusts the half-built thing, and the empty half is filled with attacker data."

## Slide 6: Bug #2, the sticky note nobody removed (CVE-2026-109619)

Press → for each step:

1. **Request 1** saves data in memory, and PHP writes a **note** saying "your data is in slot 5". That note is a *pointer*, and it is kept between requests.
2. **Request 1 crashes** (a fatal error, for example running out of memory).
3. **PHP frees the memory**, so all the slots are thrown away. But the **note is not removed**, and it still points to slot 5.
4. **Request 2 (attacker)** puts its **own data into slot 5**.
5. **Request 3** reads the old note and goes to slot 5.
6. PHP **trusts what it finds there**, and **the attacker's code runs**.

- This is called a **use-after-free**: using memory after it was freed.
- Real examples of these notes:
  - the saved **fatal error backtrace** (PHP 8.5)
  - **session upload progress**, which is on by default
- The catch for the attacker is that the requests must land on the **same worker**. There are only a few workers, so attackers just keep retrying.

> **One line:** "PHP threw the memory away but kept a note pointing to it. The attacker moves into that spot, and PHP trusts whatever it finds there."

> **Both bugs in one line:** "A crash leaves a mess behind, and PHP trusts the mess."

## Slide 7: The attack in 3 moves

1. **Crash it:** make PHP run out of memory at the wrong moment, so a mess is left behind.
2. **Fill it:** send requests that plant the attacker's data in the freed memory.
3. **Trigger it:** the next request uses the mess, and **the attacker's code runs**.

- **No login** needed and **no bug in the website** needed.

## Slide 8: How bad was it?

- 🔓 **No login needed:** an attacker can run commands on your server from anywhere on the internet.
- 🔑 **Secrets leak:** passwords, tokens and API keys can be read straight out of memory, like Heartbleed.
- 🌐 **Any PHP website:** shown on WordPress, Drupal and Joomla, but the bug is in PHP, so any app can be at risk.
- 🕰️ **10+ years old:** every PHP version since **5.4** has at least one of these bugs.
- **Severity: 9.2 / 10.**
- Highest risk: **Apache `mod_php`**. Also affected: PHP-FPM, FrankenPHP, LiteSpeed and php-cgi.

## Slide 9: AI helped build the exploit

- The bugs sat **hidden for 10+ years**.
- Turning them into a working attack was **too complex** for humans to do in practice, because it means chaining several bugs and matching each server's memory layout.
- With frontier AI models (Gemini 4 Argon, GPT-5.6 Sol), Wiz Research built working exploits for several apps **in hours**.
- **Lesson:** "complicated" no longer means "safe".
- **Found by Wiz Research:** Sagi Tzadik, Shir Tamari, Nir Ohfeld and Tomer Schwartz, with help from Calif and OpenAI. Fixed by the PHP team.

## Slide 10: Update PHP. Restart. Done.

- Fixed versions: **8.5.12 · 8.4.27 · 8.3.36 · 8.2.35**, released **21 Oct 2026**.
- After updating, **restart every PHP worker**.
- **Can't update today?** These stopgaps only cover part of the problem:
  - `session.upload_progress.enabled = 0`
  - `fatal_error_backtraces = 0` (PHP 8.5 only)
  - Restart every worker after changing them.
- Updating is the **only real fix**.

## Slide 11: In one sentence

> "PHP got kicked out mid-task, forgot to clean up, and the next visitor used the mess to take over the server."

- Outro: *Let's learn cybersecurity. Subscribe to sawlemon 🍋*
