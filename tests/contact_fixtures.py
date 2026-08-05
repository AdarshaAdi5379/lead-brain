from __future__ import annotations

# Shared HTML fixtures for the contact intelligence engine tests.
# No network, no API keys: pure markup passed straight into the extractors.

JSONLD_HOMEPAGE = """<html><head><title>Acme Plumbing</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Plumber",
  "name": "Acme Plumbing",
  "telephone": "+1-512-555-0100",
  "email": "office@acme.example.com",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "100 Main St",
    "addressLocality": "Austin",
    "addressRegion": "TX",
    "postalCode": "78701",
    "addressCountry": "US"
  },
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": "Monday",
      "opens": "09:00",
      "closes": "17:00"
    },
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": "Tuesday",
      "opens": "09:00",
      "closes": "17:00"
    }
  ],
  "areaServed": ["Austin", "Round Rock"],
  "sameAs": [
    "https://www.instagram.com/acmeplumbing",
    "https://www.youtube.com/@acmeplumbing"
  ],
  "founder": {"@type": "Person", "name": "Bob Acme"}
}
</script></head><body>
<h1>Acme Plumbing</h1>
<p>We fix pipes in Austin.</p>
<nav>
  <a href="/about">About Us</a>
  <a href="/contact">Contact</a>
</nav>
<footer>
  <a href="https://www.facebook.com/acmeplumbing">Facebook</a>
  <a href="https://x.com/acmeplumbing">Twitter</a>
  <a href="https://wa.me/15125550100">WhatsApp</a>
  <a href="https://facebook.com/sharer/sharer.php?u=https%3A%2F%2Facme.example.com">Share</a>
</footer>
</body></html>"""

# JSON-LD with a graph wrapper and Organization node (no LocalBusiness token).
GRAPH_PAGE = """<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "WebSite", "name": "Acme Site"},
    {
      "@type": "Organization",
      "name": "Acme Plumbing",
      "contactPoint": [
        {"@type": "ContactPoint", "telephone": "+1-512-555-0199", "email": "info@acme.example.com"}
      ],
      "address": {"streetAddress": "5 Oak Ave", "addressLocality": "Austin", "postalCode": "78702"}
    }
  ]
}
</script></head><body><p>Graph page body.</p></body></html>"""

SOCIALS_PAGE = """<html><body>
<a href="https://www.facebook.com/acmepage">Facebook</a>
<a href="https://fb.com/acmepage">Facebook short</a>
<a href="https://www.instagram.com/acmephotos">Instagram</a>
<a href="https://www.linkedin.com/company/acme-plumbing">LinkedIn</a>
<a href="https://twitter.com/acmetweets">Twitter</a>
<a href="https://www.youtube.com/channel/UCabc123">YouTube</a>
<a href="https://wa.me/15125550100?text=hello">WhatsApp</a>
<a href="https://www.linkedin.com/login">Login</a>
<a href="https://x.com/intent/tweet?text=hi">Intent</a>
<a href="/privacy">Privacy</a>
</body></html>"""

CONTACT_FORM_PAGE = """<html><body>
<form action="/submit-contact" method="post">
  <input name="name" type="text">
  <input name="email" type="email">
  <textarea name="message"></textarea>
  <button>Send message</button>
</form>
<form action="/search"><input name="q" type="search"></form>
</body></html>"""

LOGIN_ONLY_PAGE = """<html><body>
<form action="/login" method="post">
  <input name="email" type="email">
  <input name="password" type="password">
  <button>Sign in</button>
</form>
</body></html>"""

NO_FORM_PAGE = """<html><body><p>No forms here.</p></body></html>"""
