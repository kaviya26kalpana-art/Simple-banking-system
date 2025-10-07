from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
import bcrypt
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'banking.db'

app = Flask(__name__)
app.secret_key = 'replace_this_with_a_random_secret_in_production'

# --- Database helpers ---

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash BLOB NOT NULL,
        balance REAL NOT NULL DEFAULT 0.0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        counterparty TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    conn.commit()
    conn.close()

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Please provide username and password', 'error')
            return redirect(url_for('register'))

        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, pw_hash))
            conn.commit()
            conn.close()
            flash('Registration successful — please login', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
        row = c.fetchone()
        conn.close()
        if row and bcrypt.checkpw(password.encode('utf-8'), row['password_hash']):
            session['user_id'] = row['id']
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    balance = row['balance'] if row else 0.0
    conn.close()
    return render_template('dashboard.html', balance=balance)

@app.route('/deposit', methods=['POST'])
def deposit():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        amount = float(request.form['amount'])
    except Exception:
        flash('Invalid amount', 'error')
        return redirect(url_for('dashboard'))
    if amount <= 0:
        flash('Amount must be positive', 'error')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, session['user_id']))
    c.execute('INSERT INTO transactions (user_id, type, amount) VALUES (?, ?, ?)', (session['user_id'], 'deposit', amount))
    conn.commit()
    conn.close()
    flash(f'Deposited {amount:.2f}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/withdraw', methods=['POST'])
def withdraw():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        amount = float(request.form['amount'])
    except Exception:
        flash('Invalid amount', 'error')
        return redirect(url_for('dashboard'))
    if amount <= 0:
        flash('Amount must be positive', 'error')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    if not row or row['balance'] < amount:
        conn.close()
        flash('Insufficient funds', 'error')
        return redirect(url_for('dashboard'))

    c.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))
    c.execute('INSERT INTO transactions (user_id, type, amount) VALUES (?, ?, ?)', (session['user_id'], 'withdraw', amount))
    conn.commit()
    conn.close()
    flash(f'Withdrew {amount:.2f}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/transfer', methods=['POST'])
def transfer():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    target = request.form['target'].strip()
    try:
        amount = float(request.form['amount'])
    except Exception:
        flash('Invalid amount', 'error')
        return redirect(url_for('dashboard'))
    if amount <= 0:
        flash('Amount must be positive', 'error')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE username = ?', (target,))
    tr = c.fetchone()
    if not tr:
        conn.close()
        flash('Target user not found', 'error')
        return redirect(url_for('dashboard'))

    target_id = tr['id']
    c.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    if not row or row['balance'] < amount:
        conn.close()
        flash('Insufficient funds', 'error')
        return redirect(url_for('dashboard'))

    c.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, session['user_id']))
    c.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, target_id))
    c.execute('INSERT INTO transactions (user_id, type, amount, counterparty) VALUES (?, ?, ?, ?)', (session['user_id'], 'transfer_out', amount, target))
    c.execute('INSERT INTO transactions (user_id, type, amount, counterparty) VALUES (?, ?, ?, ?)', (target_id, 'transfer_in', amount, session['username']))
    conn.commit()
    conn.close()
    flash(f'Transferred {amount:.2f} to {target}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT type, amount, counterparty, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp DESC', (session['user_id'],))
    rows = c.fetchall()
    conn.close()
    return render_template('transactions.html', transactions=rows)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
