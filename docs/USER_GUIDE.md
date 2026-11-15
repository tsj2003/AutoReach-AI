# Attainlly — Complete User Guide

Everything you need to understand what Attainlly is and how to use every feature
in the app. No prior knowledge assumed.

---

## 1. What is Attainlly?

Attainlly is a **cold-email outreach platform**. You use it to send personalized
emails to people who have not heard from you yet (prospects), book meetings from
the ones who are interested, and do it all without wrecking your email
reputation.

The hard part of cold email is not writing the email — it is **deliverability**:
making sure your messages land in the inbox instead of spam, and that sending a
lot of email does not get your domain blacklisted. Attainlly is built around
protecting that reputation while it does the outreach for you.

### What makes it different

- **AI reads and acts on replies.** Every reply is automatically read and sorted
  into one of seven categories (Interested, Objection, Out-of-Office, Referral,
  Not-interested, Do-not-contact, Auto-reply). Interested replies get a draft
  response with your booking link; out-of-office replies reschedule the
  follow-up to the person's return date.
- **Dynamic ESP matching.** When you send to a Gmail address, Attainlly routes
  the email through one of your connected Gmail accounts; Outlook to Outlook.
  Email providers trust messages inside their own network more, so more of your
  mail reaches the primary inbox.
- **Automatic mailbox rotation.** It warms up new mailboxes gradually and watches
  their health. If one starts bouncing or hitting spam, it is paused and a
  healthy spare takes over — so one bad mailbox never sinks the whole campaign.
- **Handles forwarded replies.** If a prospect forwards your email to a colleague
  who replies from a different address, that reply lands in an "Others" folder
  where you can attach it back to the original lead.
- **Built for scale.** Lead lists of 100,000+ stay fast because of cursor-based
  pagination.

### The core vocabulary

| Term | What it means |
|------|---------------|
| **Campaign** | One outreach effort: an offer, a target audience (ICP), and the leads you contact. |
| **Lead / Contact / Prospect** | A person you are reaching out to. |
| **Mailbox** | A connected email account (Gmail/Outlook) used to send from. |
| **ICP** | "Ideal Customer Profile" — a description of who you want to reach. |
| **Sequence** | The ordered series of emails (first touch + follow-ups). |
| **Unibox** | The unified inbox where all replies show up. |
| **HITL** | "Human-in-the-Loop" — you approve AI actions before they happen. |
| **Tick / Drain** | Manual buttons that tell the engine to do its next unit of work. |

---

## 2. Getting in: trial, signup, and login

### Sign up
1. Go to the landing page and click **Start free trial** (or **Start free** in
   the top nav).
2. Fill in company name, your name, email, and a password (min 8 characters).
   You can click **Show** to reveal the password as you type.
3. Or click **Continue with Google** to sign up with one click.

Every new account starts on a **7-day Pro trial** — full features, no credit
card required. A banner at the top of the dashboard shows how many days are left.

### Log in
- Go to **/login**, enter email + password, click **Sign in**.
- Or use **Continue with Google**.
- **Demo account:** on the login page, click **✨ Use demo account** to auto-fill
  a pre-loaded demo (campaigns, leads, and replies already populated) so you can
  explore without setting anything up.

### What happens when the trial ends
If you do not pick a paid plan within 7 days, your account drops to **Free**
limits automatically (1 campaign, 1 mailbox, 500 leads). Nothing is deleted — you
just can't exceed free limits until you upgrade.

---

## 3. The dashboard (home page)

The first screen after login. It gives you a portfolio-level view:

- **Stat cards** across the top: total Campaigns, Active campaigns, Booked
  meetings, Qualified leads, Revenue, Cost, and Margin.
- **Campaigns table** below: each campaign with its status, qualified count, and
  revenue. Click any campaign name to open it.

If you have no campaigns yet, the **onboarding wizard** pops up automatically (see
next section).

---

## 4. First-run onboarding wizard

The first time you land on an empty dashboard, a wizard appears: **"What do you
want to achieve?"**

1. **Pick a goal** — Book sales meetings, Fill my pipeline, Reach candidates, or
   Run client campaigns. Each pre-fills sensible starting settings.
2. **Tune your campaign** — the offer text and target audience (ICP) are
   pre-written for your goal; edit anything that doesn't fit.
3. Click **Create my campaign** and you land on a real, ready campaign.

You can click **Skip for now** at any point to explore an empty dashboard
instead. The wizard won't nag you again once dismissed.

---

## 5. Campaigns

This is where most of your work happens. Open **Campaigns** from the sidebar.

### Create a campaign
1. Click **+ New campaign**.
2. Fill the form:
   - **Customer name** — a label for the campaign (e.g. "SaaS Founders Q3").
   - **Offer** — what you're pitching, in a sentence or two.
   - **ICP description** — who you're targeting.
   - **Booking URL** — your Cal.com (or similar) link, e.g. `https://cal.com/you`.
     Used in interested-reply drafts so prospects can book directly.
   - **Meeting target** — how many meetings/month you're aiming for.
   - **Price/meeting (cents)** — used to calculate revenue and margin. `50000` =
     $500.00.
   - **HITL threshold** — controls how cautious the AI is about acting on its own
     (see HITL below).
   - **Enable Gemini personalization** — turns on AI-written, per-lead email
     personalization (a paid-plan feature).
3. Click **Create**.

### Campaign list
Each row shows the campaign name (click to open), a status pill, qualified count,
and revenue.

---

## 6. Inside a campaign (campaign detail)

Click a campaign to open its control room.

### Header
- The campaign name and a **status pill** (active, paused, cancelled…).
- **Contacts (N)** button → the leads list.
- **Inbox (N)** button → the Unibox for this campaign (N = pending replies).

### Stat cards
Booked, Qualified, Revenue, Cost, and Margin for this campaign.

### Offer card + engine controls
Shows the offer and ICP, plus three action buttons that drive the engine
manually:

- **Tick** — runs one engine cycle: picks up due work (send the next email,
  process a reply, advance a sequence step) and does a single pass.
- **Drain** — runs several cycles in a row until the immediate queue is empty.
  Use this to push a batch of work through at once.
- **Poll replies** — checks the connected mailbox for new replies right now and
  pulls them into the Unibox. (Requires a connected Gmail mailbox.)

> In production the engine also runs on a schedule in the background. These
> buttons are for when you want to make something happen immediately.

### HITL approval queue
"Human-in-the-Loop" means the AI drafts an action but waits for your approval
before it sends. When the AI wants to send something it isn't fully confident
about, it lands here.

- Each row shows the recipient and subject.
- **Approve** sends it. **Reject** discards it.
- The **HITL threshold** you set on the campaign controls how often this happens:
  a higher threshold = the AI asks for approval more often (more cautious); a
  lower threshold = the AI acts on its own more (more autonomous).

### Recent events
A live feed of what the engine has done (emails sent, replies classified,
meetings booked, etc.) with timestamps.

---

## 7. Contacts (leads)

From a campaign, click **Contacts**.

### Upload leads
1. In the **Upload CSV** card, choose a `.csv` file.
2. **Required column:** `email`. **Optional columns:** `name`, `company`,
   `title`.
3. After upload you'll see a summary: how many were loaded, how many were skipped
   for invalid emails, duplicates, or already-existing leads.

### Leads table
Shows email, name, company, and a **status pill** for each lead (new, contacted,
replied, qualified, booked, unsubscribed, etc.).

### Big lists
If you uploaded thousands of leads, only the first 50 load. Click **Load more** to
page through. This uses cursor pagination, so it stays fast even at 100,000+
leads.

---

## 8. Unibox (the inbox)

From a campaign, click **Inbox**. This is where every reply shows up, split into
two folders.

### Primary folder
Replies from people who match a known lead. Each reply card shows:

- A **classification pill** — the AI's category (Interested, Objection, OOO,
  Referral, Not-interested, Do-not-contact, Auto).
- A **status pill** (pending, sent, discarded…).
- The sender's email/company and a preview of the message.
- A **suggested reply** drafted by the AI (e.g. for "Interested", a reply with
  your booking link).

For pending replies you get three buttons:
- **Mark sent** — approve/send the suggested reply.
- **Regenerate** — ask the AI for a fresh draft.
- **Discard** — drop it.

### Others folder (orphaned replies)
This is the clever part. When someone replies from an address that doesn't match
any lead — a forward to a colleague, a personal email, a different domain — it
can't be matched automatically, so it lands here.

Each Others card has:
- **Attach lead** — opens a search box. Find the original lead by email, name, or
  company and click it to link this reply to that lead. Once attached, the
  engine folds the reply into that lead's sequence (and stops follow-ups if the
  person responded).
- **Ignore** — dismiss it if it's not relevant.

This means a prospect forwarding your email to the actual decision-maker never
falls through the cracks.

---

## 9. Billing & plans

Open **Billing** from the sidebar.

### What you see
- Your **current plan** and a usage summary (campaigns used vs. limit, leads used
  vs. limit).
- Plan cards you can upgrade to.

### Plans

| Plan | Price | Campaigns | Mailboxes | Leads |
|------|-------|-----------|-----------|-------|
| **Free** | ₹0 | 1 | 1 | 500 |
| **Starter** | ₹2,900/mo | 5 | 3 | 5,000 |
| **Pro** | ₹7,900/mo | 25 | 15 | 50,000 |

(Your 7-day trial gives you Pro-level access from day one.)

### How to upgrade (Razorpay)
1. Click **Upgrade to Starter** or **Upgrade to Pro**.
2. The Razorpay payment window opens. Pay with a card, UPI, netbanking, etc.
3. On success, your plan upgrades instantly and the trial banner disappears.

Payment is secure: the server verifies the payment signature with Razorpay and
re-checks the order before changing your plan — the price and plan can't be
tampered with from the browser.

> **Test mode:** if the app is running with Razorpay test keys, use card
> `4111 1111 1111 1111`, any future expiry, any CVV, and OTP `1111`. No real
> money moves.

---

## 10. A typical end-to-end workflow

Here's how it all fits together:

1. **Sign up** → land on the dashboard (7-day Pro trial).
2. **Create a campaign** (via the onboarding wizard or the Campaigns page): set
   your offer, ICP, and booking URL.
3. **Upload leads** in the campaign's Contacts page (CSV with an `email` column).
4. **Connect a mailbox** (Gmail/Outlook) so the engine can send. *(Mailbox
   connection is handled via the connect flow; on the free/dev setup, sending
   uses a console adapter that simulates sends.)*
5. **Let the engine run** — click **Tick**/**Drain** to send immediately, or let
   the background schedule do it. Leads move from *new* → *contacted*.
6. **Replies arrive** in the Unibox. The AI categorizes each one and drafts
   responses. Interested replies get a booking link; OOO reschedules itself.
7. **Approve actions** in the HITL queue when the AI asks.
8. **Attach orphaned replies** (forwards/colleagues) to their original lead in the
   Others folder.
9. **Watch results** on the dashboard and campaign stat cards: booked meetings,
   qualified leads, revenue, and margin.
10. **Upgrade** before the trial ends to keep Pro limits.

---

## 11. Reading the status pills

Pills are color-coded throughout the app:

- **Green** — good/positive: active, qualified, replied, sent, interested,
  booked, warming.
- **Amber** — needs attention/neutral: paused, pending, objection, out-of-office,
  contacted.
- **Red** — negative/stopped: cancelled, unsubscribed, failed, do-not-contact,
  not-interested, revoked.
- **Lavender** — referral.
- **Grey** — new / auto-reply.

---

## 12. Tips & FAQ

**I logged in but the dashboard is empty.**
You're on a fresh account. Use the onboarding wizard to create a starter
campaign, or click **✨ Use demo account** on the login page to explore
pre-loaded data.

**Where do I see replies?**
Open a campaign → **Inbox**. Tracked replies are in **Primary**; forwards and
unknown senders are in **Others**.

**A prospect replied but I don't see it under their name.**
They probably replied from a different address. Check the **Others** folder and
use **Attach lead** to link it.

**Why are some replies waiting for my approval?**
That's HITL. The AI wasn't confident enough to act alone. Approve or reject in the
campaign's **HITL approval queue**. Lower the campaign's HITL threshold if you
want the AI to act more on its own.

**Nothing is sending.**
Make sure a mailbox is connected, the campaign has leads, and either click
**Tick/Drain** or wait for the background scheduler.

**How do I cancel?**
Plans are month-to-month; you can stop anytime. Downgrading reverts you to the
free limits.

---

*This guide covers the customer-facing app. For deployment and engineering
details, see `docs/DEPLOYMENT.md` and the project `README.md`.*
