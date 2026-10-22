from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from .. import rules
from ..services import auth_service
from .common import attempt, get_db

bp = Blueprint("auth", __name__)


@bp.get("/")
def home():
    if g.user is None:
        return redirect(url_for("auth.login"))
    if g.user["role"] == rules.ROLE_OWNER:
        return redirect(url_for("owner.dashboard"))
    return redirect(url_for("shop.po_list"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = auth_service.authenticate(
            get_db(), request.form.get("username"), request.form.get("password")
        )
        if user is not None:
            session.clear()  
            session["user_id"] = user["id"]
            return redirect(url_for("auth.home"))
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        _, error = attempt(
            lambda: auth_service.register_customer(
                get_db(),
                request.form.get("username"),
                request.form.get("password"),
                request.form.get("full_name"),
                request.form.get("phone"),
            )
        )
        if error is None:
            flash("Account created. You can log in now.", "ok")
            return redirect(url_for("auth.login"))
        flash(error, "error")
        return render_template("register.html", form=request.form), 400
    return render_template("register.html", form={})


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
