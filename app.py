from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import re
import sys
import os
from getpass import getpass
from datetime import datetime

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "local-development-only-change-this-before-deployment"
)


@app.route("/")
def home():
    return redirect(url_for("login"))


ADMIN_EMAIL = "xxgamerxx93057@gmail.com"
# TEMPORARY: Promote registered account to Admin
con = get_db()
con.execute(
    "UPDATE users SET role = 'admin' WHERE email = ?",
    (ADMIN_EMAIL,)
)
con.commit()
con.close()

def get_db():
    con = sqlite3.connect("location.db")
    con.row_factory = sqlite3.Row
    return con


def is_strong_password(password):
    return (
        len(password) >= 12
        and re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"[0-9]", password)
        and re.search(r"[^A-Za-z0-9]", password)
    )


def create_database():
    import hmac

@app.route("/make-admin", methods=["GET", "POST"])
def make_admin():
    if request.method == "POST":
        token = request.form.get("token", "")
        expected_token = os.environ.get("ADMIN_PROMOTION_TOKEN", "")

        if not expected_token or not hmac.compare_digest(token, expected_token):
            return "Invalid token", 403

        con = get_db()

        cursor = con.execute(
            "UPDATE users SET role = 'admin' WHERE email = ?",
            (ADMIN_EMAIL,)
        )

        con.commit()
        updated = cursor.rowcount
        con.close()

        if updated == 1:
            return "Account successfully promoted to Admin!"

        return "Account not found. Please register first."

    return """
    <form method="POST">
        <input type="password" name="token" placeholder="Admin setup token" required>
        <button type="submit">Make Admin</button>
    </form>
    """
    con = get_db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)

    columns = [
        ("latitude", "REAL"),
        ("longitude", "REAL"),
        ("sharing_enabled", "INTEGER DEFAULT 0"),
        ("location_time", "TEXT"),
        ("security_question", "TEXT"),
        ("security_answer", "TEXT"),
        ("reset_attempts", "INTEGER DEFAULT 0")
    ]

    existing = [
        row["name"]
        for row in con.execute("PRAGMA table_info(users)").fetchall()
    ]

    for column, data_type in columns:
        if column not in existing:
            con.execute(
                f"ALTER TABLE users ADD COLUMN {column} {data_type}"
            )

    con.commit()
    con.close()


# Render/Gunicorn ke liye database initialize
create_database()


def create_admin_account():
    create_database()

    print("\n--- CREATE ADMIN ACCOUNT ---")
    print("Admin email:", ADMIN_EMAIL)

    name = input("Enter admin name: ").strip()

    password = getpass("Enter strong admin password: ")
    confirm_password = getpass("Confirm admin password: ")

    if not name:
        print("Name cannot be empty.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    if not is_strong_password(password):
        print("Password must have 12 characters, uppercase, lowercase, number and special character.")
        return

    hashed_password = generate_password_hash(password)
    con = get_db()

    existing = con.execute(
        "SELECT id FROM users WHERE email = ?",
        (ADMIN_EMAIL,)
    ).fetchone()

    if existing:
        con.execute("""
            UPDATE users
            SET name = ?, password = ?, role = 'admin'
            WHERE email = ?
        """, (name, hashed_password, ADMIN_EMAIL))

        print("Existing account has been secured as Admin.")

    else:
        con.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'admin')
        """, (name, ADMIN_EMAIL, hashed_password))

        print("Admin account created successfully.")

    con.commit()
    con.close()


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if len(password) < 8:
            return "Password must be at least 8 characters."

        hashed_password = generate_password_hash(password)

        try:
            con = get_db()

            con.execute("""
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, 'user')
            """, (name, email, hashed_password))

            con.commit()
            con.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return "This email is already registered."

    return render_template("register.html")


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        con = get_db()
        user = con.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        con.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin"))

            return redirect(url_for("dashboard"))

        return "Invalid Email or Password!"

    return render_template("login.html")


# USER DASHBOARD
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "user":
        return redirect(url_for("admin"))

    con = get_db()
    user = con.execute("""
        SELECT id, name, email, role,
               latitude, longitude, sharing_enabled
        FROM users WHERE id = ?
    """, (session["user_id"],)).fetchone()
    con.close()

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template("dashboard.html", user=user)


# SHARE LOCATION
@app.route("/share-location", methods=["POST"])
def share_location():
    if "user_id" not in session:
        return jsonify({"message": "Please login first"}), 401

    if session.get("role") != "user":
        return jsonify({"message": "User account required"}), 403

    data = request.get_json(silent=True) or {}

    try:
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])

        if not (-90 <= latitude <= 90):
            raise ValueError()

        if not (-180 <= longitude <= 180):
            raise ValueError()

    except (KeyError, TypeError, ValueError):
        return jsonify({"message": "Invalid location"}), 400

    con = get_db()
    con.execute("""
        UPDATE users
        SET latitude = ?, longitude = ?,
            sharing_enabled = 1, location_time = ?
        WHERE id = ?
    """, (
        latitude,
        longitude,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        session["user_id"]
    ))

    con.commit()
    con.close()

    return jsonify({"message": "Location updated successfully"})


# STOP LOCATION SHARING
@app.route("/stop-sharing", methods=["POST"])
def stop_sharing():
    if "user_id" not in session:
        return jsonify({"message": "Please login first"}), 401

    if session.get("role") != "user":
        return jsonify({"message": "User account required"}), 403

    con = get_db()
    con.execute("""
        UPDATE users
        SET sharing_enabled = 0,
            latitude = NULL,
            longitude = NULL,
            location_time = NULL
        WHERE id = ?
    """, (session["user_id"],))

    con.commit()
    con.close()

    return jsonify({"message": "Location sharing stopped"})


# ADMIN DASHBOARD
@app.route("/admin")
def admin():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        return "Access Denied! Admin Only."

    con = get_db()
    users = con.execute("""
        SELECT id, name, email, latitude, longitude, location_time
        FROM users
        WHERE sharing_enabled = 1
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
    """).fetchall()

    con.close()

    return render_template("admin.html", users=users)


# SECURITY SETTINGS
@app.route("/security-settings", methods=["GET", "POST"])
def security_settings():
    if "user_id" not in session:
        return redirect(url_for("login"))

    questions = [
        "What was the name of your first school?",
        "What is your childhood nickname?",
        "What was the name of your first pet?",
        "What is your favourite childhood place?"
    ]

    if request.method == "POST":
        question = request.form.get("question")
        answer = request.form.get("answer", "").strip().lower()

        if question not in questions or len(answer) < 3:
            return "Please select a question and enter a valid answer."

        hashed_answer = generate_password_hash(answer)

        con = get_db()
        con.execute("""
            UPDATE users
            SET security_question = ?, security_answer = ?
            WHERE id = ?
        """, (question, hashed_answer, session["user_id"]))

        con.commit()
        con.close()

        return "Security question saved successfully!"

    return render_template(
        "security_settings.html",
        questions=questions
    )


# FORGOT PASSWORD
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        con = get_db()
        user = con.execute("""
            SELECT id, security_question
            FROM users WHERE email = ?
        """, (email,)).fetchone()
        con.close()

        if not user or not user["security_question"]:
            return "Account not found or security question not set."

        session["reset_user_id"] = user["id"]
        session.pop("reset_allowed", None)

        return render_template(
            "forgot_password.html",
            question=user["security_question"],
            show_answer=True
        )

    session.pop("reset_user_id", None)
    session.pop("reset_allowed", None)

    return render_template(
        "forgot_password.html",
        show_answer=False
    )


# VERIFY SECURITY ANSWER
@app.route("/verify-answer", methods=["POST"])
def verify_answer():
    user_id = session.get("reset_user_id")

    if not user_id:
        return redirect(url_for("forgot_password"))

    answer = request.form.get("answer", "").strip().lower()

    con = get_db()
    user = con.execute("""
        SELECT security_answer
        FROM users WHERE id = ?
    """, (user_id,)).fetchone()
    con.close()

    if user and user["security_answer"] and check_password_hash(
        user["security_answer"], answer
    ):
        session["reset_allowed"] = user_id
        return redirect(url_for("reset_password"))

    return "Incorrect security answer."


# RESET PASSWORD
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("reset_allowed")

    if not user_id:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            return "Passwords do not match."

        con = get_db()
        user = con.execute(
            "SELECT role FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not user:
            con.close()
            session.clear()
            return redirect(url_for("login"))

        if user["role"] == "admin":
            if not is_strong_password(password):
                con.close()
                return (
                    "Admin password must have at least 12 characters, "
                    "uppercase, lowercase, number and special character."
                )
        elif len(password) < 8:
            con.close()
            return "Password must be at least 8 characters."

        hashed_password = generate_password_hash(password)

        con.execute("""
            UPDATE users
            SET password = ?, reset_attempts = 0
            WHERE id = ?
        """, (hashed_password, user_id))

        con.commit()
        con.close()

        session.pop("reset_user_id", None)
        session.pop("reset_allowed", None)

        return redirect(url_for("login"))

    return render_template("reset_password.html")


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-admin":
        create_admin_account()
    else:
        create_database()
        app.run(debug=True)