"""
AI-powered summarization: one API call generates both the newsletter Key Takeaway
and a sharp "Why it matters" for each individual article.

Uses Claude Sonnet for quality. Cost per daily run: ~$0.003.
Falls back to heuristics if ANTHROPIC_API_KEY is missing or the call fails.
"""
import json
import os
import re
from typing import Any, Dict, List

MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Heuristic fallbacks (used when API is unavailable)
# ---------------------------------------------------------------------------

def _heuristic_why_it_matters(article: Dict[str, Any]) -> str:
    """Extract the most impact-laden sentence from the article summary."""
    text = (article.get("summary") or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    impact_re = re.compile(
        r"\b(because|means?|results?|affects?|impacts?|could|will|risk|"
        r"allows?|enables?|forces?|first|major|significant|change[s]?)\b",
        re.IGNORECASE,
    )
    best = max(sentences, key=lambda s: len(impact_re.findall(s)), default="")
    snippet = (best or sentences[0])[:220]
    return snippet if snippet.endswith((".", "!", "?")) else snippet + "."


def _heuristic_takeaway(stories: List[Dict[str, Any]]) -> str:
    snippets = [_heuristic_why_it_matters(s) for s in stories if s.get("summary")]
    if not snippets:
        return "Today's AI news spans people, processes, and technology — see the stories below."
    return " ".join(snippets[:2])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def enrich_stories(
    stories: List[Dict[str, Any]],
    newsletter_type: str = "general",
) -> Dict[str, Any]:
    """
    Make a single API call that returns:
      - "takeaway": concise synthesis of all stories
      - "summaries": list of {index, why_it_matters} for each story

    newsletter_type="general"    – framed for tech/business decision-makers
    newsletter_type="healthcare" – framed for CMIOs, health IT leaders, clinicians

    Mutates each story dict in-place, setting story["_why_it_matters_ai"].
    Returns {"takeaway": str, "stories": updated list}.

    Falls back gracefully to heuristics on any failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [summarize] ANTHROPIC_API_KEY not set – using heuristic summaries.")
        return _apply_heuristics(stories)

    # Build story context for the prompt
    story_blocks = []
    for i, s in enumerate(stories, 1):
        cat = s.get("_category") or s.get("category_candidate") or "Tech"
        title = s.get("title", "")
        raw = (s.get("summary") or "")[:600]
        pub = s.get("published_at", "")
        story_blocks.append(
            f"Story {i} [{cat}]{' (published: ' + pub[:16] + ')' if pub else ''}\n"
            f"Headline: {title}\nBackground: {raw}"
        )

    stories_text = "\n\n".join(story_blocks)

    # Build dynamic summaries template for however many stories we have
    summaries_template = ",\n    ".join(
        f'{{"index": {i}, "why_it_matters": "<one direct sentence: what changed and its consequence>"}}'
        for i in range(1, len(stories) + 1)
    )

    prompt = f"""\
You are a senior AI industry analyst writing for C-suite executives and technology leaders.

Today's top AI news stories (most recent first):

{stories_text}

Return a JSON object with exactly this structure (no markdown, no explanation, raw JSON only):
{{
  "takeaway": "<1-2 sentences that name the single biggest theme connecting these stories — especially if multiple recent articles point to the same shift. Be specific: name the companies, technologies, or decisions involved. No filler, no buzzwords, no 'In summary'.>",
  "summaries": [
    {summaries_template}
  ]
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_json = message.content[0].text.strip()

        # Strip any accidental markdown fences
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json, flags=re.MULTILINE).strip()
        data = json.loads(raw_json)

        takeaway = data.get("takeaway", "").strip()

        # Map AI summaries back onto story dicts by index
        summary_map = {item["index"]: item["why_it_matters"] for item in data.get("summaries", [])}
        for i, story in enumerate(stories, 1):
            story["_why_it_matters_ai"] = summary_map.get(i, _heuristic_why_it_matters(story))

        print(f"  [summarize] AI summaries generated via {MODEL}.")
        return {"takeaway": takeaway, "stories": stories}

    except Exception as exc:
        print(f"  [summarize] API call failed ({exc}) – using heuristic summaries.")
        return _apply_heuristics(stories)


def _apply_heuristics(stories: List[Dict[str, Any]]) -> Dict[str, Any]:
    for story in stories:
        story["_why_it_matters_ai"] = _heuristic_why_it_matters(story)
    return {"takeaway": _heuristic_takeaway(stories), "stories": stories}
