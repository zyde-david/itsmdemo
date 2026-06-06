import sqlite3, hashlib
conn = sqlite3.connect('tickets.db')
c = conn.cursor()

demo_hash = hashlib.sha256(b'demo2026').hexdigest()

# Check existing users
print('=== Existing users ===')
for r in c.execute('SELECT id, username, role, staff_id FROM users ORDER BY id'):
    print(r)

# Check columns
cols = [row[1] for row in c.execute('PRAGMA table_info(users)')]
print(f'\nColumns: {cols}')

# Check Pattani staff
print('\n=== Pattani staff (first 10) ===')
for r in c.execute("SELECT id, name, role, branch FROM staff WHERE province='ปัตตานี' ORDER BY id LIMIT 10"):
    print(r)

# Check leave requests
print('\n=== Leave requests ===')
for r in c.execute('SELECT id, username, leave_type, status FROM leave_requests ORDER BY id'):
    print(r)

conn.close()
