#!/usr/bin/env python3
import hashlib
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, g
import calendar
import sqlite3, random, os, logging, json
from datetime import date, datetime, timedelta
from functools import wraps

# Ensure static files resolve correctly on WSGI hosts (PythonAnywhere, etc.)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(_BASE_DIR, 'static'))
app.config['SECRET_KEY'] = 'demo-2026-secret'
DB_PATH = os.environ.get('DB_PATH', os.path.join(_BASE_DIR, 'tickets.db'))

app.logger.setLevel(logging.ERROR)

def check_pw(pw, pw_hash):
    return hashlib.sha256(pw.encode()).hexdigest() == pw_hash

def login_required(f):
    @wraps(f)
    def decorated(*a, **kw):
        if not session.get('user_id'):
            return redirect('/login')
        return f(*a, **kw)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*a, **kw):
            if not session.get('user_id'):
                return redirect('/login')
            if session.get('role') not in roles:
                return jsonify(success=False, error='ไม่มีสิทธิ์เข้าถึง'), 403
            return f(*a, **kw)
        return decorated
    return decorator

def get_current_user():
    if not session.get('user_id'):
        return None
    c = get_db()
    u = c.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    return dict(u) if u else None

ROLE_LABELS = {
    'admin': 'Admin — สิทธิ์เต็มระบบ',
    'manager': 'Manager — Service Manager / Resolver Lead',
    'user': 'User — ผู้แจ้ง / Self-service',
    'hr': 'HR — งานบุคคลและ HR tickets',
}
VALID_ROLES = tuple(ROLE_LABELS.keys())
HR_KEYWORDS = ('HR', 'บุคคล', 'พนักงาน', 'ลา', 'สวัสดิการ', 'เงินเดือน')

def current_role():
    return session.get('role', 'user')

def is_admin():
    return current_role() == 'admin'

def is_manager():
    return current_role() in ('admin', 'manager')

def is_hr_role():
    return current_role() == 'hr'

def can_manage_users():
    return is_admin()

def can_view_assets():
    return current_role() in ('admin', 'manager')

def can_view_staff():
    return current_role() in ('admin', 'manager', 'hr')

def can_manage_staff():
    return is_admin()

def can_manage_kb():
    return current_role() in ('admin', 'manager')

def is_hr_ticket(ticket):
    if not ticket:
        return False
    text = ' '.join(str(ticket[k] or '') for k in ('category', 'title', 'description') if k in ticket.keys())
    return any(k.lower() in text.lower() for k in HR_KEYWORDS)

def can_access_ticket(ticket):
    if not ticket:
        return False
    role = current_role()
    username = session.get('username', '')
    if role in ('admin', 'manager'):
        return True
    if role == 'hr' and (is_hr_ticket(ticket) or ticket['reported_by'] == username or ticket['assigned_to'] == username):
        return True
    return ticket['reported_by'] == username or ticket['assigned_to'] == username

def can_manage_ticket(ticket=None):
    role = current_role()
    if role in ('admin', 'manager'):
        return True
    if role == 'hr' and ticket and is_hr_ticket(ticket):
        return True
    return False

def ticket_scope_clause(prefix=''):
    role = current_role()
    username = session.get('username', '')
    col = (lambda name: f"{prefix}.{name}" if prefix else name)
    if role in ('admin', 'manager'):
        return '', []
    if role == 'hr':
        hr_like = [f'%{k}%' for k in HR_KEYWORDS]
        return (f"(({col('reported_by')}=? OR {col('assigned_to')}=?) OR "
                f"({col('category')} LIKE ? OR {col('title')} LIKE ? OR {col('description')} LIKE ? OR "
                f"{col('category')} LIKE ? OR {col('title')} LIKE ? OR {col('description')} LIKE ? OR "
                f"{col('category')} LIKE ? OR {col('title')} LIKE ? OR {col('description')} LIKE ? OR "
                f"{col('category')} LIKE ? OR {col('title')} LIKE ? OR {col('description')} LIKE ? OR "
                f"{col('category')} LIKE ? OR {col('title')} LIKE ? OR {col('description')} LIKE ? OR "
                f"{col('category')} LIKE ? OR {col('title')} LIKE ? OR {col('description')} LIKE ?))",
                [username, username] + [v for pat in hr_like for v in (pat, pat, pat)])
    return f"({col('reported_by')}=? OR {col('assigned_to')}=?)", [username, username]

def forbidden_response(message='ไม่มีสิทธิ์เข้าถึง'):
    if request.path.startswith('/api/'):
        return jsonify(success=False, error=message), 403
    return message, 403

def get_staff_for_user(user=None):
    user = user or get_current_user()
    if not user:
        return None
    c = get_db()
    staff = None
    if int(user.get('staff_id') or 0):
        staff = c.execute('SELECT * FROM staff WHERE id=?', (user['staff_id'],)).fetchone()
    if not staff:
        staff = c.execute('SELECT * FROM staff WHERE name=?', (user.get('username', ''),)).fetchone()
    return staff

def manager_staff_branch():
    staff = get_staff_for_user()
    return staff['branch'] if staff else ''

def can_view_staff_asset_history(staff):
    if not staff:
        return False
    role = current_role()
    user = get_current_user()
    if role in ('admin', 'hr'):
        return True
    if role == 'manager':
        branch = manager_staff_branch()
        return not branch or staff['branch'] == branch
    if user and int(user.get('staff_id') or 0) == staff['id']:
        return True
    return session.get('username', '') == staff['name']

def ensure_asset_history_baseline(c):
    c.execute('''CREATE TABLE IF NOT EXISTS asset_ownership_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER,
        staff_name TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        action TEXT DEFAULT 'assigned',
        note TEXT DEFAULT '',
        created_by TEXT DEFAULT 'System',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''
        INSERT INTO asset_ownership_history (asset_id, staff_name, started_at, action, note, created_by)
        SELECT a.id, a.assigned_to, CURRENT_TIMESTAMP, 'baseline', 'เจ้าของปัจจุบันตอนเริ่มเก็บประวัติ', 'System'
        FROM assets a
        WHERE COALESCE(a.assigned_to, '') <> ''
          AND NOT EXISTS (
              SELECT 1 FROM asset_ownership_history h
              WHERE h.asset_id = a.id AND h.ended_at IS NULL
          )
    ''')

def staff_asset_history_payload(c, staff):
    ensure_asset_history_baseline(c)
    current_assets = [dict(a) for a in c.execute(
        'SELECT * FROM assets WHERE assigned_to=? ORDER BY asset_type, asset_tag, name',
        (staff['name'],)
    ).fetchall()]
    history = [dict(h) for h in c.execute('''
        SELECT h.*, a.asset_tag, a.asset_code, a.asset_type, a.name AS asset_name, a.serial, a.status
        FROM asset_ownership_history h
        LEFT JOIN assets a ON a.id = h.asset_id
        WHERE h.staff_name=?
        ORDER BY COALESCE(h.ended_at, h.started_at) DESC, h.id DESC
    ''', (staff['name'],)).fetchall()]
    previous_assets = [h for h in history if h.get('ended_at')]
    return {
        'current_assets': current_assets,
        'history': history,
        'previous_assets': previous_assets,
        'current_count': len(current_assets),
        'previous_count': len(previous_assets),
    }

@app.context_processor
def inject_rbac():
    return dict(ROLE_LABELS=ROLE_LABELS, current_role=current_role(),
                can_manage_users=can_manage_users(), can_view_assets=can_view_assets(),
                can_view_staff=can_view_staff(), can_manage_staff=can_manage_staff(),
                can_manage_kb=can_manage_kb(), is_manager=is_manager(), is_admin=is_admin(),
                is_kanban_operator=is_kanban_operator())

ALL_BRANCHES = [
 {"branch":"สาขาเมืองปัตตานี","district":"เมืองปัตตานี","province":"ปัตตานี","type":"main"},
 {"branch":"สาขาโคกโพธิ์","district":"โคกโพธิ์","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาหนองจิก","district":"หนองจิก","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาปะนาเระ","district":"ปะนาเระ","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขามายอ","district":"มายอ","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาทุ่งยางแดง","district":"ทุ่งยางแดง","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาสายบุรี","district":"สายบุรี","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาไม้แก่น","district":"ไม้แก่น","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขายะหริ่ง","district":"ยะหริ่ง","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขายะรัง","district":"ยะรัง","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขากะพ้อ","district":"กะพ้อ","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาแม่ลาน","district":"แม่ลาน","province":"ปัตตานี","type":"branch"},
 {"branch":"สาขาเมืองยะลา","district":"เมืองยะลา","province":"ยะลา","type":"main"},
 {"branch":"สาขาบันนังสตา","district":"บันนังสตา","province":"ยะลา","type":"branch"},
 {"branch":"สาขายะหา","district":"ยะหา","province":"ยะลา","type":"branch"},
 {"branch":"สาขารามัน","district":"รามัน","province":"ยะลา","type":"branch"},
 {"branch":"สาขาเบตง","district":"เบตง","province":"ยะลา","type":"branch"},
 {"branch":"สาขากาบัง","district":"กาบัง","province":"ยะลา","type":"branch"},
 {"branch":"สาขากรงปินัง","district":"กรงปินัง","province":"ยะลา","type":"branch"},
 {"branch":"สาขาธารโต","district":"ธารโต","province":"ยะลา","type":"branch"},
 {"branch":"สาขาเมืองนราธิวาส","district":"เมืองนราธิวาส","province":"นราธิวาส","type":"main"},
 {"branch":"สาขาตากใบ","district":"ตากใบ","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาบาเจาะ","district":"บาเจาะ","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขายี่งอ","district":"ยี่งอ","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาระแงะ","district":"ระแงะ","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขารือเสาะ","district":"รือเสาะ","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาศรีสาคร","district":"ศรีสาคร","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาแว้ง","district":"แว้ง","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาสุคิริน","district":"สุคิริน","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาสุไหงโก-ลก","district":"สุไหงโก-ลก","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาสุไหงปาดี","district":"สุไหงปาดี","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาจะแนะ","district":"จะแนะ","province":"นราธิวาส","type":"branch"},
 {"branch":"สาขาเจาะไอร้อง","district":"เจาะไอร้อง","province":"นราธิวาส","type":"branch"},
]
NUM_BRANCHES = len(ALL_BRANCHES)  # 33
PROVINCE_TO_BRANCHES = {}
for b in ALL_BRANCHES:
    prov = b['province']
    if prov not in PROVINCE_TO_BRANCHES:
        PROVINCE_TO_BRANCHES[prov] = []
    PROVINCE_TO_BRANCHES[prov].append({'branch': b['branch'], 'district': b['district']})

CATEGORY_CODES = {'คอมพิวเตอร์':'PC','เครื่องพิมพ์':'PR','Scanner':'SC','Router':'RT','Switch':'SW','UPS':'UP'}
BRANCH_CODES = {}
for prov in ['ปัตตานี','ยะลา','นราธิวาส']:
    branches_in_prov = [b for b in ALL_BRANCHES if b['province']==prov]
    for i, b in enumerate(branches_in_prov):
        code = str(i+1) if i < 9 else chr(ord('A') + i - 9)
        BRANCH_CODES[b['branch']] = code
PROVINCE_CODES = {'ปัตตานี':'1','ยะลา':'2','นราธิวาส':'3'}
PROVINCE_ABBR = {'ปัตตานี':'ตานี','ยะลา':'ยะลา','นราธิวาส':'นรา'}

# Build short branch display: {province_num}{district} e.g. "2ยะหา"
def _short_branch(branch_full):
    """Convert 'สาขายะหา' → '2ยะหา' (province number + district)"""
    for b in ALL_BRANCHES:
        if b['branch'] == branch_full:
            return PROVINCE_CODES.get(b['province'],'0') + b['district']
    return branch_full.replace('สาขา','')

SHORT_BRANCHES = {b['branch']: _short_branch(b['branch']) for b in ALL_BRANCHES}

TICKET_CATS = {
 "ระบบ Core Banking":{"titles":["Core Banking ล่ม","เข้า Core ไม่ได้","บันทึกรายการไม่ได้","ถอนเงินผิดพลาด","ปิดรอบวันไม่ได้","พิมพ์ใบเสร็จไม่ได้","สินเชื่อดอกเบี้ยผิดปกติ","ระบบสมาชิก Error"],"priority":"critical","ai":"1. VPN Tunnel สำคัญ!\n2. เช็ค Server\n3. สำรองข้อมูล\n4. แจ้ง IT ทันที"},
 "เครือข่าย/อินเทอร์เน็ต":{"titles":["อินเทอร์เน็ตไม่ได้","อินเทอร์เน็ตช้า","WiFi ดรอป","WAN IP เปลี่ยน","DNS ไม่ resolve","Firewall Block","IP Camera ภาพไม่ขึ้น"],"priority":"high","ai":"1. เช็ค Router/Switch\n2. Ping Gateway\n3. เช็ค LAN\n4. รีสตาร์ท Modem"},
 "VPN/ระบบเสีย":{"titles":["VPN Tunnel หลุด","เชื่อมต่อ HO ไม่ได้","VPN ช้า","Site-to-Site VPN Down"],"priority":"high","ai":"1. เช็ค WAN IP\n2. Tunnel Status\n3. Firewall Rules\n4. ติดต่อ IT"},
 "เครื่องพิมพ์/สมุด":{"titles":["ปริ้นเตอร์คายกระดาษ","พิมพ์ทับ","หมึกหมด","เครื่องพิมพ์ค้าง","Sensor เลอะ","ลายไม่ชัด","เครื่องพิมพ์ขาว"],"priority":"medium","ai":"1. เช็ค Sensor\n2. ลูกยางดึงสมุด\n3. Calibrate\n4. เปลี่ยนผ้าคราบ"},
 "คอมพิวเตอร์เสีย":{"titles":["PC เปิดไม่ติด","จอฟ้า","คีย์บอร์ดเสีย","เมาส์เสีย","ฮาร์ดดิสเต็ม","RAM ไม่พอ","ลำโพงไม่ดัง","USB ไม่ทำงาน","ไวรัส"],"priority":"low","ai":"1. เช็คสาย\n2. รีสตาร์ท\n3. เช็ค RAM/HDD\n4. เช็ค VGA"},
 "ไฟฟ้า/สาธารณูปโภค":{"titles":["ไฟดับ","แอร์ไม่ทำงาน","UPS แบตหมด","ไฟกระพริบ","UPS Alarm ดัง","แบต UPS บวม"],"priority":"high","ai":"1. เช็คสวิตช์\n2. เช็ค UPS\n3. Circuit Breaker\n4. แจ้งผู้ดูแลอาคาร"},
}

ASSET_TICKET_RULES = {
    'Router': {'category': 'เครือข่าย/อินเทอร์เน็ต', 'priority': 'high'},
    'Switch': {'category': 'เครือข่าย/อินเทอร์เน็ต', 'priority': 'high'},
    'UPS': {'category': 'ไฟฟ้า/สาธารณูปโภค', 'priority': 'high'},
    'เครื่องพิมพ์': {'category': 'เครื่องพิมพ์/สมุด', 'priority': 'medium'},
    'Scanner': {'category': 'เครื่องพิมพ์/สมุด', 'priority': 'medium'},
    'คอมพิวเตอร์': {'category': 'คอมพิวเตอร์เสีย', 'priority': 'low'},
}

PRIORITY_HELP_TH = {
    'critical': 'Critical: ระบบหลักล่ม/ทำธุรกรรมไม่ได้ กระทบหลายคน ต้องรีบแจ้ง IT ทันที',
    'high': 'High: งานสาขาสะดุด เช่น network/VPN/ไฟ/UPS ต้องแก้ไวในวันเดียวกัน',
    'medium': 'Medium: ยังทำงานได้บางส่วน เช่น printer/scanner มีปัญหา ควรวางคิวแก้',
    'low': 'Low: กระทบคนเดียวหรือมีทางเลี่ยง เช่น mouse/keyboard/PC ช้า จัดคิวปกติ',
}

CATEGORY_HELP_TH = {
    'ระบบ Core Banking': 'ระบบทำธุรกรรม/สมาชิก/ปิดรอบวัน ถ้าล่มให้ถือว่าวิกฤต',
    'เครือข่าย/อินเทอร์เน็ต': 'Internet, WiFi, LAN, Router, Switch ทำให้สาขาต่อระบบไม่ได้',
    'VPN/ระบบเสีย': 'Tunnel เชื่อม HQ/Core หลุดหรือช้า กระทบงานสาขาโดยตรง',
    'เครื่องพิมพ์/สมุด': 'Printer, passbook, scanner งานเอกสาร/สมุดสมาชิกติดขัด',
    'คอมพิวเตอร์เสีย': 'PC, keyboard, mouse, disk, จอฟ้า กระทบผู้ใช้งานรายเครื่อง',
    'ไฟฟ้า/สาธารณูปโภค': 'ไฟ, UPS, แอร์, อุปกรณ์ไฟฟ้าที่ทำให้ระบบ IT เสี่ยงหยุด',
}

def suggest_ticket_defaults(asset=None, category=''):
    rule = ASSET_TICKET_RULES.get(asset['asset_type'] if asset else '', {})
    suggested_category = category or rule.get('category') or 'คอมพิวเตอร์เสีย'
    suggested_priority = rule.get('priority') or TICKET_CATS.get(suggested_category, {}).get('priority', 'medium')
    return suggested_category, suggested_priority


TM = ["สมชาย","สมศักดิ์","สมหมาย","สมบูรณ์","ประเสริฐ","วิชัย","ศุภชัย","ธนากร","รัตนชัย","ชัยวัฒน์","ธีรวัฒน์","นเรศ","พีรพัฒน์","สุรศักดิ์"]
TF = ["ปราณี","ประไพ","วิไล","ศิริพร","กนกพร","ชลิดา","ธนพร","นงลักษณ์","บุญสม","พรทิพย์","รัตนา","สุนิสา","อรพรรณ"]
MM = ["มูฮัมมัด","อาหมัด","อับดุลเลาะห์","ฮาซัน","ฮุสซัยน์","อิบรอฮีม์","ซูไลมาน","รอสลี","นาซรี","ยูโซฟ","ซัลมาน"]
MF = ["ฟาติมะห์","นาฟีสะห์","นูรุลฮูดา","นาอีมะห์","มะรียัม","มุนีระห์","อามีนะห์","ซอรายา","ฮาวา","รอกายัฮ์"]
LN = ["ทิพย์โชคชัย","จันทร์เพ็ญ","แก้วมณี","ศรีสุข","บัวทอง","ทองคำ","พูนผล","ใจดี","ยูโซฟ","มะแม","ลายเพชร","เจะอาแซ","มะนู","สาและ","ดือราแม","เปาะซี","กาเซ็ม","ลาฮี","วารีซัน","นูรูลลอฮ์","ฟารีฮีน","กอมาลี","รักษาศักดิ์","รุ่งเรือง"]

def _name():
    m = random.random()<0.4
    male = random.random()<0.55
    f = random.choice(MM if m and male else MF if m and not male else TM if not m and male else TF)
    l = random.choice(LN)
    p = ("นาย" if male else random.choice(["นาง","นางสาว"]))
    return f"{p} {f} {l}"

def _staff():
    S = []
    name_pool = [
        "นายสมชาย ใจดี","นางสาวปราณี สุขใจ","นายวิชัย รุ่งเรือง","นางสาวกนกพร พูนผล",
        "นายธนากร ศรีสุข","นางสาวนงลักษณ์ บัวทอง","นายรัตนชัย ทองคำ","นางสาวชลิดา จันทร์เพ็ญ",
        "นายพีรพัฒน์ ยูโซฟ","นางสาวฟาติมะห์ นาซรี","นายอาหมัด ลาหี","นางสาวนูรุลฮูดา มะนู",
        "นายซุลธาน เทค","นายอารีฟ กอมาลี","นายฮาซัน ดือราแม","นางสาวอามีนะห์ ซอรายา",
        "นายสุรศักดิ์ ลายเพชร","นางสาววิไล ศรีสุข","นายชัยวัฒน์ เจะอาแซ","นางสาวรัตนา สมบูรณ์",
    ]
    idx = 0
    for b in ALL_BRANCHES:
        n = random.randint(3,5) if b["type"]=="main" else random.randint(2,3) if b["type"]=="service_point" else random.randint(2,4)
        pool = ["ผู้จัดการสาขา","เจ้าหน้าที่บัญชี","เจ้าหน้าที่สินเชื่อ","เจ้าหน้าที่รับ-ส่งเงิน","เจ้าหน้าที่สมาชิก","เจ้าหน้าที่คอมพิวเตอร์","IT Support","พนักงานต้อนรับ"] if b["type"]=="main" else ["ผู้จัดการสาขา","เจ้าหน้าที่บัญชี","เจ้าหน้าที่สมาชิก","เจ้าหน้าที่คอมพิวเตอร์","พนักงานต้อนรับ"]
        while len(pool)<n: pool.append(random.choice(["เจ้าหน้าที่บัญชี","เจ้าหน้าที่สมาชิก","พนักงานต้อนรับ"]))
        for i in range(n):
            nm = name_pool[idx % len(name_pool)]
            idx += 1
            role = pool[i] if i<len(pool) else random.choice(["เจ้าหน้าที่บัญชี","เจ้าหน้าที่สมาชิก"])
            S.append({"name":nm,"role":role,"branch":b["branch"],"province":b["province"],"is_it":role=="IT Support"})
    return S

def _tickets(S):
    EU = [s for s in S if not s["is_it"]]
    IT = [s for s in S if s["is_it"]]
    if not IT: IT = [{"name":"นายซุลธาน เทค","branch":"สาขาเมืองปัตตานี","province":"ปัตตานี"},{"name":"นายอารีฟ","branch":"สาขาเมืองนราธิวาส","province":"นราธิวาส"}]
    T = []
    tc = 0
    for _ in range(random.randint(20,30)):
        tc += 1
        year_code = datetime.utcnow().strftime('%y')
        ticket_code = f"TK-{year_code}-{tc:04d}"
        cat = random.choice(list(TICKET_CATS.keys()))
        cd = TICKET_CATS[cat]
        rep = random.choice(EU)
        ast = random.choice(IT)
        st = random.choice({"critical":["open","in_progress","pending","resolved"],"high":["open","in_progress","in_progress","pending","resolved","resolved"],"medium":["open","in_progress","pending","resolved","resolved","resolved"],"low":["resolved","resolved","resolved","in_progress","pending"]}[cd["priority"]])
        da = random.randint(0,60)
        cd2 = datetime.utcnow()-timedelta(days=da,hours=random.randint(6,18))
        rs = None
        if st in ("resolved","closed"):
            rd = cd2+timedelta(hours=random.randint(1,72))
            if rd<datetime.utcnow(): rs=rd.strftime("%Y-%m-%d %H:%M:%S")
        T.append({"ticket_code":ticket_code,"branch":rep["branch"],"province":rep["province"],"category":cat,"title":random.choice(cd["titles"]),"description":f"แจ้ง: {random.choice(cd['titles'])} ที่{rep['branch']} โดย{rep['name']}","priority":cd["priority"],"status":st,"reported_by":rep["name"],"assigned_to":ast["name"],"asset_id":0,"created_at":cd2.strftime("%Y-%m-%d %H:%M:%S"),"reported_at":cd2.strftime("%Y-%m-%d %H:%M:%S"),"resolved_at":rs,"ai_suggestion":cd["ai"],"ai_confidence":round(random.uniform(0.65,0.98),2)})
    return T

def _assets():
    A = []
    sc = {}
    # branch numeric code (01-33, ordered by province then district)
    branch_num = {}
    for i, b in enumerate(ALL_BRANCHES):
        branch_num[b["branch"]] = i + 1  # 1-based
    AC = {"คอมพิวเตอร์":{"m":["Dell OptiPlex 3090","HP ProDesk 400 G7","Lenovo M70q"],"p":"PC","spec":"Core i5/8GB/256GB SSD"},"เครื่องพิมพ์":{"m":["HP LaserJet M404dn","Epson L3250","Brother HL-L2350DW","Canon G3010"],"p":"PRT","spec":"Laser/Inkjet A4"},"Scanner":{"m":["Fujitsu fi-7160","Epson DS-1640","Brother DS-640"],"p":"SCN","spec":"A4 Duplex 60ppm"},"Router":{"m":["Cisco ISR 1111","MikroTik hEX","TP-Link ER7206"],"p":"RT","spec":"Gigabit VPN Router"},"Switch":{"m":["Cisco SG250-26","TP-Link TL-SG1024","MikroTik CRS326"],"p":"SW","spec":"24-Port Gigabit"},"UPS":{"m":["APC 1500VA","Eaton 5S 1500VA","CyberPower OL2000"],"p":"UPS","spec":"1500VA Online"}}
    S_pool = ["นายสมชาย ใจดี","นางสาวปราณี สุขใจ","นายวิชัai","นางสาวกนกพร พูนผล"]
    for b in ALL_BRANCHES:
        n = random.randint(2,3) if b["type"]=="main" else random.randint(1,2) if b["type"]=="service_point" else random.randint(1,2)
        ch = random.sample(list(AC.keys()),k=min(n,len(AC)))
        if n>=2: ch[0]="คอมพิวเตอร์"
        if n>=3: ch[1]="เครื่องพิมพ์"
        bn = branch_num.get(b["branch"], 1)
        for at in ch[:n]:
            c2 = AC[at]; mdl=random.choice(c2["m"]); p=c2["p"]; sp=c2["spec"]
            sc[p]=sc.get(p,100)+1
            seq = sc[p] - 100
            sn = f"{p}-{sc[p]}"
            prov_code = PROVINCE_CODES.get(b['province'],'0')
            br_code = BRANCH_CODES.get(b['branch'],'0')
            cat_code = CATEGORY_CODES.get(at,'XX')
            asset_tag = f"{prov_code}{br_code}{cat_code}{seq:02d}"
            asset_code = asset_tag  # use same 1BPC01 format
            st=random.choices(["active","active","active","active","maintenance","retired"],weights=[65,12,8,5,5,5],k=1)[0]
            lc=datetime.now()-timedelta(days=random.randint(3,60))
            nx=lc+timedelta(days=90)
            nm2={"active":random.choice(["สถานะปกติ","ใช้งานปกติ"]),"maintenance":random.choice(["รออะไหล่","ส่งซ่อน"]),"retired":random.choice(["เกษียณแล้ว","รอจำหน่าย"])}
            A.append({"asset_code":asset_code,"asset_tag":asset_tag,"branch":b["branch"],"asset_type":at,"name":mdl,"serial":sn,"status":st,"brand":mdl.split()[0],"spec":sp,"assigned_to":random.choice(S_pool),"last_check":lc.strftime("%Y-%m-%d"),"next_check":nx.strftime("%Y-%m-%d"),"notes":nm2.get(st,"")})
    return A

KB = [
    {"title":"แก้เครื่องพิมพ์คายกระดาษ","cat":"เครื่องพิมพ์","content":"1. ปิดเครื่อง ถอดปั๊ก\n2. เปิดฝา\n3. ดึงกระดาษคาย\n4. เช็คลูกยาง\n5. เปิดใหม่","v":156},
    {"title":"แก้อินเทอร์เน็ตไม่ได้","cat":"เครือข่าย","content":"1. เช็คสาย LAN\n2. รีสตาร์ท Router\n3. Ping 8.8.8.8\n4. แจ้ง IT","v":287},
    {"title":"VPN Tunnel หลุด","cat":"VPN","content":"1. เช็คอินเทอร์เน็ต\n2. รีสตาร์ท Router\n3. เช็ค WAN IP\n4. แจ้ง IT","v":93},
    {"title":"Reset Password Core Banking","cat":"Core Banking","content":"1. Forgot Password\n2. รอ OTP\n3. ตั้งรหัสใหม่\n4. แจ้ง Admin","v":174},
    {"title":"เช็คระบบก่อนเปิดสาขา","cat":"Core Banking","content":"1. เปิด PC\n2. เช็ค VPN\n3. เปิด Core\n4. เช็คยอด\n5. เปิดพิมพ์","v":67},
    {"title":"แจ้งปัญหา IT","cat":"ทั่วไป","content":"1. เข้า Tickets\n2. New Ticket\n3. เลือกหมวด\n4. ระบุรายละเอียด\n5. Submit","v":342},
    {"title":"แก้จอฟ้า BSOD","cat":"คอมพิวเตอร์","content":"1. ปิดเครื่อง 10 วิ\n2. F8 Safe Mode\n3. รีเซ็ต Driver\n4. แจ้ง IT","v":78},
    {"title":"ใช้เครื่องนับเงิน","cat":"ทั่วไป","content":"1. เปิดเครื่อง\n2. วางธนบัตร\n3. กดนับ\n4. เช็คยอด\n5. Confirm","v":124},
    {"title":"ติดตั้ง Printer ใหม่","cat":"เครื่องพิมพ์","content":"1. Download Driver จากเว็บผู้ผลิต\n2. ติดตั้ง Driver\n3. เชื่อมต่อ USB/Network\n4. เพิ่ม Printer ใน Settings\n5. Test Print","v":201},
    {"title":"แก้ WiFi ดรอปชะงัก","cat":"เครือข่าย","content":"1. เช็คสัญญาณ WiFi\n2. เปลี่ยน Channel Router\n3. เช็ค Interference\n4. ติดตั้ง Access Point เพิ่ม\n5. แจ้ง ISP","v":145},
    {"title":"อัพเดท Windows Update","cat":"คอมพิวเตอร์","content":"1. บันทึกงานทั้งหมด\n2. เปิด Settings → Update\n3. Check for Updates\n4. รอดาวน์โหลด\n5. Restart เครื่อง","v":189},
    {"title":"แก้เครื่องสแกนเนอร์ไม่ทำงาน","cat":"เครื่องพิมพ์","content":"1. เช็คสาย USB\n2. ติดตั้ง Driver ใหม่\n3. เช็ค Software\n4. ทดสอบสแกน\n5. แจ้ง IT ถ้ายังไม่ได้","v":67},
    {"title":"เปิดใช้งานโปรแกรม Core Banking","cat":"Core Banking","content":"1. เข้าระบบ Core\n2. ใส่ User/Password\n3. เช็ค VPN ก่อน\n4. เลือกเมนูงาน\n5. เริ่มทำรายการ","v":234},
    {"title":"ถอด/เปลี่ยนตลับหมึก","cat":"เครื่องพิมพ์","content":"1. ปิดเครื่อง\n2. เปิดฝาหน้า\n3. ดึงตลับหมึกเก่า\n4. ใส่ตลับใหม่\n5. ปิดฝา เปิดเครื่อง","v":156},
    {"title":"แก้ IP Camera ภาพไม่ขึ้น","cat":"เครือข่าย","content":"1. เช็คสาย LAN Camera\n2. ตรวจสอบ IP Address\n3. Ping Camera\n4. รีสตาร์ท NVR\n5. แจ้ง IT","v":89},
    {"title":"ใช้เครื่องบันทึกเงิน","cat":"ทั่วไป","content":"1. เปิดเครื่อง\n2. ใส่รหัสพนักงาน\n3. ทำรายการปกติ\n4. ปิดกะ → สรุปยอด\n5. ส่งเงิน","v":178},
    {"title":"แก้ Password ล็อก","cat":"Core Banking","content":"1. กด Forgot Password\n2. รอ OTP SMS\n3. ใส่ OTP\n4. ตั้งรหัสใหม่\n5. เข้าระบบใหม่","v":267},
    {"title":"Backup ข้อมูลก่อนปิดวัน","cat":"Core Banking","content":"1. ปิดระบบ Core\n2. สำรองข้อมูล (Backup)\n3. เช็ค Log\n4. ปิด Server\n5. ปิดไฟ","v":145},
    {"title":"แก้เครื่องเปิดไม่ติด","cat":"คอมพิวเตอร์","content":"1. เช็คสายไฟ\n2. เช็ค Power Supply\n3. กด Power ค้าง 10 วิ\n4. ถอด RAM เช็ค\n5. แจ้ง IT","v":56},
    {"title":"เช็คสต็อกเอกสาร","cat":"ทั่วไป","content":"1. เข้าระบบ Stock\n2. เลือกประเภทเอกสาร\n3. ตรวจสอบจำนวน\n4. สั่งเพิ่มถ้าต่ำกว่า\n5. บันทึก","v":112},
]

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    c=get_db()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT DEFAULT \'user\',staff_id INTEGER DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS staff (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,role TEXT,branch TEXT,province TEXT,is_it INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_code TEXT,branch TEXT,province TEXT,category TEXT,title TEXT,description TEXT,priority TEXT,status TEXT,reported_by TEXT,assigned_to TEXT,asset_id INTEGER DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,reported_at TIMESTAMP,resolved_at TIMESTAMP,ai_suggestion TEXT,ai_confidence REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS work_notes (id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER,note TEXT,created_by TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS assets (id INTEGER PRIMARY KEY AUTOINCREMENT,asset_code TEXT,branch TEXT,asset_type TEXT,name TEXT,serial TEXT,status TEXT,brand TEXT,spec TEXT,assigned_to TEXT,last_check DATE,next_check DATE,notes TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS knowledge_base (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,category TEXT,content TEXT,views INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS asset_logs (id INTEGER PRIMARY KEY AUTOINCREMENT,asset_id INTEGER,note TEXT,created_by TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    ensure_asset_history_baseline(c)
    c.execute("CREATE TABLE IF NOT EXISTS leave_requests (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,username TEXT,leave_type TEXT,start_date DATE,end_date DATE,days REAL,reason TEXT,status TEXT DEFAULT 'pending',approver_id INTEGER DEFAULT 0,approval_note TEXT DEFAULT '',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    # Migrations for existing persistent Fly/SQLite volumes. CREATE TABLE IF NOT EXISTS
    # does not add columns to old tables, so keep every route/template dependency here.
    def ensure_column(table, column, definition):
        cols = [row[1] for row in c.execute(f'PRAGMA table_info({table})')]
        if column not in cols:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

    for column, definition in {
        'ticket_code': "TEXT DEFAULT ''",
        'assigned_to': "TEXT DEFAULT ''",
        'asset_id': 'INTEGER DEFAULT 0',
        'reported_at': 'TIMESTAMP',
        'kb_id': 'INTEGER DEFAULT 0',
    }.items():
        ensure_column('tickets', column, definition)

    for column, definition in {
        'asset_code': "TEXT DEFAULT ''",
        'brand': "TEXT DEFAULT ''",
        'spec': "TEXT DEFAULT ''",
        'assigned_to': "TEXT DEFAULT ''",
        'last_check': 'DATE',
        'next_check': 'DATE',
        'asset_tag': "TEXT DEFAULT ''",
        'province': "TEXT DEFAULT ''",
    }.items():
        ensure_column('assets', column, definition)

    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    for branch, province in branch_to_province.items():
        c.execute('UPDATE assets SET province=? WHERE branch=? AND (province IS NULL OR province="")', (province, branch))

    for column, definition in {
        'role': "TEXT DEFAULT 'user'",
        'staff_id': 'INTEGER DEFAULT 0',
        'created_at': 'TIMESTAMP',
    }.items():
        ensure_column('users', column, definition)
    demo_hash = hashlib.sha256(b'demo2026').hexdigest()
    demo_users = [('admin', 'admin'), ('manager', 'manager'), ('user', 'user'), ('hr', 'hr')]
    for username, role in demo_users:
        if c.execute('SELECT COUNT(*) FROM users WHERE username=?', (username,)).fetchone()[0] == 0:
            c.execute('INSERT INTO users (username,password_hash,role) VALUES (?,?,?)', (username, demo_hash, role))
    c.commit()
    if c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]>0:
        return
    print('Seeding...')
    S=_staff();T=_tickets(S);A=_assets()
    for s in S:c.execute('INSERT INTO staff (name,role,branch,province,is_it) VALUES (?,?,?,?,?)',(s['name'],s['role'],s['branch'],s['province'],1 if s['is_it'] else 0))
    for t in T:c.execute('INSERT INTO tickets (ticket_code,branch,province,category,title,description,priority,status,reported_by,assigned_to,asset_id,created_at,reported_at,resolved_at,ai_suggestion,ai_confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(t.get('ticket_code',''),t['branch'],t['province'],t['category'],t['title'],t['description'],t['priority'],t['status'],t['reported_by'],t['assigned_to'],t.get('asset_id',0),t['created_at'],t.get('reported_at',''),t['resolved_at'],t['ai_suggestion'],t['ai_confidence']))
    for a in A:c.execute('INSERT INTO assets (asset_code,branch,asset_type,name,serial,status,brand,spec,assigned_to,last_check,next_check,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(a.get('asset_code',''),a['branch'],a['asset_type'],a['name'],a['serial'],a['status'],a.get('brand',''),a.get('spec',''),a.get('assigned_to',''),a['last_check'],a['next_check'],a['notes']))
    for k in KB:c.execute('INSERT INTO knowledge_base (title,category,content,views) VALUES (?,?,?,?)',(k['title'],k['cat'],k['content'],k['v']))
    c.commit();
    print(f'Seeded: {len(S)} staff, {len(T)} tickets, {len(A)} assets')

@app.route('/howto-public')
def howto_public():
    return render_template('howto-public.html')

@app.route('/interview')
def interview_page():
    return render_template('interview.html')

@app.route('/vision')
def vision_page():
    return render_template('vision.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        c = get_db()
        u = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if u and check_pw(password, u['password_hash']):
            session['user_id'] = u['id']
            session['username'] = u['username']
            session['role'] = u['role']
            return redirect('/')
        return render_template('login.html',error='ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
@login_required
def dashboard():
    c=get_db()
    total=c.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
    op=c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    res=c.execute("SELECT COUNT(*) FROM tickets WHERE status='resolved'").fetchone()[0]
    prog=c.execute("SELECT COUNT(*) FROM tickets WHERE status='in_progress'").fetchone()[0]
    pend=c.execute("SELECT COUNT(*) FROM tickets WHERE status='pending'").fetchone()[0]
    critical=c.execute("SELECT COUNT(*) FROM tickets WHERE priority='critical'").fetchone()[0]
    recent=c.execute('SELECT * FROM tickets ORDER BY created_at DESC LIMIT 10').fetchall()
    _branch_short = {}
    for b in ALL_BRANCHES:
        abbr = PROVINCE_ABBR.get(b['province'], b['province'][:3])
        _branch_short[b['branch']] = abbr + b['district']
    recent = [dict(r, short_branch=_branch_short.get(r['branch'], r['branch'])) for r in recent]
    bp=c.execute('SELECT province,COUNT(*) as cnt,SUM(CASE WHEN status="open" THEN 1 ELSE 0 END) as open_cnt FROM tickets GROUP BY province').fetchall()
    bc=c.execute('SELECT category,COUNT(*) as cnt FROM tickets GROUP BY category ORDER BY cnt DESC').fetchall()
    ns=c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]
    na=c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    aa=c.execute("SELECT COUNT(*) FROM assets WHERE status='active'").fetchone()[0]
    itc=c.execute('SELECT COUNT(*) FROM staff WHERE is_it=1').fetchone()[0]
    nk=c.execute('SELECT COUNT(*) FROM knowledge_base').fetchone()[0]
    cl=[r['category'] for r in bc];cc=[r['cnt'] for r in bc]
    tp=round(bc[0]['cnt']/total*100) if bc and total>0 else 0
    return render_template('dashboard.html',total=total,open_tickets=op,resolved=res,in_progress=prog,pending=pend,critical=critical,recent=recent,by_province=bp,by_category=bc,cat_labels=cl,cat_counts=cc,top_cat_pct=tp,branch_count=NUM_BRANCHES,total_staff=ns,total_assets=na,active_assets=aa,it_team=itc,total_kb=nk)

@app.route('/tickets/v2')
@login_required
def tickets_v2_page():
    """TanStack Table v2 tickets page (React SPA via CDN)."""
    current_user = get_current_user()
    return render_template('tickets_v2.html', current_user=current_user)


@app.route('/tickets')
@login_required
def tickets_page():
    c=get_db()
    # Build query from filter params
    where = []
    params = []
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    branch = request.args.get('branch', '')
    province = request.args.get('province', '')
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    if status:
        where.append('status=?')
        params.append(status)
    if priority:
        where.append('priority=?')
        params.append(priority)
    if branch:
        where.append('branch=?')
        params.append(branch)
    if province:
        where.append('province=?')
        params.append(province)
    if category:
        where.append('category=?')
        params.append(category)
    if search:
        where.append('(title LIKE ? OR ticket_code LIKE ? OR branch LIKE ? OR reported_by LIKE ?)')
        params.extend(['%'+search+'%']*4)
    q = 'SELECT * FROM tickets'
    if where:
        q += ' WHERE ' + ' AND '.join(where)
    q += ' ORDER BY created_at DESC'
    rows=c.execute(q, params).fetchall()
    # Build short_branch lookup: {branch_name: abbr+district}
    _branch_short = {}
    for b in ALL_BRANCHES:
        abbr = PROVINCE_ABBR.get(b['province'], b['province'][:3])
        _branch_short[b['branch']] = abbr + b['district']
    rows = [dict(r, short_branch=_branch_short.get(r['branch'], r['branch'])) for r in rows]
    total=c.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
    open_tickets=c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    in_progress=c.execute("SELECT COUNT(*) FROM tickets WHERE status='in_progress'").fetchone()[0]
    pending=c.execute("SELECT COUNT(*) FROM tickets WHERE status='pending'").fetchone()[0]
    resolved=c.execute("SELECT COUNT(*) FROM tickets WHERE status='resolved'").fetchone()[0]
    closed_tickets=c.execute("SELECT COUNT(*) FROM tickets WHERE status='closed'").fetchone()[0]
    critical_tickets=c.execute("SELECT COUNT(*) FROM tickets WHERE priority='critical'").fetchone()[0]
    province_to_branches = PROVINCE_TO_BRANCHES
    province_to_branches_short = {prov: [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district']} for b in blist] for prov, blist in PROVINCE_TO_BRANCHES.items()}
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    branches_short = [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district'], 'province': b['province']} for b in ALL_BRANCHES]
    assets = c.execute('SELECT id, asset_tag, asset_type, name, branch, province, status FROM assets WHERE status="active" ORDER BY asset_tag, serial').fetchall()
    asset_suggestions = []
    for a in assets:
        cat, pri = suggest_ticket_defaults(a)
        asset_suggestions.append(dict(a, suggested_category=cat, suggested_priority=pri))
    current_user = get_current_user()
    return render_template('tickets.html',tickets=rows,branches=branches_short,
        filter_status=status, filter_priority=priority, filter_branch=branch,
        filter_province=province, filter_category=category, filter_search=search,
        total=total, open_tickets=open_tickets, in_progress=in_progress,
        pending=pending, resolved=resolved, closed_tickets=closed_tickets,
        branch_to_province=branch_to_province,
        province_to_branches=province_to_branches,
        province_to_branches_short=province_to_branches_short,
        critical_tickets=critical_tickets,
        assets=asset_suggestions,
        ticket_categories=list(TICKET_CATS.keys()),
        priority_help=PRIORITY_HELP_TH,
        category_help=CATEGORY_HELP_TH,
        current_user=current_user)

@app.route('/api/tickets')
@login_required
def api_tickets():
    """JSON API for TanStack Table v2 tickets page."""
    c = get_db()
    where = []
    params = []
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')
    branch = request.args.get('branch', '')
    province = request.args.get('province', '')
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    if status:
        where.append('status=?'); params.append(status)
    if priority:
        where.append('priority=?'); params.append(priority)
    if branch:
        where.append('branch=?'); params.append(branch)
    if province:
        where.append('province=?'); params.append(province)
    if category:
        where.append('category=?'); params.append(category)
    if search:
        where.append('(title LIKE ? OR ticket_code LIKE ? OR branch LIKE ? OR reported_by LIKE ?)')
        params.extend(['%'+search+'%']*4)
    # Role-based scope
    scope_sql, scope_params = ticket_scope_clause()
    if scope_sql:
        where.append(scope_sql)
        params.extend(scope_params)
    q = 'SELECT * FROM tickets'
    if where:
        q += ' WHERE ' + ' AND '.join(where)
    q += ' ORDER BY created_at DESC'
    rows = c.execute(q, params).fetchall()
    tickets = []
    for r in rows:
        t = dict(r)
        t['short_branch'] = SHORT_BRANCHES.get(t['branch'], t['branch'].replace('สาขา',''))
        tickets.append(t)
    # Stats
    stats = {
        'total': c.execute('SELECT COUNT(*) FROM tickets').fetchone()[0],
        'open': c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0],
        'in_progress': c.execute("SELECT COUNT(*) FROM tickets WHERE status='in_progress'").fetchone()[0],
        'pending': c.execute("SELECT COUNT(*) FROM tickets WHERE status='pending'").fetchone()[0],
        'resolved': c.execute("SELECT COUNT(*) FROM tickets WHERE status='resolved'").fetchone()[0],
        'closed': c.execute("SELECT COUNT(*) FROM tickets WHERE status='closed'").fetchone()[0],
        'critical': c.execute("SELECT COUNT(*) FROM tickets WHERE priority='critical'").fetchone()[0],
    }
    return jsonify(success=True, tickets=tickets, stats=stats)


@app.route('/ticket/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    c=get_db()
    t=c.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
    notes=c.execute('SELECT * FROM work_notes WHERE ticket_id=? ORDER BY created_at ASC',(ticket_id,)).fetchall()
    staff=c.execute('SELECT * FROM staff WHERE is_it=1 ORDER BY name').fetchall()
    assets=c.execute('SELECT * FROM assets WHERE status="active" ORDER BY asset_tag,serial').fetchall()
    kb=c.execute('SELECT * FROM knowledge_base ORDER BY views DESC').fetchall()
    kb_linked=None
    if t and t['kb_id']:
        kb_linked=c.execute('SELECT * FROM knowledge_base WHERE id=?',(t['kb_id'],)).fetchone()
    if not t:return 'Not found',404
    ticket = dict(t)
    ticket['short_branch'] = SHORT_BRANCHES.get(ticket['branch'], ticket['branch'].replace('สาขา',''))
    branches_short = [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district'], 'province': b['province']} for b in ALL_BRANCHES]
    provinces = sorted(set(b['province'] for b in ALL_BRANCHES))
    # Add short_branch to each asset dict
    asset_list = [dict(a) for a in assets]
    for a in asset_list:
        a['short_branch'] = SHORT_BRANCHES.get(a['branch'], a['branch'].replace('สาขา',''))
    current_user = get_current_user()
    return render_template('ticket_detail.html',ticket=ticket,notes=[dict(n) for n in notes],
        staff_list=[dict(s) for s in staff],asset_list=asset_list,kb_articles=[dict(k) for k in kb],kb_linked=dict(kb_linked) if kb_linked else None,
        current_user=current_user,branches_short=branches_short,provinces=provinces)

@app.route('/asset/<int:asset_id>')
@login_required
def asset_detail(asset_id):
    c=get_db()
    a=c.execute('SELECT * FROM assets WHERE id=?',(asset_id,)).fetchone()
    if not a:  return 'Not found',404
    a = dict(a)
    a['short_branch'] = SHORT_BRANCHES.get(a['branch'], a['branch'].replace('สาขา',''))
    linked=c.execute('SELECT * FROM tickets WHERE asset_id=? ORDER BY created_at DESC',(asset_id,)).fetchall()
    logs=c.execute('SELECT * FROM asset_logs WHERE asset_id=? ORDER BY created_at DESC',(asset_id,)).fetchall()
    return render_template('asset_detail.html',asset=a,linked_tickets=linked,logs=logs,current_user=session.get('username'))

@app.route('/api/assets')
@login_required
def api_assets():
    """JSON API for TanStack Table v2 assets page."""
    c = get_db()
    rows = c.execute('SELECT * FROM assets ORDER BY branch, asset_type').fetchall()
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    assets = []
    for r in rows:
        a = dict(r)
        a['province'] = branch_to_province.get(a['branch'], '-')
        a['short_branch'] = SHORT_BRANCHES.get(a['branch'], a['branch'].replace('สาขา',''))
        assets.append(a)
    stats = {
        'total': c.execute('SELECT COUNT(*) FROM assets').fetchone()[0],
        'active': c.execute("SELECT COUNT(*) FROM assets WHERE status='active'").fetchone()[0],
        'maintenance': c.execute("SELECT COUNT(*) FROM assets WHERE status='maintenance'").fetchone()[0],
        'retired': c.execute("SELECT COUNT(*) FROM assets WHERE status='retired'").fetchone()[0],
    }
    return jsonify(success=True, assets=assets, stats=stats)


@app.route('/api/staff')
@login_required
def api_staff():
    """JSON API for TanStack Table v2 staff page."""
    c = get_db()
    rows = c.execute('SELECT * FROM staff ORDER BY province, branch, name').fetchall()
    staff = [dict(r) for r in rows]
    for s in staff:
        s['short_branch'] = SHORT_BRANCHES.get(s['branch'], s['branch'].replace('สาขา',''))
    stats = {
        'total': c.execute('SELECT COUNT(*) FROM staff').fetchone()[0],
        'it': c.execute('SELECT COUNT(*) FROM staff WHERE is_it=1').fetchone()[0],
    }
    return jsonify(success=True, staff=staff, stats=stats)


@app.route('/api/knowledge')
@login_required
def api_knowledge():
    """JSON API for TanStack Table v2 knowledge page."""
    c = get_db()
    rows = c.execute('''
        SELECT kb.*, COALESCE(COUNT(t.id), 0) AS ticket_count
        FROM knowledge_base kb
        LEFT JOIN tickets t ON t.kb_id = kb.id
        GROUP BY kb.id
        ORDER BY kb.views DESC
    ''').fetchall()
    articles = [dict(r) for r in rows]
    stats = {
        'total': len(articles),
        'categories': len(set(a['category'] for a in articles)),
    }
    return jsonify(success=True, articles=articles, stats=stats)


@app.route('/assets/v2')
@login_required
def assets_v2_page():
    current_user = get_current_user()
    return render_template('assets_v2.html', current_user=current_user)


@app.route('/staff/v2')
@login_required
def staff_v2_page():
    current_user = get_current_user()
    return render_template('staff_v2.html', current_user=current_user)


@app.route('/knowledge/v2')
@login_required
def knowledge_v2_page():
    current_user = get_current_user()
    return render_template('knowledge_v2.html', current_user=current_user)


@app.route('/profile')
@app.route('/about')
def about_page():
    return render_template('about.html')


@login_required
def profile_page():
    c = get_db()
    current_user = get_current_user()
    staff = get_staff_for_user(current_user)
    asset_payload = None
    if staff and can_view_staff_asset_history(staff):
        asset_payload = staff_asset_history_payload(c, staff)
        c.commit()
    return render_template('profile.html', current_user=current_user, staff=staff, asset_payload=asset_payload)

@app.route('/assets')
@login_required
def assets_page():
    c=get_db()
    rows=c.execute('SELECT * FROM assets ORDER BY branch,asset_type').fetchall()
    total=c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    active=c.execute("SELECT COUNT(*) FROM assets WHERE status='active'").fetchone()[0]
    maint=c.execute("SELECT COUNT(*) FROM assets WHERE status='maintenance'").fetchone()[0]
    retired=c.execute("SELECT COUNT(*) FROM assets WHERE status='retired'").fetchone()[0]
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    branch_to_district = {b['branch']: b['district'] for b in ALL_BRANCHES}
    assets_list = []
    for r in rows:
        a = dict(r)
        a['province'] = branch_to_province.get(a['branch'], '-')
        a['short_branch'] = SHORT_BRANCHES.get(a['branch'], a['branch'].replace('สาขา',''))
        assets_list.append(a)
    province_to_branches = PROVINCE_TO_BRANCHES
    province_to_branches_short = {prov: [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district']} for b in blist] for prov, blist in PROVINCE_TO_BRANCHES.items()}
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    branches_short = [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district'], 'province': b['province']} for b in ALL_BRANCHES]
    current_user = get_current_user()
    return render_template('assets.html',assets=assets_list,total=total,active=active,maintenance=maint,retired=retired,branches=branches_short,asset_types=sorted(set(a['asset_type'] for a in assets_list)),branch_to_province=branch_to_province,province_to_branches=province_to_branches,province_to_branches_short=province_to_branches_short,current_user=current_user)

@app.route('/staff')
@login_required
def staff_page():
    c=get_db();rows=c.execute('SELECT * FROM staff ORDER BY province,branch,name').fetchall()
    total=c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]
    itc=c.execute('SELECT COUNT(*) FROM staff WHERE is_it=1').fetchone()[0]
    staff_by_province = c.execute('SELECT province,COUNT(*) as cnt,SUM(CASE WHEN is_it=1 THEN 1 ELSE 0 END) as it_cnt FROM staff GROUP BY province').fetchall()
    asset_count_rows = c.execute('''
        SELECT staff.id, COUNT(assets.id) AS cnt
        FROM staff
        LEFT JOIN assets ON assets.assigned_to = staff.name
        GROUP BY staff.id
    ''').fetchall()
    asset_counts = {r['id']: r['cnt'] for r in asset_count_rows}
    provinces = sorted(set(s['province'] for s in rows))
    roles = sorted(set(s['role'] for s in rows))
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    province_to_branches = PROVINCE_TO_BRANCHES
    province_to_branches_short = {prov: [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district']} for b in blist] for prov, blist in PROVINCE_TO_BRANCHES.items()}
    branches_short = [{'branch': b['branch'], 'short': SHORT_BRANCHES.get(b['branch'], b['district']), 'district': b['district'], 'province': b['province']} for b in ALL_BRANCHES]
    return render_template('staff.html',staff=rows,total=total,it_count=itc,branches=branches_short,staff_provinces=provinces,staff_roles=roles,branch_to_province=branch_to_province,province_to_branches=province_to_branches,province_to_branches_short=province_to_branches_short,staff_by_province=staff_by_province,asset_counts=asset_counts)

@app.route('/knowledge')
@login_required
def kb_page():
    c=get_db();rows=c.execute('''
        SELECT kb.*, COALESCE(COUNT(t.id), 0) AS ticket_count
        FROM knowledge_base kb
        LEFT JOIN tickets t ON t.kb_id = kb.id
        GROUP BY kb.id
        ORDER BY kb.views DESC
    ''').fetchall();
    cats = sorted(set(r['category'] for r in rows))
    return render_template('knowledge.html',articles=rows,kb_categories=cats)

@app.route('/kb/<int:kb_id>')
@login_required
def kb_detail(kb_id):
    c=get_db()
    a=c.execute('SELECT * FROM knowledge_base WHERE id=?',(kb_id,)).fetchone()
    if a:c.execute('UPDATE knowledge_base SET views=views+1 WHERE id=?',(kb_id,));c.commit()
    if not a:return 'Not found',404
    return render_template('kb_detail.html',article=a)

# ── API ──
@app.route('/api/ticket',methods=['POST'])
@login_required
def api_create():
    d = request.json or {}
    c = get_db()
    asset_id = int(d.get('asset_id') or 0)
    asset = c.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone() if asset_id else None
    cat, suggested_pri = suggest_ticket_defaults(asset, d.get('category',''))
    pri = d.get('priority') if d.get('priority') in ('critical','high','medium','low') else suggested_pri
    ai = TICKET_CATS.get(cat, {}).get('ai', '')
    branch = d.get('branch') or (asset['branch'] if asset else '')
    province = d.get('province') or (asset['province'] if asset else '')
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO tickets (branch,province,category,title,description,priority,status,reported_by,assigned_to,asset_id,created_at,reported_at,ai_suggestion,ai_confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (branch, province, cat, d.get('title',''), d.get('description',''), pri, 'open', d.get('reported_by',''), '', asset_id, now_str, now_str, ai, round(random.uniform(0.7,0.98),2)))
    c.commit();tid=c.execute('SELECT last_insert_rowid()').fetchone()[0];
    return jsonify(success=True,ticket_id=tid, suggested_category=cat, suggested_priority=pri)

@app.route('/api/ticket/<int:tid>/status',methods=['POST'])
@login_required
def api_status(tid):
    st=request.json.get('status','')
    if st not in ('open','in_progress','pending','resolved','closed'):return jsonify(success=False,error='Invalid'),400
    c=get_db()
    STATUS_LABELS = {'open':'เปิด','in_progress':'กำลังแก้','pending':'รอ','resolved':'เสร็จแล้ว','closed':'ปิด'}
    old = c.execute('SELECT status,assigned_to FROM tickets WHERE id=?',(tid,)).fetchone()
    old_label = STATUS_LABELS.get(old['status'],old['status']) if old else '?'
    new_label = STATUS_LABELS.get(st,st)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if st=='resolved':
        c.execute('UPDATE tickets SET status=?,resolved_at=? WHERE id=?',(st,now_str,tid))
    else:
        c.execute('UPDATE tickets SET status=?,resolved_at=NULL WHERE id=?',(st,tid))
    # Auto-log status change as work note
    author = request.json.get('changed_by','System')
    note_text = f'เปลี่ยนสถานะ: {old_label} → {new_label}'
    c.execute('INSERT INTO work_notes (ticket_id,note,created_by,created_at) VALUES (?,?,?,?)',(tid,note_text,author,now_str))
    c.commit()
    return jsonify(success=True)

@app.route('/api/ticket/<int:tid>/edit',methods=['POST'])
@login_required
def api_edit(tid):
    d=request.json;c=get_db()
    t=c.execute('SELECT * FROM tickets WHERE id=?',(tid,)).fetchone()
    if not t:
        return jsonify(success=False,error='Not Found'),404
    sets = []
    vals = []
    for field in ('title','description','priority','status','assigned_to','branch','province','category','reported_by','asset_id','kb_id'):
        val = d.get(field, None)
        if val is not None and val != '':
            sets.append(f'{field}=?')
            vals.append(val)
    if not sets:
        return jsonify(success=True)
    vals.append(tid)
    c.execute(f'UPDATE tickets SET {",".join(sets)} WHERE id=?', vals)
    # Auto-log field changes
    FIELD_LABELS = {'title':'หัวข้อ','description':'รายละเอียด','priority':'ความสำคัญ','category':'หมวด','branch':'สาขา','province':'จังหวัด','reported_by':'ผู้แจ้ง'}
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    author = d.get('changed_by','System')
    for field in ('title','description','priority','category','branch','province','reported_by'):
        new_val = d.get(field)
        old_val = t[field] if t else None
        if new_val is not None and new_val != '' and str(new_val) != str(old_val):
            label = FIELD_LABELS.get(field, field)
            note_text = f'แก้ไข: {label} เดิม: \'{old_val}\' → ใหม่: \'{new_val}\''
            c.execute('INSERT INTO work_notes (ticket_id,note,created_by,created_at) VALUES (?,?,?,?)',(tid,note_text,author,now_str))
    # Auto-log reassign if assigned_to changed
    new_assign = d.get('assigned_to')
    old_assign = t['assigned_to'] or 'ยังไม่มอบหมาย'
    if new_assign is not None and new_assign != '' and new_assign != t['assigned_to']:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        author = d.get('changed_by','System')
        note_text = f'มอบหมาย: {new_assign} (เดิม: {old_assign})'
        c.execute('INSERT INTO work_notes (ticket_id,note,created_by,created_at) VALUES (?,?,?,?)',(tid,note_text,author,now_str))
    # Auto-log asset change if asset_id changed
    new_asset = d.get('asset_id')
    if new_asset is not None and new_asset != '' and str(new_asset) != str(t['asset_id']):
        old_asset = t['asset_id'] or 'ไม่มี'
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        author = d.get('changed_by','System')
        # Fetch asset info for readable note
        a_row = c.execute('SELECT asset_tag,name FROM assets WHERE id=?',(int(new_asset),)).fetchone()
        asset_label = f"{a_row['asset_tag']} — {a_row['name']}" if a_row else str(new_asset)
        note_text = f'เชื่อม Asset: {asset_label}'
        c.execute('INSERT INTO work_notes (ticket_id,note,created_by,created_at) VALUES (?,?,?,?)',(tid,note_text,author,now_str))
    c.commit()
    return jsonify(success=True)

@app.route('/api/ticket/<int:tid>/delete',methods=['POST'])
@login_required
def api_delete(tid):
    c=get_db();c.execute('DELETE FROM tickets WHERE id=?',(tid,));c.commit();
    return jsonify(success=True)

@app.route('/api/ticket/<int:tid>/kb',methods=['POST'])
@login_required
def api_ticket_kb(tid):
    d=request.json;c=get_db()
    kb_id=d.get('kb_id',0)
    old_kb = c.execute('SELECT kb_id FROM tickets WHERE id=?',(tid,)).fetchone()
    old_kb_id = old_kb['kb_id'] if old_kb else 0
    c.execute('UPDATE tickets SET kb_id=? WHERE id=?',(kb_id,tid))
    # Auto-log KB attach
    if kb_id and kb_id != old_kb_id:
        kb_row = c.execute('SELECT title FROM knowledge_base WHERE id=?',(kb_id,)).fetchone()
        kb_title = kb_row['title'] if kb_row else f'#{kb_id}'
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        author = d.get('changed_by','System')
        note_text = f'แนบ KB: {kb_title}'
        c.execute('INSERT INTO work_notes (ticket_id,note,created_by,created_at) VALUES (?,?,?,?)',(tid,note_text,author,now_str))
    c.commit()
    return jsonify(success=True)

# ── Work Notes API ──
@app.route('/api/ticket/<int:tid>/notes',methods=['GET'])
@login_required
def api_notes_get(tid):
    c=get_db();rows=c.execute('SELECT * FROM work_notes WHERE ticket_id=? ORDER BY created_at ASC',(tid,)).fetchall();
    return jsonify(notes=[dict(r) for r in rows])

@app.route('/api/ticket/<int:tid>/notes',methods=['POST'])
@login_required
def api_notes_add(tid):
    d=request.json;c=get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO work_notes (ticket_id,note,created_by,created_at) VALUES (?,?,?,?)',(tid,d.get('note',''),d.get('created_by','Admin'),now_str))
    c.commit();nid=c.execute('SELECT last_insert_rowid()').fetchone()[0];
    return jsonify(success=True,id=nid)

@app.route('/api/chatbot',methods=['POST'])
@login_required
def chatbot():
    q=request.json.get('question','').lower()
    R={
        "printer":"🔧 เครื่องพิมพ์\n1. เช็ค Sensor\n2. ลูกยาง\n3. Calibrate\n4. แจ้ง IT",
        "เครื่องพิมพ์":"🔧 เครื่องพิมพ์\n1. เช็ค Sensor\n2. ลูกยาง\n3. Calibrate\n4. แจ้ง IT",
        "สมุด":"🔧 เครื่องพิมพ์: 1.Sensor 2.ลูกยาง 3.Calibrate",
        "vpn":"🔒 VPN\n1. เช็คอินเทอร์เน็ต\n2. รีสตาร์ท Router\n3. เช็ค WAN IP",
        "network":"🌐 เครือข่าย\n1. Ping Gateway\n2. เช็ค LAN\n3. รีสตาร์ท Modem",
        "เครือข่าย":"🌐 เครือข่าย\n1. Ping Gateway\n2. เช็ค LAN\n3. รีสตาร์ท Modem",
        "อินเทอร์เน็ต":"🌐 แก้: 1.Router 2.Ping 8.8.8.8 3.รีสตาร์ท",
        "core":"⚠️ ระบบ Core Banking ล่ม\n1. VPN Tunnel สำคัญ!\n2. เช็ค Server\n3. สำรองข้อมูล\n4. แจ้ง IT ทันที"
    }
    a="❓ ลองถาม: เครื่องพิมพ์, VPN, เครือข่าย, Core Banking"
    for kw,resp in R.items():
        if kw in q:a=resp;break
    return jsonify(answer=a)

# ── Asset API ──
@app.route('/api/asset/search',methods=['GET'])
@login_required
def api_asset_search():
    serial=request.args.get('serial','');c=get_db()
    a=c.execute('SELECT * FROM assets WHERE serial LIKE ?',('%'+serial+'%',)).fetchone()
    if not a: return jsonify(asset=None)
    cnt=c.execute('SELECT COUNT(*) FROM tickets WHERE asset_id=?',(a['id'],)).fetchone()[0];
    return jsonify(asset=dict(a),ticket_count=cnt)

@app.route('/api/asset/<int:aid>',methods=['GET'])
@login_required
def api_asset_get(aid):
    c=get_db();a=c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
    if not a: return jsonify(asset=None)
    cnt=c.execute('SELECT COUNT(*) FROM tickets WHERE asset_id=?',(aid,)).fetchone()[0]
    return jsonify(asset=dict(a),ticket_count=cnt)

@app.route('/api/asset',methods=['POST'])
@login_required
def api_asset_create():
    d=request.json;c=get_db()
    branch=d.get('branch','')
    asset_type=d.get('asset_type','')
    # Auto-generate asset_tag: prov_code + br_code + cat_code + seq
    branch_obj = next((b for b in ALL_BRANCHES if b['branch']==branch), None)
    prov_code = PROVINCE_CODES.get(branch_obj['province'],'0') if branch_obj else '0'
    br_code = BRANCH_CODES.get(branch,'0')
    cat_code = CATEGORY_CODES.get(asset_type,'XX')
    # Count existing assets of this type in this branch for sequence
    existing = c.execute('SELECT COUNT(*) FROM assets WHERE branch=? AND asset_type=?',(branch,asset_type)).fetchone()[0]
    seq = existing + 1
    asset_tag = f"{prov_code}{br_code}{cat_code}{seq:02d}"
    asset_code = f"{ALL_BRANCHES.index(branch_obj)+1 if branch_obj else 1:02d}{CATEGORY_CODES.get(asset_type,'XX')}{seq:02d}"
    c.execute('INSERT INTO assets (asset_tag,asset_code,branch,asset_type,name,serial,status,last_check,next_check,notes) VALUES (?,?,?,?,?,?,?,?,?,?)',
              (asset_tag,asset_code,branch,asset_type,d.get('name',''),d.get('serial',''),d.get('status','active'),d.get('last_check',''),d.get('next_check',''),d.get('notes','')))
    c.commit();aid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
    return jsonify(success=True,id=aid,asset_tag=asset_tag)

@app.route('/api/asset/<int:aid>/edit',methods=['POST'])
@login_required
def api_asset_edit(aid):
    d=request.json;c=get_db()
    old = c.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
    if not old:
        return jsonify(success=False,error='Not Found'),404
    # Build change log
    changes = []
    STATUS_LABELS = {'active':'Active','maintenance':'Maintenance','retired':'Retired'}
    field_labels = {'name':'รุ่น','serial':'Serial','asset_type':'ประเภท','status':'สถานะ','branch':'สาขา','assigned_to':'ผู้ถือครอง','next_check':'ตรวจครั้งต่อไป','notes':'หมายเหตุ'}
    for field, label in field_labels.items():
        old_val = old[field] or ''
        new_val = d.get('field', '')  # will check below
    # Actually compare each field
    for field in ('name','serial','asset_type','status','branch','assigned_to','next_check','notes'):
        old_val = old[field] or ''
        new_val = d.get(field, '') or ''
        if str(old_val) != str(new_val):
            label = field_labels.get(field, field)
            if field == 'status':
                old_val = STATUS_LABELS.get(old_val, old_val)
                new_val = STATUS_LABELS.get(new_val, new_val)
            elif field == 'branch':
                old_val = SHORT_BRANCHES.get(old_val, old_val)
                new_val = SHORT_BRANCHES.get(new_val, new_val)
            changes.append(f'{label}: {old_val} → {new_val}')
    
    new_assigned_to = d.get('assigned_to', old['assigned_to'] or '')
    c.execute('UPDATE assets SET name=?,serial=?,asset_type=?,status=?,branch=?,assigned_to=?,next_check=?,notes=? WHERE id=?',
              (d.get('name',''),d.get('serial',''),d.get('asset_type',''),d.get('status','active'),d.get('branch',''),new_assigned_to,d.get('next_check',''),d.get('notes',''),aid))

    if str(old['assigned_to'] or '') != str(new_assigned_to or ''):
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        author = d.get('changed_by','System')
        c.execute("UPDATE asset_ownership_history SET ended_at=?, note=CASE WHEN note='' THEN ? ELSE note END WHERE asset_id=? AND ended_at IS NULL",
                  (now_str, 'โอน/เปลี่ยนผู้ถือครอง', aid))
        if new_assigned_to:
            c.execute('INSERT INTO asset_ownership_history (asset_id, staff_name, started_at, action, note, created_by, created_at) VALUES (?,?,?,?,?,?,?)',
                      (aid, new_assigned_to, now_str, 'assigned', 'รับครอง Asset', author, now_str))

    # Log changes
    if changes:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        author = d.get('changed_by','System')
        note_text = 'แก้ไข Asset: ' + ', '.join(changes)
        c.execute('INSERT INTO asset_logs (asset_id,note,created_by,created_at) VALUES (?,?,?,?)',(aid,note_text,author,now_str))
    c.commit()
    return jsonify(success=True)

@app.route('/api/asset/<int:aid>/delete',methods=['POST'])
@login_required
def api_asset_delete(aid):
    c=get_db();c.execute('DELETE FROM assets WHERE id=?',(aid,));c.commit();
    return jsonify(success=True)

# ── Settings & User Management ──
@app.route('/settings')
@login_required
def settings_page():
    user = get_current_user()
    c = get_db()
    users = c.execute('SELECT id, username, role, created_at FROM users ORDER BY id').fetchall()
    return render_template('settings.html', user=user, users=users)

@app.route('/api/user', methods=['POST'])
@role_required('admin')
def api_user_create():
    d = request.json
    c = get_db()
    pw_hash = hashlib.sha256(d.get('password', 'demo2026').encode()).hexdigest()
    try:
        c.execute('INSERT INTO users (username, password_hash, role) VALUES (?,?,?)',
                  (d['username'], pw_hash, d.get('role', 'user')))
        c.commit()
        uid = c.execute('SELECT last_insert_rowid()').fetchone()[0]
        return jsonify(success=True, id=uid)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 400

@app.route('/api/user/<int:uid>/role', methods=['POST'])
@role_required('admin')
def api_user_role(uid):
    d = request.json
    c = get_db()
    c.execute('UPDATE users SET role=? WHERE id=?', (d['role'], uid))
    c.commit()
    return jsonify(success=True)

@app.route('/api/user/<int:uid>/delete', methods=['POST'])
@role_required('admin')
def api_user_delete(uid):
    if uid == session.get('user_id'):
        return jsonify(success=False, error='ไม่สามารถลบตัวเองได้'), 400
    c = get_db()
    c.execute('DELETE FROM users WHERE id=?', (uid,))
    c.commit()
    return jsonify(success=True)

@app.route('/api/user/password', methods=['POST'])
@login_required
def api_change_password():
    d = request.json
    c = get_db()
    u = c.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    if not check_pw(d.get('current', ''), u['password_hash']):
        return jsonify(success=False, error='รหัสผ่านปัจจุบันไม่ถูกต้อง'), 400
    new_hash = hashlib.sha256(d['new'].encode()).hexdigest()
    c.execute('UPDATE users SET password_hash=? WHERE id=?', (new_hash, session['user_id']))
    c.commit()
    return jsonify(success=True)


# ── Staff API ──
@app.route('/api/staff',methods=['POST'])
@login_required
def api_staff_create():
    d=request.json;c=get_db()
    c.execute('INSERT INTO staff (name,role,branch,province,is_it) VALUES (?,?,?,?,?)',
              (d.get('name',''),d.get('role',''),d.get('branch',''),d.get('province',''),d.get('is_it',0)))
    c.commit();sid=c.execute('SELECT last_insert_rowid()').fetchone()[0];
    return jsonify(success=True,id=sid)

@app.route('/api/staff/<int:sid>/edit',methods=['POST'])
@login_required
def api_staff_edit(sid):
    d=request.json;c=get_db()
    c.execute('UPDATE staff SET name=?,role=?,is_it=?,branch=?,province=? WHERE id=?',
              (d.get('name',''),d.get('role',''),d.get('is_it',0),d.get('branch',''),d.get('province',''),sid))
    c.commit();
    return jsonify(success=True)

@app.route('/api/staff/<int:sid>/delete',methods=['POST'])
@login_required
def api_staff_delete(sid):
    c=get_db();c.execute('DELETE FROM staff WHERE id=?',(sid,));c.commit();
    return jsonify(success=True)

# ── KB API ──
@app.route('/api/kb',methods=['POST'])
@login_required
def api_kb_create():
    d=request.json;c=get_db()
    c.execute('INSERT INTO knowledge_base (title,category,content,views) VALUES (?,?,?,?)',
              (d.get('title',''),d.get('category',''),d.get('content',''),d.get('views',0)))
    c.commit();tid=c.execute('SELECT last_insert_rowid()').fetchone()[0];
    return jsonify(success=True,id=tid)

@app.route('/api/kb/<int:kid>/edit',methods=['POST'])
@login_required
def api_kb_edit(kid):
    d=request.json;c=get_db()
    c.execute('UPDATE knowledge_base SET title=?,category=?,content=?,views=? WHERE id=?',
              (d.get('title',''),d.get('category',''),d.get('content',''),d.get('views',0),kid))
    c.commit();
    return jsonify(success=True)

@app.route('/api/kb/<int:kid>/delete',methods=['POST'])
@login_required
def api_kb_delete(kid):
    c=get_db();c.execute('DELETE FROM knowledge_base WHERE id=?',(kid,));c.commit();
    return jsonify(success=True)


@app.route('/api/district-data')
@login_required
def api_district_data():
    c = get_db()
    # Get ticket count per district
    branch_district = {b['branch']: b['district'] for b in ALL_BRANCHES}
    branch_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    district_coords = {b['district']: {'lat': 6.8, 'lng': 101.3} for b in ALL_BRANCHES}  # approximate

    # Ticket counts by branch
    ticket_counts = {}
    rows = c.execute('SELECT branch, COUNT(*) as cnt FROM tickets GROUP BY branch').fetchall()
    for r in rows:
        d = branch_district.get(r['branch'], '')
        if d:
            ticket_counts[d] = ticket_counts.get(d, 0) + r['cnt']

    # Asset counts by branch
    asset_counts = {}
    rows = c.execute('SELECT branch, COUNT(*) as cnt FROM assets GROUP BY branch').fetchall()
    for r in rows:
        d = branch_district.get(r['branch'], '')
        if d:
            asset_counts[d] = asset_counts.get(d, 0) + r['cnt']
    # Build result for all 33 districts
    result = []
    for b in ALL_BRANCHES:
        d = b['district']
        result.append({
            'name': d,
            'province': b['province'],
            'tickets': ticket_counts.get(d, 0),
            'assets': asset_counts.get(d, 0),
            'lat': b.get('lat', 6.8),
            'lng': b.get('lng', 101.3)
        })
    return jsonify(result)

@app.route('/sitemap')
@login_required
def sitemap_page():
    c = get_db()
    total_tickets = c.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
    total_assets = c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    total_staff = c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]
    total_kb = c.execute('SELECT COUNT(*) FROM knowledge_base').fetchone()[0]
    return render_template('sitemap.html', total_tickets=total_tickets, total_assets=total_assets, total_staff=total_staff, total_kb=total_kb)

@app.route('/howto')
@login_required
def howto_page():
    return render_template('howto.html')

LEAVE_TYPES = ('ลาป่วย', 'ลากิจ', 'ลาพักร้อน', 'ลาอื่น ๆ')
LEAVE_STATUS_LABELS = {'pending':'รออนุมัติ','approved':'อนุมัติ','rejected':'ไม่อนุมัติ','cancelled':'ยกเลิก'}

@app.route('/calendar')
@login_required
def calendar_page():
    c = get_db()
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
        month = int(request.args.get('month', today.month))
        if month < 1 or month > 12:
            raise ValueError
    except ValueError:
        year = today.year
        month = today.month

    first_day = date(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    last_day = date(year, month, days_in_month)
    prev_month = first_day.replace(day=1) - timedelta(days=1)
    next_month = last_day + timedelta(days=1)

    rows = c.execute(
        """
        SELECT * FROM leave_requests
        WHERE start_date <= ? AND end_date >= ?
        ORDER BY start_date ASC, id ASC
        """,
        (last_day.isoformat(), first_day.isoformat())
    ).fetchall()
    leave_requests = [dict(r) for r in rows]

    leave_by_day = {}
    for req in leave_requests:
        try:
            start_dt = datetime.strptime(req['start_date'], '%Y-%m-%d').date()
            end_dt = datetime.strptime(req['end_date'], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            continue
        cursor = max(start_dt, first_day)
        end_limit = min(end_dt, last_day)
        while cursor <= end_limit:
            leave_by_day.setdefault(cursor.isoformat(), []).append(req)
            cursor += timedelta(days=1)

    month_weeks = []
    for week in calendar.Calendar(firstweekday=6).monthdatescalendar(year, month):
        month_weeks.append([
            {
                'date': day,
                'iso': day.isoformat(),
                'day': day.day,
                'in_month': day.month == month,
                'is_today': day == today,
                'leaves': leave_by_day.get(day.isoformat(), []),
            }
            for day in week
        ])

    return render_template('calendar.html', current_user=get_current_user(), month_weeks=month_weeks,
                           month_name=first_day.strftime('%B %Y'), month=month, year=year,
                           prev_year=prev_month.year, prev_month=prev_month.month,
                           next_year=next_month.year, next_month=next_month.month,
                           leave_requests=leave_requests, status_labels=LEAVE_STATUS_LABELS)

@app.route('/leave', methods=['GET','POST'])
@login_required
def leave_page():
    c = get_db()
    current_user = get_current_user()
    message = ''
    error = ''
    if request.method == 'POST':
        leave_type = request.form.get('leave_type','').strip()
        start_date = request.form.get('start_date','').strip()
        end_date = request.form.get('end_date','').strip()
        reason = request.form.get('reason','').strip()
        if leave_type not in LEAVE_TYPES:
            error = 'กรุณาเลือกประเภทการลา'
        elif not start_date or not end_date:
            error = 'กรุณาระบุวันที่เริ่มและวันที่สิ้นสุด'
        elif not reason:
            error = 'กรุณาระบุเหตุผล'
        else:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                days = (end_dt - start_dt).days + 1
                if days <= 0:
                    error = 'วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่ม'
                else:
                    c.execute('INSERT INTO leave_requests (user_id,username,leave_type,start_date,end_date,days,reason,status) VALUES (?,?,?,?,?,?,?,?)',
                              (current_user['id'], current_user['username'], leave_type, start_date, end_date, days, reason, 'pending'))
                    c.commit()
                    message = 'ส่งคำขอลาแล้ว — รอ Manager/Admin อนุมัติ'
            except ValueError:
                error = 'รูปแบบวันที่ไม่ถูกต้อง'
    rows = c.execute('SELECT * FROM leave_requests WHERE user_id=? ORDER BY created_at DESC, id DESC', (current_user['id'],)).fetchall()
    leave_requests = [dict(r) for r in rows]
    pending_count = sum(1 for r in leave_requests if r['status'] == 'pending')
    approved_count = sum(1 for r in leave_requests if r['status'] == 'approved')
    rejected_count = sum(1 for r in leave_requests if r['status'] == 'rejected')
    return render_template('leave.html', current_user=current_user, can_approve=is_manager(), leave_types=LEAVE_TYPES,
                           leave_requests=leave_requests, status_labels=LEAVE_STATUS_LABELS, pending_count=pending_count,
                           approved_count=approved_count, rejected_count=rejected_count, message=message, error=error)

@app.route('/leave-approvals', methods=['GET','POST'])
@login_required
def leave_approvals_page():
    if not is_manager():
        return forbidden_response()

    c = get_db()
    current_user = get_current_user()
    message = ''
    error = ''

    if request.method == 'POST':
        action = request.form.get('action', '').strip()
        approval_note = request.form.get('approval_note', '').strip()[:300]
        try:
            request_id = int(request.form.get('request_id', '0'))
        except ValueError:
            request_id = 0

        if action not in ('approve', 'reject'):
            error = 'คำสั่งไม่ถูกต้อง'
        elif request_id <= 0:
            error = 'ไม่พบคำขอที่ต้องการดำเนินการ'
        else:
            leave_request = c.execute(
                "SELECT * FROM leave_requests WHERE id=? AND status='pending'",
                (request_id,)
            ).fetchone()
            if not leave_request:
                error = 'คำขอนี้ไม่อยู่ในสถานะรออนุมัติแล้ว'
            else:
                new_status = 'approved' if action == 'approve' else 'rejected'
                c.execute(
                    'UPDATE leave_requests SET status=?, approver_id=?, approval_note=? WHERE id=?',
                    (new_status, current_user['id'], approval_note, request_id)
                )
                c.commit()
                message = 'อนุมัติคำขอลาแล้ว' if new_status == 'approved' else 'ไม่อนุมัติคำขอลาแล้ว'

    pending_rows = c.execute(
        "SELECT * FROM leave_requests WHERE status='pending' ORDER BY created_at ASC, id ASC"
    ).fetchall()
    recent_rows = c.execute(
        "SELECT * FROM leave_requests WHERE status IN ('approved','rejected') ORDER BY created_at DESC, id DESC LIMIT 20"
    ).fetchall()
    return render_template('leave-approvals.html', current_user=current_user,
                           pending_requests=[dict(r) for r in pending_rows],
                           recent_requests=[dict(r) for r in recent_rows],
                           status_labels=LEAVE_STATUS_LABELS, message=message, error=error)

@app.route('/route-planner')
@login_required
def route_planner_page():
    c = get_db()
    branch_district = {b['branch']: b['district'] for b in ALL_BRANCHES}
    branch_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    district_branch = {b['district']: b['branch'] for b in ALL_BRANCHES}

    # Approximate district center points for dispatch planning map.
    district_coords = {
        'เมืองปัตตานี': (6.8690, 101.2500), 'โคกโพธิ์': (6.7200, 101.0900), 'หนองจิก': (6.8400, 101.1800),
        'ปะนาเระ': (6.8600, 101.4900), 'มายอ': (6.7200, 101.4100), 'ทุ่งยางแดง': (6.6200, 101.4300),
        'สายบุรี': (6.7000, 101.6200), 'ไม้แก่น': (6.6200, 101.6800), 'ยะหริ่ง': (6.8700, 101.3600),
        'ยะรัง': (6.7600, 101.2900), 'กะพ้อ': (6.5900, 101.5400), 'แม่ลาน': (6.6700, 101.2400),
        'เมืองยะลา': (6.5400, 101.2800), 'เบตง': (5.7700, 101.0700), 'บันนังสตา': (6.2700, 101.2700),
        'ธารโต': (6.0800, 101.1800), 'ยะหา': (6.4800, 101.1300), 'รามัน': (6.4800, 101.4300),
        'กาบัง': (6.4200, 101.0200), 'กรงปินัง': (6.4100, 101.2800),
        'เมืองนราธิวาส': (6.4200, 101.8200), 'ตากใบ': (6.2600, 102.0500), 'บาเจาะ': (6.5200, 101.6500),
        'ยี่งอ': (6.3900, 101.7100), 'ระแงะ': (6.3000, 101.7200), 'รือเสาะ': (6.3900, 101.5200),
        'ศรีสาคร': (6.2400, 101.5000), 'แว้ง': (5.9300, 101.8900), 'สุคิริน': (5.9400, 101.7700),
        'สุไหงโก-ลก': (6.0300, 101.9700), 'สุไหงปาดี': (6.0800, 101.8700), 'จะแนะ': (6.0900, 101.6400),
        'เจาะไอร้อง': (6.2300, 101.8000),
    }

    priority_counts = {}
    rows = c.execute("""
        SELECT branch, priority, COUNT(*) as cnt
        FROM tickets
        WHERE status NOT IN ('resolved','closed')
        GROUP BY branch, priority
    """).fetchall()
    for r in rows:
        d = branch_district.get(r['branch'], '')
        if not d:
            continue
        priority_counts.setdefault(d, {'critical': 0, 'high': 0, 'medium': 0, 'low': 0})
        priority_counts[d][r['priority']] = priority_counts[d].get(r['priority'], 0) + r['cnt']

    category_counts = {}
    cat_rows = c.execute("""
        SELECT branch, category, COUNT(*) as cnt
        FROM tickets
        WHERE status NOT IN ('resolved','closed')
        GROUP BY branch, category
    """).fetchall()
    for r in cat_rows:
        d = branch_district.get(r['branch'], '')
        if not d:
            continue
        category_counts.setdefault(d, {})
        category_counts[d][r['category']] = category_counts[d].get(r['category'], 0) + r['cnt']

    ticket_counts = {}
    rows = c.execute("SELECT branch, COUNT(*) as cnt FROM tickets WHERE status NOT IN ('resolved','closed') GROUP BY branch").fetchall()
    for r in rows:
        d = branch_district.get(r['branch'], '')
        if d:
            ticket_counts[d] = ticket_counts.get(d, 0) + r['cnt']

    asset_counts = {}
    rows = c.execute('SELECT branch, COUNT(*) as cnt FROM assets GROUP BY branch').fetchall()
    for r in rows:
        d = branch_district.get(r['branch'], '')
        if d:
            asset_counts[d] = asset_counts.get(d, 0) + r['cnt']

    def distance_km(a, b):
        import math
        lat1, lon1 = a; lat2, lon2 = b
        r = 6371
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
        h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*r*math.asin(math.sqrt(h))

    hq = {'name': 'HQ เมืองปัตตานี', 'short_branch': 'HQ', 'lat': 6.8690, 'lng': 101.2500, 'x': 0, 'y': 0}
    districts = []
    for b in ALL_BRANCHES:
        d = b['district']
        p = priority_counts.get(d, {'critical': 0, 'high': 0, 'medium': 0, 'low': 0})
        active = ticket_counts.get(d, 0)
        assets = asset_counts.get(d, 0)
        cats = category_counts.get(d, {})
        cat_summary = ' · '.join(f'{k} {v}' for k, v in sorted(cats.items(), key=lambda item: item[1], reverse=True)[:3])
        dispatch_score = p.get('critical',0)*100 + p.get('high',0)*40 + p.get('medium',0)*12 + p.get('low',0)*5 + active*2
        lat, lng = district_coords.get(d, (6.45, 101.45))
        if active <= 0:
            color = 'none'
        elif p.get('critical',0) > 0 or dispatch_score >= 100:
            color = 'orange'
        elif p.get('high',0) > 0 or dispatch_score >= 40:
            color = 'yellow'
        else:
            color = 'green'
        districts.append({
            'name': d, 'short_branch': _short_branch(b['branch']), 'branch': b['branch'], 'province': b['province'],
            'tickets': active, 'assets': assets, 'critical': p.get('critical',0), 'high': p.get('high',0),
            'medium': p.get('medium',0), 'low': p.get('low',0), 'score': dispatch_score,
            'categories': cats, 'category_summary': cat_summary or '-',
            'priority': 'สูง' if color == 'orange' else ('กลาง' if color == 'yellow' else ('ต่ำ' if color == 'green' else '-')),
            'color': color, 'lat': lat, 'lng': lng, 'distance_from_hq': distance_km((hq['lat'], hq['lng']), (lat, lng))
        })

    active_sites = [d for d in districts if d['tickets'] > 0]
    ranked = sorted(districts, key=lambda x: (x['score'], -x['distance_from_hq']), reverse=True)

    # Dispatch route: start HQ, choose most urgent next; when urgency ties, choose nearer current site.
    remaining = active_sites[:]
    route_points = []
    current = (hq['lat'], hq['lng'])
    while remaining and len(route_points) < 12:
        remaining.sort(key=lambda d: (d['score'], -distance_km(current, (d['lat'], d['lng']))), reverse=True)
        chosen = remaining.pop(0)
        chosen['leg_km'] = round(distance_km(current, (chosen['lat'], chosen['lng'])), 1)
        route_points.append(chosen)
        current = (chosen['lat'], chosen['lng'])

    min_lat, max_lat = 5.70, 6.95
    min_lng, max_lng = 100.95, 102.10
    def xy(lat, lng):
        return (60 + ((lng - min_lng) / (max_lng - min_lng)) * 880,
                470 - ((lat - min_lat) / (max_lat - min_lat)) * 400)
    hq['x'], hq['y'] = xy(hq['lat'], hq['lng'])
    for i, d in enumerate(route_points, start=1):
        d['route_no'] = i
        d['x'], d['y'] = xy(d['lat'], d['lng'])
    for d in districts:
        d['x'], d['y'] = xy(d['lat'], d['lng'])

    route_segments = []
    prev = hq
    for d in route_points:
        route_segments.append({
            'x1': prev['x'], 'y1': prev['y'], 'x2': d['x'], 'y2': d['y'],
            'km': d['leg_km'], 'mx': (prev['x'] + d['x']) / 2, 'my': (prev['y'] + d['y']) / 2
        })
        prev = d

    total_tickets = sum(d['tickets'] for d in districts)
    total_assets = sum(d['assets'] for d in districts)
    total_critical = sum(d['critical'] for d in districts)
    import json as _json
    geo = _json.loads(open(os.path.join(_BASE_DIR, 'static', 'districts-geo.json'), encoding='utf-8').read())
    south = {"type": "FeatureCollection", "features": [f for f in geo['features'] if f.get('properties',{}).get('province') in ('ปัตตานี','ยะลา','นราธิวาส')]}
    return render_template('route-planner.html', districts=ranked, route_points=route_points, route_segments=route_segments, hq=hq,
                           total_tickets=total_tickets, total_assets=total_assets, total_critical=total_critical,
                           south_geojson=_json.dumps(south, ensure_ascii=False))

def _start_init_db():
    """Run init_db in a background thread so it doesn't block gunicorn startup."""
    try:
        with app.app_context():
            init_db()
            c = get_db()
            ns = c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]
            nt = c.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
            na = c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
            print(f'[INIT OK] {ns} staff, {nt} tickets, {na} assets')
    except Exception as e:
        print(f'[INIT ERR] {e}')

if __name__ == '__main__':
    import threading
    t = threading.Thread(target=_start_init_db, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # Running under gunicorn — init_db runs in background thread
    import threading
    t = threading.Thread(target=_start_init_db, daemon=True)
    t.start()

@app.route('/test')
@login_required
def test_page():
    import json as _json
    geo = _json.loads(open(os.path.join(_BASE_DIR, 'static', 'districts-geo.json'), encoding='utf-8').read())
    south = {"type": "FeatureCollection", "features": [f for f in geo['features'] if f.get('properties',{}).get('province') in ('ปัตตานี','ยะลา','นราธิวาส')]}
    return render_template('test.html', south_geojson=_json.dumps(south, ensure_ascii=False))


@app.route('/api/district-tickets')
@login_required
def api_district_tickets():
    c = get_db()
    branch_district = {b['branch']: b['district'] for b in ALL_BRANCHES}
    rows = c.execute("""
        SELECT branch, priority, category, COUNT(*) as cnt
        FROM tickets
        WHERE status NOT IN ('resolved','closed')
        GROUP BY branch, priority, category
    """).fetchall()
    result = {}
    for r in rows:
        d = branch_district.get(r['branch'], '')
        if not d:
            continue
        result.setdefault(d, {'tickets': 0, 'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'categories': {}})
        result[d]['tickets'] += r['cnt']
        result[d][r['priority']] = result[d].get(r['priority'], 0) + r['cnt']
        cats = result[d]['categories']
        cats[r['category']] = cats.get(r['category'], 0) + r['cnt']
    return jsonify(result)


# ─── Projects (admin only) ───

PROJECT_STATUS_LABELS = {
    'planned': 'วางแผน',
    'in_progress': 'กำลังทำ',
    'done': 'เสร็จแล้ว',
    'paused': 'พักไว้',
}
PROJECT_STATUS_COLORS = {
    'planned': '#95a5a6',
    'in_progress': '#3498db',
    'done': '#27ae60',
    'paused': '#e67e22',
}


def _seed_projects():
    c = get_db()
    if c.execute('SELECT COUNT(*) FROM projects').fetchone()[0] > 0:
        return
    projects = [
        {
            'name': 'ITSM Demo', 'slug': 'itsm-demo', 'status': 'in_progress',
            'phase': 'v0.7 — Pre-interview polish',
            'description': 'ระบบ IT Service Management Demo สำหรับสัมภาษณ์งาน',
            'live_url': 'https://itsmdemo-zyde.fly.dev',
            'github_url': 'https://github.com/zyde-david/itsmdemo',
            'sort_order': 1,
            'before_text': 'เริ่มจากระบบ ticket ธรรมดา',
            'now_text': 'มี dashboard, tickets, assets, staff, route planner ครบ',
            'next_text': 'เพิ่ม asset-staff link, audit log, polish UI',
        },
        {
            'name': 'Pi4 Home Server', 'slug': 'pi4-home', 'status': 'planned',
            'phase': 'Planning — hardware ready',
            'description': 'Pi4 8GB เป็น home server: AdGuard + Tailscale',
            'live_url': '', 'github_url': '', 'sort_order': 2,
            'before_text': 'ยังไม่มี server ตัวเล็ก',
            'now_text': 'วางแผน hardware และ software stack',
            'next_text': 'ติดตั้ง Ubuntu ARM64 + Docker + AdGuard + Tailscale',
        },
    ]
    for p in projects:
        c.execute(
            'INSERT INTO projects (name,slug,status,phase,description,live_url,github_url,sort_order,before_text,now_text,next_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (p['name'], p['slug'], p['status'], p['phase'], p['description'], p['live_url'], p['github_url'], p['sort_order'], p['before_text'], p['now_text'], p['next_text'])
        )
    itsm_id = c.execute('SELECT id FROM projects WHERE slug=?', ('itsm-demo',)).fetchone()[0]
    tasks = [
        (itsm_id, 'Dashboard + Tickets UI', 'done', 'v0.1', 1),
        (itsm_id, 'Assets + Staff pages', 'done', 'v0.2', 2),
        (itsm_id, 'Route Planner (Leaflet map)', 'done', 'v0.3', 3),
        (itsm_id, 'Settings + Role card', 'done', 'v0.4', 4),
        (itsm_id, 'Dev log + Footer polish', 'done', 'v0.5', 5),
        (itsm_id, 'Asset-Staff link', 'pending', 'v0.6', 6),
        (itsm_id, 'Pre-interview audit + polish', 'in_progress', 'v0.7', 7),
    ]
    for t in tasks:
        c.execute('INSERT INTO project_tasks (project_id,title,status,phase,sort_order) VALUES (?,?,?,?,?)', t)
    logs = [
        (itsm_id, '31 May 2026 — เริ่มโปรเจค สร้าง Flask app + SQLite'),
        (itsm_id, '1 Jun 2026 — Dashboard + Tickets + Assets pages'),
        (itsm_id, '2 Jun 2026 — Staff page + Route Planner + Settings'),
        (itsm_id, '3 Jun 2026 — Deploy Fly.io + Leaflet map + Dev log'),
        (itsm_id, '4 Jun 2026 — Footer polish + Tech Stack reorder + Projects page'),
    ]
    for l in logs:
        c.execute('INSERT INTO project_logs (project_id,note) VALUES (?,?)', l)
    c.commit()


@app.route('/projects')
@login_required
def projects_page():
    if not is_admin():
        return redirect('/dashboard')
    _seed_projects()
    c = get_db()
    projects = c.execute('SELECT * FROM projects ORDER BY sort_order').fetchall()
    result = []
    for p in projects:
        p = dict(p)
        counts = c.execute('SELECT status, COUNT(*) as cnt FROM project_tasks WHERE project_id=? GROUP BY status', (p['id'],)).fetchall()
        p['tasks_done'] = sum(r['cnt'] for r in counts if r['status'] == 'done')
        p['tasks_total'] = sum(r['cnt'] for r in counts)
        p['status_label'] = PROJECT_STATUS_LABELS.get(p['status'], p['status'])
        p['status_color'] = PROJECT_STATUS_COLORS.get(p['status'], '#95a5a6')
        total_min = c.execute('SELECT COALESCE(SUM(minutes),0) FROM project_time_entries WHERE project_id=?', (p['id'],)).fetchone()[0]
        p['time_spent'] = total_min or p.get('time_spent_minutes', 0)
        result.append(p)
    return render_template('projects.html', projects=result, current_user=session.get('username'))


KANBAN_DB_PATH = os.environ.get('KANBAN_DB_PATH', os.path.expanduser('~/.hermes/kanban.db'))
KANBAN_OPERATOR_USERS = tuple(
    user.strip().lower()
    for user in os.environ.get('KANBAN_OPERATOR_USERS', 'zyde').split(',')
    if user.strip()
)
KANBAN_STATUS_GROUPS = {
    'done': ('done', 'completed', 'archived'),
    'processing': ('running', 'claimed'),
    'next': ('ready', 'todo', 'blocked', 'triage'),
}


def _kanban_ts(value):
    if not value:
        return ''
    try:
        return datetime.fromtimestamp(int(value)).strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError, OSError):
        return ''


def _safe_summary(text, limit=180):
    text = (text or '').replace('\n', ' ').strip()
    return text[:limit - 1] + '…' if len(text) > limit else text


def _kanban_progress(metadata_text):
    if not metadata_text:
        return None
    try:
        metadata = json.loads(metadata_text)
    except (TypeError, ValueError):
        return None
    for key in ('progress_percent', 'percent', 'progress'):
        if key in metadata:
            try:
                value = float(metadata[key])
                if 0 <= value <= 1:
                    value *= 100
                return max(0, min(100, round(value)))
            except (TypeError, ValueError):
                pass
    done = metadata.get('steps_done') or metadata.get('tests_passed')
    total = metadata.get('steps_total') or metadata.get('tests_run')
    try:
        if total and float(total) > 0:
            return max(0, min(100, round(float(done or 0) / float(total) * 100)))
    except (TypeError, ValueError):
        return None
    return None


def is_kanban_operator():
    username = (session.get('username') or '').strip().lower()
    return bool(username and username in KANBAN_OPERATOR_USERS)


def _fetch_kanban_cards(limit=80):
    if not os.path.exists(KANBAN_DB_PATH):
        return [], {'done': 0, 'processing': 0, 'next': 0, 'other': 0}, f'Kanban DB not found: {KANBAN_DB_PATH}'
    con = sqlite3.connect(KANBAN_DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('''
        SELECT
            t.id, t.title, t.assignee, t.status, t.priority, t.created_by,
            t.created_at, t.started_at, t.completed_at,
            COALESCE(MAX(e.created_at), t.completed_at, t.started_at, t.created_at) AS updated_at,
            r.status AS run_status, r.outcome, r.summary, r.metadata,
            r.started_at AS run_started_at, r.ended_at AS run_ended_at,
            r.last_heartbeat_at
        FROM tasks t
        LEFT JOIN task_events e ON e.task_id = t.id
        LEFT JOIN task_runs r ON r.id = (
            SELECT id FROM task_runs WHERE task_id = t.id ORDER BY id DESC LIMIT 1
        )
        GROUP BY t.id
        ORDER BY
            CASE t.status WHEN 'running' THEN 0 WHEN 'ready' THEN 1 WHEN 'blocked' THEN 2 WHEN 'todo' THEN 3 WHEN 'done' THEN 4 ELSE 5 END,
            updated_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    con.close()
    cards = []
    counts = {'done': 0, 'processing': 0, 'next': 0, 'other': 0}
    for row in rows:
        status = row['status'] or 'unknown'
        if status in KANBAN_STATUS_GROUPS['done']:
            group = 'done'
        elif status in KANBAN_STATUS_GROUPS['processing']:
            group = 'processing'
        elif status in KANBAN_STATUS_GROUPS['next']:
            group = 'next'
        else:
            group = 'other'
        counts[group] += 1
        cards.append({
            'id': row['id'],
            'title': row['title'],
            'assignee': row['assignee'] or 'unassigned',
            'status': status,
            'group': group,
            'priority': row['priority'] or 0,
            'created_by': row['created_by'] or '',
            'created_at': _kanban_ts(row['created_at']),
            'started_at': _kanban_ts(row['started_at'] or row['run_started_at']),
            'completed_at': _kanban_ts(row['completed_at'] or row['run_ended_at']),
            'updated_at': _kanban_ts(row['updated_at']),
            'last_heartbeat_at': _kanban_ts(row['last_heartbeat_at']),
            'summary': _safe_summary(row['summary'] or row['outcome'] or ''),
            'progress': _kanban_progress(row['metadata']),
        })
    return cards, counts, None


@app.route('/kanban')
@login_required
def kanban_dashboard_page():
    if not is_kanban_operator():
        return redirect('/')
    return redirect('/ops/kanban')


@app.route('/ops/kanban')
@login_required
def kanban_operator_dashboard_page():
    if not is_kanban_operator():
        return redirect('/')
    cards, counts, error = _fetch_kanban_cards()
    return render_template(
        'kanban_dashboard.html',
        cards=cards,
        counts=counts,
        error=error,
        operator_user=session.get('username', ''),
    )


@app.route('/api/kanban/cards')
@app.route('/ops/api/kanban/cards')
@login_required
def api_kanban_cards():
    if not is_kanban_operator():
        return jsonify(success=False, error='forbidden'), 403
    cards, counts, error = _fetch_kanban_cards()
    return jsonify(success=error is None, error=error, cards=cards, counts=counts)


@app.route('/project/<slug>')
@login_required
def project_detail(slug):
    if not is_admin():
        return redirect('/dashboard')
    c = get_db()
    project = c.execute('SELECT * FROM projects WHERE slug=?', (slug,)).fetchone()
    if not project:
        return redirect('/projects')
    project = dict(project)
    tasks = c.execute('SELECT * FROM project_tasks WHERE project_id=? ORDER BY sort_order', (project_id,)).fetchall()
    logs = c.execute('SELECT * FROM project_logs WHERE project_id=? ORDER BY created_at DESC', (project_id,)).fetchall()
    time_entries = c.execute('SELECT * FROM project_time_entries WHERE project_id=? ORDER BY created_at DESC', (project_id,)).fetchall()
    total_min = sum(t['minutes'] for t in time_entries) + project.get('time_spent_minutes', 0)
    project['time_spent'] = total_min
    project['status_label'] = PROJECT_STATUS_LABELS.get(project['status'], project['status'])
    project['status_color'] = PROJECT_STATUS_COLORS.get(project['status'], '#95a5a6')
    return render_template('project_detail.html', project=project, tasks=tasks, logs=logs, time_entries=time_entries, current_user=session.get('username'))


@app.route('/api/project/<int:project_id>/log', methods=['POST'])
@login_required
def api_project_log(project_id):
    if not is_admin():
        return jsonify(success=False, error='forbidden'), 403
    note = request.json.get('note', '').strip()
    if not note:
        return jsonify(success=False, error='note required'), 400
    c = get_db()
    c.execute('INSERT INTO project_logs (project_id,note) VALUES (?,?)', (project_id, note))
    c.execute('UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (project_id,))
    c.commit()
    return jsonify(success=True)


@app.route('/api/project/<int:project_id>/time', methods=['POST'])
@login_required
def api_project_time(project_id):
    if not is_admin():
        return jsonify(success=False, error='forbidden'), 403
    note = request.json.get('note', '').strip()
    minutes = int(request.json.get('minutes', 0))
    if not note or minutes <= 0:
        return jsonify(success=False, error='note and minutes required'), 400
    c = get_db()
    c.execute('INSERT INTO project_time_entries (project_id,note,minutes) VALUES (?,?,?)', (project_id, note, minutes))
    c.execute('UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (project_id,))
    c.commit()
    return jsonify(success=True)


@app.route('/api/project/<int:project_id>/task/<int:task_id>/toggle', methods=['POST'])
@login_required
def api_project_task_toggle(project_id, task_id):
    if not is_admin():
        return jsonify(success=False, error='forbidden'), 403
    c = get_db()
    task = c.execute('SELECT * FROM project_tasks WHERE id=? AND project_id=?', (task_id, project_id)).fetchone()
    if not task:
        return jsonify(success=False, error='not found'), 404
    new_status = 'done' if task['status'] != 'done' else 'pending'
    c.execute('UPDATE project_tasks SET status=? WHERE id=?', (new_status, task_id))
    c.execute('UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?', (project_id,))
    c.commit()
    return jsonify(success=True, status=new_status)


@app.route('/api/project/<int:project_id>/update', methods=['POST'])
@login_required
def api_project_update(project_id):
    if not is_admin():
        return jsonify(success=False, error='forbidden'), 403
    data = request.json
    allowed = ['before_text', 'now_text', 'next_text', 'status', 'phase', 'description']
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f'{k}=?')
            vals.append(data[k])
    if not sets:
        return jsonify(success=False, error='no fields'), 400
    vals.append(project_id)
    c = get_db()
    c.execute(f"UPDATE projects SET {','.join(sets)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", vals)
    c.commit()
    return jsonify(success=True)


@app.route('/api/staff/<int:sid>/assets')
@login_required
def api_staff_assets(sid):
    c = get_db()
    staff = c.execute('SELECT * FROM staff WHERE id=?', (sid,)).fetchone()
    if not staff:
        return jsonify(success=False, error='not found'), 404
    if not can_view_staff_asset_history(staff):
        return jsonify(success=False, error='ไม่มีสิทธิ์ดูประวัติ Asset ของพนักงานคนนี้'), 403
    payload = staff_asset_history_payload(c, staff)
    c.commit()
    return jsonify(success=True, staff=dict(staff), assets=payload['current_assets'], **payload)


@app.route('/api/asset/<int:aid>/history')
@login_required
def api_asset_history(aid):
    c = get_db()
    asset = c.execute('SELECT * FROM assets WHERE id=?', (aid,)).fetchone()
    if not asset:
        return jsonify(success=False, error='not found'), 404
    logs = c.execute('SELECT * FROM asset_logs WHERE asset_id=? ORDER BY created_at DESC', (aid,)).fetchall()
    return jsonify(success=True, asset=dict(asset), logs=[dict(l) for l in logs])

