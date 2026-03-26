"""
Central configuration for all sources, queries, and domain lists.
Edit this file to add or remove sources without touching ingestion logic.

Two fetch streams are defined:
  - General: broad AI news (tech, policy, research, enterprise, society)
  - Healthcare: healthcare-specific AI news (clinical, regulatory, research)
"""
from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# RSS feed sources
# Keys become the "bucket" label stored with each article.
# ---------------------------------------------------------------------------
FEEDS: Dict[str, List[str]] = {
    # AI lab announcements and model releases
    "ai_model_and_platform_updates": [
        "https://openai.com/news/rss.xml",
        "https://blog.google/technology/ai/rss/",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        "https://nvidianews.nvidia.com/releases.xml",
        "https://www.theregister.com/software/ai_ml/headlines.atom",
        "https://huggingface.co/blog/feed.xml",
        "https://bair.berkeley.edu/blog/feed",
    ],
    # Mainstream tech journalism
    "tech_news": [
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",  # The Verge AI
        "https://feeds.arstechnica.com/arstechnica/technology-lab",            # Ars Technica
        "https://feeds.bbci.co.uk/news/technology/rss.xml",                    # BBC Technology
        "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",         # ZDNet AI
        "https://spectrum.ieee.org/feeds/feed.rss",                            # IEEE Spectrum
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.technologyreview.com/feed/",
        "https://www.geekwire.com/feed/",
        "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml",
    ],
    # Healthcare AI and health policy
    "healthcare_ai_and_regulation": [
        "https://www.cms.gov/newsroom/rss-feeds",
        "https://www.statnews.com/feed/",
        "https://kffhealthnews.org/feed/",
        "https://www.fiercehealthcare.com/rss/xml",
        "https://www.healthcareitnews.com/home/feed",
    ],
    # Enterprise adoption and business impact
    "enterprise_adoption": [
        "https://www.cio.com/feed/",
    ],
    # Human-AI intersection: ethics, research, workforce, society
    # Covers how AI affects people, organisations, and public policy.
    "human_ai_intersection": [
        "https://montrealethics.ai/feed/",               # Montreal AI Ethics Institute
        "https://futureoflife.org/feed/",                # Future of Life Institute
        "https://www.pewresearch.org/internet/feed/",    # Pew Research: tech & society
        "https://ainowinstitute.org/feed",               # AI Now Institute
        "https://www.eff.org/rss/updates.xml",           # EFF: digital rights & AI policy
        "https://www.rand.org/pubs/research_reports.xml", # RAND research reports
    ],
}

# ---------------------------------------------------------------------------
# Google News RSS search queries (free, no API key)
# ---------------------------------------------------------------------------
GOOGLE_NEWS_QUERIES: List[str] = [
    # Model and platform news
    "OpenAI OR Anthropic OR Google DeepMind OR Meta AI",
    "LLM benchmark OR foundation model release",
    "AI chips OR semiconductor OR inference infrastructure",
    # Policy and governance
    "AI regulation OR AI policy OR AI governance",
    "AI safety OR AI alignment",
    # Enterprise and workflows
    "enterprise AI adoption",
    "generative AI workflow automation",
    # Human-AI intersection
    "AI ethics OR algorithmic bias OR AI fairness",
    "human AI collaboration OR human AI interaction",
    "AI workforce impact OR future of work AI",
    "AI mental health OR AI wellbeing OR AI and society",
    # Research institutions without RSS feeds
    "Stanford HAI OR MIT Media Lab AI research",
    "Brookings Institution AI OR Alan Turing Institute AI",
]

# ---------------------------------------------------------------------------
# Hacker News (Algolia search API – free, no auth)
# ---------------------------------------------------------------------------
HN_QUERIES: List[str] = [
    "large language model",
    "AI agent",
    "AI safety",
    "AI regulation",
    "GPT OR Claude OR Gemini OR Llama",
    "human AI interaction",
    "AI ethics",
]
HN_MAX_RESULTS: int = 15

# ---------------------------------------------------------------------------
# arXiv API queries (free, no auth)
# Covers both technical AI research and human-AI intersection papers.
# ---------------------------------------------------------------------------
ARXIV_QUERIES: List[str] = [
    "large language model",
    "AI safety alignment",
    "clinical AI medical",
    "AI agents reasoning",
    "human computer interaction AI",        # HCI + AI papers (cs.HC)
    "AI ethics fairness accountability",    # Responsible AI research
    "AI workforce automation labour",       # Economic and societal impact
]
ARXIV_MAX_RESULTS: int = 10

# ---------------------------------------------------------------------------
# Reddit RSS (read-only, no auth)
# ---------------------------------------------------------------------------
REDDIT_FEEDS: Dict[str, List[str]] = {
    "reddit_ai_research": [
        "https://www.reddit.com/r/MachineLearning/top/.rss?t=day",
        "https://www.reddit.com/r/LocalLLaMA/top/.rss?t=day",
    ],
    "reddit_enterprise_ai": [
        "https://www.reddit.com/r/artificial/top/.rss?t=day",
    ],
    "reddit_human_ai": [
        "https://www.reddit.com/r/AIethics/top/.rss?t=day",
        "https://www.reddit.com/r/Futurology/top/.rss?t=day",
    ],
}

# ---------------------------------------------------------------------------
# Known paywalled domains – articles flagged and deprioritised in ranking.
# Note: technologyreview.com and wired.com are metered but RSS summaries
# are accessible, so they are intentionally excluded from this list.
# ---------------------------------------------------------------------------
PAYWALLED_DOMAINS: Set[str] = {
    "wsj.com",
    "nytimes.com",
    "ft.com",
    "bloomberg.com",
    "economist.com",
    "hbr.org",
    "theatlantic.com",
    "newyorker.com",
    "businessinsider.com",
    "forbes.com",
    "fortune.com",
    "washingtonpost.com",
    "latimes.com",
    "nature.com",           # research papers behind paywall
    "science.org",          # research papers behind paywall
}

# ---------------------------------------------------------------------------
# Healthcare-specific fetch stream
# These supplement the general stream; articles are deduplicated by URL in the DB.
# ---------------------------------------------------------------------------

HEALTHCARE_FEEDS: Dict[str, List[str]] = {
    "healthcare_ai_and_regulation": [
        "https://www.cms.gov/newsroom/rss-feeds",
        "https://www.statnews.com/feed/",
        "https://kffhealthnews.org/feed/",
        "https://www.fiercehealthcare.com/rss/xml",
        "https://www.healthcareitnews.com/home/feed",
        "https://www.modernhealthcare.com/rss/news.rss",
        "https://www.healthaffairs.org/action/showFeed?type=etoc&feed=rss",
    ],
    "health_policy": [
        "https://www.commonwealthfund.org/publications/rss.xml",
        "https://www.healthsystemtracker.org/feed/",
    ],
}

HEALTHCARE_GOOGLE_NEWS_QUERIES: List[str] = [
    "AI healthcare OR AI hospital OR clinical AI",
    "FDA AI medical device OR AI diagnostics approval",
    "AI radiology OR AI pathology OR medical imaging AI",
    "EHR AI OR electronic health record artificial intelligence",
    "AI clinical decision support OR AI diagnosis treatment",
    "healthcare AI regulation OR health data privacy",
    "AI drug discovery OR AI genomics OR precision medicine",
    "AI nursing OR clinical workflow AI OR physician burnout AI",
    "hospital AI deployment OR health system AI adoption",
    "AI mental health therapy OR AI psychiatry",
]

HEALTHCARE_HN_QUERIES: List[str] = [
    "healthcare AI",
    "clinical AI",
    "medical AI",
    "health technology AI",
]

HEALTHCARE_ARXIV_QUERIES: List[str] = [
    "clinical AI medical imaging diagnosis",
    "large language model clinical notes EHR",
    "AI healthcare prediction treatment outcomes",
    "federated learning healthcare privacy",
    "AI mental health depression prediction",
    "drug discovery machine learning deep learning",
    "medical NLP clinical text extraction",
]

HEALTHCARE_REDDIT_FEEDS: Dict[str, List[str]] = {
    "reddit_healthcare_ai": [
        "https://www.reddit.com/r/healthIT/top/.rss?t=day",
        "https://www.reddit.com/r/medicine/top/.rss?t=day",
        "https://www.reddit.com/r/pharmacy/top/.rss?t=day",
    ],
}

# Bucket names that are intrinsically healthcare-focused (used to seed the
# healthcare newsletter's article pool alongside keyword matching).
HEALTHCARE_BUCKETS: Set[str] = {
    "healthcare_ai_and_regulation",
    "health_policy",
    "reddit_healthcare_ai",
}

# ---------------------------------------------------------------------------
# Source credibility scores (0–5 scale)
# Matched case-insensitively as substring of the article's source field.
# ---------------------------------------------------------------------------
SOURCE_CREDIBILITY: Dict[str, int] = {
    # Research institutions
    "arxiv": 5,
    "stanford": 5,
    "mit": 4,
    "turing": 4,
    "rand": 4,
    "brookings": 4,
    "pew research": 4,
    "ieee": 4,
    # AI labs
    "anthropic": 4,
    "openai": 4,
    "deepmind": 4,
    "google": 3,
    # Ethics and policy
    "montreal ai ethics": 4,
    "future of life": 3,
    "ai now": 4,
    "eff": 3,
    # Health
    "stat news": 3,
    "statnews": 3,
    "kff health news": 3,
    "health affairs": 4,
    "commonwealth fund": 4,
    "modern healthcare": 3,
    "health system tracker": 3,
    # Tech journalism
    "mit technology review": 3,
    "ars technica": 3,
    "bbc": 3,
    "techcrunch": 2,
    "venturebeat": 2,
    "the register": 2,
    "the verge": 2,
    "zdnet": 2,
    "hacker news": 2,
    "geekwire": 2,
    "fiercehealthcare": 2,
    "cms": 2,
    "cio": 1,
}
