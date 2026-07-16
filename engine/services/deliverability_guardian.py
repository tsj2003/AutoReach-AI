"""Deliverability Guardian — pre-send spam + AI-fingerprint risk scoring.

Why this exists (the 2026 wedge)
--------------------------------
Filters now penalize the *statistical fingerprint* of AI-generated text: AI
emails are spam-flagged ~8% vs ~3% for human-written, and that gap is WIDENING.
Meanwhile Google/Yahoo/Microsoft moved to outright rejection above a 0.3% spam
rate. So the dangerous thing in 2026 isn't "write an email" — it's "send an
AI-shaped, spam-triggering email and burn the domain."

The Guardian scores every draft BEFORE a human approves it and returns concrete
fixes. It turns AI's deliverability penalty into a control: high-risk drafts are
flagged (and force human approval even past the trust-ramp). It's the missing
gate between "AI wrote it" and "we sent it."

Design
------
Deterministic + explainable by default (no API key, fully testable): spam-trigger
lexicon, AI-tell / cliché phrases, link/caps/exclamation density, length, and a
grounding check (does the copy reference the cited signal, or is it generic?).
An optional `llm_critic` callable can add a model's judgment ("does this read
generated? what would a human change?") — provider-agnostic, so it can be wired
to OpenAI or Gemini without touching this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

# Classic spam-trigger words (subset of the 2026 lists) — presence raises risk.
_SPAM_WORDS = (
    "free", "guarantee", "guaranteed", "act now", "limited time", "click here",
    "risk-free", "100%", "winner", "congratulations", "cash", "offer expires",
    "buy now", "order now", "cheap", "discount", "earn money", "make money",
    "no obligation", "special promotion", "urgent", "wire transfer", "$$$",
    "credit card", "increase sales", "double your", "extra income",
)

# AI-fingerprint / cliché tells — the phrases filters and humans both flag as
# "generated / templated". The personalizer already forbids some of these; the
# Guardian is the backstop that catches them regardless of who wrote the draft.
_AI_TELLS = (
    "i hope this email finds you well",
    "i hope this finds you well",
    "i hope you're doing well",
    "i wanted to reach out",
    "i am reaching out",
    "in today's fast-paced",
    "in today's competitive",
    "i came across your",
    "circle back", "touch base", "synergy", "synergies",
    "leverage", "cutting-edge", "cutting edge", "revolutionary",
    "game-changer", "game changer", "seamless", "unlock the power",
    "take your business to the next level", "boost your", "supercharge",
)

_LINK_RE = re.compile(r"https?://", re.IGNORECASE)
_ALLCAPS_RE = re.compile(r"\b[A-Z]{3,}\b")
_WORD_RE = re.compile(r"\b\w+\b")
_SENTENCE_SPLIT = re.compile(r"[.!?]+")


@dataclass(frozen=True)
class RiskIssue:
    code: str
    severity: str  # "low" | "medium" | "high"
    detail: str
    fix: str
    weight: int = 0  # score penalty; 0 → derive from severity

    def as_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "detail": self.detail, "fix": self.fix}


@dataclass(frozen=True)
class DraftRiskReport:
    score: int                      # 0-100, higher = safer / more inbox-likely
    level: str                      # "green" | "warn" | "block"
    ai_fingerprint: int             # 0-100, higher = reads more AI-generated
    issues: tuple[RiskIssue, ...] = ()

    @property
    def is_send_safe(self) -> bool:
        return self.level != "block"

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "level": self.level,
            "ai_fingerprint": self.ai_fingerprint,
            "issues": [i.as_dict() for i in self.issues],
        }


_SEVERITY_PENALTY = {"low": 4, "medium": 9, "high": 16}


class DeliverabilityGuardian:
    def __init__(
        self,
        *,
        block_below: int = 55,
        warn_below: int = 78,
        llm_critic: Optional[Callable[[str, str], Sequence[RiskIssue]]] = None,
    ) -> None:
        self.block_below = block_below
        self.warn_below = warn_below
        self._llm_critic = llm_critic

    def score(
        self,
        *,
        subject: str,
        body: str,
        grounded_evidence: Optional[Sequence[str]] = None,
    ) -> DraftRiskReport:
        subject = subject or ""
        body = body or ""
        low_all = f"{subject}\n{body}".lower()
        issues: list[RiskIssue] = []

        # 1. Spam-trigger lexicon.
        hits = sorted({w for w in _SPAM_WORDS if w in low_all})
        if hits:
            issues.append(RiskIssue(
                "spam_words", "high" if len(hits) > 2 else "medium",
                f"Spam-trigger phrase(s): {', '.join(hits[:5])}",
                "Remove or rephrase these — they push spam-filter scores up fast.",
                weight=min(45, len(hits) * 10),
            ))

        # 2. AI-fingerprint / cliché tells.
        tells = sorted({t for t in _AI_TELLS if t in low_all})
        ai_fingerprint = min(100, len(tells) * 22)
        if tells:
            issues.append(RiskIssue(
                "ai_tells", "high" if len(tells) > 1 else "medium",
                f"AI/templated tell(s): {', '.join(tells[:4])}",
                "Rewrite in plain, specific language — filters penalize the generated fingerprint.",
                weight=min(40, len(tells) * 12),
            ))

        # 3. Link density.
        links = len(_LINK_RE.findall(body))
        if links > 2:
            issues.append(RiskIssue(
                "link_density", "high", f"{links} links in the body.",
                "Keep to at most 1 link in a cold email; more looks promotional.",
                weight=18,
            ))

        # 4. Shouting: ALL-CAPS words and exclamation marks.
        caps = len(_ALLCAPS_RE.findall(f"{subject} {body}"))
        excls = (subject + body).count("!")
        if caps >= 2 or excls >= 2:
            issues.append(RiskIssue(
                "shouting", "medium", f"{caps} ALL-CAPS token(s), {excls} exclamation mark(s).",
                "Drop the caps/exclamations — they read promotional and trip filters.",
                weight=14,
            ))

        # 5. Length — 2026 data favors short, human cold emails.
        word_count = len(_WORD_RE.findall(body))
        if word_count > 150:
            issues.append(RiskIssue(
                "too_long", "low", f"Body is {word_count} words.",
                "Cut to ~50-120 words; short, direct emails reply and deliver better.",
            ))

        # 6. Subject hygiene.
        if len(subject) > 60:
            issues.append(RiskIssue(
                "subject_long", "low", f"Subject is {len(subject)} chars.",
                "Keep subjects under ~50 chars, sentence case, specific.",
            ))

        # 7. Grounding: when we have cited signals, the copy should reference the
        #    trigger — generic copy is both lower-reply and more spam-prone.
        if grounded_evidence:
            grounded = any(str(ev).lower() in low_all for ev in grounded_evidence if ev)
            if not grounded:
                ai_fingerprint = min(100, ai_fingerprint + 20)
                issues.append(RiskIssue(
                    "ungrounded", "medium",
                    "Copy doesn't reference the buying signal that triggered it.",
                    "Ground the opener in the actual trigger (funding, hiring, etc.), not a generic hook.",
                ))

        # 8. Uniform sentence length is an AI fingerprint (low burstiness).
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(body) if s.strip()]
        if len(sentences) >= 3:
            lengths = [len(_WORD_RE.findall(s)) for s in sentences]
            mean = sum(lengths) / len(lengths)
            var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
            if mean > 0 and var < 4.0:  # very uniform → generated cadence
                ai_fingerprint = min(100, ai_fingerprint + 15)
                issues.append(RiskIssue(
                    "uniform_cadence", "low",
                    "Sentences are near-uniform length (an AI-writing fingerprint).",
                    "Vary sentence length — mix a short punchy line with a longer one.",
                ))

        # Optional model critique (provider-agnostic; adds, never overrides).
        if self._llm_critic is not None:
            try:
                for extra in self._llm_critic(subject, body) or ():
                    issues.append(extra)
            except Exception:
                pass  # never let the critic break scoring

        penalty = sum(i.weight if i.weight else _SEVERITY_PENALTY.get(i.severity, 4) for i in issues)
        score = max(0, 100 - penalty)
        level = "block" if score < self.block_below else "warn" if score < self.warn_below else "green"
        return DraftRiskReport(score=score, level=level, ai_fingerprint=ai_fingerprint, issues=tuple(issues))
