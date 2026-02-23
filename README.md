# Ultimate GSC Audit AI Agent

A comprehensive Streamlit web app that performs **56 advanced Google Search Console audit tasks** across 9 categories, powered by AI-driven analysis via OpenRouter.

## What It Does

Connects to any Google Search Console property via OAuth, runs a full-spectrum audit of your organic search performance, and generates a prioritized content optimization plan with downloadable Markdown + HTML reports.

### 9 Audit Categories (56 Tasks)

| # | Category | Tasks | Focus |
|---|----------|-------|-------|
| 1 | **Foundational Audit** | 1-6 | CTR optimization, dead pages, dying content, cannibalization, quick wins, branded keywords |
| 2 | **Query Intelligence** | 7-16 | Long-tail gaps, zero-click queries, intent drift, question mining, seasonality, spam detection |
| 3 | **Page-Level Deep Analysis** | 17-26 | Impression funnels, consolidation candidates, parameterized URLs, pre-crash detection |
| 4 | **CTR & Position Curve** | 27-31 | Site-specific CTR modeling, title tag A/B prioritization, mobile/desktop gaps, country anomalies |
| 5 | **Search Appearance & SERP Features** | 32-37 | Rich result coverage, sitelinks, video gaps, AI Overview displacement, featured snippets |
| 6 | **Device & Country Segmentation** | 38-42 | Geographic demand gaps, hreflang validation, mobile position deltas, tablet assessment |
| 7 | **Indexing & Coverage Diagnostics** | 43-47 | Index bloat ratio, crawled-not-indexed patterns, sitemap reconciliation, canonical overrides |
| 8 | **Core Web Vitals & Experience** | 48-51 | CWV regression detection, INP bottlenecks, mobile/desktop CWV disparity |
| 9 | **Trend & Strategic Analysis** | 52-56 | Algorithm update impact, YoY demand shifts, content freshness decay, topic impression share |

## Key Features

- **Smart Data Fetching** — 16 unique data shapes fetched once and shared across all 56 tasks (no redundant API calls)
- **Flexible Scope** — Run all 56 tasks, select by group, or pick individual tasks
- **AI-Powered Analysis** — Gemini Flash for group-level narratives, Claude Sonnet for executive summary and content plan (~$0.15-0.50 per audit)
- **Health Scoring** — 0-100 score with A-F grades based on finding severity
- **Dual Reports** — Downloadable Markdown + professionally styled HTML
- **Streamlit Cloud Ready** — OAuth flow, secrets management, ephemeral-storage compatible

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Credentials

Copy the secrets template and fill in your credentials:

```bash
cp secrets_template.toml .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
[google]
client_id = "your-google-client-id.apps.googleusercontent.com"
client_secret = "your-google-client-secret"
redirect_uri = "http://localhost:8501"

[openrouter]
api_key = "your-openrouter-api-key"

[pagespeed]
api_key = ""  # Optional - works without key at lower rate limits
```

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select existing)
3. Enable the **Google Search Console API**
4. Create OAuth 2.0 credentials (Web application)
5. Add `http://localhost:8501` as an authorized redirect URI
6. Copy the Client ID and Client Secret to your secrets file

### 3. Run the App

```bash
streamlit run app.py
```

## Streamlit Cloud Deployment

1. Push this repo to GitHub
2. Connect the repo on [Streamlit Cloud](https://share.streamlit.io/)
3. Add your secrets via the app settings dashboard
4. Update `redirect_uri` in secrets to match your deployed URL (e.g., `https://your-app.streamlit.app`)
5. Update the redirect URI in Google Cloud Console to match

## Project Structure

```
GSC Auditor/
├── app.py                     # Main Streamlit entry point
├── core/                      # Data infrastructure
│   ├── gsc_client.py          # OAuth 2.0 + GSC API wrapper
│   ├── data_fetcher.py        # Smart data fetching orchestrator
│   ├── data_store.py          # Session-state DataFrame cache
│   └── pagespeed_client.py    # PageSpeed Insights API client
├── auditors/                  # 56 audit tasks (9 groups)
│   ├── base_auditor.py        # Abstract base class
│   ├── foundational.py        # Group 1: Tasks 1-6
│   ├── query_intelligence.py  # Group 2: Tasks 7-16
│   ├── page_analysis.py       # Group 3: Tasks 17-26
│   ├── ctr_position.py        # Group 4: Tasks 27-31
│   ├── search_appearance.py   # Group 5: Tasks 32-37
│   ├── device_country.py      # Group 6: Tasks 38-42
│   ├── indexing_coverage.py   # Group 7: Tasks 43-47
│   ├── core_web_vitals.py     # Group 8: Tasks 48-51
│   └── trend_strategic.py     # Group 9: Tasks 52-56
├── ai/                        # AI analysis layer
│   ├── openrouter_client.py   # OpenRouter API client
│   ├── prompt_builder.py      # Finding serialization + prompt assembly
│   └── analysis_engine.py     # Group analysis + executive summary orchestration
├── models/                    # Data models
│   ├── audit_finding.py       # AuditFinding, Severity, task/group mappings
│   ├── audit_result.py        # AuditResult with health scoring
│   └── gsc_data.py            # Data shape definitions + task-to-shape mapping
├── reports/
│   └── report_generator.py    # Markdown + HTML report generation
└── utils/                     # Helpers
    ├── date_utils.py          # Date range calculations
    ├── url_utils.py           # URL parsing and normalization
    └── formatting.py          # Number and display formatting
```

## How It Works

1. **Authenticate** — Sign in with Google OAuth to access your Search Console data
2. **Select Property** — Choose which GSC property to audit
3. **Configure Scope** — Pick all 56 tasks, specific groups, or individual tasks
4. **Run Audit** — The app fetches data, runs analysis, and generates AI insights
5. **Review Results** — Interactive dashboard with severity scoring, data tables, and charts
6. **Export** — Download Markdown and HTML reports

## API Costs

| Component | Model | Cost per Audit |
|-----------|-------|----------------|
| Group Analysis (x9) | Gemini 2.0 Flash | ~$0.09-0.27 |
| Executive Summary (x1) | Claude Sonnet | ~$0.05-0.15 |
| **Total** | | **~$0.15-0.50** |

AI analysis is optional and can be toggled off in the sidebar.

## Requirements

- Python 3.10+
- Google Cloud project with Search Console API enabled
- OpenRouter API key (for AI analysis)
- PageSpeed Insights API key (optional, for Core Web Vitals tasks)
