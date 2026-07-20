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

### 2. Expand intents — add 10 new intents to the LLM system prompt ⬜
**Goal:** The classifier recognises the new operations (tasks 5–11).

**Current state:** `SYSTEM_PROMPT` in `orchestrator/services/llm.py` lists only
`transfer, balance, payment, statement, unknown`.

**Do:** Add intents + few-shot examples (kk/ru/en each) for:
`transfer_own`, `transfer_phone`, `deposit_open`, `card_block`, `card_unblock`,
`card_limit`, `statement_pdf`, `certificate`, `navigation`, `manager`.
Document each param (e.g. `from_account`, `to_account_kind`, `phone`, `term`,
`card_last4`, `limit_kind`, `limit_amount`, `period`).

**Acceptance:** Sample utterances classify to the right intent with the right params.

---

### 3. All scenarios in the DB — one migration for every new scenario ⬜
**Goal:** New scenarios are seeded via a single Alembic revision.

**Current state:** Only `001_create_scenarios.py` (4 canonical scenarios). Live
lookups go through `scenario.get(intent)`.

**Do:** Add `002_add_scenarios.py` inserting rows for all new intents with
`required_params`, `optional_params`, per-language `confirm_templates`, and
`mib_endpoint`/`mib_method`. Keep `db/seed.sql` in sync for fresh boots.

**Acceptance:** `alembic upgrade head` on an empty DB yields all scenarios; each
resolves and confirms in the right language.

---

### 4. Multi-step parameter collection — ask one field at a time ⬜  *(core infra)*
**Goal:** When required params are missing, the bot asks for them one by one
instead of a single "missing: a, b, c" message.

**Current state:** `routers/chat.py` step 5 returns a flat `missing_params`
message and stops. Listed as an open TODO in `PROGRESS.md`.

**Do:** Introduce a "slot-filling" pending state in the session (Redis) holding
the intent + params gathered so far + the next slot to ask. On each turn, merge
the user's answer into the slot, re-validate, and either ask the next slot or
proceed to confirmation. Reuse `session.py`; keep it immutable (new dict per
update). Per-language prompt per slot.

**Acceptance:** "Открой депозит" → bot asks term → asks amount → confirms.
This unblocks tasks 5–11, which all have multiple params.

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
