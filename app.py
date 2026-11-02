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