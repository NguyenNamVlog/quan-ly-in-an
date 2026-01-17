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

# --- QUẢN LÝ KHÁCH HÀNG ---
def fetch_customers():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("Customers")
        except:
            return [] 
        return ws.get_all_records()
    except: return []

def save_customer_db(name, phone, address):
    client = get_gspread_client()
    if not client or not phone: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("Customers")
        except: 
            ws = sh.add_worksheet("Customers", 1000, 5)
            ws.append_row(["phone", "name", "address", "last_order"])
        try:
            phones = ws.col_values(1)
        except:
            phones = []
        if str(phone) not in [str(p) for p in phones]:
            ws.append_row([str(phone), name, address, datetime.now().strftime("%Y-%m-%d")])
            st.cache_data.clear() 
    except: pass

# --- QUẢN LÝ NGƯỜI DÙNG ---
def init_users():
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("Users")
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
        try:
            ws = sh.worksheet("Orders")
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
        try:
            ws = sh.worksheet("Cashbook")
        except: 
            ws = sh.add_worksheet("Cashbook", 1000, 10)
            ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"])
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
        pdf.cell(0, 8, txt('CONG TY TNHH SAN XUAT KINH DOANH THUONG MAI AN LOC PHAT'), 0, 1, 'C')
        pdf.set_font_size(10)
        pdf.cell(0, 5, txt('Ma so thue: 3603995632'), 0, 1, 'C')
        pdf.ln(2)

    pdf.set_font_size(16)
    pdf.cell(0, 8, txt(title), 0, 1, 'C')
    pdf.set_font_size(11)
    
    oid = order.get('order_id', '')
    raw_date = order.get('date', '')
    try: odate = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except: odate = raw_date

    cust = order.get('customer', {})
    items = order.get('items', [])
    
    pdf.cell(0, 6, txt(f"Ma so: {oid} | Ngay: {odate}"), 0, 1, 'C')
    pdf.ln(1)
    pdf.cell(0, 6, txt(f"Khach hang: {cust.get('name', '')}"), 0, 1)
    pdf.cell(0, 6, txt(f"Dien thoai: {cust.get('phone', '')}"), 0, 1)
    pdf.cell(0, 6, txt(f"Dia chi: {cust.get('address', '')}"), 0, 1)
    pdf.ln(2)
  
    # Header bảng
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(75, 8, txt("Ten hang / Quy cach"), 1, 0, 'C', 1)
    pdf.cell(15, 8, txt("DVT"), 1, 0, 'C', 1)
    pdf.cell(15, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(35, 8, txt("Don gia"), 1, 0, 'C', 1)
    pdf.cell(40, 8, txt("Thanh tien"), 1, 1, 'C', 1)
    
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
        
        # --- FIX LỖI XUỐNG HÀNG TỰ ĐỘNG ---
        start_y = pdf.get_y()
        # Tính toán độ cao cần thiết cho cột tên hàng trước
        pdf.set_xy(20, start_y) # Vị trí cột Tên hàng
        pdf.multi_cell(75, 8, txt(item.get('name', '')), 1, 'L')
        end_y = pdf.get_y()
        h = end_y - start_y
        
        # Vẽ các cột còn lại dựa trên độ cao h
        pdf.set_xy(10, start_y)
        pdf.cell(10, h, str(i+1), 1, 0, 'C') # STT
        
        pdf.set_xy(95, start_y) # Sau cột Tên hàng
        pdf.cell(15, h, txt(item.get('unit', '')), 1, 0, 'C')
        pdf.cell(15, h, str(item.get('qty', 0)), 1, 0, 'C')
        pdf.cell(35, h, format_currency(price), 1, 0, 'R')
        pdf.cell(40, h, format_currency(line_total), 1, 1, 'R')
        pdf.set_y(end_y) # Nhảy xuống dòng tiếp theo
    
    final_total = sum_items_total + total_vat
    pdf.cell(150, 8, txt("Cong tien hang:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(sum_items_total), 1, 1, 'R')
    pdf.cell(150, 8, txt("Tien VAT:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total_vat), 1, 1, 'R')
    pdf.cell(150, 8, txt("TONG CONG THANH TOAN:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(final_total), 1, 1, 'R')
    
    pdf.ln(5)
    money_text = read_money_vietnamese(final_total)
    pdf.multi_cell(0, 6, txt(f"Bang chu: {money_text}"))
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
                st.rerun()
            else:
                st.error("Sai tên đăng nhập hoặc mật khẩu!")

# --- MAIN APP ---
def main_app():
    is_admin = st.session_state.role == 'admin'
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user['username']}**")
        if st.button("Đăng xuất"):
            st.session_state.logged_in = False
            st.rerun()

    st.title("Hệ Thống Quản Lý An Lộc Phát")
    menu = st.sidebar.radio("CHỨC NĂNG", ["1. Tạo Báo Giá", "2. Quản Lý Đơn Hàng", "3. Sổ Quỹ", "4. Báo Cáo"])

    if 'cart' not in st.session_state: st.session_state.cart = []

    # 1. TẠO BÁO GIÁ
    if menu == "1. Tạo Báo Giá":
        st.header("📝 Tạo Báo Giá Mới")
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên Khách Hàng")
        phone = c2.text_input("Số Điện Thoại")
        addr = st.text_input("Địa Chỉ")
        
        with st.form("item_form", clear_on_submit=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            i_name = col1.text_input("Tên hàng")
            i_unit = col2.text_input("ĐVT")
            i_qty = col3.number_input("SL", 1.0)
            col4, col5, col6 = st.columns(3)
            i_cost = col4.number_input("Giá Vốn", 0.0)
            i_price = col5.number_input("Giá Bán", 0.0)
            i_vat = col6.number_input("% VAT", 0.0)
            if st.form_submit_button("Thêm hàng"):
                st.session_state.cart.append({
                    "name": i_name, "unit": i_unit, "qty": i_qty, "cost": i_cost,
                    "price": i_price, "vat_rate": i_vat, "total_line": (i_qty * i_price) * (1 + i_vat/100),
                    "profit": (i_qty * i_price) - (i_qty * i_cost)
                })
                st.rerun()

        if st.session_state.cart:
            st.table(pd.DataFrame(st.session_state.cart)[["name", "qty", "price", "total_line"]])
            if st.button("LƯU ĐƠN HÀNG", type="primary"):
                total_f = sum(i['total_line'] for i in st.session_state.cart)
                total_p = sum(i['profit'] for i in st.session_state.cart)
                new_order = {
                    "order_id": gen_id(), "date": datetime.now().strftime("%Y-%m-%d"),
                    "status": "Báo giá", "payment_status": "Chưa TT",
                    "customer": {"name": name, "phone": phone, "address": addr},
                    "items": st.session_state.cart,
                    "financial": {"total": total_f, "paid": 0, "debt": total_f, "total_profit": total_p}
                }
                if add_new_order(new_order):
                    save_customer_db(name, phone, addr)
                    st.session_state.cart = []
                    st.success("Đã tạo đơn!")
                    st.rerun()

    # 2. QUẢN LÝ ĐƠN HÀNG
    elif menu == "2. Quản Lý Đơn Hàng":
        st.header("📋 Danh Sách Đơn Hàng")
        orders = fetch_all_orders()
        for o in orders:
            with st.expander(f"{o['order_id']} - {o['customer']['name']} ({o['status']})"):
                st.write(f"Tổng tiền: {format_currency(o['financial']['total'])}")
                pdf_data = create_pdf(o, "BAO GIA")
                st.download_button("Tải PDF", pdf_data, f"{o['order_id']}.pdf")
                if is_admin and st.button("Xóa", key=o['order_id']):
                    delete_order(o['order_id'])
                    st.rerun()

    # CÁC TAB KHÁC TƯƠNG TỰ...
    elif menu == "3. Sổ Quỹ":
        st.header("💰 Quản Lý Sổ Quỹ")
        df_cash = pd.DataFrame(fetch_cashbook())
        st.dataframe(df_cash)

    elif menu == "4. Báo Cáo":
        st.header("📈 Báo Cáo Doanh Thu")
        st.info("Tính năng đang phát triển...")

if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if not st.session_state.logged_in:
        login_page()
    else:
        main_app()
