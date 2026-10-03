from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_socketio import SocketIO, join_room, leave_room, emit
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.secret_key = "codealpha_task4_secret_key_change_this"

# threading mode avoids requiring an extra async server for this beginner project.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DATABASE = "communication.db"
UPLOAD_FOLDER = os.path.join("static", "uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

active_rooms = {}


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = get_db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        owner_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS room_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at TEXT NOT NULL,
        UNIQUE(room_id, user_id),
        FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()
    return user


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


def generate_room_code():
    while True:
        code = uuid.uuid4().hex[:8].upper()
        conn = get_db()
        exists = conn.execute(
            "SELECT id FROM rooms WHERE room_code = ?",
            (code,)
        ).fetchone()
        conn.close()

        if not exists:
            return code


def user_has_room_access(conn, room_id, user_id):
    room = conn.execute(
        "SELECT owner_id FROM rooms WHERE id = ?",
        (room_id,)
    ).fetchone()

    if not room:
        return False

    if room["owner_id"] == user_id:
        return True

    member = conn.execute("""
        SELECT id FROM room_members
        WHERE room_id = ? AND user_id = ?
    """, (room_id, user_id)).fetchone()

    return member is not None


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if len(username) < 3:
            flash("Username must have at least 3 characters.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must have at least 6 characters.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        conn = get_db()

        exists = conn.execute("""
            SELECT id FROM users
            WHERE username = ? OR email = ?
        """, (username, email)).fetchone()

        if exists:
            conn.close()
            flash("Username or email already exists.", "danger")
            return render_template("register.html")

        conn.execute("""
            INSERT INTO users (username, email, password, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            email,
            generate_password_hash(password),
            now()
        ))

        conn.commit()
        conn.close()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    rooms = conn.execute("""
        SELECT
            r.*,
            u.username AS owner_name,
            (
                SELECT COUNT(*)
                FROM room_members rm
                WHERE rm.room_id = r.id
            ) AS member_count
        FROM rooms r
        JOIN users u ON u.id = r.owner_id
        WHERE r.owner_id = ?
           OR EXISTS (
               SELECT 1
               FROM room_members rm
               WHERE rm.room_id = r.id AND rm.user_id = ?
           )
        ORDER BY r.id DESC
    """, (session["user_id"], session["user_id"])).fetchall()

    conn.close()

    return render_template("dashboard.html", rooms=rooms)


@app.route("/room/create", methods=["GET", "POST"])
@login_required
def create_room():
    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Room name is required.", "danger")
            return render_template("create_room.html")

        room_code = generate_room_code()

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO rooms
            (room_code, name, owner_id, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            room_code,
            name,
            session["user_id"],
            now()
        ))

        room_id = cursor.lastrowid

        conn.execute("""
            INSERT INTO room_members
            (room_id, user_id, joined_at)
            VALUES (?, ?, ?)
        """, (
            room_id,
            session["user_id"],
            now()
        ))

        conn.commit()
        conn.close()

        flash("Meeting room created.", "success")
        return redirect(url_for("meeting", room_code=room_code))

    return render_template("create_room.html")


@app.route("/room/join", methods=["POST"])
@login_required
def join_room_by_code():
    room_code = request.form.get("room_code", "").strip().upper()

    if not room_code:
        flash("Enter a room code.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()

    room = conn.execute(
        "SELECT * FROM rooms WHERE room_code = ?",
        (room_code,)
    ).fetchone()

    if not room:
        conn.close()
        flash("Room not found.", "danger")
        return redirect(url_for("dashboard"))

    conn.execute("""
        INSERT OR IGNORE INTO room_members
        (room_id, user_id, joined_at)
        VALUES (?, ?, ?)
    """, (
        room["id"],
        session["user_id"],
        now()
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("meeting", room_code=room_code))


@app.route("/meeting/<room_code>")
@login_required
def meeting(room_code):
    conn = get_db()

    room = conn.execute("""
        SELECT r.*, u.username AS owner_name
        FROM rooms r
        JOIN users u ON u.id = r.owner_id
        WHERE r.room_code = ?
    """, (room_code.upper(),)).fetchone()

    if not room:
        conn.close()
        flash("Meeting room not found.", "danger")
        return redirect(url_for("dashboard"))

    # Joining from a shared code automatically gives the user access.
    conn.execute("""
        INSERT OR IGNORE INTO room_members
        (room_id, user_id, joined_at)
        VALUES (?, ?, ?)
    """, (
        room["id"],
        session["user_id"],
        now()
    ))
    conn.commit()

    messages = conn.execute("""
        SELECT m.*, u.username
        FROM messages m
        JOIN users u ON u.id = m.user_id
        WHERE m.room_id = ?
        ORDER BY m.id ASC
        LIMIT 100
    """, (room["id"],)).fetchall()

    members = conn.execute("""
        SELECT u.username
        FROM room_members rm
        JOIN users u ON u.id = rm.user_id
        WHERE rm.room_id = ?
        ORDER BY u.username
    """, (room["id"],)).fetchall()

    conn.close()

    return render_template(
        "meeting.html",
        room=room,
        messages=messages,
        members=members,
        room_code=room_code.upper()
    )


@app.route("/upload/<room_code>", methods=["POST"])
@login_required
def upload_file(room_code):
    conn = get_db()

    room = conn.execute(
        "SELECT id FROM rooms WHERE room_code = ?",
        (room_code.upper(),)
    ).fetchone()

    if not room or not user_has_room_access(
        conn, room["id"], session["user_id"]
    ):
        conn.close()
        return jsonify({"success": False, "message": "Access denied."}), 403

    uploaded = request.files.get("file")

    if not uploaded or uploaded.filename == "":
        conn.close()
        return jsonify({"success": False, "message": "No file selected."}), 400

    original_name = secure_filename(uploaded.filename)

    if not original_name:
        conn.close()
        return jsonify({"success": False, "message": "Invalid filename."}), 400

    unique_name = (
        datetime.now().strftime("%Y%m%d%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
        + "_"
        + original_name
    )

    uploaded.save(
        os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    )

    conn.close()

    return jsonify({
        "success": True,
        "filename": original_name,
        "url": url_for("download_file", filename=unique_name)
    })


@app.route("/uploads/<filename>")
@login_required
def download_file(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=False
    )


@app.route("/api/room/<room_code>/messages")
@login_required
def room_messages(room_code):
    conn = get_db()

    room = conn.execute(
        "SELECT id FROM rooms WHERE room_code = ?",
        (room_code.upper(),)
    ).fetchone()

    if not room or not user_has_room_access(
        conn, room["id"], session["user_id"]
    ):
        conn.close()
        return jsonify({"success": False}), 403

    messages = conn.execute("""
        SELECT m.id, m.message, m.created_at, u.username
        FROM messages m
        JOIN users u ON u.id = m.user_id
        WHERE m.room_id = ?
        ORDER BY m.id ASC
        LIMIT 100
    """, (room["id"],)).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "messages": [dict(row) for row in messages]
    })


@socketio.on("join_meeting")
def socket_join(data):
    if "user_id" not in session:
        return

    room_code = str(data.get("room", "")).upper()

    conn = get_db()
    room = conn.execute(
        "SELECT id FROM rooms WHERE room_code = ?",
        (room_code,)
    ).fetchone()

    if not room or not user_has_room_access(
        conn, room["id"], session["user_id"]
    ):
        conn.close()
        return

    username = session["username"]
    join_room(room_code)

    if room_code not in active_rooms:
        active_rooms[room_code] = {}

    active_rooms[room_code][request.sid] = {
        "username": username,
        "user_id": session["user_id"]
    }

    emit("room_users", {
        "users": list(active_rooms[room_code].values())
    }, to=room_code)

    emit("system_message", {
        "message": f"{username} joined the meeting."
    }, to=room_code)

    conn.close()


@socketio.on("leave_meeting")
def socket_leave(data):
    if "user_id" not in session:
        return

    room_code = str(data.get("room", "")).upper()
    username = session["username"]

    if room_code in active_rooms:
        active_rooms[room_code].pop(request.sid, None)

        if not active_rooms[room_code]:
            active_rooms.pop(room_code, None)

    leave_room(room_code)

    emit("room_users", {
        "users": list(active_rooms.get(room_code, {}).values())
    }, to=room_code)

    emit("system_message", {
        "message": f"{username} left the meeting."
    }, to=room_code)


@socketio.on("chat_message")
def socket_chat(data):
    if "user_id" not in session:
        return

    room_code = str(data.get("room", "")).upper()
    message = str(data.get("message", "")).strip()

    if not message:
        return

    message = message[:1000]

    conn = get_db()

    room = conn.execute(
        "SELECT id FROM rooms WHERE room_code = ?",
        (room_code,)
    ).fetchone()

    if not room or not user_has_room_access(
        conn, room["id"], session["user_id"]
    ):
        conn.close()
        return

    conn.execute("""
        INSERT INTO messages
        (room_id, user_id, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        room["id"],
        session["user_id"],
        message,
        now()
    ))

    conn.commit()
    conn.close()

    emit("chat_message", {
        "username": session["username"],
        "message": message,
        "created_at": now()
    }, to=room_code)


# WebRTC signaling events.
@socketio.on("webrtc_offer")
def webrtc_offer(data):
    if "user_id" not in session:
        return

    target = data.get("target")

    if target:
        emit("webrtc_offer", {
            "offer": data.get("offer"),
            "from": request.sid,
            "username": session["username"]
        }, to=target)


@socketio.on("webrtc_answer")
def webrtc_answer(data):
    if "user_id" not in session:
        return

    target = data.get("target")

    if target:
        emit("webrtc_answer", {
            "answer": data.get("answer"),
            "from": request.sid
        }, to=target)


@socketio.on("ice_candidate")
def ice_candidate(data):
    if "user_id" not in session:
        return

    target = data.get("target")

    if target:
        emit("ice_candidate", {
            "candidate": data.get("candidate"),
            "from": request.sid
        }, to=target)


@socketio.on("request_connection")
def request_connection(data):
    if "user_id" not in session:
        return

    target = data.get("target")

    if target:
        emit("connection_request", {
            "from": request.sid,
            "username": session["username"]
        }, to=target)


@socketio.on("whiteboard_draw")
def whiteboard_draw(data):
    if "user_id" not in session:
        return

    room_code = str(data.get("room", "")).upper()

    emit("whiteboard_draw", {
        "x": data.get("x"),
        "y": data.get("y"),
        "lastX": data.get("lastX"),
        "lastY": data.get("lastY"),
        "drawing": data.get("drawing"),
        "color": data.get("color"),
        "size": data.get("size")
    }, to=room_code, include_self=False)


@socketio.on("whiteboard_clear")
def whiteboard_clear(data):
    if "user_id" not in session:
        return

    room_code = str(data.get("room", "")).upper()
    emit("whiteboard_clear", {}, to=room_code, include_self=False)


@socketio.on("disconnect")
def socket_disconnect():
    for room_code, users in list(active_rooms.items()):
        if request.sid in users:
            username = users[request.sid]["username"]
            users.pop(request.sid, None)

            emit("room_users", {
                "users": list(users.values())
            }, to=room_code)

            emit("system_message", {
                "message": f"{username} disconnected."
            }, to=room_code)

            if not users:
                active_rooms.pop(room_code, None)


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)
