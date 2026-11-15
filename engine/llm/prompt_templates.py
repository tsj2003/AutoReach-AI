"""Gojiberry AI 18 Built-in Multichannel Sequence Prompt Templates (F5e).

Extracted verbatim from Gojiberry's production Angular bundle (`main-O256LF4G.js`)
and documented in Book IV of `docs/GOJIBERRY_COMPLETE_REVERSE_ENGINEERING_SPEC.md`.
"""

from __future__ import annotations

from typing import Any, Dict, List

GOJIBERRY_PROMPT_TEMPLATES: List[Dict[str, Any]] = [
    # --- LinkedIn Prompt Templates (9) ---
    {
        "id": "signal-hook",
        "title": "Signal Hook",
        "channel": "linkedin",
        "description": "Reference the buying signal that triggered outreach",
        "prompt": (
            "Write a short LinkedIn message (under 300 characters) that directly references "
            "the intent signal that triggered this outreach (e.g. a post they liked, a job "
            "change, a funding round, or a hiring surge). Open with the signal as a natural "
            "conversation starter, briefly connect it to how we help similar teams, and end "
            "with a low-friction question — no hard pitch."
        ),
    },
    {
        "id": "pain-point",
        "title": "Pain Point",
        "channel": "linkedin",
        "description": "Lead with a challenge specific to their role",
        "prompt": (
            "Write a concise LinkedIn message addressing a key pain point typical for someone "
            "in the prospect's role and industry. Show empathy for the challenge, briefly "
            "mention how our solution eliminates that friction with a concrete outcome, and "
            "ask if this is something they're currently prioritizing."
        ),
    },
    {
        "id": "social-proof",
        "title": "Social Proof",
        "channel": "linkedin",
        "description": "Share a relevant result from a similar company",
        "prompt": (
            "Write a short LinkedIn message leading with a tangible result we achieved for a "
            "company similar to the prospect's (same industry or size). Keep it conversational, "
            "explain the one key lever that drove the result, and ask if they'd be open to "
            "hearing how it could apply to their team."
        ),
    },
    {
        "id": "question-opener",
        "title": "Question Opener",
        "channel": "linkedin",
        "description": "Start with a thought-provoking question",
        "prompt": (
            "Write an ultra-short LinkedIn message (2-3 sentences max) that opens with a sharp, "
            "thought-provoking question relevant to the prospect's current priorities and role. "
            "Tie the question lightly to the problem we solve without pitching features, and "
            "invite their perspective."
        ),
    },
    {
        "id": "compliment-bridge",
        "title": "Compliment & Bridge",
        "channel": "linkedin",
        "description": "Acknowledge their work and connect to your offer",
        "prompt": (
            "Write a warm, genuine LinkedIn message that starts by acknowledging something "
            "specific about the prospect's recent work, career trajectory, or company growth. "
            "Bridge naturally from that observation to the area we specialize in, and end "
            "with a casual open-ended question."
        ),
    },
    {
        "id": "gentle-followup",
        "title": "Gentle Follow-up",
        "channel": "linkedin",
        "description": "Soft bump that adds new value",
        "prompt": (
            "Write a brief, polite LinkedIn follow-up to the previous message. Do not say "
            "'just bumping this' or 'circling back'. Instead, add one fresh angle, insight, "
            "or micro-case-study relevant to their role, and make it easy for them to reply "
            "with a simple yes or no."
        ),
    },
    {
        "id": "value-drop",
        "title": "Value Drop",
        "channel": "linkedin",
        "description": "Share an insight or tip with no strings attached",
        "prompt": (
            "Write a value-first LinkedIn message that shares a concise, actionable insight "
            "or benchmark relevant to the prospect's role and industry — no sales pitch. "
            "Close by asking if they're seeing the same trend on their side."
        ),
    },
    {
        "id": "mutual-context",
        "title": "Mutual Context",
        "channel": "linkedin",
        "description": "Leverage shared industry, event, or community",
        "prompt": (
            "Write a friendly LinkedIn message that highlights shared context (same ecosystem, "
            "event, group, or industry trend). Keep the tone peer-to-peer, briefly mention "
            "what we're building for teams in this space, and ask if they'd be open to "
            "exchanging notes."
        ),
    },
    {
        "id": "breakup",
        "title": "Breakup Message",
        "channel": "linkedin",
        "description": "Polite final touch that leaves the door open",
        "prompt": (
            "Write a short, respectful final LinkedIn message acknowledging that timing might "
            "not be right. Leave the door open without guilt-tripping, summarize in one line "
            "when teams usually reach out to us, and wish them well."
        ),
    },
    # --- Cold Email Prompt Templates (9) ---
    {
        "id": "email-signal-hook",
        "title": "Signal Hook",
        "channel": "email",
        "description": "Open with the buying signal that triggered outreach",
        "prompt": (
            "Write a concise cold email (under 90 words) that opens by referencing the specific "
            "buying signal detected for this prospect or company. Connect that signal directly "
            "to the problem we solve, include one concrete proof point, and end with an "
            "interest-based CTA (e.g., 'Worth exploring?'). Also generate a short 2-4 word "
            "lowercase subject line."
        ),
    },
    {
        "id": "email-pain-agitate-solve",
        "title": "Pain → Agitate → Solve",
        "channel": "email",
        "description": "Classic PAS framework tailored to their role",
        "prompt": (
            "Write a punchy cold email (under 100 words) using the Pain-Agitate-Solve framework "
            "tailored to the prospect's job title and company profile. State the pain clearly "
            "in sentence one, highlight the cost of the status quo in sentence two, show how "
            "we solve it with a specific metric in sentence three, and close with a soft CTA."
        ),
    },
    {
        "id": "email-case-study",
        "title": "Case Study",
        "channel": "email",
        "description": "Lead with a concrete customer result",
        "prompt": (
            "Write a cold email centered on a mini case study relevant to the prospect's "
            "industry. Structure: 1) Why you're reaching out, 2) How a peer company used our "
            "solution to achieve a specific measurable result, 3) A low-friction question "
            "asking if they'd like to see the playbook."
        ),
    },
    {
        "id": "email-one-liner",
        "title": "Ultra-Short One-Liner",
        "channel": "email",
        "description": "3-sentence email designed for mobile replies",
        "prompt": (
            "Write an ultra-short 3-sentence cold email (under 50 words total) optimized for "
            "mobile reading. Sentence 1: personalized observation or signal. Sentence 2: "
            "one-sentence value proposition with a concrete outcome. Sentence 3: simple "
            "interest question."
        ),
    },
    {
        "id": "email-trigger-event",
        "title": "Trigger Event",
        "channel": "email",
        "description": "Tie outreach to company news, hiring, or funding",
        "prompt": (
            "Write a timely cold email anchored to a company trigger event (hiring, funding, "
            "new leadership, or tech stack change). Explain why teams going through this exact "
            "transition typically hit a bottleneck, how we help them move faster, and ask if "
            "this is on their radar."
        ),
    },
    {
        "id": "email-followup-bump",
        "title": "Value Follow-up",
        "channel": "email",
        "description": "Follow up on the previous email with a new angle",
        "prompt": (
            "Write a short follow-up email (under 65 words) to a previous cold email. Bring a "
            "fresh angle or address a common objection prospects in their role have, rather "
            "than just asking if they saw the last note. End with a simple one-line question."
        ),
    },
    {
        "id": "email-competitor-angle",
        "title": "Status Quo Contrast",
        "channel": "email",
        "description": "Contrast modern workflow against legacy manual approach",
        "prompt": (
            "Write a sharp cold email contrasting how most teams in the prospect's industry "
            "currently handle the problem (slow, manual, or fragmented) versus how top-performing "
            "teams automate or streamline it with us. Keep it under 85 words with a low-friction CTA."
        ),
    },
    {
        "id": "email-referral-ask",
        "title": "Right Person Check",
        "channel": "email",
        "description": "Polite check if they own this initiative",
        "prompt": (
            "Write a concise, respectful email asking if the prospect is the right person to "
            "speak with regarding the problem we solve, or if there's someone else on their "
            "team leading that initiative. Briefly state in one sentence why it's relevant "
            "to their company right now."
        ),
    },
    {
        "id": "email-breakup",
        "title": "Breakup Email",
        "channel": "email",
        "description": "Polite closing email that often triggers replies",
        "prompt": (
            "Write a short, zero-pressure breakup email (under 55 words) letting the prospect "
            "know this is your last note for now. Mention the one core outcome we help teams "
            "like theirs achieve in case priorities shift later, and wish them a great quarter."
        ),
    },
]


def get_gojiberry_prompt_templates(channel: str | None = None) -> List[Dict[str, Any]]:
    if not channel:
        return [dict(item) for item in GOJIBERRY_PROMPT_TEMPLATES]
    norm = channel.strip().lower()
    return [dict(item) for item in GOJIBERRY_PROMPT_TEMPLATES if item["channel"] == norm]


list_prompt_templates = get_gojiberry_prompt_templates
