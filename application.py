import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    table = db.execute("SELECT * FROM exchanges WHERE id=?",
                       session["user_id"])
    remaining_cash = db.execute(
        "SELECT cash FROM users WHERE id=?", session["user_id"])

    float_total = 0.0
    total = str()
    for i in table:
        total = i["total"]
        if len(total) > 1:
            total = total.lstrip("$")
            total = total.replace(",", "")
            float_total += float(total)

    return render_template("index.html", table=table, total=float_total, cash=remaining_cash[0]["cash"])


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    # if method was GET
    if request.method == "GET":
        return render_template("buy.html")

    # get dict of name, symbol, price of quote
    quote = lookup(request.form.get("symbol"))
    # check for invalid quote
    if quote is None:
        return apology("No share has found", 400)

    # hold shares
    shares = request.form.get("shares")

    # taking shares as positive integers only
    try:
        shares = int(shares)
    except:
        return apology("shares must positive integers", 400)

    # check for shares existence and if it's not less than 0
    if not shares or shares <= 0:
        return apology("please enter number of shares", 400)

    # check how much user has
    user = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    current_cash = user[0]["cash"]

    # calculating total price in $
    total = quote["price"] * float(shares)
    if total > current_cash:
        return apology("sorry, not enough money", 400)

    # before updating users cash we need to subtract it from total
    current_cash -= total

    # update history table
    db.execute("INSERT INTO history (id, symbol, shares, price) VALUES(?,?,?,?)",
               session["user_id"],
               quote["symbol"],
               shares,
               usd(quote["price"])
               )
    # update user's cash
    db.execute("UPDATE users SET cash=? WHERE id=?",
               current_cash, session["user_id"])

    # grab number of user shares
    user_shares = db.execute(
        "SELECT * FROM exchanges WHERE symbol=? AND id=?", quote["symbol"], session["user_id"])

    # if user does not have shares of that symbol
    if not user_shares:
        db.execute("INSERT INTO exchanges VALUES(?,?,?,?,?,?)",
                   session["user_id"],
                   quote["symbol"],
                   quote["name"],
                   shares,
                   usd(quote["price"]),
                   usd(total))
    # if user has: ++shares count
    else:
        total_shares = user_shares[0]["shares"] + float(shares)
        db.execute("UPDATE exchanges SET shares=? WHERE id=? AND symbol =?",
                   total_shares, session["user_id"], quote["symbol"])
    flash("Bought!")

    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute(
        "SELECT * FROM history WHERE id=?", session["user_id"])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")

    symbol = lookup(request.form.get("symbol"))
    if symbol is None:
        return apology("No share has found", 400)
    return render_template("quoted.html", value=symbol)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("registration.html")

    # make sure username is provided
    if not request.form.get("username"):
        return apology("sorry, must provied username", 400)

    # make sure password is provided
    if not request.form.get("password"):
        return apology("sorry, must provied a password", 400)

    # make sure both passwords are same
    if request.form.get("password") != request.form.get("confirmation"):
        return apology("sorry, both passwords must be same", 400)

    rows = db.execute("SELECT * FROM users WHERE username=?",
                      request.form.get("username"))

    # if user already exists
    if len(rows) == 1:
        return apology("sorry, username already taken", 400)

    else:
        db.execute("INSERT INTO users (username, hash) VALUES(?,?)", request.form.get("username"),
                   generate_password_hash(request.form.get("password")))
    # make user manually log in
    return render_template("login.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user_symbols = db.execute(
        "SELECT symbol FROM exchanges WHERE id=?", session["user_id"])
    if request.method == "GET":
        return render_template("sell.html", symbols=user_symbols)

    quote = lookup(request.form.get("symbol"))
    shares = request.form.get("shares")
    # checks for shares
    try:
        shares = int(shares)
    except:
        return apology("shares must be positive integers", 403)

    if shares <= 0:
        return apology("shares must greater than 0", 403)

    user_shares = db.execute("SELECT shares FROM exchanges WHERE id=? AND symbol=?",
                             session["user_id"],
                             quote["symbol"])

    if not user_shares or int(user_shares[0]["shares"]) < shares:
        return apology("sorry, you don't have enough shares")

    # INSERT sell into history
    db.execute("INSERT INTO history (id, symbol, shares, price) VALUES(?,?,?,?)",
               session["user_id"],
               quote["symbol"],
               -shares,
               usd(quote["price"])
               )

    # update user's cash
    db.execute("UPDATE users SET cash=cash+ :increase WHERE id=:id",
               increase=usd(quote["price"] * float(shares)),
               id=session["user_id"])

    # --shares
    total_shares = user_shares[0]["shares"] - shares

    # remove the transaction from exchanges table
    if total_shares == 0:
        db.execute("DELETE FROM exchanges WHERE id=? AND symbol=?",
                   session["user_id"], quote["symbol"])

    # if not update the share count & total
    else:
        db.execute("UPDATE exchanges SET shares = :shares WHERE id= :id AND symbol= :symbol",
                   shares=total_shares, id=session["user_id"], symbol=quote["symbol"])
        # calculate new total
        total_ = (total_shares * quote["price"])
        db.execute("UPDATE exchanges SET total = :total WHERE id= :id AND symbol= :symbol",
                   total=usd(total_), id=session["user_id"], symbol=quote["symbol"])

    return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
