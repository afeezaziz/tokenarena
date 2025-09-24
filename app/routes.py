from flask import Blueprint, render_template, redirect, session
from .models import get_session, User

ui_bp = Blueprint("ui", __name__)


@ui_bp.route("/")
def index():
    # Data is fetched dynamically via JS from /api endpoints
    return render_template("index.html")


@ui_bp.route("/u/<npub>")
def user_page(npub: str):
    return render_template("user.html", title=f"User {npub}", npub=npub)


@ui_bp.route("/t/<symbol>")
def token_page(symbol: str):
    sym = (symbol or "").upper()
    return render_template("token.html", title=f"{sym} · Token", symbol=sym)


@ui_bp.route("/c/<slug>")
def competition_page(slug: str):
    return render_template("competition.html", title=f"Competition · {slug}", slug=slug)


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
    uid = session.get("user_id")
    if not uid:
        return redirect("/", code=302)
    return render_template("settings.html", title="Settings")
