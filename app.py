import streamlit as st
import pandas as pd
import json
import time
import os
import requests
import unicodedata
from datetime import datetime
from fpdf import FPDF
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials

# --- CẤU HÌNH ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit"
FONT_FILENAME = 'arial.ttf' # Đảm bảo file này có trong thư mục GitHub

# --- HÀM HỖ TRỢ XỬ LÝ VĂN BẢN ---
def remove_accents(input_str):
    if not input_str: return ""
    input_str = str(input_str)
    s = input_str.replace('đ', 'd').replace('Đ', 'D')
    nfkd_form = unicodedata.normalize('NFKD', s)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def format_currency(value):
    if value is None: return "0"
    try: return "{:,.0f}".format(float(value))
    except: return "0"

def read_money_vietnamese(amount):
    try: return num2words(amount, lang='vi').capitalize() + " đồng chẵn."
    except: return "..................... đồng."

# --- KẾT NỐI GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets:
            return None
        creds_dict = dict(st.secrets["service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except: return None

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

def save_cash_log(date, type_, amount, desc):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Cashbook")
        except: 
            ws = sh.add_worksheet("Cashbook", 1000, 10)
            ws.append_row(["date", "type", "amount", "category", "desc"])
        ws.append_row([str(date), type_, amount, "Thu tiền hàng" if type_=='Thu' else "Chi phí", desc])
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
    def header(self):
        # Header xử lý trong body để an toàn font
        pass

def create_pdf(order, title):
    pdf = PDFGen()
    pdf.add_page()
    
    # 1. Cài đặt Font
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

    # --- Nội dung PDF ---
    pdf.set_font_size(14)
    pdf.cell(0, 10, txt('CÔNG TY IN ẤN AN LỘC PHÁT'), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)

    pdf.set_font_size(16)
    pdf.cell(0, 10, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    
    pdf.set_font_size(11)
    oid = order.get('order_id', '')
    odate = order.get('date', '')
    pdf.cell(0, 8, txt(f"Mã: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    
    cust = order.get('customer', {})
    pdf.cell(0, 7, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"SĐT: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Header bảng
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", border=1, align='C', fill=True)
    pdf.cell(90, 8, txt("Tên hàng / Quy cách"), border=1, align='C', fill=True)
    pdf.cell(20, 8, "SL", border=1, align='C', fill=True)
    pdf.cell(30, 8, txt("Đơn giá"), border=1, align='C', fill=True)
    pdf.cell(40, 8, txt("Thành tiền"), border=1, align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
    
    total = 0
    items = order.get('items', [])
    for i, item in enumerate(items):
        try: val = float(item.get('total', 0))
        except: val = 0
        total += val
        
        pdf.cell(10, 8, str(i+1), border=1, align='C')
        pdf.cell(90, 8, txt(item.get('name', '')), border=1)
        pdf.cell(20, 8, txt(str(item.get('qty', 0))), border=1, align='C')
        pdf.cell(30, 8, format_currency(item.get('price', 0)), border=1, align='R')
        pdf.cell(40, 8, format_currency(val), border=1, align='R', new_x="LMARGIN", new_y="NEXT")
    
    pdf.cell(150, 8, txt("TỔNG CỘNG:"), border=1, align='R')
    pdf.cell(40, 8, format_currency(total), border=1, align='R', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    money_text = ""
    if SAFE_MODE: money_text = f"Tong cong: {format_currency(total)} VND"
    else:
        try: money_text = read_money_vietnamese(total)
        except: money_text = f"{format_currency(total)} đồng."
    pdf.multi_cell(0, 8, txt(f"Bằng chữ: {money_text}"))
    
    return bytes(pdf.output())

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Hệ Thống In Ấn", layout="wide")
    menu = st.sidebar.radio("CHỨC NĂNG", ["1. Tạo Báo Giá", "2. Quản Lý Đơn Hàng (Pipeline)", "3. Sổ Quỹ & Báo Cáo"])

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'last_order' not in st.session_state: st.session_state.last_order = None

    # --- TAB 1: TẠO BÁO GIÁ (ĐÃ SỬA LỖI FORM) ---
    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        
        # 1. KHÔNG DÙNG st.form CHO THÔNG TIN KHÁCH (để tránh lỗi)
        st.subheader("1. Thông tin khách hàng")
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên Khách Hàng", key="in_name")
        phone = c2.text_input("Số Điện Thoại", key="in_phone")
        addr = st.text_input("Địa Chỉ", key="in_addr")
        staff = st.selectbox("Nhân Viên", ["Nam", "Dương", "Thảo", "Khác"], key="in_staff")

        st.divider()
        st.subheader("2. Chi tiết hàng hóa")
        
        # 2. CHỈ DÙNG st.form CHO VIỆC THÊM HÀNG
        with st.form("add_item_form", clear_on_submit=True):
            c3, c4, c5 = st.columns([3, 1, 2])
            i_name = c3.text_input("Tên hàng")
            i_qty = c4.number_input("Số lượng", 1.0, step=1.0)
            i_price = c5.number_input("Đơn giá", 0.0, step=1000.0)
            
            # Nút Submit nằm TRONG form này -> OK
            btn_add = st.form_submit_button("➕ Thêm vào danh sách")
            if btn_add:
                if i_name:
                    st.session_state.cart.append({
                        "name": i_name, "qty": i_qty, "price": i_price, "total": i_qty*i_price
                    })
                    st.rerun() # Refresh để cập nhật bảng bên dưới
                else:
                    st.error("Vui lòng nhập tên hàng!")

        # 3. Hiển thị giỏ hàng (Ngoài form)
        if st.session_state.cart:
            st.write("---")
            cart_df = pd.DataFrame(st.session_state.cart)
            
            # Hiển thị đẹp
            view_df = cart_df.copy()
            view_df['price'] = view_df['price'].apply(format_currency)
            view_df['total'] = view_df['total'].apply(format_currency)
            st.table(view_df)
            
            total_val = sum(i['total'] for i in st.session_state.cart)
            st.metric("TỔNG TIỀN", format_currency(total_val))
            
            c_del, c_save = st.columns(2)
