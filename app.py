import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user,
    UserMixin,
)
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------------------------------
# App and database setup
# --------------------------------------------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")

# Use Postgres if DATABASE_URL is set, otherwise fall back to local SQLite
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    # Render and some services provide postgres://, SQLAlchemy prefers postgresql+psycopg2://
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///ascend_internal.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


# --------------------------------------------------
# Models
# --------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="freelancer")  # "founder" or "freelancer"
    active = db.Column(db.Boolean, default=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    date_start = db.Column(db.Date, nullable=False)
    date_end = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200), nullable=True)

    sessions = db.relationship("Session", backref="event", lazy=True)


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    label = db.Column(db.String(100), nullable=False)  # e.g., "Day 1 AM"
    date = db.Column(db.Date, nullable=False)
    time_block = db.Column(db.String(20), nullable=True)  # "AM" or "PM"

    athlete_sessions = db.relationship("AthleteSession", backref="session", lazy=True)
    manpower_allocations = db.relationship("ManpowerAllocation", backref="session", lazy=True)


class Package(db.Model):
    __tablename__ = "packages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)


class Athlete(db.Model):
    __tablename__ = "athletes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    team = db.Column(db.String(150), nullable=True)
    weight_class = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.String(255), nullable=True)

    athlete_sessions = db.relationship("AthleteSession", backref="athlete", lazy=True)


class AthleteSession(db.Model):
    __tablename__ = "athlete_sessions"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey("athletes.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey("packages.id"), nullable=False)

    music_link = db.Column(db.String(255), nullable=True)
    music_start = db.Column(db.String(20), nullable=True)
    music_end = db.Column(db.String(20), nullable=True)
    paid = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(255), nullable=True)

    package = db.relationship("Package")


class SdCard(db.Model):
    __tablename__ = "sd_cards"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(50), nullable=False, unique=True)
    capacity_gb = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="available")  # available, checked_out, lost

    logs = db.relationship("SdCardLog", backref="sd_card", lazy=True)


class SdCardLog(db.Model):
    __tablename__ = "sd_card_logs"

    id = db.Column(db.Integer, primary_key=True)
    sd_card_id = db.Column(db.Integer, db.ForeignKey("sd_cards.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)

    purpose = db.Column(db.String(255), nullable=True)
    checked_out_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    returned_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    event = db.relationship("Event")
    session = db.relationship("Session")


class ManpowerAllocation(db.Model):
    __tablename__ = "manpower_allocations"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    role = db.Column(db.String(100), nullable=False)  # photographer, videographer, etc
    notes = db.Column(db.String(255), nullable=True)

    event = db.relationship("Event")
    user = db.relationship("User")


class EditTask(db.Model):
    __tablename__ = "edit_tasks"

    id = db.Column(db.Integer, primary_key=True)
    athlete_session_id = db.Column(db.Integer, db.ForeignKey("athlete_sessions.id"), nullable=False)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    type = db.Column(db.String(50), nullable=False)  # photos, highlight, static_video
    status = db.Column(db.String(50), nullable=False, default="not_started")
    deliverable_link = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    athlete_session = db.relationship("AthleteSession")
    assigned_to = db.relationship("User")


# --------------------------------------------------
# Login manager
# --------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --------------------------------------------------
# Role decorator
# --------------------------------------------------

def founder_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "founder":
            abort(403)
        return view_func(*args, **kwargs)
    return wrapper


# --------------------------------------------------
# Routes: auth
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email, active=True).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# --------------------------------------------------
# Routes: dashboard
# --------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    events = Event.query.order_by(Event.date_start.desc()).all()
    total_sd_cards = SdCard.query.count()
    sd_in_use = SdCard.query.filter_by(status="checked_out").count()
    pending_edits = EditTask.query.filter(EditTask.status != "sent_to_client").count()
    return render_template(
        "dashboard.html",
        events=events,
        total_sd_cards=total_sd_cards,
        sd_in_use=sd_in_use,
        pending_edits=pending_edits,
    )


# --------------------------------------------------
# Routes: SD cards
# --------------------------------------------------

@app.route("/sd-cards", methods=["GET", "POST"])
@login_required
def sd_cards_view():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_card" and current_user.role == "founder":
            label = request.form.get("label", "").strip()
            capacity_gb = request.form.get("capacity_gb", "").strip()

            if label:
                card = SdCard(label=label, capacity_gb=int(capacity_gb) if capacity_gb else None)
                db.session.add(card)
                db.session.commit()
                flash("SD card added", "success")
            else:
                flash("Label is required", "danger")

        elif action == "checkout":
            sd_card_id = request.form.get("sd_card_id")
            event_id = request.form.get("event_id") or None
            session_id = request.form.get("session_id") or None
            purpose = request.form.get("purpose", "")

            card = SdCard.query.get(sd_card_id)
            if card and card.status == "available":
                log = SdCardLog(
                    sd_card_id=card.id,
                    user_id=current_user.id,
                    event_id=int(event_id) if event_id else None,
                    session_id=int(session_id) if session_id else None,
                    purpose=purpose,
                )
                card.status = "checked_out"
                db.session.add(log)
                db.session.commit()
                flash("SD card checked out", "success")
            else:
                flash("Card not available", "danger")

        elif action == "return":
            log_id = request.form.get("log_id")
            log = SdCardLog.query.get(log_id)
            if log and log.returned_at is None:
                log.returned_at = datetime.utcnow()
                card = log.sd_card
                card.status = "available"
                db.session.commit()
                flash("SD card returned", "success")
            else:
                flash("Could not return card", "danger")

        return redirect(url_for("sd_cards_view"))

    events = Event.query.order_by(Event.date_start.desc()).all()
    sessions = Session.query.order_by(Session.date.asc()).all()
    sd_cards = SdCard.query.order_by(SdCard.label.asc()).all()
    open_logs = (
        SdCardLog.query.filter(SdCardLog.returned_at.is_(None))
        .order_by(SdCardLog.checked_out_at.desc())
        .all()
    )

    return render_template(
        "sd_cards.html",
        sd_cards=sd_cards,
        open_logs=open_logs,
        events=events,
        sessions=sessions,
    )


# --------------------------------------------------
# Routes: Athletes and packages
# --------------------------------------------------

@app.route("/athletes", methods=["GET", "POST"])
@login_required
def athletes_view():
    if request.method == "POST" and current_user.role == "founder":
        action = request.form.get("action")

        if action == "add_athlete_session":
            athlete_name = request.form.get("athlete_name", "").strip()
            team = request.form.get("team", "").strip()
            weight_class = request.form.get("weight_class", "").strip()
            notes = request.form.get("notes", "").strip()

            session_id = request.form.get("session_id")
            package_id = request.form.get("package_id")
            music_link = request.form.get("music_link", "").strip()
            music_start = request.form.get("music_start", "").strip()
            music_end = request.form.get("music_end", "").strip()
            paid = bool(request.form.get("paid"))

            if not (athlete_name and session_id and package_id):
                flash("Athlete name, session and package are required", "danger")
            else:
                athlete = Athlete.query.filter_by(name=athlete_name, team=team).first()
                if not athlete:
                    athlete = Athlete(
                        name=athlete_name,
                        team=team,
                        weight_class=weight_class,
                        notes=notes,
                    )
                    db.session.add(athlete)
                    db.session.flush()

                athlete_session = AthleteSession(
                    athlete_id=athlete.id,
                    session_id=int(session_id),
                    package_id=int(package_id),
                    music_link=music_link,
                    music_start=music_start,
                    music_end=music_end,
                    paid=paid,
                    notes=notes,
                )
                db.session.add(athlete_session)
                db.session.commit()
                flash("Athlete session saved", "success")

        return redirect(url_for("athletes_view"))

    events = Event.query.order_by(Event.date_start.desc()).all()
    sessions = Session.query.order_by(Session.date.asc()).all()
    packages = Package.query.order_by(Package.name.asc()).all()

    selected_event_id = request.args.get("event_id", type=int)
    selected_session_id = request.args.get("session_id", type=int)

    query = AthleteSession.query.join(Athlete).join(Session).join(Event)
    if selected_event_id:
        query = query.filter(Event.id == selected_event_id)
    if selected_session_id:
        query = query.filter(Session.id == selected_session_id)

    athlete_sessions = query.order_by(Session.date.asc(), Athlete.name.asc()).all()

    return render_template(
        "athletes.html",
        events=events,
        sessions=sessions,
        packages=packages,
        athlete_sessions=athlete_sessions,
        selected_event_id=selected_event_id,
        selected_session_id=selected_session_id,
    )


@app.route("/session-athletes")
@login_required
def session_athletes_view():
    session_id = request.args.get("session_id", type=int)
    if not session_id:
        flash("Select a session", "warning")
        return redirect(url_for("athletes_view"))

    session_obj = Session.query.get_or_404(session_id)
    athlete_sessions = (
        AthleteSession.query.filter_by(session_id=session_id)
        .join(Athlete)
        .join(Package)
        .order_by(Athlete.name.asc())
        .all()
    )

    return render_template(
        "session_athletes.html",
        session=session_obj,
        athlete_sessions=athlete_sessions,
    )


# --------------------------------------------------
# Routes: manpower planning
# --------------------------------------------------

@app.route("/manpower", methods=["GET", "POST"])
@login_required
def manpower_view():
    if request.method == "POST" and current_user.role == "founder":
        event_id = request.form.get("event_id", type=int)
        session_id = request.form.get("session_id", type=int)
        user_id = request.form.get("user_id", type=int)
        role = request.form.get("role", "").strip()
        notes = request.form.get("notes", "").strip()

        if event_id and session_id and user_id and role:
            allocation = ManpowerAllocation(
                event_id=event_id,
                session_id=session_id,
                user_id=user_id,
                role=role,
                notes=notes,
            )
            db.session.add(allocation)
            db.session.commit()
            flash("Manpower allocation added", "success")
        else:
            flash("Event, session, user and role are required", "danger")

        return redirect(url_for("manpower_view"))

    events = Event.query.order_by(Event.date_start.desc()).all()
    sessions = Session.query.order_by(Session.date.asc()).all()
    users = User.query.filter_by(active=True).order_by(User.name.asc()).all()
    allocations = (
        ManpowerAllocation.query.join(Session).join(Event).join(User)
        .order_by(Session.date.asc(), Session.label.asc())
        .all()
    )

    return render_template(
        "manpower.html",
        events=events,
        sessions=sessions,
        users=users,
        allocations=allocations,
    )


# --------------------------------------------------
# Routes: edit tracking
# --------------------------------------------------

@app.route("/edits", methods=["GET", "POST"])
@login_required
def edits_view():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_task" and current_user.role == "founder":
            athlete_session_id = request.form.get("athlete_session_id", type=int)
            assigned_to_user_id = request.form.get("assigned_to_user_id", type=int)
            edit_type = request.form.get("type", "").strip()

            if athlete_session_id and assigned_to_user_id and edit_type:
                task = EditTask(
                    athlete_session_id=athlete_session_id,
                    assigned_to_user_id=assigned_to_user_id,
                    type=edit_type,
                )
                db.session.add(task)
                db.session.commit()
                flash("Edit task created", "success")
            else:
                flash("All fields are required", "danger")

        elif action == "update_status":
            task_id = request.form.get("task_id", type=int)
            status = request.form.get("status", "").strip()
            deliverable_link = request.form.get("deliverable_link", "").strip()

            task = EditTask.query.get(task_id)
            if not task:
                flash("Task not found", "danger")
            else:
                if current_user.role != "founder" and task.assigned_to_user_id != current_user.id:
                    abort(403)
                if status:
                    task.status = status
                task.deliverable_link = deliverable_link or task.deliverable_link
                task.updated_at = datetime.utcnow()
                db.session.commit()
                flash("Task updated", "success")

        return redirect(url_for("edits_view"))

    events = Event.query.order_by(Event.date_start.desc()).all()
    sessions = Session.query.order_by(Session.date.asc()).all()
    users = User.query.filter_by(active=True).order_by(User.name.asc()).all()

    selected_event_id = request.args.get("event_id", type=int)
    selected_session_id = request.args.get("session_id", type=int)
    selected_editor_id = request.args.get("editor_id", type=int)
    selected_status = request.args.get("status", type=str)

    query = EditTask.query.join(AthleteSession).join(Session).join(Event).join(User, EditTask.assigned_to)

    if selected_event_id:
        query = query.filter(Event.id == selected_event_id)
    if selected_session_id:
        query = query.filter(Session.id == selected_session_id)
    if selected_editor_id:
        query = query.filter(EditTask.assigned_to_user_id == selected_editor_id)
    if selected_status:
        query = query.filter(EditTask.status == selected_status)

    tasks = query.order_by(EditTask.updated_at.desc()).all()
    athlete_sessions = AthleteSession.query.join(Session).join(Event).all()

    return render_template(
        "edits.html",
        events=events,
        sessions=sessions,
        users=users,
        tasks=tasks,
        athlete_sessions=athlete_sessions,
        selected_event_id=selected_event_id,
        selected_session_id=selected_session_id,
        selected_editor_id=selected_editor_id,
        selected_status=selected_status,
    )

# --------------------------------------------------
# Admin: events and sessions
# --------------------------------------------------

@app.route("/admin/events", methods=["GET", "POST"])
@login_required
@founder_required
def manage_events():
    from datetime import datetime as _dt

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_event":
            name = request.form.get("name", "").strip()
            date_start_str = request.form.get("date_start", "").strip()
            date_end_str = request.form.get("date_end", "").strip()
            location = request.form.get("location", "").strip()

            try:
                date_start = _dt.strptime(date_start_str, "%Y-%m-%d").date()
                date_end = _dt.strptime(date_end_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid dates for event", "danger")
                return redirect(url_for("manage_events"))

            if not name:
                flash("Event name is required", "danger")
            else:
                event = Event(name=name, date_start=date_start, date_end=date_end, location=location)
                db.session.add(event)
                db.session.commit()
                flash("Event created", "success")

        elif action == "add_session":
            event_id = request.form.get("event_id", type=int)
            label = request.form.get("label", "").strip()
            date_str = request.form.get("date", "").strip()
            time_block = request.form.get("time_block", "").strip()  # AM / PM or empty

            if not (event_id and label and date_str):
                flash("Event, label and date are required for session", "danger")
                return redirect(url_for("manage_events"))

            try:
                date = _dt.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid session date", "danger")
                return redirect(url_for("manage_events"))

            session = Session(
                event_id=event_id,
                label=label,
                date=date,
                time_block=time_block or None,
            )
            db.session.add(session)
            db.session.commit()
            flash("Session created", "success")

        return redirect(url_for("manage_events"))

    events = Event.query.order_by(Event.date_start.desc()).all()
    # sessions accessible via e.sessions in template
    return render_template("admin_events.html", events=events)


# --------------------------------------------------
# Admin: packages
# --------------------------------------------------

@app.route("/admin/packages", methods=["GET", "POST"])
@login_required
@founder_required
def manage_packages():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Package name is required", "danger")
        else:
            pkg = Package(name=name, description=description)
            db.session.add(pkg)
            db.session.commit()
            flash("Package created", "success")

        return redirect(url_for("manage_packages"))

    packages = Package.query.order_by(Package.name.asc()).all()
    return render_template("admin_packages.html", packages=packages)


# --------------------------------------------------
# Admin: users
# --------------------------------------------------

@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@founder_required
def manage_users():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_user":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "freelancer")
            active = bool(request.form.get("active"))

            if not (name and email and password):
                flash("Name, email and password are required", "danger")
            else:
                existing = User.query.filter_by(email=email).first()
                if existing:
                    flash("User with that email already exists", "danger")
                else:
                    user = User(name=name, email=email, role=role, active=active)
                    user.set_password(password)
                    db.session.add(user)
                    db.session.commit()
                    flash("User created", "success")

        elif action == "toggle_active":
            user_id = request.form.get("user_id", type=int)
            user = User.query.get(user_id)
            if user:
                user.active = not user.active
                db.session.commit()
                flash("User status updated", "success")
            else:
                flash("User not found", "danger")

        elif action == "change_role":
            user_id = request.form.get("user_id", type=int)
            new_role = request.form.get("role", "").strip()
            user = User.query.get(user_id)
            if user and new_role in ["founder", "freelancer"]:
                user.role = new_role
                db.session.commit()
                flash("User role updated", "success")
            else:
                flash("Could not change role", "danger")

        return redirect(url_for("manage_users"))

    users = User.query.order_by(User.name.asc()).all()
    return render_template("admin_users.html", users=users)

# --------------------------------------------------
# CLI util to create tables
# --------------------------------------------------

@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Database initialised.")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
