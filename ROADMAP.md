# Roadmap — Week of 2026-07-20

Feature roadmap for the Forte voice/text banking assistant. Scope spans two repos:

- **`banking-assistant/`** — bot + orchestrator (10 of 11 tasks)
- **`speechkit/`** — Yandex STT/TTS service (task 1)
- **`forte-deploy/`** — AWS hosting (deploy target, end of week)

Legend: ⬜ not started · 🟡 partially built · ✅ done

---

## Foundation already in place (reuse, don't rebuild)

Grounding for the tasks below — these primitives already exist and every new
scenario should be built on top of them rather than reimplemented:

| Capability | Where | Notes |
|---|---|---|
| Intent classification (LLM, JSON-mode + regex fallback) | `orchestrator/services/llm.py` | Add intents by editing `SYSTEM_PROMPT` |
| Scenario catalogue (DB-driven, no code change to add) | `orchestrator/services/scenario.py`, `db/models.py` | `required_params`, `confirm_templates` (per-lang), `mib_endpoint` |
| Confirmation flow (Redis pending, clear-before-execute) | `orchestrator/services/confirm.py`, `routers/confirm.py` | Double-tap safe |
| Session store (24h TTL, merges `account_id`) | `orchestrator/services/session.py` | Reuse for multi-turn param collection |
| Per-language confirm templates (`ru-RU`/`kk-KZ`/`en-US`) | `db/seed.sql`, alembic `001` | Every new scenario needs all three |
| TTS spell-out for identifiers (account/bill/phone) | `orchestrator/services/speechtext.py` | `IDENTIFIER_PARAMS` frozenset |
| Per-language TTS voice mapping | `bot/config.py::voice_for_lang` | `kk→madi`, `ru→jane`, `en→jane` |
| MIB error → user-message mapping | `orchestrator/services/mib.py` | New endpoints get friendly errors for free |

---

## Tasks

### 1. Fix Kazakh TTS — pass the `madi` voice for `kk-KZ` ✅
**Goal:** Kazakh replies are spoken by the Kazakh voice `madi`, not the Russian default.

**Root cause found:** The bot chain was correct, but the **config** was wrong —
the live `.env` had `TTS_VOICE_KK=amira` and `.env.example` had a duplicated,
conflicting TTS block (`amira` then `madi`), with `TTS_VOICE_DEFAULT` being dead
config the bot never read. Separately, `speechkit`'s `YandexTTSEngine.synthesize`
accepted `lang` but **ignored it**, so nothing enforced a Kazakh voice for
Kazakh text.

**Done:**
- `banking-assistant/.env` + `.env.example`: `TTS_VOICE_KK=madi`,
  `TTS_VOICE_EN=jane` (was invalid `john`); removed the duplicate TTS block.
- `bot/config.py`: wired up `TTS_VOICE_DEFAULT` as the real fallback in
  `voice_for_lang()` (was dead config).
- `speechkit/app/engines/yandex/tts.py`: added `_resolve_voice()` — a
  language-aware safety net that substitutes the language's default voice
  (`kk → madi`) when the requested voice doesn't match `lang`, so a Russian
  voice can never read Kazakh text.
- `speechkit/tests/test_tts.py`: test asserting `jane + kk-KZ → madi`.

**Verified:** `voice_for_lang("kk-KZ") → madi`; speechkit TTS tests pass (5/5
with `API_KEY_ENABLED=false`).

**Acceptance:** A Kazakh confirmation is returned as a `madi`-voiced OGG note. ✅

---

### 2. Expand intents — add 10 new intents to the LLM system prompt ✅
**Goal:** The classifier recognises the new operations (tasks 5–11).

**Done (`orchestrator/services/llm.py`):** Added all 10 intents to
`SYSTEM_PROMPT` — `transfer_own`, `transfer_phone`, `deposit_open`,
`card_block`, `card_unblock`, `card_limit`, `statement_pdf`, `certificate`,
`navigation`, `manager` — with a "choosing between similar intents" guide, new
parameter rules (`from_account_kind`, `to_account_kind`, `phone`, `term`,
`card_last4`, `card_kind`, `limit_kind`, `limit_amount`, `period`, `cert_kind`),
and multilingual few-shot examples (ru/kk/en).

Also wired the collection side: per-language `slot_prompt`s for every new param
(`i18n.py`) and `card_last4` added to `speechtext.IDENTIFIER_PARAMS` (spelled
out for TTS).

**Acceptance:** guard test asserts all 10 intents are in the prompt; slot prompts
exist for every new param in all three languages. ✅

---

### 3. All scenarios in the DB — one migration for every new scenario ✅
**Goal:** New scenarios are seeded via a single Alembic revision.

**Done:** `002_add_scenarios.py` (down_revision `001`) inserts all 10 rows with
`required_params`, `optional_params`, per-language `confirm_templates`, and
`mib_endpoint` (`mib_method` defaults POST; endpoints hit the mock-mib catch-all
for now). Idempotent via `ON CONFLICT (intent) DO NOTHING`; `downgrade()` deletes
just the new intents. `db/seed.sql` kept in sync for fresh boots.

Validated offline: every `confirm_templates` literal is valid JSON with all
three languages, and every `{placeholder}` maps to a known param (no typos).

**Note:** `navigation`/`manager` currently route through the confirm flow as a
placeholder — task 11 converts them to direct informational replies.

**Acceptance:** `alembic upgrade head` seeds all scenarios; each resolves and
confirms per language. ✅ *(applied on deploy)*

---

### 4. Multi-step parameter collection — ask one field at a time ✅  *(core infra)*
**Goal:** When required params are missing, the bot asks for them one by one
instead of a single "missing: a, b, c" message.

**Done (orchestrator-only — no bot changes):**
- `services/slotfill.py`: Redis-backed in-progress collection
  (`{intent, params, missing, lang}`), separate key with a short `SLOTFILL_TTL`
  (300s) so a half-finished collection expires quickly.
- `llm.extract_param(text, intent, param, lang)`: focused single-slot extraction
  so bare answers ("12 months", "100000", "тенге") fill the asked slot.
- `i18n.slot_prompt(lang, param)`: per-language prompt per slot, with a generic
  fallback for params not yet listed.
- `routers/chat.py`: refactored around a shared `_advance()` that validates →
  asks the next missing slot (`action="collect"`) or confirms. Handles
  **cancel** ("no"/"отмена") and **context switch** (a new high-confidence
  intent mid-collection abandons the old one).
- New `ChatResponse.action="collect"`; the bot treats it like any reply (no
  change needed — voice replies naturally speak the prompt).

**Tests:** slot-fill continuation, ask-next-slot, cancel, context-switch, and
`extract_param` parsing. Full suite green (36 passed).

**Acceptance:** missing params now drive one-at-a-time collection → confirm. ✅
Unblocks tasks 5–11.

---

### 5. Transfer between own accounts ⬜
**Goal:** "Переведи с тенгового на долларовый 10000" resolves account names to
`account_id`s and confirms with human-readable account names.

**Do:** Intent `transfer_own` (params `from_account_kind`, `to_account_kind`,
`amount`). Resolve "тенговый/долларовый/…" → `account_id` via a MIB/mock account
lookup; confirm with names ("с Тенгового счёта на Долларовый"). Needs a
mock-mib accounts endpoint.

**Acceptance:** Kind words resolve to accounts; confirmation shows names, not IDs.

---

### 6. Transfer by phone number ⬜
**Goal:** Extract a phone number from speech, look up the contact, confirm with
the recipient's name.

**Do:** Intent `transfer_phone` (params `phone`, `amount`). Normalise spoken
digits → E.164; contact lookup (mock); confirm "Перевести 5000 ₸ — Айгуль
(+7 701 …)?". `phone` already spelled out for TTS via `speechtext`.

**Acceptance:** Spoken number → normalised → contact name in confirmation.

---

### 7. Open a deposit ⬜
**Goal:** Pick a deposit product by term + amount, show the rate in confirmation.

**Do:** Intent `deposit_open` (params `term`, `amount`). Product-selection over a
mock product catalogue; confirmation includes the resolved rate ("12 мес,
100000 ₸, ставка 14.5% — открыть?").

**Acceptance:** Term+amount select a product; rate shown before confirm.

---

### 8. Block / unblock a card ⬜
**Goal:** Resolve the card by last-4 or type, then confirm.

**Do:** Intents `card_block` / `card_unblock` (param `card_last4` or
`card_kind`). Card resolution over a mock cards endpoint; confirm "Заблокировать
карту •• 4321?".

**Acceptance:** last4/type resolves to one card; block and unblock both confirm.

---

### 9. Change card limit ⬜
**Goal:** Change daily/monthly limit, showing current → new.

**Do:** Intent `card_limit` (params `card_last4`, `limit_kind`
daily|monthly, `limit_amount`). Read current limit (mock), confirm "Суточный
лимit: 200000 → 500000 ₸?".

**Acceptance:** Confirmation shows both current and requested limit.

---

### 10. Statement & certificate — send a PDF in Telegram ⬜
**Goal:** Period statement + certificates, delivered as a PDF document.

**Do:** Intents `statement_pdf` (params `account_id`, `period`) and
`certificate` (param `cert_kind`). Generate/fetch a PDF (mock), and send it from
the bot via `answer_document(BufferedInputFile(...))` — new bot path alongside
the existing text/voice replies.

**Acceptance:** Bot delivers a PDF file, not just text.

---

### 11. Navigation & talk to a manager ⬜
**Goal:** Text answer with navigation + a manager card with a phone number.

**Do:** Intents `navigation` (branch/ATM/how-to answers) and `manager` (returns
a contact card). These are informational — reply directly, no MIB confirm step.
Manager card = name + phone (phone spelled out for TTS).

**Acceptance:** Navigation returns guidance; manager returns a contact card.

---

## Suggested sequencing

| Day | Focus |
|---|---|
| 1 | **Task 1** (TTS fix, quick) + **Task 2** (intents) — set up the vocabulary |
| 2 | **Task 4** (multi-step slot filling) — core infra that 5–11 depend on |
| 3 | **Task 3** (migration) + **Task 5** (transfer own) + **Task 6** (transfer phone) |
| 4 | **Task 7** (deposit) + **Task 8** (card block/unblock) |
| 5 | **Task 9** (card limit) + **Task 10** (statement/PDF) |
| 6 | **Task 11** (navigation/manager) + mock-mib endpoints round-out |
| 7 | End-to-end test pass, seed sync, deploy via `forte-deploy/` |

**Critical path:** Task 4 gates 5–11 (all multi-param). Task 2 + 3 travel
together (an intent without a scenario row 404s, a scenario without an intent is
never reached). Each new scenario needs a matching **mock-mib** endpoint and
per-language confirm templates.

---

## Cross-cutting checklist (per scenario)

- [ ] Intent + few-shot examples in `SYSTEM_PROMPT` (kk/ru/en)
- [ ] Scenario row in migration `002` **and** `db/seed.sql`
- [ ] `confirm_templates` for all three languages
- [ ] mock-mib endpoint returning a plausible payload
- [ ] Identifier params added to `speechtext.IDENTIFIER_PARAMS` if spoken
- [ ] Unit test in `tests/` (classify + confirm path)
