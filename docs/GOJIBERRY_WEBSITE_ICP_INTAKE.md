# Gojiberry website → ICP → signals intake

Evidence from shipped client JS under `/tmp/rea-gojiberry/app-chunks/` (`chunk-G5VJFVLN.js`, `chunk-IKMU54LD.js`) and `docs/GOJIBERRY_COMPLETE_REVERSE_ENGINEERING_SPEC.md`. Server-side scrape/LLM weights are **not** in the public JS.

Attainly matches the **observed API contract, field semantics, thin-site handling, and signal wiring**. It does not copy private model weights. Labels below: **Observation** (in the JS) vs **Inference** (Attainly design) vs **Unknown**.

## 1. Exact request/response JSON shapes

**Observation — landing is not an API call.** `Input_button_wesite_URL.CqN95wHh.mjs` only normalizes the typed URL and redirects:

`https://app.gojiberry.ai/registration?onboarding_website=<encodeURIComponent(url)>`

Login/registration then does `localStorage.setItem("onboarding_website", queryParam)` and onboarding pre-fills the website field + `onWebsiteBlur` → `analyzeWebsite`.

**Observation — service methods (`chunk-G5VJFVLN.js`) send URL only:**

| Call | Request body | Response fields the client reads |
|---|---|---|
| `POST …/generate-website-analysis-v2` | `{ websiteUrl }` | `companyName`, `industry`, `description`, `keyFeatures[]`, `socialProof[]`, `pains`; settings UI also reads `companySize` |
| `POST …/generate-icp-from-website` | `{ websiteUrl }` | `job_titles`, `industries`, `company_sizes`, `countries`, `company_types`, `competitors`, `search_keywords` |
| `POST …/generate-website-description` | `{ websiteUrl }` | older onboarding: `description`, `companyName`, `industry`, `pains` |
| `POST …/generate-target-job-titles` | `{ companyName, industry, description, keyFeatures, socialProof, painPoints }` | `jobTitles`, `adjacentJobTitles`, `industries`, `locations`, `companyTypes`, `companySizes`, `excludedCompanies` |
| `POST …/generate-engagement-keywords-v2` | confirmed ICP + `campaignGoal` / `campaignTone` / `channelStrategy` | `{ selected: string[], suggested: string[] }` |

**Observation — empty stays empty.** Onboarding maps those arrays as returned. On generate-target-job-titles **error**, arrays are cleared (`mainJobTitles=[]`, `selectedJobTitles=new Set`), not replaced with Head of Sales / VP Revenue. Max 10 job titles, max 10 keywords, max 15 `AgentVariableV2Dto` rows.

**Inference — Attainly one-shot.** `POST /api/onboarding/analyze-website` `{ url, product_blurb? }` returns both snake_case and the observed Gojiberry names (`job_titles`, `search_keywords`, `companyName`, `ignoredCompanies`, `event_signal_defaults`, `multichannel_sequence`).

## 2. Does the client ever send page HTML?

**Observation: no.** Every generate-* website call is `{ websiteUrl }` (a string). HTML is never in the POST body. The server (unobserved) scrapes.

**Inference:** Attainly crawls homepage + `/about` + `/pricing` + `/manifest.json` + `/login`, optionally Firecrawl markdown, then prompts an LLM with that evidence blob.

## 3. How `job_titles` get populated when the marketing site has no titles

**Observation:** `generate-icp-from-website` returns `job_titles` and the client assigns `icpData.targetJobTitles = e.job_titles`. There is **no** client-side fill of a SaaS exec pack. The later `generate-target-job-titles` call (after the operator confirms pitch + pains) is a second LLM that *may* invent titles from the confirmed company description — still mapped as returned, cleared on error.

**Unknown:** the server prompt that turns a URL into `job_titles` (not in public JS; no live authenticated capture of those POST responses in `/tmp/rea-gojiberry`).

**Inference (Attainly):** infer buyer *role types* from product-category language when exact titles are absent:

- `"built for shop owners"` / `"software for independent shops"` → Shop Owner / Independent Shop Owner
- `"for sales teams"` → Sales Manager (not VP Revenue)
- you / consumers / shoppers / businesses / teams with no department → `[]`
- Head of Sales / VP Revenue / CRO / Head of Growth / GTM Engineer only if those words are on the page

This is **not** a fixed SaaS exec list and **not** the old category packs (invoices → Shop Owner + funding, HR+hospital → Hospital HR Manager).

## 4. `search_keywords` → `SEARCH_KEYWORD` variables

**Observation:** `this.keywords = e.search_keywords.map(t => ({ text: \`"\${t}"\`, trackType: "all" }))`. `formatAgentVariables` emits `{ type: "SEARCH_KEYWORD", value: _.text }` with the quotes already in `text`. Max 10 keywords. `generate-engagement-keywords-v2` only adds more LinkedIn phrases (`selected` / `suggested`), not funding/hiring types.

**Inference:** Attainly `signals_from_search_keywords` wraps each phrase in double quotes and sets `type: "SEARCH_KEYWORD"`. Event checkboxes are separate UI defaults.

## 5. Sequence defaults vs ICP

**Observation — LinkedIn-only default (older onboarding + new onboarding when channel ≠ multichannel):**

```
invitation (delay 2) → AI message (delay 1) → follow_up_1 (delay 2) → follow_up_2 (delay 3)
```

**Observation — multichannel default (`selectedChannelStrategy === "multichannel"`):**

```
invitation + likePostsBeforeInvitation (delay 2)
→ AI message (delay 3) → AI email (delay 2) → visitProfile
→ AI message (delay 1) → AI email (delay 3) → AI message (delay 2)
```

ICP does not change the step types. `generateAiCampaign` only fills follow-up copy. F5e (18 prompt shortcuts in `chunk-IKMU54LD.js`) is a template palette, not the sequence.

**Inference:** Attainly ships a compact 5-step warmup equivalent of `likePostsBeforeInvitation` + invite + DM + email:

1. visitProfile (Day 0)
2. likePosts (Day 1)
3. invitationNote (Day 1)
4. message (Day 3)
5. email (Day 4)

Funding/hiring are **off**. Activity + recent job-change UI defaults are **on**. Sequence is not derived from the website.

## 6. Thin / Cloudflare / login handling

**Observation:** `analyzeWebsite` treats a falsy `generate-website-analysis-v2` result as:

> “We could not generate the website description. You can try again or fill it in yourself. This usually happens when the website is protected by an anti-bot filter like Cloudflare.”

Then it still opens the empty company-description form. Error path does the same (`showCompanyDescription = true`). No Head of Sales fill.

**Unknown:** exact JSON the API returns for Cloudflare/thin pages (client only checks falsy vs object).

**Inference:** Attainly `status: "low_evidence"`, empty `job_titles` / keywords / signals, same Cloudflare/login note, optional product-blurb retry.

## 7. Competitor list usage

**Observation:** `excludeCompetitors = e.competitors`, then the operator’s own `companyName` is appended, then that array is sent as **`ignoredCompanies`** on `POST /v1/agent`. They are **not** turned into `COMPETITOR_PAGE_URL` unless the operator later adds LinkedIn company URLs. Agent-drawer generate-icp merges competitors into `ignoredCompanies` with case-insensitive dedupe.

**Inference:** Attainly returns `competitors` / `ignoredCompanies` / `ignored_companies` as the exclude list. Wizard shows them as excluded companies.

## Event-signal UI defaults (`signalOptions` / `Ob()`)

**Observation, not website-derived:**

| UI id | AgentVariableV2Dto.type | Default |
|---|---|---|
| `top-5-active` | `RECENT_ACTIVITY` | on |
| `recent-job-changes` | `RECENTLY_CHANGED_JOB` | on |
| `recent-funding` | `RECENT_FUNDING_EVENT` | **off** |
| `companies-hiring` | `HIRING` | **off** |

`LOOKALIKE` / `WEBSITE_VISITOR` are `agentType`, not `variables[]`.

## What the operator should see

These are **Attainly** outcomes for representative public-page *types*. They are not live captures of Gojiberry’s private `generate-icp-from-website` responses.

| URL type | Gojiberry client (observed) | Attainly (this change) |
|---|---|---|
| **gojiberry.ai** (B2B product: “helps your sales team…”) | Redirect → after auth, `{ websiteUrl }` → arrays as returned | `product_type: b2b_product`. Role type from “sales teams” (e.g. Sales Manager), **not** VP Revenue. Keywords from outbound/ICP/LinkedIn language. Funding/hiring off. 5-step sequence. |
| **amazon.in** (consumer marketplace) | Same URL-only POST; client shows whatever arrays come back, or empty form if falsy | `product_type: consumer_marketplace`. Pitch/keywords from the page. **`job_titles: []`**. Note that this is not a B2B buyer page. No VP Revenue, no “we help consumers shop” as an invented outbound ICP. |
| **Barkat-style app login** | Falsy analysis → Cloudflare/login alert + empty form | `product_type: app_login`, `status: low_evidence`, empty titles/keywords/signals, Cloudflare/login note + blurb retry. |
| **Normal B2B product** (e.g. “GST invoicing for independent shops”) | URL-only POST; titles only if the model returns them | `product_type: b2b_product`. Role types from “for shops” / “shop owners”. Keywords from invoicing/GST/retail copy. JSON-LD industry if present. Sequence + event defaults unchanged. |

## Unknown (still)

- Server scrape stack and prompts behind `generate-icp-from-website` / `generate-website-analysis-v2`
- Exact thin-site JSON (falsy vs `{}` vs error)
- Whether `generate-engagement-keywords-v2` ever emits non-keyword signal types (client only reads string arrays)
