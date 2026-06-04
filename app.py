#!/usr/bin/env python3
import hashlib
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, g
import sqlite3, random, os, logging
from datetime import datetime, timedelta
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

TICKET_CATS = {
 "ระบบ Core Banking":{"titles":["Core Banking ล่ม","เข้า Core ไม่ได้","บันทึกรายการไม่ได้","ถอนเงินผิดพลาด","ปิดรอบวันไม่ได้","พิมพ์ใบเสร็จไม่ได้","สินเชื่อดอกเบี้ยผิดปกติ","ระบบสมาชิก Error"],"priority":"critical","ai":"1. VPN Tunnel สำคัญ!\n2. เช็ค Server\n3. สำรองข้อมูล\n4. แจ้ง IT ทันที"},
 "เครือข่าย/อินเทอร์เน็ต":{"titles":["อินเทอร์เน็ตไม่ได้","อินเทอร์เน็ตช้า","WiFi ดรอป","WAN IP เปลี่ยน","DNS ไม่ resolve","Firewall Block","IP Camera ภาพไม่ขึ้น"],"priority":"high","ai":"1. เช็ค Router/Switch\n2. Ping Gateway\n3. เช็ค LAN\n4. รีสตาร์ท Modem"},
 "VPN/ระบบเสีย":{"titles":["VPN Tunnel หลุด","เชื่อมต่อ HO ไม่ได้","VPN ช้า","Site-to-Site VPN Down"],"priority":"high","ai":"1. เช็ค WAN IP\n2. Tunnel Status\n3. Firewall Rules\n4. ติดต่อ IT"},
 "เครื่องพิมพ์/สมุด":{"titles":["ปริ้นเตอร์คายกระดาษ","พิมพ์ทับ","หมึกหมด","เครื่องพิมพ์ค้าง","Sensor เลอะ","ลายไม่ชัด","เครื่องพิมพ์ขาว"],"priority":"medium","ai":"1. เช็ค Sensor\n2. ลูกยางดึงสมุด\n3. Calibrate\n4. เปลี่ยนผ้าคราบ"},
 "คอมพิวเตอร์เสีย":{"titles":["PC เปิดไม่ติด","จอฟ้า","คีย์บอร์ดเสีย","เมาส์เสีย","ฮาร์ดดิสเต็ม","RAM ไม่พอ","ลำโพงไม่ดัง","USB ไม่ทำงาน","ไวรัส"],"priority":"low","ai":"1. เช็คสาย\n2. รีสตาร์ท\n3. เช็ค RAM/HDD\n4. เช็ค VGA"},
 "ไฟฟ้า/สาธารณูปโภค":{"titles":["ไฟดับ","แอร์ไม่ทำงาน","UPS แบตหมด","ไฟกระพริบ","UPS Alarm ดัง","แบต UPS บวม"],"priority":"high","ai":"1. เช็คสวิตช์\n2. เช็ค UPS\n3. Circuit Breaker\n4. แจ้งผู้ดูแลอาคาร"},
}

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
            asset_code=f"{bn:02d}{p}{seq:02d}"
            prov_code = PROVINCE_CODES.get(b['province'],'0')
            br_code = BRANCH_CODES.get(b['branch'],'0')
            cat_code = CATEGORY_CODES.get(at,'XX')
            asset_tag = f"{prov_code}{br_code}{cat_code}{seq:02d}"
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
    # Migration: add kb_id to tickets if missing
    cols = [row[1] for row in c.execute('PRAGMA table_info(tickets)')]
    if 'kb_id' not in cols:
        c.execute('ALTER TABLE tickets ADD COLUMN kb_id INTEGER DEFAULT 0')
    cols_assets = [row[1] for row in c.execute('PRAGMA table_info(assets)')]
    if 'asset_tag' not in cols_assets:
        c.execute('ALTER TABLE assets ADD COLUMN asset_tag TEXT DEFAULT \'\'')
    if c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]>0:
        # Seed admin user if no users exist
        if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            admin_hash = hashlib.sha256(b'demo2026').hexdigest()
            c.execute('INSERT INTO users (username,password_hash,role) VALUES (?,?,?)', ('admin', admin_hash, 'admin'))
            c.commit()
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
    province_to_branches_short = {prov: [{'branch': b['branch'], 'district': PROVINCE_ABBR.get(prov, prov[:3]) + b['district']} for b in blist] for prov, blist in PROVINCE_TO_BRANCHES.items()}
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    branches_short = [{'branch': b['branch'], 'district': PROVINCE_ABBR.get(b['province'], b['province'][:3]) + b['district'], 'province': b['province']} for b in ALL_BRANCHES]
    return render_template('tickets.html',tickets=rows,branches=branches_short,
        filter_status=status, filter_priority=priority, filter_branch=branch,
        filter_province=province, filter_category=category, filter_search=search,
        total=total, open_tickets=open_tickets, in_progress=in_progress,
        pending=pending, resolved=resolved, closed_tickets=closed_tickets,
        branch_to_province=branch_to_province,
        province_to_branches=province_to_branches,
        province_to_branches_short=province_to_branches_short,
        critical_tickets=critical_tickets)

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
    return render_template('ticket_detail.html',ticket=dict(t),notes=[dict(n) for n in notes],
        staff_list=[dict(s) for s in staff],asset_list=[dict(a) for a in assets],kb_articles=[dict(k) for k in kb],kb_linked=dict(kb_linked) if kb_linked else None)

@app.route('/asset/<int:asset_id>')
@login_required
def asset_detail(asset_id):
    c=get_db()
    a=c.execute('SELECT * FROM assets WHERE id=?',(asset_id,)).fetchone()
    if not a:  return 'Not found',404
    linked=c.execute('SELECT * FROM tickets WHERE asset_id=? ORDER BY created_at DESC',(asset_id,)).fetchall()
    return render_template('asset_detail.html',asset=a,linked_tickets=linked)

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
        assets_list.append(a)
    province_to_branches = PROVINCE_TO_BRANCHES
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    return render_template('assets.html',assets=assets_list,total=total,active=active,maintenance=maint,retired=retired,branches=ALL_BRANCHES,asset_types=sorted(set(a['asset_type'] for a in assets_list)),branch_to_province=branch_to_province,province_to_branches=province_to_branches)

@app.route('/staff')
@login_required
def staff_page():
    c=get_db();rows=c.execute('SELECT * FROM staff ORDER BY province,branch,name').fetchall()
    total=c.execute('SELECT COUNT(*) FROM staff').fetchone()[0]
    itc=c.execute('SELECT COUNT(*) FROM staff WHERE is_it=1').fetchone()[0]
    staff_by_province = c.execute('SELECT province,COUNT(*) as cnt,SUM(CASE WHEN is_it=1 THEN 1 ELSE 0 END) as it_cnt FROM staff GROUP BY province').fetchall()
    provinces = sorted(set(s['province'] for s in rows))
    roles = sorted(set(s['role'] for s in rows))
    branch_to_province = {b['branch']: b['province'] for b in ALL_BRANCHES}
    province_to_branches = PROVINCE_TO_BRANCHES
    return render_template('staff.html',staff=rows,total=total,it_count=itc,branches=ALL_BRANCHES,staff_provinces=provinces,staff_roles=roles,branch_to_province=branch_to_province,province_to_branches=province_to_branches,staff_by_province=staff_by_province)

@app.route('/knowledge')
@login_required
def kb_page():
    c=get_db();rows=c.execute('SELECT * FROM knowledge_base ORDER BY views DESC').fetchall();
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
    d=request.json;cat=d.get('category','');ai='';pri='medium'
    for k,v in TICKET_CATS.items():
        if k==cat:ai=v['ai'];pri=v['priority'];break
    c=get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO tickets (branch,province,category,title,description,priority,status,reported_by,assigned_to,created_at,reported_at,ai_suggestion,ai_confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(d.get('branch',''),d.get('province',''),cat,d.get('title',''),d.get('description',''),pri,'open',d.get('reported_by',''),'',now_str,now_str,ai,round(random.uniform(0.7,0.98),2)))
    c.commit();tid=c.execute('SELECT last_insert_rowid()').fetchone()[0];
    return jsonify(success=True,ticket_id=tid)

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
    for field in ('title','description','priority','status','assigned_to','branch','category','reported_by','asset_id','kb_id'):
        val = d.get(field, None)
        if val is not None and val != '':
            sets.append(f'{field}=?')
            vals.append(val)
    if not sets:
        return jsonify(success=True)
    vals.append(tid)
    c.execute(f'UPDATE tickets SET {",".join(sets)} WHERE id=?', vals)
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
    c.execute('UPDATE assets SET name=?,serial=?,asset_type=?,status=?,branch=?,next_check=?,notes=? WHERE id=?',
              (d.get('name',''),d.get('serial',''),d.get('asset_type',''),d.get('status','active'),d.get('branch',''),d.get('next_check',''),d.get('notes',''),aid))
    c.commit();
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

@app.route('/route-planner')
@login_required
def route_planner_page():
    return render_template('route-planner.html')

def _start_init_db():
    """Run init_db in a background thread so it doesn't block gunicorn startup."""
    try:
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
