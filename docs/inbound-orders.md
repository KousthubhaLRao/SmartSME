# Inbound orders: email and Telegram

Letting customers send orders in, with step-by-step walkthroughs for both channels.

[&larr; Back to the README](../README.md)

---

## Inbound orders (email and Telegram)

Smart Input is the window inside the app. The same engine also reads orders that
arrive from outside, so a customer can email or message an order and it reaches
the same confirm screen.

**Nothing external ever writes to the books.** An inbound message becomes a
*draft* in a review queue on the Inbox page; a signed-in user with `txn:write`
accepts it, and only then is a sale recorded. Accepting is the only path that
writes, and the draft is editable first, because the parser is a suggestion.

Reading the queue needs `data:read`, so an admin can see what arrived. Deciding
what becomes of a message - accepting, dismissing, or fetching more - needs
`txn:write`, which an admin does not hold: dismissing a customer's order is a
decision about a business's data, not part of configuring it. Deleting from the
queue needs `data:manage`, like any other destruction.

### Email, step by step

Mailpit is a complete mail server that throws everything away - an SMTP inbox,
a POP3 server and a web UI in one container. `docker compose up -d` starts it,
so there is nothing to sign up for and no real mail can escape.

| | |
|---|---|
| SMTP (things send *to* this) | `localhost:1025` |
| POP3 (SmartSME reads *from* this) | `localhost:1110` |
| Web UI (you watch it here) | <http://localhost:8025> |

**1. Start with email collection on.**

```powershell
.\run-dev.ps1 -WithEmail
```

Without `-WithEmail` everything else still works, mail just sits in Mailpit
uncollected. (The flag sets `EMAIL_INGEST_ENABLED=true` for that run; putting it
in `backend/.env` makes it permanent.)

**2. Find the address orders go to.**

```powershell
cd backend
.venv\Scripts\python -m app.cli inbox-token
```

```
Kirana Fresh Traders
  token     e4190b5fd90456b7
  email     orders+e4190b5fd90456b7@smartsme.local
  telegram  /link e4190b5fd90456b7
```

The same address is on the Inbox page under **Set up channels**. The token is
what routes the mail to your shop, so treat it like a private link.

**3. Send an order.**

Mailpit is a sink with no compose screen, so there is a command for this:

```powershell
.venv\Scripts\python -m app.cli send-test-order "Please send 12 bags rice to Anita Stores"
```

It takes any language:

```powershell
.venv\Scripts\python -m app.cli send-test-order "ಅನಿತಾಗೆ ೬ ಕಿಲೋ ಅಕ್ಕಿ ಬೇಕು"
.venv\Scripts\python -m app.cli send-test-order "अनीता को 5 किलो चावल चाहिए"
```

Useful flags: `--from "Ravi <ravi@example.com>"`, `--subject`, `--business` (to
pick a different shop by name).

Any real mail client works too - point it at SMTP `localhost:1025`, no
authentication, and send to the address from step 2.

**4. Watch it arrive.**

* <http://localhost:8025> shows the raw mail immediately.
* Open the **Inbox** page in SmartSME and press **Check now** - or wait up to
  `INBOUND_POLL_SECONDS` (30) for the automatic sweep.
* The order appears as a draft: parsed, with the customer and products already
  matched against your catalogue. **Review** lets you correct anything, and only
  then does accepting write a sale.

**Nothing showed up?**

| Symptom | Cause |
|---|---|
| Mail is in Mailpit, Inbox is empty | started without `-WithEmail` |
| "Check now" gives 403 | you are signed in as an admin; it needs `txn:write` |
| Nothing in Mailpit either | container is down - `docker compose up -d mailpit` |
| Draft says "Could not read" | the parser found nothing; the message is still queued for a person |

**A real mailbox instead.** Set `EMAIL_PROTOCOL=imap` and the host, port, user
and password of a real account, plus `INBOX_DOMAIN` to its domain. Collected
mail is marked read rather than deleted, so the mailbox owner keeps their copy.

### Telegram, step by step

Telegram is the one mainstream messenger with a genuinely free, instantly
self-issued API key - no card, no business verification, no approval queue.
WhatsApp Business needs Meta approval and a verified number; Signal has no
official API.

**1. Make a bot.** In the Telegram app (phone or desktop):

1. search for **@BotFather** and open the chat
2. send `/newbot`
3. give it a display name (anything, e.g. `Kirana Orders`)
4. give it a username ending in `bot` (e.g. `kirana_orders_bot`) - it must be
   unique across Telegram, so expect to try twice
5. BotFather replies with a token like `8123456789:AAEabc...`

**2. Give SmartSME the token.** In `backend/.env`:

```
TELEGRAM_BOT_TOKEN="8123456789:AAEabc..."
```

Then restart (`Ctrl+C` in the API window, `.\run-dev.ps1` again).

**3. Check it works.**

```powershell
cd backend
.venv\Scripts\python -m app.cli check-telegram
```

```
Bot is live: @kirana_orders_bot (Kirana Orders)
  open       https://t.me/kirana_orders_bot
  then send  /link e4190b5fd90456b7
```

It tells you exactly what is wrong if the token is missing, malformed or
revoked, rather than failing silently in a log.

**4. Link the chat.** Telegram has no way of knowing which shop a chat belongs
to, so open the bot (the `https://t.me/...` link above), press **Start**, and
send the `/link <token>` line. The bot confirms:

> Linked to Kirana Fresh Traders. Send an order as a normal message and it will
> appear in the SmartSME inbox for review.

You only do this once per chat.

**5. Send an order.** Anything that chat sends afterwards becomes a draft:

```
5 kg rice for Anita Stores
ಅನಿತಾಗೆ ೬ ಕಿಲೋ ಅಕ್ಕಿ ಬೇಕು
```

It reaches the Inbox within 30 seconds, or straight away with **Check now**.

**Notes.**

* A message from an unlinked chat gets a short reply explaining how to link,
  and is otherwise ignored - a stranger cannot put anything in your books.
* Photos, stickers and other non-text updates are skipped (OCR of a photographed
  bill is not wired up yet).
* Polling is outbound only (`getUpdates`), so this works from a laptop behind
  NAT with nothing exposed to the internet.

### Deduplication and scheduling

The `(business, channel, external_id)` unique constraint means a re-delivered
email or a repeated Telegram update can never be ingested twice - which matters
because the dedup key is the *message*, not the chat: two orders from one
customer are two drafts, not one. It is scoped to the business because the id
belongs to the channel rather than to us: a supplier mailing the same order to
two shops sends one `Message-ID`, and both shops need to see it.

Telegram is acknowledged by offset, advanced once per update after it has been
dealt with - late enough that a failed insert is retried rather than lost, early
enough that an update nothing can read (a photo, a sticker) does not pin the
offset and get re-read every thirty seconds for a day.

The sweep runs every `INBOUND_POLL_SECONDS` (30 by default): on its own thread in
inline mode, and as a Celery beat task in celery mode. Its own thread because it
is the slow, unreliable one - it talks to a mail server and then to an AI
provider - and a mailbox nobody can reach must not stop sales from updating
stock. `POST /api/inbox/collect` triggers it by hand, which is what the **Check
now** button does.

---

