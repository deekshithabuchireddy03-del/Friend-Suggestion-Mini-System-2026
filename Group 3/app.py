
import sqlite3
from pathlib import Path
from collections import deque
from functools import wraps

from flask import (
    Flask, request, redirect, url_for,
    session, flash, g, render_template_string
)

from werkzeug.security import generate_password_hash, check_password_hash


# ---------------- APPLICATION SETUP ----------------

DB_FILE = Path(__file__).with_name("students_network.db")

app = Flask(__name__)
app.secret_key = "friend-suggestion-secret-key"


# ---------------- GRAPH IMPLEMENTATION ----------------

class Graph:

    def __init__(self):
        self.adjacency_list = {}

    def add_student(self, name):
        self.adjacency_list.setdefault(name, [])

    def add_connection(self, a, b):

        if a == b:
            return

        self.add_student(a)
        self.add_student(b)

        if b not in self.adjacency_list[a]:
            self.adjacency_list[a].append(b)

        if a not in self.adjacency_list[b]:
            self.adjacency_list[b].append(a)

    def degree(self, name):
        return len(self.adjacency_list.get(name, []))

    def mutual_connections(self, a, b):

        return sorted(
            set(self.adjacency_list.get(a, []))
            &
            set(self.adjacency_list.get(b, []))
        )

    def suggest_students(self, name):

        direct = set(self.adjacency_list.get(name, []))
        candidates = set()

        for friend in direct:

            for person in self.adjacency_list.get(friend, []):

                if person != name and person not in direct:
                    candidates.add(person)

        result = []

        for person in candidates:

            mutual = direct & set(
                self.adjacency_list.get(person, [])
            )

            result.append((person, len(mutual)))

        return sorted(
            result,
            key=lambda x: (-x[1], x[0].lower())
        )

    def shortest_path(self, start, target):

        if start not in self.adjacency_list:
            return None

        if target not in self.adjacency_list:
            return None

        queue = deque([(start, [start])])
        visited = {start}

        while queue:

            current, path = queue.popleft()

            if current == target:
                return path

            for neighbor in self.adjacency_list[current]:

                if neighbor not in visited:

                    visited.add(neighbor)

                    queue.append(
                        (neighbor, path + [neighbor])
                    )

        return None


# ---------------- DATABASE CONNECTION ----------------

def connect_db():

    if "db" not in g:

        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row

        g.db.execute("PRAGMA foreign_keys=ON")

    return g.db


@app.teardown_appcontext
def close_db(error=None):

    db = g.pop("db", None)

    if db:
        db.close()


# ---------------- CREATE DATABASE TABLES ----------------

def initialize_database():

    db = sqlite3.connect(DB_FILE)

    db.execute("PRAGMA foreign_keys=ON")

    db.executescript("""

    CREATE TABLE IF NOT EXISTS users(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE NOT NULL,

        full_name TEXT NOT NULL,

        password TEXT NOT NULL

    );


    CREATE TABLE IF NOT EXISTS connections(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        sender_id INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,

        receiver_id INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,

        status TEXT NOT NULL DEFAULT 'pending',

        UNIQUE(sender_id, receiver_id)

    );


    CREATE TABLE IF NOT EXISTS posts(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,

        content TEXT NOT NULL,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

    );

    """)

    db.commit()
    db.close()


# ---------------- LOAD GRAPH FROM DATABASE ----------------

def load_graph(db):

    graph = Graph()

    users = db.execute(
        "SELECT username FROM users"
    ).fetchall()

    for row in users:
        graph.add_student(row["username"])

    connections = db.execute("""

        SELECT
            a.username AS u,
            b.username AS v

        FROM connections c

        JOIN users a ON a.id = c.sender_id

        JOIN users b ON b.id = c.receiver_id

        WHERE c.status = 'accepted'

    """).fetchall()

    for row in connections:

        graph.add_connection(
            row["u"],
            row["v"]
        )

    return graph


# ---------------- CURRENT USER ----------------

def me():

    if "user_id" not in session:
        return None

    return connect_db().execute(

        "SELECT * FROM users WHERE id=?",

        (session["user_id"],)

    ).fetchone()


# ---------------- LOGIN PROTECTION ----------------

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not me():

            flash("Please log in first.")

            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapper


# ---------------- WEBSITE DESIGN ----------------

LAYOUT = """

<!DOCTYPE html>

<html>

<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>{{ title }}</title>

<style>

body {

    font-family: Arial;

    margin: 0;

    background: #f3f6fa;

    color: #263238;

}

header {

    background: #245b78;

    color: white;

    padding: 17px 5%;

    display: flex;

    justify-content: space-between;

    flex-wrap: wrap;

}

header a {

    color: white;

    margin-left: 12px;

    text-decoration: none;

}

main {

    max-width: 900px;

    margin: 25px auto;

    padding: 0 15px;

}

.card {

    background: white;

    padding: 20px;

    margin-bottom: 18px;

    border-radius: 12px;

    box-shadow: 0 2px 8px #0001;

}

h1, h2 {

    color: #245b78;

}

input, textarea {

    width: 100%;

    padding: 11px;

    margin: 7px 0 13px;

    box-sizing: border-box;

    border: 1px solid #ccd5df;

    border-radius: 6px;

}

button, .btn {

    background: #27845b;

    color: white;

    border: 0;

    padding: 10px 15px;

    border-radius: 6px;

    text-decoration: none;

    cursor: pointer;

}

.btn2 {

    background: #245b78;

}

.item {

    padding: 12px 0;

    border-bottom: 1px solid #e5eaf0;

}

.muted {

    color: #667788;

    font-size: 14px;

}

.flash {

    background: #fff0c2;

    padding: 10px;

    margin-bottom: 12px;

    border-radius: 6px;

}

.tag {

    background: #e1f2e9;

    padding: 4px 8px;

    border-radius: 15px;

    font-size: 12px;

}

</style>

</head>

<body>

<header>

<b>Friend Suggestion Mini-System</b>

<nav>

{% if user %}

<a href="{{url_for('home')}}">Home</a>

<a href="{{url_for('students')}}">Students</a>

<a href="{{url_for('suggestions')}}">Suggestions</a>

<a href="{{url_for('requests')}}">Requests</a>

<a href="{{url_for('network')}}">Network</a>

<a href="{{url_for('logout')}}">Logout</a>

{% else %}

<a href="{{url_for('login')}}">Login</a>

<a href="{{url_for('register')}}">Register</a>

{% endif %}

</nav>

</header>

<main>

{% for msg in get_flashed_messages() %}

<div class="flash">{{msg}}</div>

{% endfor %}

{{body|safe}}

</main>

</body>

</html>

"""


def render_page(title, body, **values):

    return render_template_string(

        LAYOUT,

        title=title,

        body=render_template_string(body, **values),

        user=me()

    )


# ---------------- REGISTRATION ----------------

@app.route("/")

def index():

    return redirect(
        url_for("home" if me() else "login")
    )


@app.route("/register", methods=["GET", "POST"])

def register():

    if request.method == "POST":

        name = request.form.get(
            "full_name", ""
        ).strip()

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get("password", "")

        if not name or not username or not password:

            flash("Fill in all fields.")

        elif len(password) < 4:

            flash("Password must contain at least 4 characters.")

        else:

            try:

                db = connect_db()

                db.execute(

                    "INSERT INTO users(username,full_name,password) VALUES(?,?,?)",

                    (
                        username,
                        name,
                        generate_password_hash(password)
                    )

                )

                db.commit()

                flash("Registration successful. Please log in.")

                return redirect(url_for("login"))

            except sqlite3.IntegrityError:

                flash("Username already exists.")

    body = """

    <div class="card">

    <h1>Register</h1>

    <form method="post">

    Full Name

    <input name="full_name" required>

    Username

    <input name="username" required>

    Password

    <input type="password" name="password" required>

    <button>Create Account</button>

    </form>

    </div>

    """

    return render_page("Register", body)


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])

def login():

    if request.method == "POST":

        user = connect_db().execute(

            "SELECT * FROM users WHERE username=?",

            (request.form.get("username", "").strip(),)

        ).fetchone()

        if user and check_password_hash(

            user["password"],

            request.form.get("password", "")

        ):

            session.clear()

            session["user_id"] = user["id"]

            return redirect(url_for("home"))

        flash("Incorrect username or password.")

    body = """

    <div class="card">

    <h1>Student Login</h1>

    <form method="post">

    Username

    <input name="username" required>

    Password

    <input type="password" name="password" required>

    <button>Login</button>

    </form>

    <p class="muted">

    New student?

    <a href="/register">Register here</a>

    </p>

    </div>

    """

    return render_page("Login", body)


# ---------------- LOGOUT ----------------

@app.route("/logout")

def logout():

    session.clear()

    return redirect(url_for("login"))


# ---------------- HOME PAGE ----------------

@app.route("/home")

@login_required

def home():

    db = connect_db()

    user = me()

    graph = load_graph(db)

    friends = graph.adjacency_list.get(
        user["username"], []
    )

    posts = db.execute("""

        SELECT

        p.content,

        p.created_at,

        u.full_name,

        u.username

        FROM posts p

        JOIN users u ON u.id = p.user_id

        WHERE p.user_id = ?

        OR p.user_id IN (

            SELECT CASE

            WHEN sender_id = ? THEN receiver_id

            ELSE sender_id

            END

            FROM connections

            WHERE status = 'accepted'

            AND (sender_id = ? OR receiver_id = ?)

        )

        ORDER BY p.created_at DESC

    """, (

        user["id"],
        user["id"],
        user["id"],
        user["id"]

    )).fetchall()

    body = """

    <div class="card">

    <h1>Welcome, {{user['full_name']}}!</h1>

    <p>

    Direct Connections:

    <span class="tag">{{count}}</span>

    </p>

    </div>


    <div class="card">

    <h2>Create a Post</h2>

    <form method="post" action="/post">

    <textarea

    name="content"

    rows="3"

    maxlength="1000"

    required

    placeholder="Write something...">

    </textarea>

    <button>Publish</button>

    </form>

    </div>


    <div class="card">

    <h2>Home Feed</h2>

    {% for p in posts %}

    <div class="item">

    <b>{{p['full_name']}}</b>

    <span class="muted">

    @{{p['username']}}

    · {{p['created_at']}}

    </span>

    <p>{{p['content']}}</p>

    </div>

    {% else %}

    <p class="muted">No posts to show.</p>

    {% endfor %}

    </div>

    """

    return render_page(

        "Home",

        body,

        user=user,

        count=len(friends),

        posts=posts

    )


# ---------------- CREATE POST ----------------

@app.route("/post", methods=["POST"])

@login_required

def post():

    content = request.form.get(
        "content", ""
    ).strip()

    if content:

        db = connect_db()

        db.execute(

            "INSERT INTO posts(user_id,content) VALUES(?,?)",

            (session["user_id"], content)

        )

        db.commit()

        flash("Post published.")

    return redirect(url_for("home"))


# ---------------- SEARCH STUDENTS ----------------

@app.route("/students")

@login_required

def students():

    query = request.args.get("q", "").strip()

    rows = connect_db().execute("""

        SELECT id, username, full_name

        FROM users

        WHERE id != ?

        AND (username LIKE ? OR full_name LIKE ?)

        ORDER BY full_name

    """, (

        session["user_id"],

        f"%{query}%",

        f"%{query}%"

    )).fetchall()

    body = """

    <div class="card">

    <h1>Search Students</h1>

    <form>

    <input

    name="q"

    value="{{q}}"

    placeholder="Search by name or username">

    <button>Search</button>

    </form>


    {% for p in people %}

    <div class="item">

    <b>{{p['full_name']}}</b>

    (@{{p['username']}})

    <a class="btn btn2"

    href="{{url_for('send_request',uid=p['id'])}}">

    Connect

    </a>

    </div>

    {% else %}

    <p>No students found.</p>

    {% endfor %}

    </div>

    """

    return render_page(

        "Students",

        body,

        people=rows,

        q=query

    )


# ---------------- SEND FRIEND REQUEST ----------------

@app.route("/connect/<int:uid>")

@login_required

def send_request(uid):

    db = connect_db()

    myid = session["user_id"]

    if uid == myid:

        flash("You cannot connect to yourself.")

    else:

        exists = db.execute("""

            SELECT id FROM connections

            WHERE

            (sender_id=? AND receiver_id=?)

            OR

            (sender_id=? AND receiver_id=?)

        """, (

            myid, uid,

            uid, myid

        )).fetchone()

        target = db.execute(

            "SELECT id FROM users WHERE id=?",

            (uid,)

        ).fetchone()

        if not target:

            flash("Student not found.")

        elif exists:

            flash("A request or connection already exists.")

        else:

            db.execute("""

                INSERT INTO connections

                (sender_id,receiver_id,status)

                VALUES(?,?,'pending')

            """, (myid, uid))

            db.commit()

            flash("Connection request sent.")

    return redirect(url_for("students"))


# ---------------- VIEW REQUESTS ----------------

@app.route("/requests")

@login_required

def requests():

    rows = connect_db().execute("""

        SELECT

        c.id,

        u.full_name,

        u.username

        FROM connections c

        JOIN users u ON u.id = c.sender_id

        WHERE c.receiver_id = ?

        AND c.status = 'pending'

    """, (session["user_id"],)).fetchall()

    body = """

    <div class="card">

    <h1>Incoming Requests</h1>

    {% for r in rows %}

    <div class="item">

    <b>{{r['full_name']}}</b>

    (@{{r['username']}})

    <a class="btn"

    href="{{url_for('accept',rid=r['id'])}}">

    Accept

    </a>

    </div>

    {% else %}

    <p>No pending requests.</p>

    {% endfor %}

    </div>

    """

    return render_page("Requests", body, rows=rows)


# ---------------- ACCEPT REQUEST ----------------

@app.route("/accept/<int:rid>")

@login_required

def accept(rid):

    db = connect_db()

    result = db.execute("""

        UPDATE connections

        SET status='accepted'

        WHERE id=?

        AND receiver_id=?

        AND status='pending'

    """, (rid, session["user_id"]))

    db.commit()

    if result.rowcount:

        flash("Connection accepted.")

    else:

        flash("Request not found.")

    return redirect(url_for("requests"))


# ---------------- FRIEND SUGGESTIONS ----------------

@app.route("/suggestions")

@login_required

def suggestions():

    graph = load_graph(connect_db())

    found = graph.suggest_students(
        me()["username"]
    )

    body = """

    <div class="card">

    <h1>Friend Suggestions</h1>

    <p class="muted">

    Friends of friends, ranked by number of mutual connections.

    </p>

    {% for name,n in items %}

    <div class="item">

    <b>{{name}}</b>

    <span class="tag">

    {{n}} mutual connection(s)

    </span>

    <a href="{{url_for('details',username=name)}}">

    View

    </a>

    </div>

    {% else %}

    <p>No suggestions yet. Connect with students first.</p>

    {% endfor %}

    </div>

    """

    return render_page(

        "Suggestions",

        body,

        items=found

    )


# ---------------- CONNECTION DETAILS ----------------

@app.route("/details/<username>")

@login_required

def details(username):

    graph = load_graph(connect_db())

    mine = me()["username"]

    mutual = graph.mutual_connections(
        mine, username
    )

    path = graph.shortest_path(
        mine, username
    )

    body = """

    <div class="card">

    <h1>Connection Details: {{other}}</h1>

    <h2>Mutual Connections</h2>

    {% for x in mutual %}

    <div class="item">{{x}}</div>

    {% else %}

    <p>No mutual connections.</p>

    {% endfor %}


    <h2>BFS Shortest Path</h2>

    {% if path %}

    <p>{{path|join(' → ')}}</p>

    <p>

    Degree of separation:

    <b>{{path|length-1}}</b>

    </p>

    {% else %}

    <p>No path exists.</p>

    {% endif %}

    </div>

    """

    return render_page(

        "Connection Details",

        body,

        other=username,

        mutual=mutual,

        path=path

    )


# ---------------- NETWORK DISPLAY ----------------

@app.route("/network")

@login_required

def network():

    graph = load_graph(connect_db())

    rows = [

        (

            name,

            ", ".join(sorted(friends)) or "No connections",

            graph.degree(name)

        )

        for name, friends in sorted(
            graph.adjacency_list.items()
        )

    ]

    body = """

    <div class="card">

    <h1>Graph Adjacency List</h1>

    <p class="muted">

    Only accepted connections are represented as undirected edges.

    </p>

    {% for name,friends,d in rows %}

    <div class="item">

    <b>{{name}}</b> : {{friends}}

    <span class="tag">Degree {{d}}</span>

    </div>

    {% endfor %}

    </div>

    """

    return render_page(

        "Network",

        body,

        rows=rows

    )


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":

    initialize_database()

    print("Starting Friend Suggestion Mini-System...")

    print("Open http://127.0.0.1:5000")

    app.run(debug=True)
