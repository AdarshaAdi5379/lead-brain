# Local Lead Finder — Website Opportunity Scanner

Find local businesses that need a website (re)build — and get a ready-to-use prospect list.

Web freelancers and small agencies waste hours hunting for businesses with outdated or broken
sites. This Actor does the hunting for you: it crawls local business websites, audits them
(SEO, technology, contact info), and **scores how likely each business is to pay for a new
website** — then returns a ranked list with phone, email, the biggest opportunity, and a pitch
angle for each lead.

The output is a decision, not a raw dump: *"Here are the 20 local plumbers in Austin most likely
to buy a website redesign, why, and how to reach them."*

## Who it's for
- Freelance web developers prospecting for clients
- Small web design / SEO agencies building outreach lists
- Anyone selling websites, redesigns, or local SEO to small businesses

## How it works
1. **Discover** businesses by `category` + `location` (OpenStreetMap, free), or pass your own `urls`.
2. **Crawl** the homepage plus top internal pages (contact / about / services).
3. **Audit** each site deterministically — no LLM, no paid APIs:
   - SEO health (titles, meta, headings, thin content, alt text)
   - Technology fingerprint (CMS, framework, hosting, analytics)
   - Contact extraction (phone, email, address, socials, opening hours, maps)
4. **Score** each lead 0–100 with a transparent, weighted model and a priority band.
5. **Rank & push** leads with the top opportunity, recommended services, and a pitch angle.

## Input
- `urls` — a list of business websites (skips discovery), **or**
- `category` + `location` — e.g. `plumber` + `Austin, TX`
- `maxResults`, `maxPagesPerSite`, `minScore`, `includeNoWebsite`, `requireContact`

## Output (dataset item, abridged)
```json
{
  "business_name": "Acme Plumbing",
  "website_url": "https://acmeplumbing.example",
  "has_website": true,
  "phone": "+1-512-555-0100",
  "email": "hello@acmeplumbing.example",
  "has_contact": true,
  "contact_methods": ["phone", "email"],
  "city": "Austin",
  "state": "TX",
  "platform": "wordpress",
  "seo_score": 41,
  "seo_health": "Poor",
  "top_seo_issues": [{ "code": "missing_meta_description", "severity": "major", "reason": "..." }],
  "visual_score": 52,
  "visual_health": "Fair",
  "visual_summary": "Weak mobile layout and low contrast detected",
  "visual_issues": ["weak_mobile", "weak_cta"],
  "lead_score": 82,
  "priority": "Hot",
  "top_opportunity": "Website Redesign",
  "recommended_services": ["Responsive redesign", "Local SEO"],
  "pitch_angle": "Outdated, slow, non-mobile site — pitch a responsive rebuild.",
  "top_positive_reasons": ["No mobile viewport", "Thin content"]
}
```
A `SUMMARY` key-value record reports how many businesses were scanned and qualified.

## Pricing
Pay per result — you pay only for the leads you get. Every run returns ranked, contactable
prospects, so a single qualified lead typically pays for many runs.

## AI Agents & MCP Integration

You can integrate this Actor directly into your AI workflows (Claude Desktop, Cursor, Windsurf, or custom AI agents) via the official Apify Model Context Protocol (MCP) server.

Add the following to your `claude_desktop_config.json` or Cursor MCP settings:

```json
{
  "mcpServers": {
    "local-lead-finder": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://mcp.apify.com/?tools=adarsha5389/local-lead-finder",
        "--header",
        "Authorization: Bearer <YOUR_APIFY_API_TOKEN>"
      ]
    }
  }
}
```

Once configured, you can prompt your AI assistant directly:
> *"Find 10 interior designers in Austin who need a website rebuild, extract their emails and phones, and prepare a personalized pitch for each."*

## Notes
- No LLM or paid API keys required — fully deterministic and fast.
- Discovery uses OpenStreetMap (free). For guaranteed, reproducible runs, pass an explicit `urls` list.
- Respects site politeness with bounded page counts per site.
