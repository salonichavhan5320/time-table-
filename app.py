# -*- coding: utf-8 -*-
"""
RouteCraft - Advanced Smart Travel Planner
Main Flask Application
"""
import os, json, secrets, requests
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_file, abort)
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import config

# ── App factory ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(config['development'])

mysql = MySQL(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS'])

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated

def get_db():
    cur = mysql.connection.cursor()
    return cur

def query_db(sql, args=(), one=False, commit=False):
    cur = get_db()
    cur.execute(sql, args)
    if commit:
        mysql.connection.commit()
        return cur.lastrowid
    rv = cur.fetchone() if one else cur.fetchall()
    cur.close()
    return rv

# ── Context processor ─────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    unread = 0
    if 'user_id' in session:
        try:
            row = query_db(
                "SELECT COUNT(*) as cnt FROM notifications WHERE user_id=%s AND is_read=0",
                (session['user_id'],), one=True)
            unread = row['cnt'] if row else 0
        except Exception:
            pass
    return dict(unread_notifications=unread, current_year=datetime.now().year)

# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500

# ═════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    destinations = query_db(
        "SELECT * FROM destinations ORDER BY rating DESC LIMIT 6")
    return render_template('index.html', destinations=destinations)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name     = request.form.get('name',     '').strip()
        email    = request.form.get('email',    '').strip().lower()
        password = request.form.get('password', '').strip()
        phone    = request.form.get('phone',    '').strip()

        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('register.html')

        existing = query_db("SELECT id FROM users WHERE email=%s", (email,), one=True)
        if existing:
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('login'))

        pw_hash = generate_password_hash(password)
        query_db(
            "INSERT INTO users (name, email, password_hash, phone) VALUES (%s,%s,%s,%s)",
            (name, email, pw_hash, phone), commit=True)
        flash('Account created! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email    = request.form.get('email',    '').strip().lower()
        password = request.form.get('password', '').strip()

        user = query_db("SELECT * FROM users WHERE email=%s AND is_active=1",
                        (email,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']

    trips = query_db(
        "SELECT * FROM trips WHERE user_id=%s ORDER BY created_at DESC LIMIT 10", (uid,))

    upcoming = query_db(
        "SELECT * FROM trips WHERE user_id=%s AND start_date >= CURDATE() "
        "AND status='planning' ORDER BY start_date ASC LIMIT 5", (uid,))

    stats = query_db(
        "SELECT COUNT(*) as total_trips, "
        "SUM(total_budget) as total_spent, "
        "SUM(duration_days) as total_days "
        "FROM trips WHERE user_id=%s", (uid,), one=True)

    recent_expenses = query_db(
        "SELECT e.*, t.title as trip_title FROM expenses e "
        "JOIN trips t ON e.trip_id=t.id "
        "WHERE e.user_id=%s ORDER BY e.expense_date DESC LIMIT 5", (uid,))

    notifications = query_db(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 5",
        (uid,))

    # Expense chart data (last 6 months)
    chart_data = query_db(
        "SELECT DATE_FORMAT(expense_date,'%%b %%Y') as month, "
        "DATE_FORMAT(expense_date,'%%Y-%%m') as month_key, "
        "SUM(amount) as total FROM expenses "
        "WHERE user_id=%s AND expense_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) "
        "GROUP BY DATE_FORMAT(expense_date,'%%Y-%%m'), DATE_FORMAT(expense_date,'%%b %%Y') "
        "ORDER BY month_key ASC", (uid,))

    category_data = query_db(
        "SELECT category, SUM(amount) as total FROM expenses "
        "WHERE user_id=%s GROUP BY category", (uid,))

    return render_template('dashboard.html',
        trips=trips, upcoming=upcoming, stats=stats,
        recent_expenses=recent_expenses, notifications=notifications,
        chart_data=json.dumps([dict(r) for r in chart_data] if chart_data else []),
        category_data=json.dumps([dict(r) for r in category_data] if category_data else []))

# ═════════════════════════════════════════════════════════════════════════════
# TRIP CRUD
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/trips')
@login_required
def trips():
    uid = session['user_id']
    all_trips = query_db(
        "SELECT * FROM trips WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    return render_template('trips.html', trips=all_trips)

@app.route('/trips/create', methods=['GET', 'POST'])
@login_required
def create_trip():
    uid = session['user_id']

    if request.method == 'POST':
        title        = request.form.get('title', '').strip()
        description  = request.form.get('description', '').strip()
        start_date   = request.form.get('start_date')
        end_date     = request.form.get('end_date')
        num_travelers= int(request.form.get('num_travelers', 1))
        total_budget = float(request.form.get('total_budget', 0))
        trip_type    = request.form.get('trip_type', 'solo')
        transport    = request.form.get('transport_pref', 'mixed')
        dest_ids     = request.form.getlist('destinations')

        if not title or not start_date or not end_date:
            flash('Title, start date and end date are required.', 'danger')
            return redirect(url_for('create_trip'))

        if start_date > end_date:
            flash('End date must be after start date.', 'danger')
            return redirect(url_for('create_trip'))

        trip_id = query_db(
            "INSERT INTO trips (user_id, title, description, start_date, end_date, "
            "num_travelers, total_budget, trip_type, transport_pref) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uid, title, description, start_date, end_date,
             num_travelers, total_budget, trip_type, transport), commit=True)

        for i, did in enumerate(dest_ids, 1):
            query_db(
                "INSERT INTO trip_destinations (trip_id, destination_id, visit_order) "
                "VALUES (%s,%s,%s)", (trip_id, did, i), commit=True)

        _generate_checklist(trip_id, uid, trip_type)
        flash('Trip created successfully!', 'success')
        return redirect(url_for('trip_detail', trip_id=trip_id))

    countries = query_db("SELECT DISTINCT country FROM destinations ORDER BY country")
    cities    = query_db("SELECT DISTINCT city, country FROM destinations ORDER BY country, city")
    all_destinations = query_db(
        "SELECT id, city, country, place_name, category, avg_cost_per_day, "
        "best_season, rating, image_url FROM destinations ORDER BY country, city, place_name")

    return render_template('create_trip.html',
                           countries=countries,
                           cities=cities,
                           all_destinations=all_destinations,
                           today=date.today().isoformat())

@app.route('/trips/<int:trip_id>')
@login_required
def trip_detail(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    trip_dests = query_db(
        "SELECT td.*, d.city, d.place_name, d.image_url, d.latitude, d.longitude, "
        "d.avg_cost_per_day, d.description "
        "FROM trip_destinations td JOIN destinations d ON td.destination_id=d.id "
        "WHERE td.trip_id=%s ORDER BY td.visit_order", (trip_id,))

    itinerary = query_db(
        "SELECT * FROM itinerary WHERE trip_id=%s ORDER BY day_number, start_time",
        (trip_id,))

    expenses = query_db(
        "SELECT * FROM expenses WHERE trip_id=%s ORDER BY expense_date DESC", (trip_id,))

    expense_total = query_db(
        "SELECT SUM(amount) as total FROM expenses WHERE trip_id=%s",
        (trip_id,), one=True)

    checklist = query_db(
        "SELECT * FROM checklists WHERE trip_id=%s ORDER BY category, item",
        (trip_id,))

    members = query_db(
        "SELECT * FROM trip_members WHERE trip_id=%s", (trip_id,))

    budget_remaining = (trip['total_budget'] or 0) - (expense_total['total'] or 0)
    per_head = (trip['total_budget'] or 0) / max(trip['num_travelers'], 1)

    return render_template('trip_detail.html',
        trip=trip, trip_dests=trip_dests, itinerary=itinerary,
        expenses=expenses, expense_total=expense_total,
        checklist=checklist, members=members,
        budget_remaining=budget_remaining, per_head=per_head)

@app.route('/trips/<int:trip_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    if request.method == 'POST':
        title        = request.form.get('title', '').strip()
        description  = request.form.get('description', '').strip()
        start_date   = request.form.get('start_date')
        end_date     = request.form.get('end_date')
        num_travelers= int(request.form.get('num_travelers', 1))
        total_budget = float(request.form.get('total_budget', 0))
        trip_type    = request.form.get('trip_type', 'solo')
        transport    = request.form.get('transport_pref', 'mixed')
        status       = request.form.get('status', 'planning')

        query_db(
            "UPDATE trips SET title=%s, description=%s, start_date=%s, end_date=%s, "
            "num_travelers=%s, total_budget=%s, trip_type=%s, transport_pref=%s, status=%s "
            "WHERE id=%s AND user_id=%s",
            (title, description, start_date, end_date, num_travelers,
             total_budget, trip_type, transport, status, trip_id, uid), commit=True)

        flash('Trip updated successfully!', 'success')
        return redirect(url_for('trip_detail', trip_id=trip_id))

    return render_template('edit_trip.html', trip=trip)

@app.route('/trips/<int:trip_id>/delete', methods=['POST'])
@login_required
def delete_trip(trip_id):
    uid = session['user_id']
    query_db("DELETE FROM trips WHERE id=%s AND user_id=%s", (trip_id, uid), commit=True)
    flash('Trip deleted.', 'info')
    return redirect(url_for('trips'))

# ═════════════════════════════════════════════════════════════════════════════
# ITINERARY
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/trips/<int:trip_id>/itinerary')
@login_required
def itinerary(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    items = query_db(
        "SELECT * FROM itinerary WHERE trip_id=%s ORDER BY day_number, start_time",
        (trip_id,))

    # Group by day
    days = {}
    for item in (items or []):
        d = item['day_number']
        days.setdefault(d, []).append(item)

    return render_template('itinerary.html', trip=trip, days=days)

@app.route('/trips/<int:trip_id>/itinerary/generate', methods=['POST'])
@login_required
def generate_itinerary(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    # Clear existing
    query_db("DELETE FROM itinerary WHERE trip_id=%s", (trip_id,), commit=True)

    trip_dests = query_db(
        "SELECT d.place_name, d.city, d.description, d.avg_cost_per_day "
        "FROM trip_destinations td JOIN destinations d ON td.destination_id=d.id "
        "WHERE td.trip_id=%s ORDER BY td.visit_order", (trip_id,))

    duration = trip['duration_days'] or 1
    places   = list(trip_dests or [])
    start    = trip['start_date']

    activities_map = {
        'morning':   ['Breakfast at local cafe', 'Morning walk & sightseeing', 'Visit main attraction'],
        'afternoon': ['Lunch at popular restaurant', 'Explore local market', 'Museum / heritage visit'],
        'evening':   ['Sunset viewpoint', 'Street food exploration', 'Shopping & souvenirs'],
    }

    for day in range(1, duration + 1):
        current_date = start + timedelta(days=day - 1)
        place = places[(day - 1) % len(places)] if places else {'place_name': 'Free Day', 'city': ''}
        slot  = 9
        for period, acts in activities_map.items():
            for act in acts:
                query_db(
                    "INSERT INTO itinerary (trip_id, day_number, date, title, activity, "
                    "location, start_time, cost) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (trip_id, day, current_date,
                     f"Day {day} - {place['place_name']}",
                     act, place['city'],
                     f"{slot:02d}:00",
                     round((place.get('avg_cost_per_day') or 2000) / 9, 2)), commit=True)
                slot += 1

    flash('Itinerary generated successfully!', 'success')
    return redirect(url_for('itinerary', trip_id=trip_id))

# ═════════════════════════════════════════════════════════════════════════════
# EXPENSES
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/trips/<int:trip_id>/expenses', methods=['GET', 'POST'])
@login_required
def expenses(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    if request.method == 'POST':
        category     = request.form.get('category')
        title        = request.form.get('title', '').strip()
        amount       = float(request.form.get('amount', 0))
        expense_date = request.form.get('expense_date')
        notes        = request.form.get('notes', '').strip()

        query_db(
            "INSERT INTO expenses (trip_id, user_id, category, title, amount, expense_date, notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (trip_id, uid, category, title, amount, expense_date, notes), commit=True)

        # Update spent amount on trip
        query_db(
            "UPDATE trips SET spent_amount = ("
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE trip_id=%s) "
            "WHERE id=%s", (trip_id, trip_id), commit=True)

        flash('Expense added!', 'success')
        return redirect(url_for('expenses', trip_id=trip_id))

    all_expenses = query_db(
        "SELECT * FROM expenses WHERE trip_id=%s ORDER BY expense_date DESC", (trip_id,))

    totals = query_db(
        "SELECT category, SUM(amount) as total FROM expenses "
        "WHERE trip_id=%s GROUP BY category", (trip_id,))

    grand_total = query_db(
        "SELECT COALESCE(SUM(amount),0) as total FROM expenses WHERE trip_id=%s",
        (trip_id,), one=True)

    return render_template('expenses.html',
        trip=trip, expenses=all_expenses, totals=totals,
        grand_total=grand_total,
        budget_remaining=(trip['total_budget'] or 0) - (grand_total['total'] or 0),
        per_head=(trip['total_budget'] or 0) / max(trip['num_travelers'], 1),
        category_json=json.dumps([dict(r) for r in totals] if totals else []))

@app.route('/trips/<int:trip_id>/expenses/<int:exp_id>/delete', methods=['POST'])
@login_required
def delete_expense(trip_id, exp_id):
    uid = session['user_id']
    query_db("DELETE FROM expenses WHERE id=%s AND user_id=%s", (exp_id, uid), commit=True)
    query_db(
        "UPDATE trips SET spent_amount = ("
        "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE trip_id=%s) "
        "WHERE id=%s", (trip_id, trip_id), commit=True)
    flash('Expense removed.', 'info')
    return redirect(url_for('expenses', trip_id=trip_id))

# ═════════════════════════════════════════════════════════════════════════════
# CHECKLIST
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/trips/<int:trip_id>/checklist', methods=['GET', 'POST'])
@login_required
def checklist(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    if request.method == 'POST':
        item     = request.form.get('item', '').strip()
        category = request.form.get('category', 'general')
        if item:
            query_db(
                "INSERT INTO checklists (trip_id, user_id, item, category) VALUES (%s,%s,%s,%s)",
                (trip_id, uid, item, category), commit=True)
        return redirect(url_for('checklist', trip_id=trip_id))

    items = query_db(
        "SELECT * FROM checklists WHERE trip_id=%s ORDER BY category, item", (trip_id,))
    return render_template('checklist.html', trip=trip, items=items)

@app.route('/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist(item_id):
    query_db(
        "UPDATE checklists SET is_checked = NOT is_checked WHERE id=%s AND user_id=%s",
        (item_id, session['user_id']), commit=True)
    return jsonify({'status': 'ok'})

@app.route('/checklist/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_checklist_item(item_id):
    trip_id = request.form.get('trip_id')
    query_db("DELETE FROM checklists WHERE id=%s AND user_id=%s",
             (item_id, session['user_id']), commit=True)
    return redirect(url_for('checklist', trip_id=trip_id))

# ═════════════════════════════════════════════════════════════════════════════
# DESTINATIONS & FAVORITES
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/destinations')
def destinations_page():
    category = request.args.get('category', '')
    search   = request.args.get('q', '')
    if category:
        dests = query_db(
            "SELECT * FROM destinations WHERE category=%s ORDER BY rating DESC", (category,))
    elif search:
        dests = query_db(
            "SELECT * FROM destinations WHERE city LIKE %s OR place_name LIKE %s "
            "ORDER BY rating DESC", (f'%{search}%', f'%{search}%'))
    else:
        dests = query_db("SELECT * FROM destinations ORDER BY rating DESC")

    fav_ids = []
    if 'user_id' in session:
        favs = query_db(
            "SELECT destination_id FROM favorites WHERE user_id=%s",
            (session['user_id'],))
        fav_ids = [f['destination_id'] for f in (favs or [])]

    return render_template('destinations.html',
                           destinations=dests, fav_ids=fav_ids,
                           category=category, search=search)

@app.route('/destinations/<int:dest_id>')
def destination_detail(dest_id):
    dest = query_db("SELECT * FROM destinations WHERE id=%s", (dest_id,), one=True)
    if not dest:
        abort(404)
    reviews = query_db(
        "SELECT r.*, u.name as user_name FROM reviews r "
        "JOIN users u ON r.user_id=u.id WHERE r.destination_id=%s "
        "ORDER BY r.created_at DESC", (dest_id,))
    is_fav = False
    if 'user_id' in session:
        fav = query_db(
            "SELECT id FROM favorites WHERE user_id=%s AND destination_id=%s",
            (session['user_id'], dest_id), one=True)
        is_fav = bool(fav)
    return render_template('destination_detail.html',
                           dest=dest, reviews=reviews, is_fav=is_fav)

@app.route('/favorites/toggle/<int:dest_id>', methods=['POST'])
@login_required
def toggle_favorite(dest_id):
    uid = session['user_id']
    existing = query_db(
        "SELECT id FROM favorites WHERE user_id=%s AND destination_id=%s",
        (uid, dest_id), one=True)
    if existing:
        query_db("DELETE FROM favorites WHERE user_id=%s AND destination_id=%s",
                 (uid, dest_id), commit=True)
        return jsonify({'status': 'removed'})
    else:
        query_db("INSERT INTO favorites (user_id, destination_id) VALUES (%s,%s)",
                 (uid, dest_id), commit=True)
        return jsonify({'status': 'added'})

@app.route('/favorites')
@login_required
def favorites():
    uid = session['user_id']
    favs = query_db(
        "SELECT d.* FROM favorites f JOIN destinations d ON f.destination_id=d.id "
        "WHERE f.user_id=%s ORDER BY f.created_at DESC", (uid,))
    return render_template('favorites.html', destinations=favs)

# ═════════════════════════════════════════════════════════════════════════════
# REVIEWS
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/destinations/<int:dest_id>/review', methods=['POST'])
@login_required
def add_review(dest_id):
    uid    = session['user_id']
    rating = int(request.form.get('rating', 5))
    title  = request.form.get('title', '').strip()
    text   = request.form.get('review_text', '').strip()
    query_db(
        "INSERT INTO reviews (user_id, destination_id, rating, title, review_text) "
        "VALUES (%s,%s,%s,%s,%s)",
        (uid, dest_id, rating, title, text), commit=True)
    # Update avg rating
    query_db(
        "UPDATE destinations SET rating = ("
        "SELECT AVG(rating) FROM reviews WHERE destination_id=%s) WHERE id=%s",
        (dest_id, dest_id), commit=True)
    flash('Review submitted!', 'success')
    return redirect(url_for('destination_detail', dest_id=dest_id))

# ═════════════════════════════════════════════════════════════════════════════
# PROFILE & SETTINGS
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    uid  = session['user_id']
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)

    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        bio   = request.form.get('bio', '').strip()

        pic_filename = user['profile_pic']
        if 'profile_pic' in request.files:
            f = request.files['profile_pic']
            if f and f.filename and allowed_file(f.filename):
                pic_filename = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], pic_filename))

        query_db(
            "UPDATE users SET name=%s, phone=%s, bio=%s, profile_pic=%s WHERE id=%s",
            (name, phone, bio, pic_filename, uid), commit=True)
        session['user_name'] = name
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))

    travel_stats = query_db(
        "SELECT COUNT(*) as trips, SUM(duration_days) as days, "
        "SUM(total_budget) as budget FROM trips WHERE user_id=%s", (uid,), one=True)

    return render_template('profile.html', user=user, stats=travel_stats)

@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    uid      = session['user_id']
    current  = request.form.get('current_password', '')
    new_pw   = request.form.get('new_password', '')
    confirm  = request.form.get('confirm_password', '')

    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    if not check_password_hash(user['password_hash'], current):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('profile'))
    if new_pw != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('profile'))
    if len(new_pw) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('profile'))

    query_db("UPDATE users SET password_hash=%s WHERE id=%s",
             (generate_password_hash(new_pw), uid), commit=True)
    flash('Password changed successfully!', 'success')
    return redirect(url_for('profile'))

# ═════════════════════════════════════════════════════════════════════════════
# EMERGENCY CONTACTS
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/emergency-contacts', methods=['GET', 'POST'])
@login_required
def emergency_contacts():
    uid = session['user_id']
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        relation = request.form.get('relation', '').strip()
        phone    = request.form.get('phone', '').strip()
        email    = request.form.get('email', '').strip()
        notes    = request.form.get('notes', '').strip()
        query_db(
            "INSERT INTO emergency_contacts (user_id, name, relation, phone, email, notes) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (uid, name, relation, phone, email, notes), commit=True)
        flash('Emergency contact added!', 'success')
        return redirect(url_for('emergency_contacts'))

    contacts = query_db(
        "SELECT * FROM emergency_contacts WHERE user_id=%s AND trip_id IS NULL", (uid,))
    return render_template('emergency_contacts.html', contacts=contacts)

@app.route('/emergency-contacts/<int:cid>/delete', methods=['POST'])
@login_required
def delete_emergency_contact(cid):
    query_db("DELETE FROM emergency_contacts WHERE id=%s AND user_id=%s",
             (cid, session['user_id']), commit=True)
    flash('Contact removed.', 'info')
    return redirect(url_for('emergency_contacts'))

# ═════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/notifications')
@login_required
def notifications():
    uid   = session['user_id']
    notifs = query_db(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    query_db("UPDATE notifications SET is_read=1 WHERE user_id=%s", (uid,), commit=True)
    return render_template('notifications.html', notifications=notifs)

# ═════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS (JSON)
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/api/weather/<city>')
def api_weather(city):
    api_key = app.config.get('OPENWEATHER_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'Weather API key not configured'}), 503
    try:
        url = (f"https://api.openweathermap.org/data/2.5/weather"
               f"?q={city}&appid={api_key}&units=metric")
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if resp.status_code == 200:
            return jsonify({
                'city':        data['name'],
                'temp':        data['main']['temp'],
                'feels_like':  data['main']['feels_like'],
                'humidity':    data['main']['humidity'],
                'description': data['weather'][0]['description'],
                'icon':        data['weather'][0]['icon'],
            })
        return jsonify({'error': data.get('message', 'Not found')}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/currency')
def api_currency():
    amount = float(request.args.get('amount', 1))
    from_c = request.args.get('from', 'INR').upper()
    to_c   = request.args.get('to',   'USD').upper()
    api_key = app.config.get('CURRENCY_API_KEY', '')
    if not api_key:
        # Fallback static rates
        rates = {'USD': 0.012, 'EUR': 0.011, 'GBP': 0.0095,
                 'JPY': 1.78,  'AED': 0.044, 'INR': 1.0}
        rate = rates.get(to_c, 1) / rates.get(from_c, 1)
        return jsonify({'result': round(amount * rate, 4), 'rate': rate, 'source': 'static'})
    try:
        url  = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_c}/{to_c}/{amount}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        return jsonify({'result': data.get('conversion_result'),
                        'rate':   data.get('conversion_rate')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/destinations/search')
def api_destinations_search():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify([])
    results = query_db(
        "SELECT id, city, place_name, category, rating FROM destinations "
        "WHERE city LIKE %s OR place_name LIKE %s LIMIT 10",
        (f'%{q}%', f'%{q}%'))
    return jsonify([dict(r) for r in (results or [])])

@app.route('/api/trips/<int:trip_id>/budget')
@login_required
def api_trip_budget(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        return jsonify({'error': 'Not found'}), 404
    totals = query_db(
        "SELECT category, SUM(amount) as total FROM expenses "
        "WHERE trip_id=%s GROUP BY category", (trip_id,))
    spent = query_db(
        "SELECT COALESCE(SUM(amount),0) as total FROM expenses WHERE trip_id=%s",
        (trip_id,), one=True)
    return jsonify({
        'total_budget':    float(trip['total_budget'] or 0),
        'spent':           float(spent['total'] or 0),
        'remaining':       float((trip['total_budget'] or 0) - (spent['total'] or 0)),
        'per_head':        float((trip['total_budget'] or 0) / max(trip['num_travelers'], 1)),
        'by_category':     [dict(r) for r in (totals or [])],
    })

# ═════════════════════════════════════════════════════════════════════════════
# PDF EXPORT
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/trips/<int:trip_id>/export-pdf')
@login_required
def export_pdf(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        import io

        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(buffer, pagesize=A4,
                                   rightMargin=2*cm, leftMargin=2*cm,
                                   topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story  = []

        # Title
        title_style = ParagraphStyle('Title', parent=styles['Title'],
                                     fontSize=22, textColor=colors.HexColor('#2563eb'))
        story.append(Paragraph(f"✈ {trip['title']}", title_style))
        story.append(Spacer(1, 0.4*cm))

        # Trip info
        info = [
            ['Start Date', str(trip['start_date']),
             'End Date',   str(trip['end_date'])],
            ['Duration',   f"{trip['duration_days']} days",
             'Travelers',  str(trip['num_travelers'])],
            ['Budget',     f"₹{trip['total_budget']:,.2f}",
             'Type',       trip['trip_type'].title()],
        ]
        t = Table(info, colWidths=[3.5*cm, 5*cm, 3.5*cm, 5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#eff6ff')),
            ('TEXTCOLOR',  (0,0), (-1,-1), colors.HexColor('#1e3a5f')),
            ('FONTNAME',   (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE',   (0,0), (-1,-1), 10),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#bfdbfe')),
            ('ROWBACKGROUNDS', (0,0), (-1,-1),
             [colors.HexColor('#dbeafe'), colors.HexColor('#eff6ff')]),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.6*cm))

        # Itinerary
        items = query_db(
            "SELECT * FROM itinerary WHERE trip_id=%s ORDER BY day_number, start_time",
            (trip_id,))
        if items:
            story.append(Paragraph("Day-wise Itinerary", styles['Heading2']))
            story.append(Spacer(1, 0.3*cm))
            itin_data = [['Day', 'Time', 'Activity', 'Location', 'Cost']]
            for item in items:
                itin_data.append([
                    f"Day {item['day_number']}",
                    str(item['start_time'] or ''),
                    item['activity'] or '',
                    item['location'] or '',
                    f"₹{item['cost']:,.0f}" if item['cost'] else '-',
                ])
            it = Table(itin_data, colWidths=[1.8*cm, 2*cm, 6*cm, 4*cm, 2.5*cm])
            it.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 9),
                ('GRID',       (0,0), (-1,-1), 0.3, colors.HexColor('#bfdbfe')),
                ('ROWBACKGROUNDS', (1,0), (-1,-1),
                 [colors.white, colors.HexColor('#eff6ff')]),
            ]))
            story.append(it)
            story.append(Spacer(1, 0.6*cm))

        # Expenses
        exps = query_db(
            "SELECT * FROM expenses WHERE trip_id=%s ORDER BY expense_date", (trip_id,))
        if exps:
            story.append(Paragraph("Expense Summary", styles['Heading2']))
            story.append(Spacer(1, 0.3*cm))
            exp_data = [['Date', 'Category', 'Title', 'Amount']]
            for e in exps:
                exp_data.append([
                    str(e['expense_date']),
                    e['category'].title(),
                    e['title'],
                    f"₹{e['amount']:,.2f}",
                ])
            et = Table(exp_data, colWidths=[3*cm, 3*cm, 8*cm, 3*cm])
            et.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#059669')),
                ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 9),
                ('GRID',       (0,0), (-1,-1), 0.3, colors.HexColor('#a7f3d0')),
                ('ROWBACKGROUNDS', (1,0), (-1,-1),
                 [colors.white, colors.HexColor('#ecfdf5')]),
            ]))
            story.append(et)

        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True,
                         download_name=f"trip_{trip_id}_itinerary.pdf",
                         mimetype='application/pdf')
    except ImportError:
        flash('PDF export requires reportlab. Run: pip install reportlab', 'warning')
        return redirect(url_for('trip_detail', trip_id=trip_id))

# ═════════════════════════════════════════════════════════════════════════════
# TRIP SHARING
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/trips/<int:trip_id>/share', methods=['POST'])
@login_required
def share_trip(trip_id):
    uid  = session['user_id']
    trip = query_db("SELECT * FROM trips WHERE id=%s AND user_id=%s",
                    (trip_id, uid), one=True)
    if not trip:
        abort(404)
    token = secrets.token_urlsafe(32)
    query_db("UPDATE trips SET is_shared=1, share_token=%s WHERE id=%s",
             (token, trip_id), commit=True)
    share_url = url_for('view_shared_trip', token=token, _external=True)
    return jsonify({'url': share_url})

@app.route('/shared/<token>')
def view_shared_trip(token):
    trip = query_db("SELECT * FROM trips WHERE share_token=%s AND is_shared=1",
                    (token,), one=True)
    if not trip:
        abort(404)
    itinerary_items = query_db(
        "SELECT * FROM itinerary WHERE trip_id=%s ORDER BY day_number, start_time",
        (trip['id'],))
    days = {}
    for item in (itinerary_items or []):
        days.setdefault(item['day_number'], []).append(item)
    return render_template('shared_trip.html', trip=trip, days=days)

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN
# ═════════════════════════════════════════════════════════════════════════════
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    users_count = query_db("SELECT COUNT(*) as cnt FROM users", one=True)
    trips_count = query_db("SELECT COUNT(*) as cnt FROM trips", one=True)
    dests_count = query_db("SELECT COUNT(*) as cnt FROM destinations", one=True)
    recent_users = query_db(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT 10")
    recent_trips = query_db(
        "SELECT t.*, u.name as user_name FROM trips t "
        "JOIN users u ON t.user_id=u.id ORDER BY t.created_at DESC LIMIT 10")
    return render_template('admin.html',
        users_count=users_count, trips_count=trips_count,
        dests_count=dests_count, recent_users=recent_users,
        recent_trips=recent_trips)

@app.route('/admin/destinations/add', methods=['POST'])
@login_required
@admin_required
def admin_add_destination():
    city        = request.form.get('city', '').strip()
    place_name  = request.form.get('place_name', '').strip()
    description = request.form.get('description', '').strip()
    category    = request.form.get('category', 'city')
    country     = request.form.get('country', 'India').strip()
    best_season = request.form.get('best_season', '').strip()
    avg_cost    = float(request.form.get('avg_cost_per_day', 2000))
    lat         = request.form.get('latitude')
    lon         = request.form.get('longitude')

    query_db(
        "INSERT INTO destinations (city, country, place_name, description, category, "
        "best_season, avg_cost_per_day, latitude, longitude) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (city, country, place_name, description, category,
         best_season, avg_cost, lat or None, lon or None), commit=True)
    flash('Destination added!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/users/<int:uid>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle_user(uid):
    query_db("UPDATE users SET is_active = NOT is_active WHERE id=%s", (uid,), commit=True)
    return redirect(url_for('admin_panel'))

# ═════════════════════════════════════════════════════════════════════════════
# HELPER: Auto-generate checklist
# ═════════════════════════════════════════════════════════════════════════════
def _generate_checklist(trip_id, user_id, trip_type):
    base_items = [
        ('documents', 'Passport / ID Card'),
        ('documents', 'Travel Insurance'),
        ('documents', 'Hotel Booking Confirmation'),
        ('documents', 'Flight / Train Tickets'),
        ('health',    'Medicines & First Aid Kit'),
        ('health',    'Hand Sanitizer'),
        ('health',    'Face Masks'),
        ('clothing',  'Comfortable Walking Shoes'),
        ('clothing',  'Weather-appropriate Clothing'),
        ('clothing',  'Rain Jacket / Umbrella'),
        ('tech',      'Phone Charger & Power Bank'),
        ('tech',      'Camera'),
        ('essentials','Water Bottle'),
        ('essentials','Sunscreen SPF 50+'),
        ('essentials','Sunglasses'),
        ('essentials','Snacks for Journey'),
    ]
    if trip_type in ('adventure',):
        base_items += [
            ('gear', 'Trekking Shoes'),
            ('gear', 'Backpack'),
            ('gear', 'Torch / Headlamp'),
        ]
    for cat, item in base_items:
        query_db(
            "INSERT INTO checklists (trip_id, user_id, item, category) VALUES (%s,%s,%s,%s)",
            (trip_id, user_id, item, cat), commit=True)

# ═════════════════════════════════════════════════════════════════════════════
# RUN
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
