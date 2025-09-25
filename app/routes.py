from flask import Blueprint, render_template, redirect, session, Response, request, url_for
from urllib.parse import quote
from .models import get_session, User

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def index():
    # Data is fetched dynamically via JS from /api endpoints
    return render_template(
        "index.html",
        title="Token Arena · Where Tokens Go To Battle",
        description="Battle-ready market intel: leaderboards, holders, charts and competitions.",
    )


@ui_bp.route("/u/<npub>")
def user_page(npub: str):
    short = (npub or '')[:8] + '…' if npub and len(npub) > 8 else (npub or '')
    return render_template(
        "user.html",
        title=f"User {npub} · Portfolio",
        description="User portfolio allocation, holdings and value on Token Arena.",
        social_image=url_for('ui.og_user', npub=npub, _external=True),
        og_type='profile',
        npub=npub,
    )


@ui_bp.route("/t/<symbol>")
def token_page(symbol: str):
    sym = (symbol or "").upper()
    return render_template(
        "token.html",
        title=f"{sym} · Token",
        description=f"{sym} token: price, market cap, holders, charts and top holders.",
        social_image=url_for('ui.og_token', symbol=sym, _external=True),
        og_type='article',
        symbol=sym,
    )


@ui_bp.route("/c/<slug>")
def competition_page(slug: str):
    return render_template(
        "competition.html",
        title=f"Competition · {slug}",
        description="Leaderboard, participants and scoring for Token Arena competitions.",
        social_image=url_for('ui.og_competition', slug=slug, _external=True),
        og_type='article',
        slug=slug,
    )


@ui_bp.route("/tokens")
def tokens_list_page():
    # Full tokens list page; UI loads via main.js
    return render_template(
        "tokens.html",
        title="Tokens · Token Arena",
        description="Full token leaderboard with filters, metrics, and CSV export.",
    )


@ui_bp.route("/competitions")
def competitions_list_page():
    return render_template(
        "competitions.html",
        title="Competitions · Token Arena",
        description="Active, upcoming, and past Token Arena competitions.",
    )


@ui_bp.route("/datasources")
def datasources_list_page():
    return render_template(
        "datasources.html",
        title="Data Sources · Token Arena",
        description="Coverage, freshness and status of data sources powering Token Arena.",
    )


@ui_bp.route("/d/<slug>")
def datasource_detail_page(slug: str):
    return render_template(
        "datasource.html",
        title=f"Source · {slug}",
        description="Source coverage, freshness, status and changelog.",
        slug=slug,
    )


@ui_bp.route("/me")
def me():
    uid = session.get("user_id")
    if not uid:
        return redirect("/", code=302)
    s = get_session()
    user = s.query(User).filter(User.id == uid).one_or_none()
    if not user:
        return redirect("/", code=302)
    return redirect(f"/u/{user.npub}", code=302)


@ui_bp.route("/settings")
def settings():
    # Render settings page; API endpoints will enforce auth. In Demo Mode, mocks satisfy requests.
    return render_template("settings.html", title="Settings", description="Manage your profile, avatar and bio.")


@ui_bp.route("/features")
def features_page():
    return render_template("features.html", title="Features · Token Arena", description="Leaderboards, token pages, charts, competitions, search and exports.")


@ui_bp.route("/methodology")
def methodology_page():
    return render_template("methodology.html", title="Methodology · Token Arena", description="How we compute returns, Sharpe(7D), holders growth, market share Δ and composite scores.")


@ui_bp.route("/pricing")
def pricing_page():
    return render_template("pricing.html", title="Pricing · Token Arena", description="Start free. Upgrade for unlimited rows, exports, alerts and API access.")


@ui_bp.route("/docs")
def docs_page():
    return render_template("docs.html", title="Docs · Token Arena", description="Public API endpoints for tokens, charts, users, competitions and profile.")


@ui_bp.route("/about")
def about_page():
    return render_template("about.html", title="About · Token Arena", description="Playful, fast and transparent token market intelligence.")


@ui_bp.route("/contact")
def contact_page():
    return render_template("contact.html", title="Contact · Token Arena", description="Reach out with feedback or request early access.")


@ui_bp.route("/roadmap")
def roadmap_page():
    return render_template("roadmap.html", title="Roadmap · Token Arena", description="What we're building next for Token Arena.")


@ui_bp.route("/changelog")
def changelog_page():
    return render_template("changelog.html", title="Changelog · Token Arena", description="Recent updates and shipped features.")


@ui_bp.route("/faq")
def faq_page():
    return render_template("faq.html", title="FAQ · Token Arena", description="Frequently asked questions about Token Arena.")


@ui_bp.route("/terms")
def terms_page():
    return render_template("terms.html", title="Terms · Token Arena", description="Terms of Service for Token Arena.")


@ui_bp.route("/privacy")
def privacy_page():
    return render_template("privacy.html", title="Privacy · Token Arena", description="Privacy policy for Token Arena.")


# Open Graph dynamic image endpoints
def _render_og_image(title_text: str, subtitle_text: str) -> Response:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        return Response("OG image generator unavailable", status=500, mimetype="text/plain")
    import io
    W, H = 1200, 630
    bg = (11, 15, 26)
    accent = (124, 92, 255)
    fg = (255, 255, 255)
    img = Image.new('RGB', (W, H), color=bg)
    draw = ImageDraw.Draw(img)
    # Accent bar
    draw.rectangle([(0, H-12), (W, H)], fill=accent)
    # Try to use a decent font if available; otherwise fallback
    try:
        font_title = ImageFont.truetype('DejaVuSans-Bold.ttf', 96)
        font_sub = ImageFont.truetype('DejaVuSans.ttf', 40)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
    # Compute centered positions
    def text_size(txt, font):
        try:
            bbox = draw.textbbox((0, 0), txt, font=font)
            return (bbox[2]-bbox[0], bbox[3]-bbox[1])
        except Exception:
            return draw.textsize(txt, font=font)
    tw, th = text_size(title_text, font_title)
    sx, sy = text_size(subtitle_text, font_sub)
    x_title = max(40, (W - tw) // 2)
    y_title = (H - th) // 2 - 20
    x_sub = max(40, (W - sx) // 2)
    y_sub = y_title + th + 20
    draw.text((x_title, y_title), title_text, font=font_title, fill=fg)
    draw.text((x_sub, y_sub), subtitle_text, font=font_sub, fill=(200, 200, 210))
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="image/png")


@ui_bp.route("/og/token/<symbol>.png")
def og_token(symbol: str):
    sym = (symbol or "").upper()
    return _render_og_image(sym, "Token Arena")


@ui_bp.route("/og/competition/<slug>.png")
def og_competition(slug: str):
    return _render_og_image(f"Competition: {slug}", "Token Arena")


@ui_bp.route("/og/user/<npub>.png")
def og_user(npub: str):
    short = (npub or '')[:8] + '…' if npub and len(npub) > 8 else (npub or '')
    return _render_og_image(f"User {short}", "Token Arena")


@ui_bp.route("/robots.txt")
def robots_txt():
    content = """User-agent: *\nAllow: /\nSitemap: {sitemap}\n""".format(
        sitemap=url_for("ui.sitemap_xml", _external=True)
    )
    return Response(content, mimetype="text/plain")


@ui_bp.route("/sitemap.xml")
def sitemap_xml():
    # Basic sitemap for core pages
    base = (request.url_root or "").rstrip("/")
    pages = [
        url_for("ui.index"),
        url_for("ui.tokens_list_page"),
        url_for("ui.competitions_list_page"),
        url_for("ui.datasources_list_page"),
        url_for("ui.features_page"),
        url_for("ui.methodology_page"),
        url_for("ui.pricing_page"),
        url_for("ui.docs_page"),
        url_for("ui.about_page"),
        url_for("ui.contact_page"),
        url_for("ui.roadmap_page"),
        url_for("ui.changelog_page"),
        url_for("ui.faq_page"),
        url_for("ui.terms_page"),
        url_for("ui.privacy_page"),
    ]
    urls = "".join([f"<url><loc>{base}{p}</loc></url>" for p in pages])
    xml = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">{urls}</urlset>"
    return Response(xml, mimetype="application/xml")
