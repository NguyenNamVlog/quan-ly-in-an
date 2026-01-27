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

# --- KẾT NỐI GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets: return None
        creds_dict = dict(st.secrets["service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

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
    
   # --- PHẦN VẼ BẢNG TRONG HÀM create_pdf (ĐÃ FIX LỖI ĐỘ CAO STT) ---
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
        
        # 1. Lưu vị trí Y bắt đầu của dòng
        start_y = pdf.get_y()
        
        # 2. Bước quan trọng: Vẽ "nháp" cột Tên hàng bằng multi_cell để xác định độ cao h
        # Di chuyển con trỏ sang vị trí cột Tên hàng (x=20 vì STT chiếm 10)
        pdf.set_x(20) 
        pdf.multi_cell(75, 8, txt(item.get('name', '')), 1, 'L')
        
        # Lấy vị trí Y sau khi vẽ xong tên hàng để tính độ cao thực tế h
        end_y = pdf.get_y()
        h = end_y - start_y 
        
        # 3. Quay lại vị trí đầu dòng để vẽ cột STT với độ cao h đã tính
        pdf.set_xy(10, start_y)
        pdf.cell(10, h, str(i+1), 1, 0, 'C') # Bây giờ h đã linh hoạt theo Tên hàng
        
        # 4. Di chuyển con trỏ qua sau cột Tên hàng để vẽ nốt các cột còn lại
        pdf.set_xy(95, start_y) # 10 (STT) + 10 (lề trái) + 75 (Tên hàng) = 95
        
        pdf.cell(15, h, txt(item.get('unit', '')), 1, 0, 'C')
        pdf.cell(15, h, format_currency(qty), 1, 0, 'R')
        # pdf.cell(15, h, txt(str(item.get('qty', 0))), 1, 0, 'C')
        pdf.cell(35, h, format_currency(price), 1, 0, 'R')
        pdf.cell(40, h, format_currency(line_total), 1, 1, 'R')
        
        # 5. Đảm bảo con trỏ PDF ở đúng vị trí thấp nhất để dòng tiếp theo không đè lên
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
        pdf.multi_cell(190, 5, txt("Rất mong nhận được sự hợp tác của Quý khách hàng! Trân trọng! "))
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

    menu = st.sidebar.radio("CHỨC NĂNG", ["1. Tạo Báo Giá", "2. Quản Lý Đơn Hàng (Pipeline)", "3. Sổ Quỹ", "4. Dashboard & Báo Cáo"])

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
                            if delete_order(oid): st.success("Đã xóa!"); time.sleep(1); st.rerun()

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
                else: st.info("🔒 Bạn chỉ có quyền xem chi tiết.")

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
        if df.empty: df = pd.DataFrame(columns=["Date", "Content", "Amount", "TM/CK", "Note"])
        if 'date' in df.columns: df.rename(columns={'date': 'Date', 'type': 'Content', 'amount': 'Amount', 'desc': 'Note'}, inplace=True)
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
            st.divider()
            df_tm['Thu'] = df_tm.apply(lambda x: x['Amount'] if x['Content'] == 'Thu' else 0, axis=1)
            df_tm['Chi'] = df_tm.apply(lambda x: x['Amount'] if x['Content'] == 'Chi' else 0, axis=1)
            df_display = df_tm[['Date', 'Thu', 'Chi', 'Note']].copy()
            df_display['Thu'] = df_display['Thu'].apply(lambda x: format_currency(x) if x > 0 else "")
            df_display['Chi'] = df_display['Chi'].apply(lambda x: format_currency(x) if x > 0 else "")
            df_display.columns = ["Ngày tháng", "Thu", "Chi", "Nội dung/Ghi chú"]
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có giao dịch Tiền mặt nào.")

        if is_admin:
            st.write("---")
            st.subheader("📝 Ghi Sổ Tiền Mặt")
            with st.form("cash_entry"):
                c1, c2 = st.columns(2)
                type_option = c1.radio("Loại", ["Thu", "Chi"], horizontal=True)
                st.caption("Hình thức: Tiền Mặt (TM)")
                d = c2.date_input("Ngày", value=datetime.now())
                c3, c4 = st.columns(2)
                amount = c3.number_input("Số tiền", 0, step=10000)
                note = c4.text_input("Nội dung / Ghi chú")
                if st.form_submit_button("💾 Lưu Sổ Quỹ"):
                    if amount > 0:
                        save_cash_log(d, type_option, amount, "TM", note)
                        st.success("Đã lưu!"); time.sleep(1); st.rerun()
                    else: st.warning("Nhập số tiền > 0")
        else: st.warning("🔒 Chỉ Admin được ghi sổ.")

    # --- TAB 4: DASHBOARD & BÁO CÁO (MỚI) ---
    elif menu == "4. Dashboard & Báo Cáo":
        st.header("📈 Dashboard & Báo Cáo Quản Trị")
        
        # Load dữ liệu cần thiết
        orders = fetch_all_orders()
        cashbook = fetch_cashbook()
        
        # Chuyển đổi sang DataFrame
        df_orders = pd.DataFrame(orders)
        df_cash = pd.DataFrame(cashbook)
        
        if df_orders.empty:
            st.info("Chưa có dữ liệu đơn hàng.")
        else:
            # Xử lý dữ liệu đơn hàng để vẽ biểu đồ
            # 1. Extract financial info
            df_orders['total_revenue'] = df_orders['financial'].apply(lambda x: float(x.get('total', 0)))
            df_orders['total_profit'] = df_orders['financial'].apply(lambda x: float(x.get('total_profit', 0)))
            df_orders['total_comm'] = df_orders['financial'].apply(lambda x: float(x.get('total_comm', 0)))
            df_orders['staff'] = df_orders['financial'].apply(lambda x: x.get('staff', 'Unknown'))
            df_orders['cust_name'] = df_orders['customer'].apply(lambda x: x.get('name', 'Unknown'))
            df_orders['comm_status'] = df_orders['financial'].apply(lambda x: x.get('commission_status', 'Chưa chi'))
            
            # --- TAB UI ---
            t1, t2, t3, t4, t5 = st.tabs(["1. Tổng Quan", "2. Báo Cáo Lãi/Lỗ (P&L)", "3. Phân Tích Doanh Thu", "4. Công Nợ", "5. Hoa Hồng"])
            
            # 1. TỔNG QUAN
            with t1:
                st.subheader("Trạng Thái Đơn Hàng")
                status_counts = df_orders['status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                
                # Biểu đồ tròn
                fig = px.pie(status_counts, values='Count', names='Status', title='Tỷ lệ đơn hàng theo trạng thái', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
                
                # KPI cơ bản
                k1, k2, k3 = st.columns(3)
                k1.metric("Tổng đơn hàng", len(df_orders))
                k2.metric("Đang sản xuất", len(df_orders[df_orders['status'] == 'Sản xuất']))
                k3.metric("Hoàn thành", len(df_orders[df_orders['status'] == 'Hoàn thành']))

            # 2. P&L REPORT
            with t2:
                if is_admin:
                    st.subheader("Báo Cáo Kết Quả Kinh Doanh (Ước tính)")
                    
                    # 1. Doanh thu (Tổng giá trị đơn hàng)
                    revenue = df_orders['total_revenue'].sum()
                    
                    # 2. Giá vốn (Cost of Goods Sold)
                    # Phải tính tổng cost từ items của tất cả đơn hàng
                    total_cogs = 0
                    for o in orders:
                        items = o.get('items', [])
                        for i in items:
                            try:
                                total_cogs += float(i.get('qty', 0)) * float(i.get('cost', 0))
                            except: pass
                            
                    # 3. Lợi nhuận gộp
                    gross_profit = revenue - total_cogs
                    
                    # 4. Chi phí vận hành (Lấy từ Sổ Quỹ - Loại 'Chi')
                    total_expenses = 0
                    if not df_cash.empty:
                        # Chuẩn hóa cột
                        if 'amount' in df_cash.columns and 'type' in df_cash.columns:
                             df_cash['amt'] = pd.to_numeric(df_cash['amount'], errors='coerce').fillna(0)
                             total_expenses = df_cash[df_cash['type'] == 'Chi']['amt'].sum()
                    
                    # 5. Lợi nhuận ròng
                    net_profit = gross_profit - total_expenses
                    
                    # Hiển thị bảng
                    pl_data = {
                        "Hạng mục": ["1. Doanh thu bán hàng", "2. Giá vốn hàng bán (COGS)", "3. Lợi nhuận gộp (1-2)", "4. Chi phí vận hành (Sổ quỹ)", "5. Lợi nhuận ròng (3-4)"],
                        "Giá trị": [revenue, total_cogs, gross_profit, total_expenses, net_profit]
                    }
                    df_pl = pd.DataFrame(pl_data)
                    df_pl['Giá trị'] = df_pl['Giá trị'].apply(format_currency)
                    st.table(df_pl)
                else:
                    st.warning("🔒 Chỉ Admin mới được xem báo cáo Lãi/Lỗ.")

            # 3. PHÂN TÍCH DOANH THU
            with t3:
                st.subheader("Phân Tích Doanh Thu")
                
                # Theo Nhân viên
                st.write("###### Theo Nhân Viên")
                staff_perf = df_orders.groupby('staff')['total_revenue'].sum().reset_index().sort_values('total_revenue', ascending=False)
                fig_staff = px.bar(staff_perf, x='staff', y='total_revenue', labels={'total_revenue': 'Doanh thu', 'staff': 'Nhân viên'})
                st.plotly_chart(fig_staff, use_container_width=True)
                
                # Theo Khách hàng (Top 10)
                st.write("###### Top 10 Khách Hàng")
                cust_perf = df_orders.groupby('cust_name')['total_revenue'].sum().reset_index().sort_values('total_revenue', ascending=False).head(10)
                st.dataframe(cust_perf.style.format({"total_revenue": "{:,.0f}"}), use_container_width=True)

                # Theo Sản phẩm (Cần xử lý items)
                st.write("###### Top Sản Phẩm Bán Chạy")
                all_items = []
                for o in orders:
                    for i in o.get('items', []):
                        all_items.append({"Product": i.get('name'), "Revenue": float(i.get('total_line', 0))})
                
                if all_items:
                    df_products = pd.DataFrame(all_items)
                    prod_perf = df_products.groupby('Product')['Revenue'].sum().reset_index().sort_values('Revenue', ascending=False).head(10)
                    st.bar_chart(prod_perf.set_index('Product'))

            # 4. CÔNG NỢ
            with t4:
                st.subheader("Danh Sách Khách Nợ")
                # Lọc đơn có debt > 0
                df_orders['debt'] = df_orders['financial'].apply(lambda x: float(x.get('debt', 0)))
                debtors = df_orders[df_orders['debt'] > 0][['order_id', 'date', 'cust_name', 'total_revenue', 'debt']].copy()
                
                if not debtors.empty:
                    st.metric("Tổng Công Nợ Phải Thu", format_currency(debtors['debt'].sum()))
                    
                    debtors.columns = ["Mã ĐH", "Ngày", "Khách hàng", "Tổng đơn", "Còn nợ"]
                    debtors['Tổng đơn'] = debtors['Tổng đơn'].apply(format_currency)
                    debtors['Còn nợ'] = debtors['Còn nợ'].apply(format_currency)
                    st.dataframe(debtors, use_container_width=True)
                else:
                    st.success("Tuyệt vời! Không có công nợ.")

            # 5. HOA HỒNG
            with t5:
                st.subheader("Theo Dõi Hoa Hồng Nhân Viên")
                
                # Group by Staff and Status
                comm_summary = df_orders.groupby(['staff', 'comm_status'])['total_comm'].sum().unstack(fill_value=0).reset_index()
                
                # Đảm bảo có đủ cột
                if 'Chưa chi' not in comm_summary.columns: comm_summary['Chưa chi'] = 0.0
                if 'Đã chi' not in comm_summary.columns: comm_summary['Đã chi'] = 0.0
                
                comm_summary['Tổng hoa hồng'] = comm_summary['Chưa chi'] + comm_summary['Đã chi']
                
                # Format
                st.dataframe(
                    comm_summary,
                    column_config={
                        "staff": "Nhân viên",
                        "Chưa chi": st.column_config.NumberColumn("Chưa thanh toán", format="%.0f đ"),
                        "Đã chi": st.column_config.NumberColumn("Đã thanh toán", format="%.0f đ"),
                        "Tổng hoa hồng": st.column_config.NumberColumn("Tổng cộng", format="%.0f đ"),
                    },
                    use_container_width=True
                )
                
                # Tổng hợp toàn công ty
                m1, m2, m3 = st.columns(3)
                m1.metric("Tổng Hoa Hồng", format_currency(df_orders['total_comm'].sum()))
                # Tính tổng đã chi/chưa chi toàn bộ
                total_paid = df_orders[df_orders['comm_status'] == 'Đã chi']['total_comm'].sum()
                total_pending = df_orders[df_orders['comm_status'] != 'Đã chi']['total_comm'].sum()
                m2.metric("Đã Thanh Toán", format_currency(total_paid))
                m3.metric("Chưa Thanh Toán", format_currency(total_pending))

if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user = {}
        st.session_state.role = ""

    if not st.session_state.logged_in:
        login_page()
    else:
        try:
            main_app()
        except Exception as e:
            st.error("⚠️ Đã xảy ra lỗi ứng dụng:")
            st.code(traceback.format_exc())
