PRODUCT REQUIREMENTS DOCUMENT (PRD)
Second Brain Lead Finder – Automated Client Generation for Freelance Developers
Version: 1.0
Date: May 2026
Author: CSE Graduate (Bootstrapping Developer)
Status: Ready for Implementation

1. Executive Summary
1.1 Problem Statement
You are a computer science graduate with strong coding skills but lack a consistent, automated way to find paying clients. Manual searching for businesses with poor websites is time‑consuming, unreliable, and does not scale.

1.2 Solution Overview
Build an AI‑powered lead generation system that:

Discovers small local service businesses (and select US businesses) with minimal or outdated websites.

Extracts their contact information (business name, phone, email, website URL).

Scores each lead based on how likely they are to need a new website or web development services.

Presents the scored leads in a simple web dashboard and allows exporting to CSV.

Runs cost‑effectively (target under $10/month) to generate 100–200 leads per week.

1.3 Success Metrics
Metric	Target
Leads generated per week	100 – 200
Valid contact info (phone or email) found	≥ 80% of leads
“Hot” leads (score ≥ 70/100)	15 – 30 per week
Time from starting a run to usable leads	< 2 hours (for 200 URLs)
Monthly operating cost	< $10 (excluding optional server)
First paying client acquired	Within 4 weeks of using the system
2. Target Client Profile
You will focus on small local service businesses because they have simple websites (easy to assess) and a high need for digital improvement.

Primary Niches (you can expand later)
Home services: plumbers, electricians, HVAC, roofers, painters, landscapers, handyman, locksmiths, tree services.

Local retail & personal services: salons, barbershops, pizza shops, bakeries, car washes, dry cleaners.

Tradesmen: contractors, general contractors, flooring, window cleaning.

Geographic Focus
Local (your city and surrounding areas) – for easier outreach and potential in‑person meetings.

United States (any city) – to increase volume; outreach can be done via email/phone.

Why These Clients?
Their websites are often basic (HTML, old WordPress, Wix) or missing entirely.

They have high margins and can afford a few hundred dollars per month.

They need phone calls and form submissions – a direct pain point you can solve.

They rarely have in‑house IT departments.

3. Core Features (Functional Requirements)
3.1 URL Discovery Module
Purpose: Obtain a list of business website URLs to scrape.

Feature	Description
Manual seed list	Allow you to manually copy URLs from Google Maps search results into a CSV file. This is the primary method for initial runs.
Local category templates	Pre‑define a list of search categories (e.g., “plumbers in Austin, TX”) to generate search URLs for manual collection.
(Optional) API integration	Provide hooks to integrate with Google Places API or other paid services in the future, but not required for v1.
CSV input format	The system expects a simple CSV file with columns: business_name, category, url, city, state. You fill it manually or via helper scripts.
3.2 Scraping Engine (AI‑Powered)
Purpose: Visit each website URL and extract key business information using an LLM.

Feature	Description
Single‑page extraction	For each URL, extract: business name, phone number, email address, CMS/platform (WordPress, Wix, custom HTML), complexity (basic/medium/complex), load speed (fast/medium/slow).
Headless browser	Use Playwright to render JavaScript‑heavy sites, ensuring you capture dynamically loaded content.
Error handling	If a URL fails (timeout, 404, CAPTCHA), mark that lead as failed and continue with others.
Rate limiting	Add delays between requests (default 1 second) to avoid being blocked.
Cost tracking	Estimate token usage and cost per run based on number of URLs and average input/output token counts.
3.3 Lead Scoring Engine
Purpose: Assign a score (0–100) to each lead indicating how urgently they likely need a web developer.

Feature	Description
Weighted heuristic scoring	Uses rules derived from extracted fields (see Section 7 for exact weights).
Positive signals	No website (+40), basic platform like Wix (+30), slow load speed (+20), missing phone (+15), missing email (+15).
Negative signals	Already has a complex website (-30), uses Shopify or custom React (-20), has both phone and email (-10 each).
Score normalisation	Final score clamped between 0 and 100.
Priority labels	Hot (≥70), Warm (50‑69), Cold (30‑49), Avoid (<30).
Recommendation text	For each lead, a human‑readable action (e.g., “Send personalized email within 48 hours”).
3.4 Data Storage (Local SQLite + CSV)
Purpose: Persist leads and allow export.

Feature	Description
SQLite database	Stores all leads, extraction runs, and metadata. Prevents duplicate entries when re‑scraping the same URL.
Automatic deduplication	If the same URL appears again, update the existing record instead of creating a duplicate.
CSV export	Export any filtered set of leads (e.g., all leads with score ≥ 50) to a CSV file for use in spreadsheets or email tools.
Export folder	All exports are saved in an exports/ directory with timestamped filenames.
3.5 Web Dashboard (Streamlit)
Purpose: View, filter, and interact with leads without touching the command line.

Feature	Description
Lead table	Display business name, phone, email, website, score, priority, platform. Sortable and filterable by minimum score.
Score histogram	Visual chart showing distribution of lead scores.
Metrics cards	Show total leads in current view, number of hot leads, average score, and total leads in database.
Lead detail panel	Click a lead to see full extracted data and a generated outreach email template.
Outreach template generator	Uses lead data to create a personalised cold email (and optionally WhatsApp message). You can copy it to your clipboard.
Export buttons	Download the current table as CSV, or export all leads from the database.
Mark as contacted (future)	Simple checkbox to flag leads you have already reached out to.
3.6 Outreach Helper
Purpose: Save time writing personalised messages.

Feature	Description
Dynamic email template	Inserts business name, missing elements (e.g., “your site is slow”), and a call‑to‑action.
Multiple versions	Generate a short WhatsApp‑style message as well.
Follow‑up reminders (optional)	Track when you last contacted a lead and suggest a follow‑up after 3–5 days.
3.7 Automation & Scheduling
Purpose: Run the lead generation process on a regular cadence without manual intervention.

Feature	Description
Command‑line execution	A single command (python main.py) runs the full pipeline: load URLs → scrape → score → save → export.
Cron / scheduler friendly	The script can be scheduled via cron (Linux/macOS), Task Scheduler (Windows), or GitHub Actions (free).
Run logging	Each run records start/end time, URLs processed, successes/failures, and estimated cost.
4. How It Works – Step by Step (End‑to‑End Flow)
Prepare URL source
You manually search Google Maps for “plumbers in Chicago” and copy 50 business website URLs into a CSV file (business_urls.csv). You can also reuse the same CSV later.

Run the main script
Execute python main.py. The script reads the CSV, initialises the database, and begins scraping.

Scraping phase
For each URL, the system launches a headless browser, loads the page, and sends the HTML along with a prompt to GPT‑4.1 Nano (via OpenAI API). The prompt asks the LLM to extract business name, phone, email, platform, complexity, and load speed. The LLM returns a structured JSON object.

Error & retry handling
If a URL fails (e.g., network error, timeout), the script logs the failure and moves to the next URL. No automatic retry in v1, but you can re‑run the script on only failed URLs.

Scoring phase
After extraction, each lead passes through the scoring engine. The engine applies the weighted rules described in Section 7, producing a score (0–100) and a priority label.

Storage
All leads (successful and failed) are inserted into the SQLite database. If a lead already exists (based on URL), the new data updates the existing record, but does not create a duplicate.

Export & dashboard
The script automatically exports a CSV of leads with score ≥ 30 into the exports/ folder. Then you can launch the Streamlit dashboard (streamlit run dashboard.py) to view, filter, and generate outreach messages.

Outreach
You copy the personalised email from the dashboard, send it via your own email account or CRM, and start conversations.

Repeat weekly
Add new URLs to business_urls.csv (or reuse the same ones to check for changes). Run the script once a week to refresh leads. Over time, you will build a large database of scored prospects.

5. System Architecture (High‑Level)
The system is a Python‑based monolithic application with decoupled modules.

Component	Technology / Role
Orchestration	main.py – controls the flow from URL loading to saving.
URL loader	Reads CSV; optionally generates search templates.
Scraper	Uses scrapegraphai library which internally calls Playwright and OpenAI.
LLM	OpenAI GPT‑4.1 Nano (cheapest model for extraction).
Scorer	Pure Python heuristic module (no external API).
Storage	SQLite (database) + CSV export (pandas).
Dashboard	Streamlit – runs separately, reads from the same SQLite database.
Scheduling	Cron job or GitHub Actions (runs main.py weekly).
Data flow diagram (textual):

CSV URLs → Scraper → Extracted fields (JSON) → Scorer → Enriched leads → SQLite DB → (optional) CSV export
SQLite DB ← Dashboard (read‑only queries) → User sees leads and generates emails.

All modules run on the same machine (your local computer or a small cloud server). No external data storage services required.

6. Technology Stack (No Code, Just Names)
Programming Language: Python 3.10+

Web Scraping: ScrapeGraphAI (LLM‑based), Playwright (headless browser)

LLM / AI: OpenAI GPT‑4.1 Nano (fallback: GPT‑4o‑mini)

Database: SQLite (file‑based)

Data Manipulation: Pandas

Dashboard: Streamlit

Visualisation: Plotly (for histograms)

Environment Management: Python venv + pip

Scheduling: Cron (Linux/macOS) or GitHub Actions (free)

Optional Cloud Hosting: Railway, Render, or PythonAnywhere (for 24/7 dashboard)

Version Control: GitHub (private repo)

7. Lead Scoring Logic (Detailed Weights)
The scoring engine starts from a baseline of 50 (neutral). Then it adds or subtracts points based on the following conditions.

Condition	Points Added	Rationale
No website URL found	+40	Absolute need – they are invisible online.
Website platform = Wix / Weebly / Squarespace / basic HTML	+30	They have a presence but limited functionality; easy upgrade path.
Load speed = "slow"	+20	Slow sites lose customers and rank poorly on Google.
Phone number missing	+15	Harder to contact, but also a sign of poor customer acquisition.
Email address missing	+15	Same as above.
Platform = WordPress (but complexity = basic)	+10	Many WordPress sites are outdated and can be improved.
Phone number exists	-10	Easier to reach, but not a negative for their need.
Email address exists	-10	Same as above.
Platform = Shopify or custom complex framework	-20	They likely already have a modern e‑commerce or complex site; high friction to convert.
Complexity = "complex" or "large"	-30	The site is already sophisticated; unlikely to need a simple developer.
*Final score = min(100, max(0, 50 + sum of adjustments))*

Score Interpretation
70 – 100 (Hot): Contact immediately. The business is losing customers because of a missing or broken online presence.

50 – 69 (Warm): Contact within the week. Good potential but maybe not urgent.

30 – 49 (Cold): Low priority. Add to a nurture list for future follow‑up.

0 – 29 (Avoid): Do not waste time. These leads either already have a good site or are impossible to contact.

8. Data Model (Tables and Fields)
Table: leads
Stores every business extracted.

Field	Type	Description
id	INTEGER (PK)	Auto‑increment.
business_name	TEXT	Extracted company name.
phone	TEXT	Main contact phone number.
email	TEXT	Contact email address.
website_url	TEXT	The URL that was scraped.
platform	TEXT	e.g., WordPress, Wix, custom HTML.
complexity	TEXT	basic, medium, complex.
load_speed	TEXT	fast, medium, slow.
city	TEXT	From input CSV.
state	TEXT	From input CSV.
category	TEXT	e.g., plumber, electrician.
score	INTEGER	0–100.
priority	TEXT	Hot/Warm/Cold/Avoid.
extraction_success	BOOLEAN	True if scraper succeeded.
extracted_at	TIMESTAMP	When this record was created/updated.
outreach_sent	BOOLEAN	(Future) flag to avoid double‑contacting.
notes	TEXT	Manual notes you can add via dashboard.
Table: scraping_runs
Logs each execution of the main script.

Field	Type	Description
run_id	INTEGER (PK)	Auto‑increment.
started_at	TIMESTAMP	When the run began.
completed_at	TIMESTAMP	When it finished.
total_urls_processed	INTEGER	Number of URLs attempted.
successful_extractions	INTEGER	Count where extraction_success = True.
failed_extractions	INTEGER	Count where extraction_success = False.
total_cost_usd	REAL	Estimated OpenAI API cost for the run.
File exports (CSV)
The CSV contains a flattened version of the leads table, excluding internal IDs and timestamps.

9. User Interface (Dashboard) Description
The dashboard is built with Streamlit and has the following sections:

Header – Title and brief description.

Sidebar – Filters: minimum score slider (0–100) and number of leads to display.

Key metrics row – Cards showing total leads in current view, number of hot leads, average score, and total leads in the entire database.

Score distribution chart – A histogram (Plotly) of lead scores for the current filter.

Main lead table – Columns: Business Name, Phone, Email, Website (clickable), Score, Priority, Platform. Rows are sortable by clicking column headers.

Export controls – Two buttons: “Export Current View to CSV” and “Export All Leads (from DB) to CSV”.

Lead detail & outreach section – A dropdown to select a lead. When selected, displays:

Full extracted data (phone, email, website, platform, complexity, load speed, score, priority)

A generated email template (editable text area)

A button to copy the template to clipboard

Footer – Version info and suggestion to run the scraper weekly.

The dashboard does not trigger scraping; it only reads the database. You run the scraper separately.

10. Deployment & Operation Options
Option A: Local Machine (Easiest for Testing)
Install Python, dependencies, and Playwright browsers.

Run python main.py manually whenever you want fresh leads.

Run streamlit run dashboard.py to view results.

Pros: Zero hosting cost, full control.

Cons: Your computer must be on to run the scraper; dashboard not accessible remotely.

Option B: Cloud Server (Recommended for Regular Use)
Deploy to a low‑cost VPS or PaaS like Railway, Render, or PythonAnywhere ($5–20/month).

Set up a cron job (or scheduler) to run main.py every Sunday night.

Keep the Streamlit dashboard running continuously on a public URL (may require a persistent process).

Pros: Fully automated, accessible from anywhere, runs 24/7.

Cons: Small monthly cost.

Option C: GitHub Actions (Free for Open Source / Private Repos with limits)
Store the code in a private GitHub repository.

Create a GitHub Actions workflow that runs main.py on a schedule (e.g., every Monday at 9am).

The action can commit the exported CSV back to the repo or send it via email.

Pros: Completely free, no server needed.

Cons: Limited runtime (max 6 hours per run), cannot run a live dashboard easily.

Recommendation for v1: Start with Option A (local) to validate the system. After you land your first client, move to Option B (Railway/Render) for automation.

11. Cost Breakdown (Monthly)
Item	Cost (USD)	Notes
OpenAI API (GPT-4.1 Nano) – 5,000 lead extractions	~$2.50	Based on 2,000 input + 500 output tokens per site. Actual cost may vary slightly.
Cloud server (optional) – Railway/Render smallest tier	
5
–
5–20	Not needed if running locally.
Domain (optional)	
0
–
0–12	If you want a public dashboard URL.
Google Maps/Places API (optional, not in v1)	
0
–
0–200	Not used in the core PRD; you manually collect URLs.
Total (no server)	~$2.50	You can run 200 leads/week for under $1/month.
Total (with server)	~
7.50
–
7.50–22.50	Still very affordable after you start earning.
OpenAI free credits: New accounts receive $5 free credit, covering approximately 10,000 lead extractions.

12. Risk Mitigation
Risk	Likelihood	Mitigation
Websites block scraping (CAPTCHA, IP ban)	Medium	Use delays (1 sec between requests), rotate User‑Agent, and consider rotating proxies if it becomes frequent. For v1, most small business sites do not block.
LLM extraction inaccurate (wrong phone/email)	Medium	The scoring engine does not rely on 100% accuracy; you visually verify before contacting. You can also add a post‑processing step to validate email format.
OpenAI API cost overrun	Low	Set a hard limit in your code: stop after $X cost. Also, GPT‑4.1 Nano is extremely cheap.
No leads found in a run	Low	If your seed URLs are poor, the system still returns empty. Maintain a growing list of URLs from Google Maps.
Missing phone/email for many leads	Medium	The scoring engine gives higher scores to leads with missing contact info – but you cannot contact them. Balance by also collecting phone/email from other sources (e.g., Yellow Pages, Yelp) in future versions.
Legal / Terms of Service	Low	Scraping public business websites for lead generation is generally permitted, but you should respect robots.txt and avoid aggressive crawling. Use for B2B outreach only.
13. Future Enhancements (Roadmap v2 & v3)
v2 (after 3 months of use)
Automatic URL discovery – Integrate with Google Places API or a cheap lead database (e.g., Apollo.io) to get URLs without manual copy‑paste.

Email sending integration – Connect to Gmail API or SendGrid to send outreach emails directly from the dashboard (with manual approval).

Lead de‑duplication across multiple sources – Improve matching logic.

More detailed website analysis – Check for missing meta descriptions, broken links, no mobile viewport.

v3 (scaled up)
Multi‑user support – Support multiple users so you can work with a virtual assistant.

CRM integration – Push leads to HubSpot, Pipedrive, or a simple Airtable.

Automated follow‑up sequences – Send reminder emails if there is no reply after 5 days.

Client project scoping – Automatically suggest a price based on website complexity and missing features.

---

14. Success Definition & Next Steps for You
How you know the project is a success:

- You run the scraper once a week and consistently get 100+ leads.
- At least 15 of those leads are scored as “Hot” (≥ 70).
- You send 10–20 personalised emails per week.
- Within 4 weeks, you have your first paying client who pays at least $150/month.

Immediate next actions (no code, just steps):
1) Create an OpenAI account and get $5 in free credits.
2) Prepare a small seed list: Open Google Maps, search for “plumbers in [your city]”, copy 10 website URLs into a plain text file.
3) Set up Python on your computer and install ScrapeGraphAI, Playwright, and other dependencies.
4) Run the scraper on those 10 URLs (a minimal script is fine for the first test).
5) Manually review the extracted data and correct any obvious errors.
6) Launch the dashboard and generate your first outreach emails.
7) Send the emails and track replies.

The PRD is your blueprint. No code is included here, but every function, module, and decision is described so that you (or any developer) can implement it exactly as specified.

*End of PRD*
