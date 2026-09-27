# Demo script: Northwind Triage (~6 minutes)

Two roles:
- **🎤 Speakers:** read the *SAY* lines; they're a guide, so make them yours.
- **🖱️ Driver:** does the *DO* steps. Stay one beat behind the speakers: click as they finish a sentence, not before.

---

## Before judges arrive (driver)

1. `.env` filled in (see `.env.example`), then run `python -m jobs.rebuild` (add `--import` if using Tiger Cloud).
2. Start the server: `python -m uvicorn api.main:app --port 8000` (or open the deployed URL).
3. Open the app in Chrome, full screen, zoom at 90%. Log in with the **analyst** demo account if login is on.
4. Press **Reset** (top right) so no leftover demo cases or simulated alerts remain. **Don't run `pytest` after this.**
5. Warm-up: click through each tab once so everything is cached, then return to **Operations** and scroll to the top.
6. Check the sound works (play any YouTube clip at low volume, then stop).
7. If a service isn't configured, the demo still works: the assistant uses its "Evidence lookup" mode and voice falls back to the browser's voice. Speakers skip the service name in that case.

---

## 1. The problem (45 s)

**DO:** Start on **Operations** at the top. Hover over the **SLA breach rate** tile's sparkline.

**SAY:**
> "Let's talk about Northwind. 

> Two years ago they closed complaints in about 9 days. Today it's **38**. 

> Their SLA breach rate has gone from 44% to **over 90%**, the regulator score has fallen from 4.3 to **2.6**, and they're now looking at **£2.4 million a quarter** in penalty exposure.

> Here's the good news: we dug into the data, one clear cause stood out, and we built something to fix it."

**DO:** Scroll down to **"Two years of degradation"** so the breach chart and the transfer panel are both visible.

---

## 2. The cause (45 s)

**DO:** Point the cursor at the orange bars in **The transfer penalty**, then at **Transfer rate by entry system**.

**SAY:**
> "Complaints that get bounced between systems take **15 days longer**, cost **£121 instead of £68**, and are **three times more likely to reopen**. 

> Of the slowest 1%, **every single one** was a transfer.

> And here's the part we love: whether a complaint gets transferred has nothing to do with what it's about. It depends only on **where it comes in**. 

> Outside the "case system" it's about 46%, whatever the category, channel or region.

> That makes it a routing problem, and routing problems are solvable."

---

## 3. The fix: route once, at intake (60 s)

**DO:** Click the **Intake** tab → click the prepared example **"Barrowdale estimated read"**.

**SAY:**
> "This is what an agent sees when a complaint arrives. 

> The router decides the owner **once, at intake**. The case is created in CaseTrack, and it goes straight to Billing Resolution."

**DO:** Point to the **Legacy vs Not transferred** table, then to the **Why** list.

**SAY:**
> "Next to it you can see how complaints like this one went historically when they bounced, versus when they didn't. **About five days faster and cheaper**. 

> And every number comes with a plain-English reason. No black box. Routing and prioritisation are explainable rules."

**DO:** Click **Replay** → press **▶ Play** (it runs for ~6 seconds).

**SAY (while it runs):**
> "Here we replay the last six months of real complaints through the router. 

> Even with conservative assumptions, 80% adoption and 60% of transfers avoided, that's around **£120k a year**, **35,000 complaint-days** and **almost 500 reopens** saved.

> Those two sliders are the assumptions, and we label them that way on screen."

---

## 4. The work: a queue that makes sense (75 s)

**DO:** Go back to **Intake**, scroll up and click **"See it in the queue →"** in the blue bar.

**SAY:**
> "The complaint we just routed lands straight in the triage queue, in its place, ranked by how urgent it really is.
> Fun fact: Northwind's own records say 98% of open cases are already breached. When we worked it out from the dates, the typical
> case is about a day over. So we calculate urgency from the dates themselves."

**DO:** Press **Esc** if a drawer is open. Scroll to the top of the table, then click the **#1 row**.

**SAY:**
> "Open any case and you get four answers straight away: **what happened, what happens next, who owns it and what's blocking
> it.** And 'Why is this case number one?' is spelled out in plain arithmetic."

**DO:** Scroll down to the **Customer update** card → click **▶ Play update**.

**SAY:**
> "Customers get updates too. This is spoken with **ElevenLabs**, from a template filled with the live case status. Nothing is
> invented: no made-up dates, no false 'resolved'."

**DO:** Click **I still need help** → wait a second → click **▶ Play update** again.

**SAY:**
> "If the customer says they still need help, the case escalates immediately, and their next update reflects that."

---

## 5. Early warning: connecting the dots (60 s)

**DO:** Click **Operations** → scroll to **Early warning** → click **Inject scenario**.

**SAY:**
> "Last piece: spotting problems before they become a flood. We feed in a clearly labelled **simulated** month. Imagine MeterHub
> pushes a bad batch of estimated readings. The same detector that watches the real data catches it right away…"

**DO:** Point to the top alert and the spike chart, then scroll down to the **Investigation brief** → click **Generate brief (Gemini)**.

**SAY:**
> "…it groups Barrowdale and Dunmoor together and names the two systems they share. With **Gemini**, it drafts a short brief. **what changed, possible explanations and what to check next**."

**DO:** Scroll to **Linked open complaints** and click the first one: it opens in the queue with the alert attached.

---

## 6. Ask Northwind + what's next (45 s)

**DO:** Click the blue **Ask Northwind** button → click the suggested question **"What should I do next with this case?"** (or type
*"Why are transfers the problem?"*). Click **🔊** on the answer.

**SAY:**
> "And anyone, whether a new agent, a manager or a judge, can just ask. Answers come only from the app's own numbers, with sources
> they can click."

**DO:** Close the assistant. Scroll **Operations** down to **Where the money is**.

**SAY:**
> "Two more wins sit in the same data. A quarter of complaints only need information, so
> auto-answering them is worth about **£100k a year**. 

> And smart meters: the numbers say don't buy them everywhere, buy them in **Barrowdale and Dunmoor**, where estimated reads are almost **3 times** as bad as the other regions. A full rollout of smart meters would be expensive - around 77 million - so we are proposing a staged rollout. the interactable figure here shows how the numbers can play out."

---

## 7. Close (15 s)

**SAY:**
> "So that's Northwind Triage: route once, work the right case first, and catch problems early. It's explainable, built on
> data Northwind already has, and it runs securely behind **Auth0**, hosted on **Vultr**. Thank you!"

**DO:** Leave the Operations dashboard on screen for questions.

---

## If something goes wrong (driver)
| Problem | Do this |
|---|---|
| A page is blank or slow | Refresh (F5). The dashboard takes ~3 s on its first load. |
| "Inject scenario" is greyed out | You're not logged in as the analyst account. |
| No sound from ElevenLabs | It falls back to the browser voice automatically. Keep going; the transcript is on screen. |
| Assistant says "Evidence lookup (AI off)" | Gemini isn't configured or hit its daily cap. Answers still work; skip the word "Gemini". |
| Leftover cases from a rehearsal | **Reset** (top right), then refresh. |

## Likely judge questions (speakers)
- **"Are the savings real?"** The transfer counts and costs are real Northwind data. The savings are a scenario: we show the assumptions on screen and you can move them.
- **"Why not machine learning?"** Transfers can't be predicted from what a complaint is about; they depend on where it enters. A clear routing rule beats a model here, and anyone can audit it.
- **"Isn't this another chatbot?"** No. Northwind's £640k chatbot pilot failed because it tried to hold conversations. Ours doesn't decide anything; it explains cited evidence.
- **"What happens without the sponsor services?"** Everything still runs on a fully open-source stack. The sponsor services add voice, AI explanations, managed storage, login and hosting on top.
