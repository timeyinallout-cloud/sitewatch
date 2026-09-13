from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, BaseLoader

from sitewatch.runner import SiteReport

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>sitewatch report {{ run_id }}</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 15px/1.5 -apple-system, system-ui, sans-serif; max-width: 1100px;
         margin: 0 auto; padding: 2rem 1.2rem 4rem; background: #FCFCFA; color: #1B1B18; }
  @media (prefers-color-scheme: dark) { body { background: #17181A; color: #E9E7DD; } }
  h1 { font-size: 1.4rem; margin-bottom: .2rem; }
  .meta { color: #78786c; margin-bottom: 2rem; }
  .site { border: 1px solid #e4e2d8; border-radius: 10px; padding: 1.2rem 1.4rem; margin-bottom: 1.6rem; }
  @media (prefers-color-scheme: dark) { .site { border-color: #2c2d2e; } }
  .site h2 { margin: 0 0 .2rem; font-size: 1.15rem; }
  .site h2 a { color: inherit; }
  .badges { display: flex; gap: .5rem; flex-wrap: wrap; margin: .6rem 0 1rem; }
  .badge { border-radius: 6px; padding: .15rem .55rem; font-size: .82rem; font-weight: 600; }
  .badge.ok { background: #eaf1ea; color: #1f6b3b; }
  .badge.warn { background: #f5eedd; color: #8a5a12; }
  .badge.bad { background: #f5e6e3; color: #a23a31; }
  @media (prefers-color-scheme: dark) {
    .badge.ok { background: #16281d; color: #6fc68c; }
    .badge.warn { background: #2a2113; color: #d9ae6b; }
    .badge.bad { background: #2c1d1b; color: #de8b82; }
  }
  table { width: 100%; border-collapse: collapse; margin: .6rem 0 1.2rem; font-size: .88rem; }
  th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid #eceae0; vertical-align: top; }
  @media (prefers-color-scheme: dark) { th, td { border-color: #26272a; } }
  th { color: #78786c; font-weight: 600; }
  .section-label { font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;
                    color: #78786c; margin: 1.2rem 0 .3rem; }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1rem; }
  figure { margin: 0; }
  figure img { width: 100%; border: 1px solid #e4e2d8; border-radius: 6px; display: block; }
  figcaption { font-size: .8rem; margin-top: .3rem; word-break: break-all; }
  .pct { font-weight: 700; }
  .empty { color: #9a9a8e; font-style: italic; }
  code { font-size: .85em; }
</style>
</head>
<body>
<h1>sitewatch report</h1>
<p class="meta">Run {{ run_id }} &middot; {{ sites|length }} site(s)</p>

{% for r in sites %}
<div class="site">
  <h2><a href="{{ r.site.base_url }}">{{ r.site.name }}</a></h2>
  <div class="badges">
    <span class="badge {{ 'ok' if r.crawl.pages|length else 'bad' }}">{{ r.crawl.pages|length }} pages crawled</span>
    <span class="badge {{ 'bad' if r.crawl.broken_links else 'ok' }}">{{ r.crawl.broken_links|length }} broken links</span>
    <span class="badge {{ 'bad' if r.crawl.broken_assets else 'ok' }}">{{ r.crawl.broken_assets|length }} broken assets</span>
    <span class="badge {{ 'warn' if r.crawl.slow_pages else 'ok' }}">{{ r.crawl.slow_pages|length }} slow pages</span>
    <span class="badge {{ 'bad' if r.visual_regressions else 'ok' }}">{{ r.visual_regressions|length }} visual changes</span>
    {% if r.new_pages %}<span class="badge warn">{{ r.new_pages|length }} new baseline(s)</span>{% endif %}
    {% if r.render_failures %}<span class="badge bad">{{ r.render_failures|length }} failed to render</span>{% endif %}
  </div>

  {% if r.crawl.broken_links or r.crawl.broken_assets %}
  <p class="section-label">Broken links &amp; assets</p>
  <table>
    <thead><tr><th>Kind</th><th>Found on</th><th>Target</th><th>Status</th></tr></thead>
    <tbody>
    {% for i in r.crawl.broken_links + r.crawl.broken_assets %}
      <tr><td>{{ i.kind }}</td><td><code>{{ i.page_url }}</code></td><td><code>{{ i.target_url }}</code></td><td>{{ i.status }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if r.crawl.slow_pages %}
  <p class="section-label">Slow pages (&gt; 2s)</p>
  <table>
    <thead><tr><th>Page</th><th>Load time</th></tr></thead>
    <tbody>
    {% for p in r.crawl.slow_pages %}
      <tr><td><code>{{ p.url }}</code></td><td>{{ "%.2f"|format(p.elapsed_seconds) }}s</td></tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if r.render_failures %}
  <p class="section-label">Failed to render (screenshot)</p>
  <table>
    <tbody>
    {% for url in r.render_failures %}<tr><td><code>{{ url }}</code></td></tr>{% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if r.visual_regressions %}
  <p class="section-label">Visual changes vs. baseline</p>
  <div class="gallery">
    {% for d in r.visual_regressions %}
    <figure>
      <img src="{{ d.result.diff_image_path }}" alt="diff for {{ d.url }}">
      <figcaption><span class="pct">{{ "%.1f"|format(d.result.changed_pct) }}%</span> changed &middot; <code>{{ d.url }}</code></figcaption>
    </figure>
    {% endfor %}
  </div>
  {% endif %}

  {% if r.new_pages %}
  <p class="section-label">New pages (no prior baseline &mdash; recorded this run)</p>
  <table>
    <tbody>
    {% for d in r.new_pages %}<tr><td><code>{{ d.url }}</code></td></tr>{% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if not (r.crawl.broken_links or r.crawl.broken_assets or r.crawl.slow_pages or r.visual_regressions or r.render_failures) %}
  <p class="empty">Nothing to report &mdash; all pages healthy, no visual drift.</p>
  {% endif %}
</div>
{% endfor %}
</body>
</html>
"""


def render(run_id: str, sites: list[SiteReport], out_path: Path) -> Path:
    env = Environment(loader=BaseLoader())
    template = env.from_string(_TEMPLATE)
    html = template.render(run_id=run_id, sites=sites)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path
