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

Once accepted, the document records **which channel it arrived on** — its
Source column reads `Email` or `Telegram`, not the `AI · Text` a typed note
gets. The channel is taken from the stored message, not from the draft the
review screen sends back, so correcting a draft cannot relabel where it came
from. The five values are `Form` (typed into a form), `AI · Text` (Smart Input
text), `AI · Photo` (Smart Input upload), `Email` and `Telegram`.

### How anyone finds out

Collection is automatic and always has been: a background thread sweeps every
configured channel every `INBOUND_POLL_SECONDS` (30), on its own clock and its
own thread so a mail server nobody can reach cannot stall the event worker. In
celery mode the same work is a beat task instead.

What was missing was the telling. The sidebar now polls `GET
/api/inbox/pending-count` — one indexed `COUNT`, `data:read` — every 20 seconds
from whatever page is open, and puts the number on the **Inbox** entry and in
the browser tab title, so an order finds the shopkeeper rather than waiting to
be found. The count refreshes immediately when a backgrounded tab comes
forward, since browsers throttle timers in tabs nobody is looking at. The Inbox
page itself refreshes every 15 seconds while open, pausing whenever a message
is open for review so the list cannot move under a click.

**Check now** stays, but it is no longer how you learn something arrived — it
only skips the wait for the next sweep.

### When two people have the Inbox open

An order belongs to the **business**, not to whoever was signed in when it
arrived. The collector routes by the inbox token or the linked chat, so owner
and employee see the same queued message, and either may accept it.

Whoever clicks first wins. The row is read `FOR UPDATE`, so a second accept
waits for the first to commit, then finds the message already `accepted` and
gets `409 — This message has already been dealt with.` The order is recorded
once, by one of them, and `handledBy`/`handledAt` say which. Neither page
refreshes itself, so the loser sees the 409 rather than the button vanishing;
reloading shows the accepted row.

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

Mailpit is a sink with no compose screen - its web UI reads mail, it does not
write it - so there is a command for this:

```powershell
.venv\Scripts\python -m app.cli send-test-order "Please send 12 bags rice to Anita Stores"
```

### What a message can be

An inbound message runs through the same engine as Smart Input, so **all three
document types work by email**, not just orders. The wording decides which:

| Send this | Becomes | Why |
|---|---|---|
| `Please send 12 bags rice to Anita Stores` | **sale** | the default reading of an order |
| `sold 5 kg rice to Anita Stores` | **sale** | an explicit sale verb |
| `bought 10 Cooking Oil from ABC Suppliers` | **purchase** | "bought ... from" |
| `received 20 bags cement from Sunrise Wholesale` | **purchase** | goods coming in |
| `paid electricity bill 3200` | **expense** | no party, a cost |
| `rent 8000` | **expense** | category and amount only |
| `20 tea packets, 40 rice bags and 10 sugar packets from Sunrise Wholesale` | purchase, **3 lines** | a message can list several items |

Three things sharpen it beyond the verb:

* **A known party's own type wins.** If the name resolves to someone filed as a
  supplier, the draft becomes a purchase even when the wording was ambiguous.
* **A message can list several items.** Line breaks, commas and "and" all work,
  and the split is on quantities rather than on the word "and" - so
  `2 kg salt and pepper` stays one item while `5 rice 2 sugar` becomes two.
* **Stock moves the right way.** A purchase adds to inventory, a sale removes
  from it. This was wrong once - every accepted message defaulted to a sale, so
  an emailed purchase took stock *out* - and `test_an_emailed_purchase_is_recorded_as_a_purchase`
  exists to keep it fixed.

Any language works for any of them:

```powershell
.venv\Scripts\python -m app.cli send-test-order "ಅನಿತಾಗೆ ೬ ಕಿಲೋ ಅಕ್ಕಿ ಬೇಕು"
.venv\Scripts\python -m app.cli send-test-order "अनीता को 5 किलो चावल चाहिए"
.venv\Scripts\python -m app.cli send-test-order "ABC Suppliers se 4 litre tel kharida"
```

**What email cannot do:** record a payment against an existing invoice, or edit
anything already recorded. Every message becomes a new draft somebody approves.

Useful flags: `--from "Ravi <ravi@example.com>"`, `--subject`, `--business` (to
pick a different shop by name).

Any real mail client works too - point it at SMTP `localhost:1025`, no
authentication, and send to the address from step 2.

**4. Watch it arrive.**

* <http://localhost:8025> shows the raw mail immediately.
* Within `INBOUND_POLL_SECONDS` (30) a count appears on **Inbox** in the sidebar
  and in the browser tab title, from whatever page you happen to be on. **Check
  now** forces the sweep this second instead of waiting for the next one.
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

> **A bot for this project already exists.** If you are testing SmartSME rather
> than deploying your own, ask for the existing `TELEGRAM_BOT_TOKEN`, skip step
> 1, and carry on from step 2. Telegram allows **one poller per bot**, so only
> one machine should be running with that token at a time — a second one logs a
> `409 Conflict` and receives nothing.

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

**5. Send an order.** Anything that chat sends afterwards becomes a draft -
text, or **a photograph of a handwritten slip**:

```
5 kg rice for Anita Stores
ಅನಿತಾಗೆ ೬ ಕಿಲೋ ಅಕ್ಕಿ ಬೇಕು
20 tea packets, 40 rice bags and 10 sugar packets    ← several items, one message
```

A photo goes through the same engines as a Smart Input upload: the vision model
first, OCR.space as the fallback. Sending it as a **file** rather than a photo
keeps the original bytes and reads better - Telegram recompresses anything sent
with the camera button, and handwriting is what that compression eats. A caption
is read as well, so a picture with "for Anita Stores" written under it gets the
customer from the caption.

`backend/tests/fixtures/` has 31 slips to try. `13.png`-`31.png` match the demo
catalogue, so every line resolves to a real product; `1.jpg`-`12.jpg` are
messier, and three of them have an item crossed out.

It reaches the Inbox within 30 seconds, or straight away with **Check now**.

**Notes.**

* A message from an unlinked chat gets a short reply explaining how to link,
  and is otherwise ignored - a stranger cannot put anything in your books.
* Stickers, and anything with neither text nor a picture, are skipped.
* Polling is outbound only (`getUpdates`), so this works from a laptop behind
  NAT with nothing exposed to the internet.

### One bot, several people

A single bot serves any number of businesses: each chat is bound to one by its
own `/link <token>`, so your teammates do not each need their own bot **as long
as they are all talking to one running copy of SmartSME**.

What does not work is two laptops each running their own copy against the same
bot token. Telegram allows exactly one poller per bot; a second one does not
share the stream, it competes for it, and each side receives a random half of
the messages. The app now says so explicitly in the log rather than leaving you
to wonder why some orders vanish.

So pick one:

| If | Do this |
|---|---|
| Only one laptop runs at a time (demos) | Share the one bot token. Nothing else needed. |
| Several people run their own copy at once | One bot each - @BotFather takes two minutes and they are free |
| You want one shared shop | Deploy the backend once; then there is one poller, one database, and everybody signs in to it |

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

