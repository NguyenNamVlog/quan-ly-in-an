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
import plotly.express as px

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

        if str(phone) not in phones:
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
                ["Duong", "Duong-", "staff"],
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
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi. Nay bàn giao các hàng hóa và dịch vụ như sau:"
    else:
        raw_date = order.get('date', '')
        try: odate = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except: odate = raw_date
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi. Xin trân trọng gửi tới Quý khách hàng báo giá như sau:"

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
    
    money_text = read_money_vietnamese(final_total) if not SAFE_MODE else f"Tong cong: {format_currency(final_total)} VND"
    pdf.multi_cell(0, 6, txt(f"Bằng chữ: {money_text}"))
    pdf.ln(3)

    pdf.set_x(10)
    if is_delivery:
        pdf.cell(95, 5, txt("NGƯỜI NHẬN"), 0, 0, 'C')
        pdf.cell(95, 5, txt("NGƯỜI GIAO"), 0, 1, 'C')
    else:
        pdf.cell(0, 5, txt("NGƯỜI BÁO GIÁ"), 0, 1, 'R')
    pdf.ln(20)

    pdf.set_font_size(10)
    if is_delivery:
        pdf.multi_cell(190, 5, txt("* Quý khách vui lòng kiểm tra và phản hồi ngay về tình trạng hàng hoá khi giao nhận!"))
        pdf.multi_cell(190, 5, txt("* Giao hàng miễn phí trong nội thành thành phố Biên Hoà với đơn hàng >1.000.000đ"))
    else:
        pdf.cell(0, 5, txt("Lưu ý:"), 0, 1)
        pdf.cell(0, 5, txt("- Giá trên đã bao gồm vận chuyển, giao hàng."), 0, 1)
        pdf.cell(0, 5, txt("- Thời gian hoàn thành, giao hàng: từ 03 - 05 ngày."), 0, 1)
        pdf.cell(0, 5, txt("- Báo giá này áp dụng trong vòng 30 ngày."), 0, 1)
    
    pdf.ln(2)
    pdf.multi_cell(190, 5, txt("Rất mong được hợp tác với Quý khách hàng. Trân trọng!"))
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
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            i_name = col1.text_input("Tên hàng / Quy cách")
            i_unit = col2.text_input("ĐVT")
            i_qty = col3.number_input("Số lượng", 1.0, step=1.0)
            col4, col5, col6 = st.columns(3)
            i_cost = col4.number_input("Giá Vốn", 0.0, step=1000.0)
            i_price = col5.number_input("Giá Bán", 0.0, step=1000.0)
            i_vat = col6.number_input("% VAT", 0.0, 100.0, 0.0, step=1.0)
            if st.form_submit_button("➕ Thêm vào danh sách"):
                if i_name:
                    total_sell = i_qty * i_price
                    total_cost = i_qty * i_cost
                    vat_amt = total_sell * (i_vat / 100)
                    profit = total_sell - total_cost
                    rate = 0.6 if staff in ["Nam", "Dương"] else (0.5 if staff == "Vạn" else 0.3)
                    commission = profit * rate if profit > 0 else 0
                    st.session_state.cart.append({
                        "name": i_name, "unit": i_unit, "qty": i_qty, "cost": i_cost,
                        "price": i_price, "vat_rate": i_vat, "vat_amt": vat_amt,
                        "profit": profit, "commission": commission,
                        "total_line": total_sell + vat_amt
                    })
                    st.rerun()

        if st.session_state.cart:
            st.write("---")
            view_df = pd.DataFrame(st.session_state.cart).copy()
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
                        "order_id": gen_id(), "date": datetime.now().strftime("%Y-%m-%d"),
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
            st.success(f"✅ Đã tạo: {st.session_state.last_order['order_id']}")
            pdf_bytes = create_pdf(st.session_state.last_order, "BÁO GIÁ")
            st.download_button("🖨️ Tải PDF", pdf_bytes, f"BG_{st.session_state.last_order['order_id']}.pdf", "application/pdf")

    # --- TAB 2: QUẢN LÝ ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.header("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            current_orders = [o for o in all_orders if o.get('status') == status_filter]
            if not current_orders:
                st.info("Không có đơn hàng nào.")
                return

            table_data = []
            for o in current_orders:
                cust = o.get('customer', {})
                fin = o.get('financial', {})
                table_data.append({
                    "Mã ĐH": o.get('order_id'), "Khách hàng": cust.get('name'),
                    "Tổng tiền": format_currency(float(fin.get('total', 0))),
                    "Còn nợ": format_currency(float(fin.get('debt', 0))),
                    "Nhân viên": fin.get('staff', ''),
                    "Trạng thái": o.get('status')
                })
            
            event = st.dataframe(pd.DataFrame(table_data), use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True)
            
            if event.selection.rows:
                idx = event.selection.rows[0]
                sel_order = current_orders[idx]
                oid = sel_order.get('order_id')
                cust = sel_order.get('customer', {})
                fin = sel_order.get('financial', {})
                debt = float(fin.get('total', 0)) - float(fin.get('paid', 0))

                st.divider()
                st.subheader(f"🛠️ Xử lý đơn hàng: {oid}")
                
                c_act1, c_act2, c_act3, c_act4 = st.columns(4)
                with c_act1:
                    if pdf_type:
                        pdf_data = create_pdf(sel_order, pdf_type)
                        st.download_button(f"🖨️ In {pdf_type}", pdf_data, f"{oid}.pdf", key=f"dl_{oid}")
                with c_act2:
                    pdf_gh = create_pdf(sel_order, "PHIẾU GIAO HÀNG")
                    st.download_button("🚚 In Phiếu Giao", pdf_gh, f"GH_{oid}.pdf", key=f"dl_gh_{oid}")
                
                if is_admin:
                    with c_act3:
                        if next_status and st.button(f"{btn_text} ➡️", key=f"mv_{oid}", type="primary"):
                            update_order_status(oid, next_status)
                            st.rerun()
                    with c_act4:
                        if st.button("🗑️ Xóa Đơn", key=f"del_{oid}"):
                            if delete_order(oid): st.success("Đã xóa!"); st.rerun()

                    # --- PHẦN THU TIỀN VÀ SỬA ĐƠN (ĐÃ FIX LỖI THỤT DÒNG TẠI ĐÂY) ---
                    st.write("---")
                    st.write("💳 **THANH TOÁN & CẬP NHẬT**")
                    tab_pay, tab_edit = st.tabs(["💸 Thu Tiền", "✏️ Sửa Đơn Hàng"])
                    
                    with tab_pay:
                        c_p1, c_p2 = st.columns(2)
                        pay_method = c_p1.radio("Hình thức:", ["Một phần", "Toàn bộ"], horizontal=True, key=f"pm_{oid}")
                        current_debt = float(debt)
                        
                        if pay_method == "Toàn bộ":
                            pay_val = current_debt
                            st.info(f"Số tiền thu: {format_currency(pay_val)}")
                        else:
                            pay_val = c_p2.number_input("Nhập số tiền thu:", 0.0, current_debt, current_debt, key=f"p_val_{oid}")
                        
                        pay_via = c_p2.selectbox("Phương thức:", ["TM", "CK"], key=f"via_{oid}")
                        
                        if st.button("Xác nhận Thu Tiền", key=f"cf_pay_{oid}", type="primary"):
                            if pay_val > 0:
                                remaining_debt = current_debt - pay_val
                                new_status = status_filter
                                new_payment_status = "Cọc/Còn nợ"
                                if remaining_debt <= 0:
                                    new_status = "Hoàn thành"
                                    new_payment_status = "Đã TT"
                                
                                if update_order_status(oid, new_status, new_payment_status, pay_val):
                                    save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay_val, pay_via, f"Thu đơn {oid}")
                                    st.success(f"Đã cập nhật!"); time.sleep(1); st.rerun()

                    with tab_edit:
                        with st.form(f"form_edit_{oid}"):
                            new_name = st.text_input("Tên Khách", value=cust.get('name'))
                            edited_df = st.data_editor(pd.DataFrame(sel_order.get('items', [])), num_rows="dynamic", key=f"editor_{oid}")
                            if st.form_submit_button("Lưu Thay Đổi"):
                                new_items = edited_df.to_dict('records')
                                r_total, r_profit = 0, 0
                                for it in new_items:
                                    q, p, c = float(it.get('qty',0)), float(it.get('price',0)), float(it.get('cost',0))
                                    it['total_line'] = q*p + (q*p*(float(it.get('vat_rate',0))/100))
                                    it['profit'] = (q*p) - (q*c)
                                    r_total += it['total_line']
                                    r_profit += it['profit']
                                
                                c_staff = fin.get('staff', '')
                                rate = 0.6 if c_staff in ["Nam", "Dương"] else (0.5 if c_staff == "Vạn" else 0.3)
                                r_comm = r_profit * rate if r_profit > 0 else 0
                                
                                if edit_order_info(oid, {"name": new_name, "phone": cust.get('phone'), "address": cust.get('address')}, r_total, new_items, r_profit, r_comm):
                                    st.success("Cập nhật thành công!"); time.sleep(1); st.rerun()

        with tabs[0]: render_tab_content("Báo giá", "Thiết kế", "✅ Duyệt -> Thiết Kế", "BÁO GIÁ")
        with tabs[1]: render_tab_content("Thiết kế", "Sản xuất", "✅ Duyệt TK -> Sản Xuất", None)
        with tabs[2]: render_tab_content("Sản xuất", "Giao hàng", "✅ Xong -> Giao Hàng", None)
        with tabs[3]: render_tab_content("Giao hàng", "Công nợ", "✅ Giao Xong -> Công Nợ", "PHIẾU GIAO HÀNG")
        with tabs[4]: render_tab_content("Công nợ", None, "", None)
        with tabs[5]: render_tab_content("Hoàn thành", None, "", None)

    # --- TAB 3: SỔ QUỸ ---
    elif menu == "3. Sổ Quỹ":
        st.header("📊 Sổ Quỹ Tiền Mặt")
        df = pd.DataFrame(fetch_cashbook())
        if not df.empty:
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
            st.dataframe(df, use_container_width=True)
        
        if is_admin:
            with st.form("cash_entry"):
                type_option = st.radio("Loại", ["Thu", "Chi"], horizontal=True)
                amount = st.number_input("Số tiền", 0, step=10000)
                note = st.text_input("Ghi chú")
                if st.form_submit_button("💾 Lưu Sổ Quỹ"):
                    save_cash_log(datetime.now().strftime("%Y-%m-%d"), type_option, amount, "TM", note)
                    st.success("Đã lưu!"); st.rerun()

    # --- TAB 4: DASHBOARD ---
    elif menu == "4. Dashboard & Báo Cáo":
        st.header("📈 Dashboard")
        orders = fetch_all_orders()
        if orders:
            df_orders = pd.DataFrame(orders)
            df_orders['total_rev'] = df_orders['financial'].apply(lambda x: float(x.get('total', 0)))
            st.metric("TỔNG DOANH THU", format_currency(df_orders['total_rev'].sum()))
            fig = px.pie(df_orders, names='status', title='Trạng thái đơn hàng')
            st.plotly_chart(fig)

if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if not st.session_state.logged_in:
        login_page()
    else:
        try: main_app()
        except Exception as e:
            st.error("⚠️ Lỗi ứng dụng")
            st.code(traceback.format_exc())
