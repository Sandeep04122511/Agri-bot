from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import json
import tensorflow as tf
from tensorflow.keras.models import load_model
import numpy as np
from PIL import Image
from openai import OpenAI
import os

app = Flask(__name__)
app.secret_key = "agribot_secret_key"
# ---------------------- OPENAI CLIENT -------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------------------- LOAD ML MODEL -------------------------
MODEL_PATH = r"D:\AgriChatbot\models\Agri_disease_prediction.keras"
try:
    disease_model = load_model(MODEL_PATH)
    print("✔ Model loaded successfully!")
except Exception as e:
    print("❌ Error loading model:", e)


# ---------------------- INIT DATABASE -------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        role TEXT DEFAULT 'user',
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        feedback_type TEXT,
        rating INTEGER,
        comments TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        response TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Create default admin
    cursor.execute("SELECT * FROM users WHERE role='admin'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username,email,password,full_name,role,status)
            VALUES (?,?,?,?,?,?)
        """, ("admin", "admin@agribot.com",
              generate_password_hash("admin123"),
              "System Admin", "admin", "approved"))

    conn.commit()
    conn.close()


# ---------------------- ROUTES -------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------- USER LOGIN --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            if user[8] != "approved":
                flash("Your account is not approved by admin yet.", "danger")
                return redirect(url_for("login"))

            session["user_id"] = user[0]
            session["role"] = user[7]
            session["username"] = user[1]
            return redirect(url_for("user_dashboard"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")


# ---------------------- ADMIN LOGIN --------------------
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND role='admin'", (username,))
        admin = cursor.fetchone()
        conn.close()

        if admin and check_password_hash(admin[3], password):
            session["admin_id"] = admin[0]
            session["role"] = "admin"
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials", "danger")

    return render_template("admin_login.html")


# ---------------------- ADMIN DASHBOARD --------------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users WHERE role='user'")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE role='user' AND status='pending'")
    pending_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE status='restricted'")
    restricted_users = cursor.fetchone()[0]

    cursor.execute("SELECT id,username,email,full_name,created_at FROM users WHERE status='pending'")
    pending_list = cursor.fetchall()

    conn.close()

    return render_template("admin_dashboard.html",
                           total_users=total_users,
                           pending_users=pending_users,
                           restricted_users=restricted_users,
                           pending_users_list=pending_list)


# ---------------------- ADMIN ALL USERS --------------------
@app.route("/admin_all_users")
def admin_all_users():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id,username,email,full_name,status,created_at FROM users WHERE role='user'")
    users = cursor.fetchall()
    conn.close()

    return render_template("admin_all_users.html", users=users)


# ---------------------- ADMIN PENDING USERS --------------------
@app.route("/admin_pending_users")
def admin_pending_users():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id,username,email,full_name,created_at FROM users WHERE status='pending'")
    pending = cursor.fetchall()
    conn.close()

    return render_template("admin_pending_users.html", pending_users=pending)


# ---------------------- ADMIN USER PROFILE --------------------
@app.route("/admin_user_profile/<int:user_id>")
def admin_user_profile(user_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    return render_template("admin_user_profile.html", user=user)


# ---------------------- APPROVE / RESTRICT USERS --------------------
@app.route("/approve_user/<int:user_id>")
def approve_user(user_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status='approved' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/restrict_user/<int:user_id>")
def restrict_user(user_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status='restricted' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))


# ---------------------- ADMIN FEEDBACK --------------------
@app.route("/admin_feedback")
def admin_feedback():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT feedback.id, users.username, feedback.feedback_type,
               feedback.rating, feedback.comments, feedback.created_at
        FROM feedback
        JOIN users ON feedback.user_id = users.id
        ORDER BY feedback.id DESC
    """)
    feedback_list = cursor.fetchall()
    conn.close()

    return render_template("admin_feedback.html", feedback=feedback_list)


# ---------------------- FEEDBACK GRAPH --------------------
@app.route("/admin_feedback_graph")
def admin_feedback_graph():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))
    return render_template("admin_feedback_graph.html")


@app.route("/feedback_stats")
def feedback_stats():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT feedback_type, COUNT(*) FROM feedback GROUP BY feedback_type")
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)


# ---------------------- USER DASHBOARD --------------------
@app.route("/user_dashboard")
def user_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("user_dashboard.html")


# ---------------------- USER REGISTER --------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"]
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (username,email,password,full_name,status)
            VALUES (?,?,?,?,?)
        """, (username, email, password, full_name, "pending"))

        conn.commit()
        conn.close()

        flash("Registration successful! Wait for admin approval.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------------- FEEDBACK SUBMIT --------------------
@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        fb_type = request.form["feedback_type"]
        rating = request.form["rating"]
        comments = request.form["comments"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO feedback (user_id, feedback_type, rating, comments)
            VALUES (?,?,?,?)
        """, (session["user_id"], fb_type, rating, comments))

        conn.commit()
        conn.close()

        flash("Feedback submitted successfully!", "success")
        return redirect(url_for("feedback"))

    return render_template("feedback.html")


# ---------------------- PROFILE --------------------
@app.route("/my_profile")
def my_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (session["user_id"],))
    user = cursor.fetchone()
    conn.close()

    return render_template("my_profile.html", user=user)


@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        full_name = request.form["full_name"]
        phone = request.form["phone"]
        address = request.form["address"]

        cursor.execute("""
            UPDATE users SET full_name=?, phone=?, address=? WHERE id=?
        """, (full_name, phone, address, session["user_id"]))

        conn.commit()
        conn.close()

        flash("Profile updated successfully!", "success")
        return redirect(url_for("my_profile"))

    cursor.execute("SELECT * FROM users WHERE id=?", (session["user_id"],))
    user = cursor.fetchone()
    conn.close()

    return render_template("edit_profile.html", user=user)


# ---------------------- CHANGE PASSWORD --------------------
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_pw = request.form["current_password"]
        new_pw = request.form["new_password"]
        confirm_pw = request.form["confirm_password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE id=?", (session["user_id"],))
        user = cursor.fetchone()

        if not check_password_hash(user[0], current_pw):
            flash("Current password incorrect!", "danger")
            conn.close()
            return redirect(url_for("change_password"))

        if new_pw != confirm_pw:
            flash("Passwords do not match!", "danger")
            conn.close()
            return redirect(url_for("change_password"))

        cursor.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new_pw), session["user_id"]))
        conn.commit()
        conn.close()

        flash("Password updated!", "success")
        return redirect(url_for("my_profile"))

    return render_template("change_password.html")


# ---------------------- STATIC PAGES --------------------
@app.route("/chatbot")
def chatbot():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("chatbot.html")


@app.route("/crop")
def crop():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("crop.html")


@app.route("/fertilizer")
def fertilizer():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("fertilizer.html")


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("history.html")


@app.route("/prediction")
def prediction():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("prediction.html")


@app.route("/contact_us")
def contact_us():
    return render_template("contact_us.html")


@app.route("/about_us")
def about_us():
    return render_template("about_us.html")


@app.route("/crop_advisor")
def crop_advisor():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("crop_advisor.html")


@app.route("/disease_detector")
def disease_detector():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("disease_detector.html")

# ---------------------- CHAT API -------------------------
# Chatbot page
@app.route("/chatbot")
def chatbot_page():  # renamed from chatbot() to chatbot_page()
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("chatbot.html")


# ---------------------- CHAT API -------------------------
@app.route("/chat_api", methods=["POST"])
def chat_api():
    if "user_id" not in session:
        return jsonify({"response": "Please login first."})

    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"response": "Please type a message."})

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are AgriBot, an expert agriculture assistant. "
                        "Reply in simple, clear, farmer-friendly language."
                    )
                },
                {"role": "user", "content": user_message}
            ]
        )

        bot_reply = completion.choices[0].message.content

        # Save chat to database
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (user_id, message, response) VALUES (?, ?, ?)",
            (session["user_id"], user_message, bot_reply)
        )
        conn.commit()
        conn.close()

        return jsonify({"response": bot_reply})

    except Exception as e:
     print("Chat API Error:", e)
     return jsonify({"response": f"AI is temporarily unavailable. Error: {e}"})

    
@app.route("/fertilizer_advisor")
def fertilizer_advisor():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("fertilizer_advisor.html")


# ---------------------- LOGOUT --------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------- MAIN --------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
