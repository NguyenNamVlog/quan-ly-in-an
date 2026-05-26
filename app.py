import streamlit as st
import pandas as pd
import json
import time
import os
import requests
import unicodedata
import traceback
from datetime import datetime
from fpdf import FPDF
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px  # Thư viện vẽ biểu đồ đẹp

# --- CẤU HÌNH ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit"
FONT_FILENAME = 'arial.ttf' 
HEADER_IMAGE = 'tieu_de.png'

# --- HÀM HỖ TRỢ ---
def remove_accents(input_str):
    if not input_str: return ""
    input_str = str(input_str)
    s = input_str.replace('đ', 'd').replace('Đ', 'D')
    nfkd_form = unicodedata.normalize('NFKD', s)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def format_currency(value):
    if value is None: return "0"
    try:
        val = float(value)
        if val.is_integer():
            return "{:,.0f}".format(val).replace(",", ".")
        else:
            return "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0"

def read_money_vietnamese(amount):
    try: return num2words(amount, lang='vi').capitalize() + " đồng chẵn."
    except: return "..................... đồng."

# --- KẾT NỐI GOOGLE SHEETS (ĐÃ THÊM DEBUG) ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets:
            st.error("❌ Lỗi: Không tìm thấy mục [service_account] trong st.secrets")
            return None
        
        creds_dict = dict(st.secrets["service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"⚠️ Lỗi kết nối Google: {e}")
        return None

# --- DATABASE CHỨC NĂNG KHÁCH THÊM ---
def fetch_extra_customers():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("ExtraCustomers")
        except:
            return []
        return ws.get_all_records()
    except:
        return []

def add_extra_customer(data):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("ExtraCustomers")
        except:
            ws = sh.add_worksheet("ExtraCustomers", 1000, 10)
            ws.append_row(["id", "customer_name", "before_tax", "actual_done", "not_done", "tax_rate", "tncn_tax", "status", "created_at"])
        
        row = [
            data.get('id'),
            data.get('customer_name'),
            data.get('before_tax'),
            data.get('actual_done'),
            data.get('not_done'),
            data.get('tax_rate'),
            data.get('tncn_tax'),
            data.get('status'),
            data.get('created_at')
        ]
        ws.append_row(row)
        st.cache_data.clear()
        return True
    except:
        return False

def update_extra_customer_status(record_id, new_status):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("ExtraCustomers")
        cell = ws.find(str(record_id))
        if not cell: return False
        ws.update_cell(cell.row, 8, new_status) # Cột status ở vị trí số 8
        st.cache_data.clear()
        return True
    except:
        return False

# --- CUSTOMER MANAGEMENT ---
def fetch_customers():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Customers")
        except: return [] 
        return ws.get_all_records()
    except: return []

def save_customer_db(name, phone, address):
    client = get_gspread_client()
    if not client or not phone: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Customers")
        except: 
            ws = sh.add_worksheet("Customers", 1000, 5)
            ws.append_row(["phone", "name", "address", "last_order"])
        
        try: phones = ws.col_values(1) 
        except: phones = []

        if phone not in phones:
            ws.append_row([str(phone), name, address, datetime.now().strftime("%Y-%m-%d")])
            st.cache_data.clear() 
    except: pass

# --- USER MANAGEMENT ---
def init_users():
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Users")
        except:
            ws = sh.add_worksheet("Users", 100, 3)
            ws.append_row(["username", "password", "role"])
            default_users = [
                ["Nam", "Emyeu0901", "admin"],
                ["Duong", "Duong", "staff"],
                ["Van", "Van", "staff"]
            ]
            for u in default_users: ws.append_row(u)
    except: pass

def get_users_db():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Users")
        return ws.get_all_records()
    except: return []

def change_password(username, new_pass):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Users")
        cell = ws.find(username)
        if cell:
            ws.update_cell(cell.row, 2, new_pass)
            return True
        return False
    except: return False

def check_login(username, password):
    users = get_users_db()
    for u in users:
        if str(u['username']).strip() == username and str(u['password']).strip() == password:
            return u
    return None

# --- DATABASE CORE ---
def fetch_all_orders():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        raw_data = ws.get_all_records()
        processed_data = []
        for row in raw_data:
            try:
                cust = row.get('customer')
                row['customer'] = json.loads(cust) if isinstance(cust, str) and cust else (cust if isinstance(cust, dict) else {})
                items = row.get('items')
                row['items'] = json.loads(items) if isinstance(items, str) and items else (items if isinstance(items, list) else [])
                fin = row.get('financial')
                row['financial'] = json.loads(fin) if isinstance(fin, str) and fin else (fin if isinstance(fin, dict) else {})
                processed_data.append(row)
            except: continue
        return processed_data
    except: return []

def update_order_status(order_id, new_status, new_payment_status=None, paid_amount=0):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if not cell: return False
        
        row_idx = cell.row
        ws.update_cell(row_idx, 3, new_status)
        if new_payment_status: ws.update_cell(row_idx, 4, new_payment_status)
        
        if paid_amount > 0:
            current_fin_str = ws.cell(row_idx, 7).value
            try: fin = json.loads(current_fin_str)
            except: fin = {}
            fin['paid'] = float(fin.get('paid', 0)) + float(paid_amount)
            fin['debt'] = float(fin.get('total', 0)) - fin['paid']
            ws.update_cell(row_idx, 7, json.dumps(fin, ensure_ascii=False))
            
        st.cache_data.clear()
        return True
    except: return False

def update_commission_status(order_id, status_text):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if not cell: return False
        
        row_idx = cell.row
        old_fin_str = ws.cell(row_idx, 7).value
        try: fin = json.loads(old_fin_str)
        except: fin = {}
        fin['commission_status'] = status_text
        ws.update_cell(row_idx, 7, json.dumps(fin, ensure_ascii=False))
        st.cache_data.clear()
        return True
    except: return False

def delete_order(order_id):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if cell:
            ws.delete_rows(cell.row)
            st.cache_data.clear()
            return True
        return False
    except: return False

def edit_order_info(order_id, new_cust, new_total, new_items, new_profit, new_comm):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if not cell: return False
        r = cell.row
        
        ws.update_cell(r, 5, json.dumps(new_cust, ensure_ascii=False))
        ws.update_cell(r, 6, json.dumps(new_items, ensure_ascii=False))
        
        old_fin_str = ws.cell(r, 7).value
        try: fin = json.loads(old_fin_str)
        except: fin = {}
        fin['total'] = new_total
        fin['debt'] = new_total - float(fin.get('paid', 0))
        fin['total_profit'] = new_profit
        fin['total_comm'] = new_comm
        ws.update_cell(r, 7, json.dumps(fin, ensure_ascii=False))
        
        save_customer_db(new_cust.get('name'), new_cust.get('phone'), new_cust.get('address'))
        st.cache_data.clear()
        return True
    except: return False

def add_new_order(order_data):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Orders")
        except: 
            ws = sh.add_worksheet("Orders", 1000, 20)
            ws.append_row(["order_id", "date", "status", "payment_status", "customer", "items", "financial"])
        
        row = [
            order_data.get('order_id'), order_data.get('date'), order_data.get('status'), order_data.get('payment_status'),
            json.dumps(order_data.get('customer', {}), ensure_ascii=False),
            json.dumps(order_data.get('items', []), ensure_ascii=False),
            json.dumps(order_data.get('financial', {}), ensure_ascii=False)
        ]
        ws.append_row(row)
        st.cache_data.clear()
        return True
    except: return False

def save_cash_log(date, type_, amount, method, note):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Cashbook")
        except: 
            ws = sh.add_worksheet("Cashbook", 1000, 10)
            ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"])
        if not ws.get_all_values(): ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"])
        ws.append_row([str(date), type_, amount, method, note])
        st.cache_data.clear()
    except: pass

def fetch_cashbook():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Cashbook")
        return ws.get_all_records()
    except: return []

def gen_id():
    orders = fetch_all_orders()
    year = datetime.now().strftime("%y")
    count = 0
    for o in orders:
        if str(o.get('order_id', '')).endswith(year): count += 1
    return f"{count+1:03d}/DH.{year}"

# --- PDF GENERATOR ---
class PDFGen(FPDF):
    def header(self): pass

def create_pdf(order, title):
    pdf = PDFGen()
    pdf.add_page()
    SAFE_MODE = False
    if os.path.exists(FONT_FILENAME):
        try:
            pdf.add_font('ArialLocal', '', FONT_FILENAME)
            pdf.set_font('ArialLocal', '', 11)
        except: SAFE_MODE = True
    else: SAFE_MODE = True
    if SAFE_MODE: pdf.set_font('Helvetica', '', 11)

    def txt(text):
        if not text: return ""
        text = str(text)
        return remove_accents(text) if SAFE_MODE else text

    if os.path.exists(HEADER_IMAGE):
        try:
            pdf.image(HEADER_IMAGE, x=10, y=10, w=190)
            pdf.set_y(pdf.get_y() + 35) 
        except: pass
    else:
        pdf.set_font_size(14)
        pdf.cell(0, 8, txt('CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT'), 0, 1, 'C')
        pdf.set_font_size(10)
        pdf.cell(0, 5, txt('Mã số thuế: 3603995632'), 0, 1, 'C')
        pdf.cell(0, 5, txt('Địa chỉ: A1/204A, hẻm 244, đường Bùi Hữu Nghĩa, phường Biên Hòa, tỉnh Đồng Nai'), 0, 1, 'C')
        pdf.cell(0, 5, txt('Điện thoại: 0251 777 6868       Email: anlocphat68.ltd@gmail.com'), 0, 1, 'C')
        pdf.cell(0, 5, txt('Số tài khoản: 451557254 – Ngân hàng TMCP Việt Nam Thịnh Vượng - CN Đồng Nai'), 0, 1, 'C')
        pdf.ln(2)
        
    STAMP_FILE = 'con_dau.png'
    if os.path.exists(STAMP_FILE):
        try:
            pdf.image(STAMP_FILE, x=15, y=32, w=35)
        except: pass

    pdf.set_font_size(16)
    pdf.cell(0, 8, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font_size(11)
    
    oid = order.get('order_id', '')
    is_delivery = "GIAO HÀNG" in title.upper()
    
    if is_delivery:
        odate = datetime.now().strftime("%d/%m/%Y")
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi.  Nay bàn giao các hàng hóa và dịch vụ như sau:"
    else:
        raw_date = order.get('date', '')
        try: odate = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except: odate = raw_date
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi. Xin trân trọng gửi tới Quý  khách hàng báo giá như sau:"

    cust = order.get('customer', {})
    items = order.get('items', [])
    
    pdf.cell(0, 6, txt(f"Mã số: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(1)
    pdf.cell(0, 6, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Điện thoại: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(2)
    pdf.multi_cell(0, 5, txt(intro_text))
    pdf.ln(2)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(75, 8, txt("Tên hàng / Quy cách"), 1, 0, 'C', 1)
    pdf.cell(15, 8, txt("ĐVT"), 1, 0, 'C', 1)
    pdf.cell(15, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(35, 8, txt("Đơn giá"), 1, 0, 'C', 1)
    pdf.cell(40, 8, txt("Thành tiền"), 1, 1, 'C', 1)
    
    sum_items_total = 0
    total_vat = 0
    
    for i, item in enumerate(items):
        try: 
            price = float(item.get('price', 0))
            qty = float(item.get('qty', 0))
            line_total = price * qty
            vat_rate = float(item.get('vat_rate', 0))
            vat_val = line_total * (vat_rate / 100)
        except: 
            line_total = 0; vat_val = 0
            
        sum_items_total += line_total
        total_vat += vat_val
        
        start_y = pdf.get_y()
        pdf.set_x(20) 
        pdf.multi_cell(75, 8, txt(item.get('name', '')), 1, 'L')
        end_y = pdf.get_y()
        h = end_y - start_y 
        
        pdf.set_xy(10, start_y)
        pdf.cell(10, h, str(i+1), 1, 0, 'C')
        pdf.set_xy(95, start_y)
        
        pdf.cell(15, h, txt(item.get('unit', '')), 1, 0, 'C')
        pdf.cell(15, h, format_currency(qty), 1, 0, 'R')
        pdf.cell(35, h, format_currency(price), 1, 0, 'R')
        pdf.cell(40, h, format_currency(line_total), 1, 1, 'R')
 
        pdf.set_y(end_y)
    
    final_total = sum_items_total + total_vat
    
    pdf.cell(150, 8, txt("Cộng tiền hàng:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(sum_items_total), 1, 1, 'R')
    pdf.cell(150, 8, txt(f"Tiền VAT:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total_vat), 1, 1, 'R')
    pdf.cell(150, 8, txt("TỔNG CỘNG THANH TOÁN:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(final_total), 1, 1, 'R')
    pdf.ln(5)
    
    money_text = ""
    if SAFE_MODE: money_text = f"Tong cong: {format_currency(final_total)} VND"
    else:
        try: money_text = read_money_vietnamese(final_total)
        except: money_text = f"{format_currency(final_total)} đồng."
    pdf.multi_cell(0, 6, txt(f"Bằng chữ: {money_text}"))
    pdf.ln(3)

    pdf.set_x(10)
    if is_delivery:
        pdf.cell(95, 5, txt("NGƯỜI NHẬN"), 0, 0, 'C')
        pdf.cell(95, 5, txt("NGƯỜI GIAO"), 0, 1, 'C')
        pdf.ln(20) 
    else:
        pdf.cell(0, 5, txt("NGƯỜI BÁO GIÁ"), 0, 1, 'R')
        pdf.ln(20)

    pdf.ln(2)
    pdf.set_font_size(10)
    pdf.set_x(10)
    if is_delivery:
        pdf.multi_cell(190, 5, txt("* Quý khách vui lòng kiểm tra và phản hồi ngay về tình trạng hàng hoá khi giao nhận!"))
        pdf.set_x(10)
        pdf.multi_cell(190, 5, txt("* Giao hàng miễn phí trong nội thành thành phố Biên Hoà với đơn hàng >1.000.000đ"))
        pdf.set_x(10)
        pdf.multi_cell(190, 5, txt("Rất mong được hợp tác với Quý khách hàng. Trân trọng!"))
    else:
        pdf.cell(0, 5, txt("Lưu ý:"), 0, 1)
        pdf.set_x(10)
        pdf.cell(0, 5, txt("- Giá trên đã bao gồm vận chuyển, giao hàng."), 0, 1)
        pdf.set_x(10)
        pdf.cell(0, 5, txt("- Thời gian hoàn thành, giao hàng: từ 03 - 05 ngày."), 0, 1)
        pdf.set_x(10)
        pdf.cell(0, 5, txt("- Báo giá này áp dụng trong vòng 30 ngày."), 0, 1)
        pdf.ln(2)
        pdf.set_x(10)
        pdf.multi_cell(190, 5, txt("Rất mong nhận được sự hợp tác của Quý khách hàng! \nTrân trọng! "))
    return bytes(pdf.output())

# --- LOGIN PAGE ---
def login_page():
    st.title("🔐 Đăng Nhập Hệ Thống")
    init_users()
    with st.form("login_form"):
        username = st.text_input("Tên đăng nhập")
        password = st.text_input("Mật khẩu", type="password")
        if st.form_submit_button("Đăng nhập", type="primary"):
            user = check_login(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.session_state.role = user['role']
                st.success(f"Xin chào {username}!")
                time.sleep(0.5)
                st.rerun()
            else: st.error("Sai tên đăng nhập hoặc mật khẩu!")

# --- MAIN APP ---
def main_app():
    is_admin = st.session_state.role == 'admin'
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user['username']}** ({st.session_state.role})")
        if st.button("Đăng xuất"):
            st.session_state.logged_in = False
            st.rerun()
        with st.expander("🔑 Đổi mật khẩu"):
            new_p1 = st.text_input("Mật khẩu mới", type="password")
            new_p2 = st.text_input("Nhập lại", type="password")
            if st.button("Lưu mật khẩu"):
                if new_p1 and new_p1 == new_p2:
                    if change_password(st.session_state.user['username'], new_p1):
                        st.success("Đổi thành công!")
                    else: st.error("Lỗi hệ thống")
                else: st.error("Mật khẩu không khớp")

    st.title("Hệ Thống In Ấn An Lộc Phát")
    if "service_account" not in st.secrets:
        st.error("Lỗi: Chưa cấu hình st.secrets")
        st.stop()

    menu = st.sidebar.radio("CHỨC NĂNG", [
        "1. Tạo Báo Giá", 
        "2. Quản Lý Đơn Hàng (Pipeline)", 
        "3. Sổ Quỹ", 
        "4. Dashboard & Báo Cáo",
        "5. KHÁCH THÊM"
    ])

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'last_order' not in st.session_state: st.session_state.last_order = None

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá":
        st.header("📝 Tạo Báo Giá Mới")
        if 'c_name' not in st.session_state: st.session_state.c_name = ""
        if 'c_phone' not in st.session_state: st.session_state.c_phone = ""
        if 'c_addr' not in st.session_state: st.session_state.c_addr = ""

        customers = fetch_customers()
        cust_options = [""] + [f"{c['phone']} - {c['name']}" for c in customers]
        selected_cust = st.selectbox("🔍 Tìm khách cũ (SĐT - Tên):", cust_options)
        if selected_cust:
            s_phone = selected_cust.split(" - ")[0]
            for c in customers:
                if str(c['phone']) == s_phone:
                    st.session_state.c_name = c['name']
                    st.session_state.c_phone = str(c['phone'])
                    st.session_state.c_addr = c['address']
                    break
        
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên Khách Hàng", value=st.session_state.c_name)
        phone = c2.text_input("Số Điện Thoại", value=st.session_state.c_phone)
        addr = st.text_input("Địa Chỉ", value=st.session_state.c_addr)
        
        user_name = st.session_state.user['username']
        staff_options = ["Nam", "Dương", "Vạn", "Khác"]
        default_idx = staff_options.index(user_name) if user_name in staff_options else 0
        staff = st.selectbox("Nhân Viên Kinh Doanh", staff_options, index=default_idx, key="in_staff")

        st.divider()
        st.subheader("2. Chi tiết hàng hóa & Giá")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            i_name = col1.text_input("Tên hàng / Quy cách")
            i_unit = col2.text_input("ĐVT (Cái/M2)")
            i_qty = col3.number_input("Số lượng", 1.0, step=1.0)
            col4, col5, col6 = st.columns(3)
            i_cost = col4.number_input("Giá Vốn (Giá gốc)", 0.0, step=1000.0)
            i_price = col5.number_input("Giá Bán (Đơn giá)", 0.0, step=1000.0)
            i_vat = col6.number_input("% VAT", 0.0, 100.0, 0.0, step=1.0)
            if st.form_submit_button("➕ Thêm vào danh sách"):
                if i_name:
                    total_sell = i_qty * i_price
                    total_cost = i_qty * i_cost
                    vat_amt = total_sell * (i_vat / 100)
                    profit = total_sell - total_cost
                    comm_rate = 0.3
                    if staff in ["Nam", "Dương"]: comm_rate = 0.6
                    elif staff == "Vạn": comm_rate = 0.5
                    commission = profit * comm_rate if profit > 0 else 0
                    st.session_state.cart.append({
                        "name": i_name, "unit": i_unit, "qty": i_qty, "cost": i_cost,
                        "price": i_price, "vat_rate": i_vat, "vat_amt": vat_amt,
                        "profit": profit, "commission": commission,
                        "total_line": total_sell + vat_amt
                    })
                    st.rerun()
                else: st.error("Nhập tên hàng!")

        if st.session_state.cart:
            st.write("---")
            view_df = pd.DataFrame(st.session_state.cart).copy()
            for col in ['cost', 'price', 'vat_amt', 'profit', 'commission', 'total_line']:
                view_df[col] = view_df[col].apply(format_currency)
            view_df.columns = ["Tên hàng", "ĐVT", "SL", "Giá Vốn", "Giá Bán", "% VAT", "Tiền VAT", "Lợi Nhuận", "Hoa Hồng", "Giá Hoá Đơn"]
            st.dataframe(view_df, use_container_width=True)
            
            total_final = sum(i['total_line'] for i in st.session_state.cart)
            total_profit = sum(i['profit'] for i in st.session_state.cart)
            total_comm = sum(i['commission'] for i in st.session_state.cart)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("TỔNG GIÁ TRỊ", format_currency(total_final))
            m2.metric("TỔNG LỢI NHUẬN", format_currency(total_profit))
            m3.metric("TỔNG HOA HỒNG", format_currency(total_comm))
            
            c_del, c_save = st.columns(2)
            if c_del.button("🗑️ Xóa giỏ"):
                st.session_state.cart = []
                st.rerun()
            if c_save.button("💾 LƯU BÁO GIÁ", type="primary"):
                if not name: st.error("Thiếu tên khách!")
                else:
                    new_order = {
                        "order_id": gen_id(), 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá", "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": st.session_state.cart,
                        "financial": {
                            "total": total_final, "paid": 0, "debt": total_final, "staff": staff, 
                            "total_profit": total_profit, "total_comm": total_comm, "commission_status": "Chưa chi"
                        }
                    }
                    if add_new_order(new_order):
                        save_customer_db(name, phone, addr)
                        st.session_state.last_order = new_order
                        st.session_state.cart = []
                        st.rerun()

        if st.session_state.last_order:
            oid = st.session_state.last_order['order_id']
            st.success(f"✅ Đã tạo: {oid}")
            pdf_bytes = create_pdf(st.session_state.last_order, "BÁO GIÁ")
            st.download_button("🖨️ Tải PDF", pdf_bytes, f"BG_{oid}.pdf", "application/pdf", type="primary")

    # --- TAB 2: QUẢN LÝ ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.header("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            current_orders = [o for o in all_orders if o.get('status') == status_filter]
            if not current_orders:
                st.info("Không có đơn hàng nào trong mục này.")
                return

            table_data = []
            for o in current_orders:
                cust = o.get('customer', {})
                fin = o.get('financial', {})
                items = o.get('items', [])
                main_prod = items[0]['name'] if items else "---"
                table_data.append({
                    "Mã ĐH": o.get('order_id'), "Ngày": o.get('date'), "Khách hàng": cust.get('name'),
                    "Sản phẩm": main_prod, "Tổng tiền": format_currency(float(fin.get('total', 0))),
                    "Còn nợ": format_currency(float(fin.get('debt', 0))),
                    "Nhân viên": fin.get('staff', ''),
                    "Hoa hồng": format_currency(float(fin.get('total_comm', 0))),
                    "TT Thanh Toán": o.get('payment_status'), "TT Hoa Hồng": fin.get('commission_status', 'Chưa chi')
                })
            
            event = st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun")
            
            if event.selection.rows:
                idx = event.selection.rows[0]
                sel_order = current_orders[idx]
                oid = sel_order.get('order_id')
                st.divider()
                st.subheader(f"🛠️ Xử lý đơn hàng: {oid}")
                cust = sel_order.get('customer', {})
                items = sel_order.get('items', [])
                fin = sel_order.get('financial', {})
                total, paid = float(fin.get('total', 0)), float(fin.get('paid', 0))
                debt = total - paid
                profit_val, comm_val = fin.get('total_profit', 0), fin.get('total_comm', 0)
                comm_stat = fin.get('commission_status', 'Chưa chi')
                
                col_d1, col_d2 = st.columns([2, 1])
                with col_d1:
                    st.write(f"👤 {cust.get('name')} - {cust.get('phone')} | 📍 {cust.get('address')}")
                    st.write("📦 **Chi tiết hàng hóa:**")
                    df_items = pd.DataFrame(items)
                    if not df_items.empty:
                        cols = ["name", "unit", "qty", "price", "vat_rate", "total_line"]
                        if set(cols).issubset(df_items.columns):
                            df_show = df_items[cols].copy()
                            df_show.columns = ["Tên", "ĐVT", "SL", "Giá", "%VAT", "Thành tiền"]
                            df_show['Giá'] = df_show['Giá'].apply(format_currency)
                            df_show['Thành tiền'] = df_show['Thành tiền'].apply(format_currency)
                            st.dataframe(df_show, hide_index=True, use_container_width=True)
                with col_d2:
                    st.info(f"💰 **TÀI CHÍNH**")
                    st.write(f"Tổng đơn: **{format_currency(total)}**")
                    st.write(f"Đã thanh toán: {format_currency(paid)}")
                    st.error(f"CÒN NỢ: **{format_currency(debt)}**")
                    if is_admin:
                        with st.expander("👁️ Admin View", expanded=True):
                            st.write(f"Lợi nhuận: {format_currency(profit_val)}")
                            st.write(f"Hoa hồng ({fin.get('staff')}): {format_currency(comm_val)}")
                            st.write(f"TT Hoa hồng: {comm_stat}")
                            if comm_stat != "Đã chi" and st.button("Chi Hoa Hồng Ngay", key=f"comm_{oid}"):
                                update_commission_status(oid, "Đã chi")
                                st.rerun()
                st.write("---")
                c_act1, c_act2, c_act3, c_act4 = st.columns(4)
                with c_act1:
                    if pdf_type:
                        pdf_data = create_pdf(sel_order, pdf_type)
                        st.download_button(f"🖨️ In {pdf_type}", pdf_data, f"{oid}.pdf", "application/pdf", key=f"dl_{oid}", use_container_width=True)
                with c_act2:
                    pdf_gh = create_pdf(sel_order, "PHIẾU GIAO HÀNG, KIÊM PHIẾU THU")
                    st.download_button("🚚 In Phiếu Giao", pdf_gh, f"GH_{oid}.pdf", "application/pdf", key=f"dl_gh_{oid}", use_container_width=True)
                if is_admin:
                    with c_act3:
                        if next_status and st.button(f"{btn_text} ➡️", key=f"mv_{oid}", type="primary", use_container_width=True):
                            update_order_status(oid, next_status)
                            st.rerun()
                    with c_act4:
                        if st.button("🗑️ Xóa Đơn", key=f"del_{oid}", use_container_width=True):
                            if delete_order(oid):
                                st.success("Đã xóa!"); time.sleep(1); st.rerun()
                st.write("---")
                st.write("💳 **THANH TOÁN & CẬP NHẬT (Admin Only)**")
                tab_pay, tab_edit = st.tabs(["💸 Thu Tiền", "✏️ Sửa Đơn Hàng"])
                with tab_pay:
                    c_p1, c_p2 = st.columns(2)
                    pay_method = c_p1.radio("Hình thức:", ["Một phần", "Toàn bộ"], horizontal=True, key=f"pm_{oid}")
                    pay_val = float(debt) if pay_method == "Toàn bộ" else c_p2.number_input("Nhập số tiền thu:", 0.0, float(debt), float(debt), key=f"p_val_{oid}")
                    pay_via = c_p2.selectbox("Hình thức thanh toán:", ["TM", "CK"], key=f"via_{oid}")
                    st.write(f"👉 Xác nhận thu: **{format_currency(pay_val)}** ({pay_via})")
                    if st.button("Xác nhận Thu Tiền", key=f"cf_pay_{oid}"):
                        if pay_val > 0:
                            new_st = status_filter
                            pay_stat_new = "Đã TT" if (debt - pay_val) <= 0 else "Cọc/Còn nợ"
                            if (debt - pay_val) <= 0 and status_filter == "Công nợ": new_st = "Hoàn thành"
                            update_order_status(oid, new_st, pay_stat_new, pay_val)
                            save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay_val, pay_via, f"Thu tiền đơn {oid}")
                            st.success("Thành công!"); time.sleep(1); st.rerun()
                        else: st.warning("Số tiền phải > 0")
                with tab_edit:
                    with st.form(f"form_edit_{oid}"):
                        ce1, ce2 = st.columns(2)
                        new_name = ce1.text_input("Tên Khách", value=cust.get('name'))
                        new_phone = ce2.text_input("SĐT", value=cust.get('phone'))
                        new_addr = st.text_input("Địa chỉ", value=cust.get('address'))
                        st.write("📋 **Sửa Hàng Hóa & Giá:**")
                        edited_df = st.data_editor(pd.DataFrame(items), num_rows="dynamic", key=f"editor_{oid}")
                        if st.form_submit_button("Lưu Thay Đổi"):
                            new_items = edited_df.to_dict('records')
                            r_total, r_profit = 0, 0
                            for it in new_items:
                                q, p, v, c = float(it.get('qty',0)), float(it.get('price',0)), float(it.get('vat_rate',0)), float(it.get('cost',0))
                                it['total_line'] = q*p + (q*p*(v/100))
                                it['profit'] = (q*p) - (q*c)
                                r_total += it['total_line']
                                r_profit += it['profit']
                            c_staff = fin.get('staff', '')
                            rate = 0.6 if c_staff in ["Nam", "Dương"] else (0.5 if c_staff == "Vạn" else 0.3)
                            r_comm = r_profit * rate if r_profit > 0 else 0
                            if edit_order_info(oid, {"name": new_name, "phone": new_phone, "address": new_addr}, r_total, new_items, r_profit, r_comm):
                                st.success("Cập nhật thành công!"); time.sleep(1); st.rerun()
            else:
                st.info("🔒 Bạn chỉ có quyền xem chi tiết.")

        with tabs[0]: render_tab_content("Báo giá", "Thiết kế", "✅ Duyệt -> Thiết Kế", "BÁO GIÁ")
        with tabs[1]: render_tab_content("Thiết kế", "Sản xuất", "✅ Duyệt TK -> Sản Xuất", None)
        with tabs[2]: render_tab_content("Sản xuất", "Giao hàng", "✅ Xong -> Giao Hàng", None)
        with tabs[3]: render_tab_content("Giao hàng", "Công nợ", "✅ Giao Xong -> Công Nợ", "PHIẾU GIAO HÀNG")
        with tabs[4]: render_tab_content("Công nợ", None, "", None)
        with tabs[5]: render_tab_content("Hoàn thành", None, "", None)

    # --- TAB 3: SỔ QUỸ (CHỈ TM) ---
    elif menu == "3. Sổ Quỹ":
        st.header("📊 Sổ Quỹ Tiền Mặt")
        df = pd.DataFrame(fetch_cashbook())
        if df.empty:
            df = pd.DataFrame(columns=["Date", "Content", "Amount", "TM/CK", "Note"])
        if 'date' in df.columns:
            df.rename(columns={'date': 'Date', 'type': 'Content', 'amount': 'Amount', 'desc': 'Note'}, inplace=True)
        for col in ["Date", "Content", "Amount", "TM/CK", "Note"]:
            if col not in df.columns: df[col] = ""
        df['TM/CK'] = df['TM/CK'].replace("", "TM").fillna("TM")
        df['TM/CK_Norm'] = df['TM/CK'].astype(str).str.strip().str.upper()
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        df_tm = df[df['TM/CK_Norm'] == 'TM'].copy()
        if not df_tm.empty:
            total_thu = df_tm[df_tm['Content'] == 'Thu']['Amount'].sum()
            total_chi = df_tm[df_tm['Content'] == 'Chi']['Amount'].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Tổng Thu (TM)", format_currency(total_thu))
            c2.metric("Tổng Chi (TM)", format_currency(total_chi))
            c3.metric("Tồn Quỹ Tiền Mặt", format_currency(total_thu - total_chi))

        st.subheader("📝 Thêm Phiếu Chi")
        with st.form("cash_form", clear_on_submit=True):
            f_date = st.date_input("Ngày", datetime.now())
            f_type = st.selectbox("Loại", ["Chi"])
            f_amt = st.number_input("Số tiền", 0.0, step=1000.0)
            f_via = st.selectbox("Hình thức", ["TM", "CK"])
            f_note = st.text_input("Ghi chú nội dung chi")
            if st.form_submit_button("💾 Ghi sổ"):
                if f_amt > 0 and f_note:
                    save_cash_log(f_date.strftime("%Y-%m-%d"), f_type, f_amt, f_via, f_note)
                    st.success("Đã lưu!"); time.sleep(0.5); st.rerun()
                else: st.error("Điền đủ thông tin!")
        
        st.subheader("📋 Lịch sử quỹ")
        df_display = df[["Date", "Content", "Amount", "TM/CK", "Note"]].copy()
        df_display['Amount'] = df_display['Amount'].apply(format_currency)
        st.dataframe(df_display.sort_values(by="Date", ascending=False), use_container_width=True, hide_index=True)

    # --- TAB 4: DASHBOARD & BÁO CÁO ---
    elif menu == "4. Dashboard & Báo Cáo":
        st.header("📈 Báo Cáo Hoạt Động Doanh Nghiệp")
        all_orders = fetch_all_orders()
        if not all_orders:
            st.info("Chưa có dữ liệu đơn hàng để báo cáo.")
        else:
            df_orders = pd.DataFrame([
                {
                    "order_id": o['order_id'], "date": o['date'], "status": o['status'],
                    "total": float(o['financial'].get('total', 0)),
                    "paid": float(o['financial'].get('paid', 0)),
                    "debt": float(o['financial'].get('debt', 0)),
                    "profit": float(o['financial'].get('total_profit', 0)),
                    "total_comm": float(o['financial'].get('total_comm', 0)),
                    "staff": o['financial'].get('staff', 'Khác'),
                    "comm_status": o['financial'].get('commission_status', 'Chưa chi')
                } for o in all_orders
            ])
            
            st.subheader("📊 Doanh Số & Lợi Nhuận Toàn Công Ty")
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Tổng Doanh Thu", format_currency(df_orders['total'].sum()))
            kpi2.metric("Tổng Lợi Nhuận Gốc", format_currency(df_orders['profit'].sum()))
            kpi3.metric("Tổng Thu Thực Tế", format_currency(df_orders['paid'].sum()))
            
            st.subheader("👥 Báo cáo theo nhân viên")
            staff_rep = df_orders.groupby('staff').agg(
                doanh_thu=('total', 'sum'),
                loi_nhuan=('profit', 'sum'),
                hoa_hong=('total_comm', 'sum')
            ).reset_index()
            st.dataframe(staff_rep, use_container_width=True)

    # --- TAB 5: KHÁCH THÊM (CHỨC NĂNG MỚI ĐƯỢC CẬP NHẬT) ---
    elif menu == "5. KHÁCH THÊM":
        st.header("👥 Quản Lý Khách Thêm & Thuế TNCN")
        
        # Lấy dữ liệu hiện tại từ bảng tính ExtraCustomers
        extra_data = fetch_extra_customers()
        df_extra = pd.DataFrame(extra_data)
        
        # Thiết lập các tab nhỏ bên trong để phân chia không gian rõ ràng
        tab_input, tab_manage, tab_report = st.tabs(["📥 Form Nhập Khách Thêm", "🔍 Duyệt Chi Đơn Khách", "📊 Báo Cáo Chưa Chi"])
        
        # 1. Form nhập dữ liệu Khách Thêm
        with tab_input:
            st.subheader("Nhập thông tin đơn Khách Thêm")
            with st.form("extra_customer_form", clear_on_submit=True):
                ext_name = st.text_input("Tên Khách Hàng / Đơn Vị")
                
                col_e1, col_e2 = st.columns(2)
                ext_before_tax = col_e1.number_input("Số tiền trước thuế (đđ)", min_value=0.0, step=50000.0, format="%.0f")
                ext_actual_done = col_e2.number_input("Số tiền thực làm (đđ)", min_value=0.0, step=50000.0, format="%.0f")
                
                col_e3, col_e4 = st.columns(2)
                ext_tax_rate = col_e3.number_input("Thuế suất (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
                
                # Tính toán tự động theo công thức yêu cầu hiển thị trước nháp cho user xem
                ext_not_done_preview = ext_before_tax - ext_actual_done
                ext_tncn_tax_preview = (ext_tax_rate / 100) * ext_not_done_preview
                
                st.info(f"💡 **Xem trước kết quả tự động tính toán:**\n"
                        f"- Số tiền không làm: **{format_currency(ext_not_done_preview)} đ**\n"
                        f"- Thuế TNCN phải nộp: **{format_currency(ext_tncn_tax_preview)} đ**")
                
                if st.form_submit_button("💾 Lưu Thông Tin Khách Thêm", type="primary"):
                    if not ext_name:
                        st.error("Vui lòng điền tên khách hàng!")
                    elif ext_before_tax < ext_actual_done:
                        st.error("Số tiền trước thuế không thể nhỏ hơn số tiền thực làm!")
                    else:
                        not_done_val = ext_before_tax - ext_actual_done
                        tncn_tax_val = (ext_tax_rate / 100) * not_done_val
                        
                        new_extra_record = {
                            "id": str(int(time.time())), # Tạo ID duy nhất theo dấu thời gian
                            "customer_name": ext_name,
                            "before_tax": ext_before_tax,
                            "actual_done": ext_actual_done,
                            "not_done": not_done_val,
                            "tax_rate": ext_tax_rate,
                            "tncn_tax": tncn_tax_val,
                            "status": "Chưa chi",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        if add_extra_customer(new_extra_record):
                            st.success(f"✅ Đã thêm thông tin khách thêm: {ext_name}")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Đã xảy ra lỗi khi lưu vào hệ thống Google Sheets!")

        # 2. Quản lý trạng thái và duyệt chi chuyển đổi từ Chưa chi -> Đã chi
        with tab_manage:
            st.subheader("Duyệt Tình Trạng Chi")
            if df_extra.empty:
                st.info("Hiện tại chưa có đơn khách thêm nào trong hệ thống.")
            else:
                # Định dạng dữ liệu thô sang VNĐ để bảng nhìn đẹp mắt hơn
                df_manage_show = df_extra.copy()
                for money_col in ["before_tax", "actual_done", "not_done", "tncn_tax"]:
                    df_manage_show[money_col] = df_manage_show[money_col].apply(format_currency)
                
                # Đổi tên cột hiển thị tiêu chuẩn tiếng Việt
                df_manage_show.columns = ["ID Đơn", "Khách Hàng", "Tiền Trước Thuế", "Tiền Thực Làm", "Tiền Không Làm", "Thuế Suất (%)", "Thuế TNCN", "Tình Trạng", "Ngày Tạo"]
                
                st.write("👉 Chọn một dòng dưới đây để mở giao diện duyệt chi:")
                selected_row_event = st.dataframe(
                    df_manage_show, 
                    use_container_width=True, 
                    hide_index=True, 
                    selection_mode="single-row", 
                    on_select="rerun"
                )
                
                # Khi người dùng nhấp chọn 1 dòng đơn hàng cụ thể
                if selected_row_event.selection.rows:
                    selected_idx = selected_row_event.selection.rows[0]
                    target_record = extra_data[selected_idx]
                    
                    st.divider()
                    st.subheader(f"🔍 Chi tiết đơn khách duyệt: {target_record['customer_name']}")
                    
                    c_det1, c_det2 = st.columns(2)
                    c_det1.write(f"🔹 Khách hàng: **{target_record['customer_name']}**")
                    c_det1.write(f"🔹 Số tiền trước thuế: {format_currency(target_record['before_tax'])} đ")
                    c_det1.write(f"🔹 Số tiền thực làm: {format_currency(target_record['actual_done'])} đ")
                    
                    c_det2.write(f"🔸 Số tiền không làm: **{format_currency(target_record['not_done'])} đ**")
                    c_det2.write(f"🔸 Thuế suất TNCN: {target_record['tax_rate']}%")
                    c_det2.write(f"🔸 **Tiền thuế TNCN: {format_currency(target_record['tncn_tax'])} đ**")
                    
                    # Kiểm tra và kết xuất nút hành động dựa trên tình trạng đơn hiện tại
                    current_status = target_record['status']
                    if current_status == "Chưa chi":
                        st.warning("⚠️ Đơn này hiện đang ở trạng thái: **CHƯA CHI**")
                        if st.button("🚀 Duyệt Chi Đơn Này (Chuyển sang Đã Chi)", type="primary"):
                            if update_extra_customer_status(target_record['id'], "Đã chi"):
                                st.success("✅ Cập nhật trạng thái thành công! Đơn hàng đã chuyển sang: Đã chi.")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("Lỗi cập nhật dữ liệu trạng thái!")
                    else:
                        st.success("✅ Đơn này đã hoàn thành trạng thái: **ĐÃ CHI**")

        # 3. Báo cáo: liệt kê các khách trong trạng thái chưa chi
        with tab_report:
            st.subheader("📋 Báo Cáo Khách Thêm Chưa Chi")
            if df_extra.empty:
                st.info("Không có dữ liệu đơn.")
            else:
                # Lọc dữ liệu ra các khách hàng chỉ ở trạng thái "Chưa chi"
                df_pending = df_extra[df_extra['status'] == 'Chưa chi'].copy()
                
                if df_pending.empty:
                    st.success("🎉 Tuyệt vời! Hiện tại không có đơn khách thêm nào cần thanh toán chi trả (Tất cả đã chi).")
                else:
                    # Tính tổng hợp chỉ số tài chính của những đơn chưa chi
                    total_pending_not_done = df_pending['not_done'].sum()
                    total_pending_tncn = df_pending['tncn_tax'].sum()
                    
                    mr1, mr2 = st.columns(2)
                    mr1.metric("Tổng Số Tiền Không Làm (Chưa Chi)", f"{format_currency(total_pending_not_done)} đ")
                    mr2.metric("Tổng Thuế TNCN (Chưa Chi)", f"{format_currency(total_pending_tncn)} đ", delta="Cần nộp chi", delta_color="inverse")
                    
                    # Tiến hành format hiển thị bảng báo cáo rút gọn gửi cho sếp/kế toán xem
                    df_pending_show = df_pending[["customer_name", "before_tax", "actual_done", "not_done", "tncn_tax", "created_at"]].copy()
                    for money_col in ["before_tax", "actual_done", "not_done", "tncn_tax"]:
                        df_pending_show[money_col] = df_pending_show[money_col].apply(format_currency)
                        
                    df_pending_show.columns = ["Tên Khách Hàng", "Số Tiền Trước Thuế", "Tiền Thực Làm", "Số Tiền Không Làm", "Thuế TNCN", "Ngày Tạo Đơn"]
                    
                    st.dataframe(df_pending_show, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user = {}
        st.session_state.role = ""

    if not st.session_state.logged_in:
        login_page()
    else:
        main_app()
