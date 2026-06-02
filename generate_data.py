#!/usr/bin/env python3
"""
Data Generator for IT Ticket Demo
Generates realistic ~190 staff, ~100 tickets, ~50 assets across 16 branches
"""

from datetime import datetime, timedelta
import random
import json

# ─── Name Pools (Thai + Malay-Muslim names for Deep South context) ───
THAI_MALE_FIRST = [
    "สมชาย", "สมศักดิ์", "สมหมาย", "สมบูรณ์", "สมหวัง", "สมพร", "สมยศ", "สมคิด",
    "ประเสริฐ", "ประยุทธ์", "ประวิตร", "ประกาศิต", "ประดิษฐ์", "ประมูล", "ประสิทธิ์",
    "วิชัย", "วิทย์", "วิญญู", "วิวัฒน์", "วิทิต", "วิรัช", "วิเชียร",
    "ศุภชัย", "ศรายุทธ", "ศักดิ์ชัย", "ศิริชัย", "ศุภกิจ",
    "ธนากร", "ธนพัฒน์", "ธนวัฒน์", "ธนศักดิ์", "ธนู", "ธรรมศักดิ์",
    "ภูมิพัฒน์", "ภูวดล", "ภูมิเดช", "ภาณุพัฒน์", "ภัทรพล",
    "รัตนชัย", "รุ่งโรจน์", "ราเชน", "รณภพ", "รักษ์ศักดิ์",
    "อนันต์", "อนุชา", "อนุรักษ์", "อนุวัฒน์", "อาณัติ", "อัมพร",
    "กิตติ", "ก้องเกียรติ", "กฤษฎา", "กิตติพัฒน์", "ก้องภพ",
    "ชัยวัฒน์", "ชาญชัย", "ชาติชัย", "ชัยรัตน์", "ชุติวัฒน์",
    "ธีรวัฒน์", "ธีรศักดิ์", "ธีระพัฒน์", "ธีรเดช", "ธนินทร์",
    "นราธิป", "นเรศ", "นิติ", "นิพัฒน์", "นิรันดร์",
    "บุญธรรม", "บุญชู", "บุญทอง", "บุญรัตน์", "บุญส่ง",
    "พีรพัฒน์", "พีระชัย", "พิชิต", "พิทักษ์", "พิริยะ",
    "ศุภวิทย์", "สุรศักดิ์", "สุริยะ", "สุชาติ", "สุนทร",
    "อรรถพล", "อรุณ", "อัครเดช", "อิศรา", "อุดม",
]

THAI_FEMALE_FIRST = [
    "สมหญิง", "สมคิด", "สมจิตร", "สมฤดี", "สมพรรณ", "สมนึก", "สมทรง", "สมปอง",
    "ปราณี", "ประไพ", "ปราณประสิทธิ์", "ประภาพร", "ปริศนา", "ประดับ", "ประภัสสร",
    "วิไล", "วิชญาดา", "วิยดี", "วิมล", "วิไลวรรณ", "วิภาดา", "วิศณีย์",
    "ศุภกร", "ศิริพร", "ศิริวรรณ", "ศุภลักษณ์", "ศศิธร", "ศศินาวดี",
    "กนกพร", "กนกอร", "กมลชนก", "กมลทิพย์", "กรรณิกา", "กฤษฎา", "กัญญา",
    "ชลิดา", "ชไมพร", "ชุติมา", "ชณิชา", "ชนิสา", "ชาลินี",
    "ธนพร", "ธนวรรณ", "ธิดารัตน์", "ธัญวรรณ", "ธัญญรัตน์", "ธารินี",
    "นงลักษณ์", "นภาพร", "นรีกุล", "นรีรัตน์", "นฤมล", "นันทนา", "นัยนา",
    "บุญสม", "บุญญาพร", "บุญรื่น", "บุญธิดา", "บุณยกร", "บงกช",
    "พรรณี", "พรทิพย์", "พรพิมล", "พรสวรรค์", "พัชรี", "พิมพ์ลดา", "พิมพิกา",
    "มัลลิกา", "มาลินี", "มะลุลี", "มานิดา", "มิ่งขวัญ", "มุกดา",
    "รัตนา", "รุ่งทิวา", "รุ่งนภา", "รัชนี", "รุจิรา", "รวีวรรณ",
    "สุนิสา", "สุภาพร", "สุรีย์พร", "สุกัญญา", "สุจิตรา", "สุนันทา",
    "อรพรรณ", "อรไท", "อรุณี", "อังคณา", "อัจฉรา", "อโณชา",
    "กัญจน์เขต", "แก้วตา", "เกศริน", "เกษรา", "เข็มกลัด",
    "จันทร์เพ็ญ", "จันทิมา", "จุฑามาศ", "จุฬาภรรณ", "เจนจิรา",
    "ฐานิษา", "ฐิติมา", "ณัฐฐา", "ณิชารีย์", "ณิชมน",
]

MALAY_MALE_FIRST = [
    "มูฮัมมัด", "อาหมัด", "อีสมาอีล", "อับดุลเลาะห์", "อับดุลเราะห์มาน",
    "มะรูซานู", "อารอน", "ฮานาฟี", "ฮาซัน", "ฮุสซัยน์",
    "อิบรอฮีม์", "อิสมาแอล", "อิหลัม", "อะลี", "อุซมาน์",
    "ซูไลมาน", "รอซลัน", "รอสลี", "ริซาล", "รายฮาน",
    "นาซรี", "นาซรีย์", "นาอีม", "นาวาวี", "นูรี",
    "ฟาซลี", "ฟาซรูล", "ฟิรดอส", "ฟาอิซ", "ฟาฏีฮะห์",
    "ดาอุด", "ดาวี", "ดอวี", "ดินอัลลอฮ์", "ตอกมิน",
    "บุหารี", "บัดรี", "บุฮารี", "บิลาล", "บาการี",
    "มะห์มูด", "มะลีก", "มะนาฟ์", "มะดานี", "มะซลัน",
    "ยูโซฟ", "ยาซีร์", "ยาฮ์ยา", "ยาคูบ", "ยูซรี",
    "ซอลีฮีน", "ซอฮามี", "ซากี", "ซาบรี", "ซามัน",
    "วารีซัน", "วาวัน", "วาฮับ", "วิสมัน", "วาริส",
    "อัฟฎอน", "อัฎวาน", "อาซีซ์", "อาดีล", "อายูบ",
    "กอมารีดิน", "กุตะ", "กอลอน", "กอยุต", "กอบอล",
    "ซัลมาน", "ซอรอวาลี", "ซูฟรี", "ซัลวาน", "ซาลามัต",
    "มะรียัม", "มะมัต", "มะซรอแว", "มะลายู", "มะสกอแร",
    "ฮิลมี", "ฮัมซะห์", "ฮัฟซัน", "ฮาลีมะห์", "ฮานีมาห์",
]

MALAY_FEMALE_FIRST = [
    "ฟาติมะห์", "นาฟีสะห์", "นูรุลฮูดา", "นูรีย์มาน", "นาอีมะห์",
    "มะรียัม", "มุนีระห์", "มัสยิตะห์", "มะลานี", "มารียัม",
    "อามีนะห์", "อาซีเมาะห์", "อายิน็ะห์", "อานีสะห์", "อาซาฮ์",
    "ซอรายา", "ซาลมา", "ซูไลมา", "ซาบรียะห์", "ซอรีย์มาน",
    "ฮานาฟียะห์", "ฮาวา", "ฮาวียะห์", "ฮินด์วานี", "ฮิลมียะห์",
    "รอกายัฮ์", "รอไซดาห์", "รอมีรัตน์", "รอมาลี", "รอมิลา",
    "ลีลา", "ลายานี", "ลาติฟะห์", "ลวนดี", "ลาวะนี",
    "ดอรอวียะห์", "ดุรียะห์", "ดาเอาะนี", "ดอเราะ", "ดารีนา",
    "บาตูล", "บุรียัน", "บุฮารียะห์", "บีบี", "บารียะห์",
    "อิสมีนา", "อิสรอเฟาะ", "อิหลาส", "อินทีระห์", "อิมรอนี",
    "พาตีมะห์", "ฟาอิซะห์", "ฟารีฮะห์", "ฟาราห์", "ฟิรดาวส์",
    "มูนาวาระห์", "มูนีย์", "มาอาซียะห์", "มารี", "มายูมี",
    "ยามีน็ะห์", "ยูนิสะห์", "ยูซนี", "ยามีนา", "ยารา",
    "วารีน", "วาฮีดะห์", "วารอนี", "วิสมี", "วาฟีย์",
    "เราะซีกีน", "รอยานี", "รอแวนี", "รอมีซะห์", "รอนี",
    "จอรียะห์", "จอวารี", "จามีละห์", "จาวี", "จาเอาะดี",
    "อัยนี", "อัฟร็ะห์", "อัซนี", "อัมปง", "อัมาลีนา",
]

LAST_NAMES = [
    "ทิพย์โชคชัย", "วงศ์สวัสดิ์", "จันทร์เพ็ญ", "แก้วมณี", "ศรีสุข",
    "บัวทอง", "ทองคำ", "พูนผล", "ใจดี", "สุขสวัสดิ์",
    "มานะเลิศ", "รักษาศักดิ์", "เพชรรุ่ง", "กิตติชัย", "ชัยวัฒน์",
    "สุรเชษฐ์", "วัฒนกิจ", "ธนประเสริฐ", "พิทักษ์ไทย", "อุดมใจ",
    "มะแม", "ลายเพชร", "แวอาหมัด", "ยูโซฟ", "เจะอาแซ",
    "มะนู", "สาและ", "ดือราแม", "เปาะซี", "กาเซ็ม",
    "มะซา", "ลาเต็จ", "อาลี", "อารอง", "สุหล้า",
    "บินตีมะ", "ลาเซ็ง", "เต็งมะลี", "มะลีดีน", "แวมะ",
    "อาแว็ง", "กอเดร์", "ลาฮี", "ซีกา", "เปาะลี",
    "มะเซ็ง", "สือบูรี", "แวฮาเล็ง", "จือลาแม", "ดือมะ",
    "บาซีเลาะ", "ยามีน็ะ", "รอซานี", "ลาวะซี", "แมะซูกี",
    "อาดีล", "ฮานาฟี", "ซาบรีย์", "นาซรีย์", "ฟาซีรอน",
    "มะซรอแว", "ดาเราะ", "ยูซรี", "ซอลีฮีน", "วารีซัน",
    "นูรูลลอฮ์", "ฟารีฮีน", "อายีซีน", "มูฮัมมัดอาลี", "อัฟรอน",
    "บูฮารี", "กอมาลี", "ยาซีรี", "ริซวาน", "อัซรอน",
    "ชมเกตุ", "สมบัติ", "รุ่งเรือง", "สิทธิ์ไชย", "วัฒนา",
    "มณีนก", "พรหมใจ", "สว่างจิต", "ศรีวิไล", "รัตนประชา",
    "รุ่งโรจน์วิทย์", "สุขุมาลี", "กาญจนวัลลภ", "อรุณรัตน์", "ธัญลักษณ์",
]

# ─── Roles ───
ROLES = [
    "ผู้จัดการสาขา",
    "รองผู้จัดการสาขา",
    "เจ้าหน้าที่บัญชี",
    "เจ้าหน้าที่สินเชื่อ",
    "เจ้าหน้าที่รับ-ส่งเงิน",
    "เจ้าหน้าที่สมาชิก",
    "เจ้าหน้าที่คอมพิวเตอร์",
    "พนักงานต้อนรับ",
    "พนักงานขับรถ",
    "พนักงานรักษาความปลอดภัย",
    "พนักงานทำความสะอาด",
    "เจ้าหน้าที่สนับสนุน",
]

IT_ROLES = [
    "IT Support",
    "IT Officer",
    "System Administrator",
]

# ─── Branch Data (16 branches, 3 provinces) ───
ALL_BRANCHES = [
    # ปัตตานี (8)
    {"branch": "สาขาเมืองปัตตานี",     "district": "เมืองปัตตานี",     "province": "ปัตตานี",    "type": "main"},
    {"branch": "สาขาหนองจิก",          "district": "หนองจิก",          "province": "ปัตตานี",    "type": "branch"},
    {"branch": "สาขายะหริ่ง",          "district": "ยะหริ่ง",          "province": "ปัตตานี",    "type": "branch"},
    {"branch": "สาขามายอ",             "district": "มายอ",             "province": "ปัตตานี",    "type": "branch"},
    {"branch": "สาขาโคกโพธิ์",        "district": "โคกโพธิ์",        "province": "ปัตตานี",    "type": "branch"},
    {"branch": "สาขาปะนาเระ",         "district": "ปะนาเระ",         "province": "ปัตตานี",    "type": "branch"},
    {"branch": "สาขาถนนพุทธศาสนา",    "district": "เมืองปัตตานี",     "province": "ปัตตานี",    "type": "branch"},
    {"branch": "สาขาระแว้ง",           "district": "ระแว้ง",           "province": "ปัตตานี",    "type": "branch"},
    # ยะลา (4)
    {"branch": "สาขาเมืองยะลา",       "district": "เมืองยะลา",       "province": "ยะลา",       "type": "main"},
    {"branch": "สาขาบันนังสตา",       "district": "บันนังสตา",       "province": "ยะลา",       "type": "branch"},
    {"branch": "สาขาเบตง",            "district": "เบตง",            "province": "ยะลา",       "type": "branch"},
    {"branch": "สาขายะรม",            "district": "เบตง",            "province": "ยะลา",       "type": "service_point"},
    # นราธิวาส (7)
    {"branch": "สาขาเมืองนราธิวาส",   "district": "เมืองนราธิวาส",   "province": "นราธิวาส",   "type": "main"},
    {"branch": "สาขาตากใบ",            "district": "ตากใบ",            "province": "นราธิวาส",   "type": "branch"},
    {"branch": "สาขาสุไหงปาดี",       "district": "สุไหงปาดี",       "province": "นราธิวาส",   "type": "branch"},
    {"branch": "สาศารุษะเตมีย์",     "district": "เมืองนราธิวาส",   "province": "นราธิวาส",   "type": "branch"},
    {"branch": "สาขาบาเจาะ",           "district": "บาเจาะ",           "province": "นราธิวาส",   "type": "branch"},
    {"branch": "สาขาจะแนะ",            "district": "จะแนะ",            "province": "นราธิวาส",   "type": "branch"},
    {"branch": "สาขาสุไหงโก-ลก",      "district": "สุไหงโก-ลก",      "province": "นราธิวาส",   "type": "branch"},
]


def generate_name():
    """Generate a realistic Thai/Malay-Muslim name"""
    use_malay = random.random() < 0.4  # 40% Malay names (Deep South context)
    is_male = random.random() < 0.55   # 55% male

    if use_malay:
        if is_male:
            first = random.choice(MALAY_MALE_FIRST)
        else:
            first = random.choice(MALAY_FEMALE_FIRST)
    else:
        if is_male:
            first = random.choice(THAI_MALE_FIRST)
        else:
            first = random.choice(THAI_FEMALE_FIRST)

    last = random.choice(LAST_NAMES)

    prefix = ""
    if is_male:
        if use_malay:
            prefix = random.choice(["นาย", "นาย", "นาย", "นาย", "ว่าที่ร้อยตรี"])
        else:
            prefix = random.choice(["นาย", "นาย", "นาย", "นาย", "นาย"])
    else:
        if use_malay:
            prefix = random.choice(["นาง", "นาง", "นาง", "นางสาว", "นาง", "เจ้าหญิง"])
        else:
            prefix = random.choice(["นาง", "นาง", "นางสาว", "นาง", "นาง"])

    return f"{prefix} {first} {last}", is_male


def generate_staff_for_branch(branch_info, count=12):
    """Generate staff list for a branch"""
    staff = []
    branch_name = branch_info["branch"]
    province = branch_info["province"]
    branch_type = branch_info["type"]

    # Role distribution based on branch type
    if branch_type == "main":
        # Main branch: full staff + IT
        role_pool = [
            ("ผู้จัดการสาขา", 1),
            ("รองผู้จัดการสาขา", 1),
            ("เจ้าหน้าที่บัญชี", 2),
            ("เจ้าหน้าที่สินเชื่อ", 2),
            ("เจ้าหน้าที่รับ-ส่งเงิน", 2),
            ("เจ้าหน้าที่สมาชิก", 1),
            ("เจ้าหน้าที่คอมพิวเตอร์", 1),
            ("IT Support", 1),
            ("พนักงานต้อนรับ", 1),
            ("พนักงานรักษาความปลอดภัย", 1),
            ("พนักงานทำความสะอาด", 1),
        ]
    else:
        # Regular branch: leaner
        role_pool = [
            ("ผู้จัดการสาขา", 1),
            ("เจ้าหน้าที่บัญชี", 1),
            ("เจ้าหน้าที่สินเชื่อ", 1),
            ("เจ้าหน้าที่รับ-ส่งเงิน", 1),
            ("เจ้าหน้าที่สมาชิก", 1),
            ("เจ้าหน้าที่คอมพิวเตอร์", 1),
            ("พนักงานต้อนรับ", 1),
            ("พนักงานรักษาความปลอดภัย", 1),
            ("พนักงานทำความสะอาด", 1),
        ]

    # Flatten role pool with dedup
    assigned_roles = []
    for role, num in role_pool:
        for _ in range(num):
            assigned_roles.append(role)

    # Add extra roles if needed
    extra = count - len(assigned_roles)
    for _ in range(max(0, extra)):
        assigned_roles.append(random.choice(ROLES[2:9]))  # non-leadership roles

    # Generate names
    used_names = set()
    for i in range(min(count, len(assigned_roles))):
        role = assigned_roles[i]
        attempts = 0
        while attempts < 20:
            name, is_male = generate_name()
            if name not in used_names:
                used_names.add(name)
                break
            attempts += 1

        staff.append({
            "name": name,
            "role": role,
            "branch": branch_name,
            "province": province,
            "email": f"staff{i+1}@{branch_name.replace('สาขา', '').strip().replace(' ', '').lower()}.coop",
            "phone": f"073-{random.randint(100,999)}-{random.randint(1000,9999)}",
        })

    return staff


def generate_all_staff():
    """Generate ~190 staff across all branches"""
    all_staff = []
    # Main branch gets more staff, service point gets fewer
    for b_info in ALL_BRANCHES:
        if b_info["type"] == "main":
            count = random.randint(11, 16)
        elif b_info["type"] == "service_point":
            count = random.randint(6, 9)
        else:
            count = random.randint(9, 13)
        staff = generate_staff_for_branch(b_info, count)
        all_staff.extend(staff)

    return all_staff


# ─── Ticket Templates ───
TICKET_CATEGORIES = {
    "ระบบ Core Banking": {
        "titles": [
            "ระบบ Core Banking ล่ม", "เข้าใช้งาน Core ไม่ได้",
            "ระบบไม่สามารถบันทึกรายการได้", "ถอนเงินผิดพลาดยอดเงิน",
            "รายงานไม่ตรงกับงบดุล", "สินเชื่อค้างดอกเบี้ยผิดปกติ",
            "ปิดรอบวันไม่ได้", "ระบบสแกนเอกสารไม่ทำงาน",
            "ไม่สามารถพิมพ์ใบเสร็จได้", "ระบบสมาชิก Error ตอนลงทะเบียน"
        ],
        "priority": "critical",
        "ai": "1. เช็ค VPN Tunnel สำคัญ!\n2. ตรวจสอบสถานะ Server\n3. สำรองข้อมูลก่อนแก้ไข\n4. แจ้ง IT Support ทันที"
    },
    "เครือข่าย/อินเทอร์เน็ต": {
        "titles": [
            "อินเทอร์เน็ตเชื่อมต่อไม่ได้", "อินเทอร์เน็ตช้ามาก",
            "WiFi ดรอปบ่อย", "WAN IP เปลี่ยน",
            "DNS ไม่ resolve", "Firewall Block ระบบ",
            "เชื่อมต่อระบบ EF ไม่ได้", "ระบบ IP Camera ภาพไม่ขึ้น",
            "โหลดเอกสาร ป.ป.ช. ไม่ได้", "ระบบ Cloud Backup ไม่ upload"
        ],
        "priority": "high",
        "ai": "1. เช็คสถานะ Router/Switch\n2. Ping Gateway และ DNS\n3. เช็คสาย LAN\n4. รีสตาร์ท Modem หากจำเป็น"
    },
    "VPN/ระบบเสีย": {
        "titles": [
            "VPN Tunnel หลุด", "เชื่อมต่อสำนักงานใหญ่ไม่ได้",
            "VPN เชื่อมต่อช้า", "Site-to-Site VPN Down",
            "Remote Access ไม่ได้"
        ],
        "priority": "high",
        "ai": "1. เช็ค WAN IP ของสาขา\n2. ตรวจสอบ Tunnel Status\n3. เช็ค Firewall Rules\n4. ติดต่อ IT Support"
    },
    "เครื่องพิมพ์/สมุด": {
        "titles": [
            "ปริ้นเตอร์คายกระดาษ", "พิมพ์ทับบรรทัด",
            "หมึกหมด", "เครื่องพิมพ์ไม่ตอบสนอง",
            "เครื่องพิมพ์ค้าง", "แท่นวางกระดาษเสีย",
            "Sensor ตรวจจับเลอะ", "เครื่องพิมพ์ลายไม่ชัด",
            "เครื่องพิมพ์ขาว", "โหลดกระดาษไม่เข้า"
        ],
        "priority": "medium",
        "ai": "1. เช็ค Optical Sensor\n2. สังเกตลูกยางดึงสมุด\n3. ตรวจสอบ Calibration\n4. เปลี่ยนผ้าคราบหากเลอะ"
    },
    "คอมพิวเตอร์เสีย": {
        "titles": [
            "PC เปิดไม่ติด", "จอฟ้า (BSOD)", "คีย์บอร์ดเสีย",
            "เมาส์เสีย", "ฮาร์ดดิสก์เต็ม", "RAM ไม่พอ ระบบช้า",
            "จอฟิลเตอร์ไม่ทำงาน", "ลำโพงไม่ดัง", "USB Port ไม่ทำงาน",
            "Windows Update Error", "ไวรัสตัวใหม่"
        ],
        "priority": "low",
        "ai": "1. เช็คการเสียบสาย\n2. รีสตาร์ทเครื่อง\n3. เช็ค RAM และ HDD/SSD\n4. หากจอฟ้า ลองเช็ค VGA/GPU"
    },
    "ไฟฟ้า/สาธารณูปโภค": {
        "titles": [
            "ไฟดับ", "แอร์ไม่ทำงาน", "UPS แบตหมด",
            "ไฟกระพริบ", "ระบบไฟฟ้าลัดวงจร",
            "เครื่องสำรองไฟติด Alarm", "แบตเตอรี่ UPS บวม",
            "พัดลมระบายอากาศไม่ติด"
        ],
        "priority": "high",
        "ai": "1. เช็คสวิตช์ไฟ\n2. ตรวจสอบ UPS ทำงานไหม\n3. เช็ค Circuit Breaker\n4. แจ้งผู้ดูแลอาคาร"
    }
}

GENERAL_TICKET_STATUSES = [
    "open", "open", "open", "in_progress", "in_progress",
    "in_progress", "in_progress", "resolved", "resolved", "resolved",
    "resolved", "resolved", "resolved", "closed"
]

PRIORITY_OVERRIDE = {
    "critical": ["open", "in_progress", "resolved"],
    "high": ["open", "in_progress", "in_progress", "resolved", "resolved"],
    "medium": ["open", "in_progress", "resolved", "resolved", "resolved"],
    "low": ["resolved", "resolved", "resolved", "in_progress"]
}


def generate_tickets(all_staff, count=random.randint(85, 105)):
    """Generate realistic tickets"""
    tickets = []
    end_users = [s for s in all_staff if s["role"] not in IT_ROLES]
    it_staff = [s for s in all_staff if s["role"] in IT_ROLES]

    if not it_staff:
        it_staff = [
            {"name": "นายซุลธาน เทค", "role": "System Administrator", "branch": "สาขาเมืองปัตตานี", "province": "ปัตตานี"},
            {"name": "นายอารีฟ อินฟรา", "role": "IT Officer", "branch": "สาขาเมืองนราธิวาส", "province": "นราธิวาส"},
        ]

    for i in range(count):
        cat = random.choice(list(TICKET_CATEGORIES.keys()))
        cat_data = TICKET_CATEGORIES[cat]
        title = random.choice(cat_data["titles"])
        base_priority = cat_data["priority"]

        reporter = random.choice(end_users)
        assignee = random.choice(it_staff)

        # Status based on priority
        status = random.choice(PRIORITY_OVERRIDE.get(base_priority, GENERAL_TICKET_STATUSES))

        # Created within last 60 days
        days_ago = random.randint(0, 60)
        created = (datetime.now() - timedelta(days=days_ago, hours=random.randint(6, 18), minutes=random.randint(0, 59)))
        created_str = created.strftime("%Y-%m-%d %H:%M:%S")

        resolved_str = None
        if status in ("resolved", "closed"):
            resolved = created + timedelta(hours=random.randint(1, 72))
            if resolved < datetime.now():
                resolved_str = resolved.strftime("%Y-%m-%d %H:%M:%S")

        ai_conf = round(random.uniform(0.65, 0.98), 2)

        tickets.append({
            "branch": reporter["branch"],
            "province": reporter["province"],
            "category": cat,
            "title": title,
            "description": f"แจ้งปัญหา: {title} ที่{reporter['branch']} โดย{reporter['name']} ({reporter['role']})",
            "priority": base_priority,
            "status": status,
            "reported_by": reporter["name"],
            "assigned_to": assignee["name"],
            "created_at": created_str,
            "resolved_at": resolved_str,
            "ai_suggestion": cat_data["ai"],
            "ai_confidence": ai_conf,
        })

    return tickets


# ─── Asset Templates ───
ASSET_TYPES = {
    "คอมพิวเตอร์": {
        "models": ["Dell OptiPlex 3090", "HP ProDesk 400 G7", "Lenovo ThinkCentre M70q", "ASUS D500SD", "Acer Veriton X2670G"],
        "prefix": "PC",
    },
    "โน้ตบุ๊ค": {
        "models": ["Dell Latitude 3420", "HP EliteBook 840", "Lenovo ThinkPad E14", "ASUS ExpertBook B1"],
        "prefix": "NB",
    },
    "เครื่องพิมพ์": {
        "models": ["HP LaserJet Pro M404dn", "Epson L3250", "Brother HL-L2350DW", "Canon G3010", "HP LaserJet Pro MFP 135w"],
        "prefix": "PRT",
    },
    "Scanner": {
        "models": ["富士 ScanSnap iX1600", "Epson DS-1640", "Brother DS-640", "HP ScanJet Pro 2000"],
        "prefix": "SCN",
    },
    "Router": {
        "models": ["Cisco ISR 1111", "MikroTik hEX", "TP-Link ER7206", "Ubiquiti EdgeRouter X"],
        "prefix": "RT",
    },
    "Switch": {
        "models": ["Cisco SG250-26", "TP-Link TL-SG1024", "MikroTik CRS326", "Netgear GS724T"],
        "prefix": "SW",
    },
    "UPS": {
        "models": ["APC Smart-UPS 1500VA", "Eaton 5S 1500VA", "CyberPower OL2000", "APC Back-UPS Pro 1000"],
        "prefix": "UPS",
    },
    "เครื่องสแกนเอกสาร": {
        "models": ["Brother ADS-2200", "Fujitsu fi-7160", "HP ScanJet Pro 3000"],
        "prefix": "DOC",
    },
    "เครื่องนับเงิน": {
        "models": ["GLORY GFR-S60ITF", "Cassida 8800", "Semacon S-1665"],
        "prefix": "CNT",
    },
    "เครื่องสิทธิ์บัตร": {
        "models": ["Smart Card Reader ACR38U", "HID Omnikey 5427"],
        "prefix": "SCR",
    }
}

ASSET_STATUSES = ["active", "active", "active", "active", "active", "maintenance", "retired"]
ASSET_STATUS_WEIGHTS = [0.65, 0.15, 0.10, 0.10]  # active, maintenance, retired, spare


def generate_assets():
    """Generate ~45 assets across all branches"""
    assets = []
    serial_counter = {}

    for b_info in ALL_BRANCHES:
        branch = b_info["branch"]
        branch_type = b_info["type"]

        # Main branch gets more assets
        if branch_type == "main":
            n_assets = random.randint(4, 6)
        elif branch_type == "service_point":
            n_assets = random.randint(1, 3)
        else:
            n_assets = random.randint(2, 4)

        # Select diverse asset types
        chosen_types = random.sample(list(ASSET_TYPES.keys()), k=min(n_assets, len(ASSET_TYPES)))
        # Always give every branch a PC and printer for realism
        if n_assets >= 2:
            chosen_types[0] = "คอมพิวเตอร์"
        if n_assets >= 3:
            chosen_types[1] = "เครื่องพิมพ์"

        for atype in chosen_types[:n_assets]:
            type_data = ASSET_TYPES[atype]
            model = random.choice(type_data["models"])
            prefix = type_data["prefix"]

            serial_counter[prefix] = serial_counter.get(prefix, 100) + 1
            serial = f"{prefix}-{b_info['province'][:3].upper()}-{serial_counter[prefix]:04d}"

            status = random.choices(
                ["active", "active", "active", "maintenance", "retired"],
                weights=[70, 12, 8, 5, 5],
                k=1
            )[0]

            last_check = datetime.now() - timedelta(days=random.randint(3, 60))
            next_check = last_check + timedelta(days=90)

            install_date = (datetime.now() - timedelta(days=random.randint(30, 1500))).strftime("%Y-%m-%d")

            asset_notes_map = {
                "active": random.choice(["สถานะปกติ", "ใช้งานปกติ", "ติดตั้งแล้ว"]),
                "maintenance": random.choice(["รออะไหล่", "ส่งซ่อน", "เช็คเครื่อง"]),
                "retired": random.choice(["เกษียณแล้ว", "รอจำหน่าย", "เปลี่ยนใหม่"]),
            }

            assets.append({
                "branch": branch,
                "asset_type": atype,
                "name": model,
                "serial": serial,
                "status": status,
                "last_check": last_check.strftime("%Y-%m-%d"),
                "next_check": next_check.strftime("%Y-%m-%d"),
                "install_date": install_date,
                "notes": asset_notes_map.get(status, ""),
            })

    return assets


# ─── Knowledge Base ───
KB_ARTICLES = [
    {
        "title": "วิธีแก้ไขเครื่องพิมพ์คายกระดาษ",
        "category": "เครื่องพิมพ์/สมุด",
        "content": "1. ปิดเครื่องและถอดปั๊ก\n2. เปิดฝาหน้าเครื่อง\n3. ดึงกระดาษที่คายออก\n4. เช็คลูกยางดึงสมุด\n5. เปิดเครื่องใหม่",
        "views": random.randint(50, 200),
    },
    {
        "title": "วิธีแก้ไขอินเทอร์เน็ตเชื่อมต่อไม่ได้",
        "category": "เครือข่าย/อินเทอร์เน็ต",
        "content": "1. เช็คสาย LAN เสียบแน่น\n2. รีสตาร์ท Router\n3. Ping 8.8.8.8 ที่ CMD\n4. แจ้ง IT Support หากยังไม่ได้",
        "views": random.randint(80, 300),
    },
    {
        "title": "วิธีแก้ไข VPN Tunnel หลุด",
        "category": "VPN/ระบบเสีย",
        "content": "1. เช็คอินเทอร์เน็ตสาขา\n2. รีสตาร์ท Router\n3. เช็ค WAN IP ถ้าเปลี่ยน\n4. แจ้ง IT ฝ่าย Infrastructure",
        "views": random.randint(30, 150),
    },
    {
        "title": "วิธี Reset Password Core Banking",
        "category": "ระบบ Core Banking",
        "content": "1. กด Forgot Password ที่หน้าล็อกอิน\n2. รอ OTP ทาง SMS\n3. ตั้งรหัสผ่านใหม่\n4. หากไม่ได้รับ OTP แจ้ง Admin",
        "views": random.randint(40, 180),
    },
    {
        "title": "วิธีเช็คระบบก่อนเปิดสาขา",
        "category": "ระบบ Core Banking",
        "content": "1. เปิด PC → รอ Boot\n2. เช็ค VPN Tunnel Green\n3. เปิด Core Banking → ล็อกอิน\n4. เช็คยอดเงินเปิดวัน\n5. เปิดเครื่องพิมพ์\n6. พร้อมรับลูกค้า",
        "views": random.randint(20, 100),
    },
    {
        "title": "วิธีแจ้งปัญหา IT ผ่านระบบ",
        "category": "ทั่วไป",
        "content": "1. เข้าเมนู Tickets\n2. กด New Ticket\n3. เลือกหมวดปัญหา\n4. ระบุรายละเอียด\n5. กด Submit → รอ IT Support",
        "views": random.randint(100, 400),
    },
    {
        "title": "วิธีแก้ไขจอฟ้า (BSOD)",
        "category": "คอมพิวเตอร์เสีย",
        "content": "1. ปิดเครื่อง\n2. รอ 10 วินาที\n3. เปิดใหม่ กด F8\n4. เลือก Safe Mode\n5. รีเซ็ต Driver\n6. แจ้ง IT หากยัง Error",
        "views": random.randint(30, 120),
    },
]


# ─── Main Export ───
if __name__ == "__main__":
    # (datetime, timedelta already imported at top)

    print("Generating IT Ticket demo data...")
    print()

    # Staff
    all_staff = generate_all_staff()
    print(f"Staff generated: {len(all_staff)}")

    # Tickets
    tickets = generate_tickets(all_staff)
    print(f"Tickets generated: {len(tickets)}")

    # Assets
    assets = generate_assets()
    print(f"Assets generated: {len(assets)}")

    # Summary
    by_province = {}
    for s in all_staff:
        by_province[s["province"]] = by_province.get(s["province"], 0) + 1

    ticket_by_priority = {}
    for t in tickets:
        ticket_by_priority[t["priority"]] = ticket_by_priority.get(t["priority"], 0) + 1

    ticket_by_status = {}
    for t in tickets:
        ticket_by_status[t["status"]] = ticket_by_status.get(t["status"], 0) + 1

    print()
    print("=== Staff by Province ===")
    for p, c in sorted(by_province.items()):
        print(f"  {p}: {c}")

    print()
    print("=== Tickets by Priority ===")
    for p, c in sorted(ticket_by_priority.items(), key=lambda x: ["critical", "high", "medium", "low"].index(x[0])):
        print(f"  {p}: {c}")

    print()
    print("=== Tickets by Status ===")
    for s, c in sorted(ticket_by_status.items()):
        print(f"  {s}: {c}")

    print()
    print("=== Assets by Branch ===")
    by_branch = {}
    for a in assets:
        by_branch[a["branch"]] = by_branch.get(a["branch"], 0) + 1
    for b, c in sorted(by_branch.items()):
        print(f"  {b}: {c}")

    # Save to JSON for inspection
    demo_data = {
        "staff": all_staff,
        "tickets": tickets,
        "assets": assets,
        "kb_articles": KB_ARTICLES,
    }
    with open("/tmp/it_demo_data.json", "w", encoding="utf-8") as f:
        json.dump(demo_data, f, ensure_ascii=False, indent=2)
    print(f"\nFull data saved to /tmp/it_demo_data.json")

    # Print sample staff per branch
    print("\n=== Sample Staff Per Branch (first 3) ===")
    for b in ALL_BRANCHES[:4]:
        branch_staff = [s for s in all_staff if s["branch"] == b["branch"]]
        print(f"\n{b['branch']} ({len(branch_staff)} staff):")
        for s in branch_staff[:3]:
            print(f"  - {s['name']} ({s['role']})")
        if len(branch_staff) > 3:
            print(f"  ... and {len(branch_staff)-3} more")
