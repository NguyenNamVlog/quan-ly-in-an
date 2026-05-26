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
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit" [cite: 1]
FONT_FILENAME = 'arial.ttf' [cite: 1]
HEADER_IMAGE = 'tieu_de.png' [cite: 1]

# --- HÀM HỖ TRỢ ---
def remove_accents(input_str):
    if not input_str: return "" [cite: 1]
    input_str = str(input_str) [cite: 1]
    s = input_str.replace('đ', 'd').replace('Đ', 'D') [cite: 1]
    nfkd_form = unicodedata.normalize('NFKD', s) [cite: 1]
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]) [cite: 1]

def format_currency(value):
    if value is None: return "0" [cite: 2]
    try:
        val = float(value) [cite: 2]
        if val.is_integer():
            return "{:,.0f}".format(val).replace(",", ".") [cite: 2]
        else:
            return "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".") [cite: 2]
    except: return "0" [cite: 2]

def read_money_vietnamese(amount):
    try: return num2words(amount, lang='vi').capitalize() + " đồng chẵn." [cite: 2]
    except: return "..................... đồng." [cite: 3]

# --- KẾT NỐI GOOGLE SHEETS (ĐÃ THÊM DEBUG) ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets: [cite: 3]
            st.error("❌ Lỗi: Không tìm thấy mục [service_account] trong st.secrets") [cite: 3]
            return None [cite: 3]
        
        creds_dict = dict(st.secrets["service_account"]) [cite: 3]
        if "private_key" in creds_dict: [cite: 3]
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n") [cite: 4]
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"] [cite: 4]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope) [cite: 4]
        return gspread.authorize(creds) [cite: 4]
    except Exception as e:
        st.error(f"⚠️ Lỗi kết nối Google: {e}") [cite: 4]
        return None [cite: 4]

# --- CUSTOMER MANAGEMENT ---
def fetch_customers():
    client = get_gspread_client() [cite: 5]
    if not client: return [] [cite: 5]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 5]
        try: ws = sh.worksheet("Customers") [cite: 5]
        except: return [] [cite: 5]
        return ws.get_all_records() [cite: 5]
    except: return [] [cite: 5]

def save_customer_db(name, phone, address):
    client = get_gspread_client() [cite: 5]
    if not client or not phone: return [cite: 5]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 5]
        try: ws = sh.worksheet("Customers") [cite: 6]
        except: 
            ws = sh.add_worksheet("Customers", 1000, 5) [cite: 6]
            ws.append_row(["phone", "name", "address", "last_order"]) [cite: 6]
        
        try: phones = ws.col_values(1) [cite: 6]
        except: phones = [] [cite: 6]

        if phone not in phones: [cite: 6]
            ws.append_row([str(phone), name, address, datetime.now().strftime("%Y-%m-%d")]) [cite: 7]
            st.cache_data.clear() [cite: 7]
    except: pass

# --- USER MANAGEMENT ---
def init_users():
    client = get_gspread_client() [cite: 7]
    if not client: return [cite: 7]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 7]
        try: ws = sh.worksheet("Users") [cite: 7]
        except:
            ws = sh.add_worksheet("Users", 100, 3) [cite: 7]
            ws.append_row(["username", "password", "role"]) [cite: 8]
            default_users = [ [cite: 8]
                ["Nam", "Emyeu0901", "admin"], [cite: 8]
                ["Duong", "Duong", "staff"], [cite: 8]
                ["Van", "Van", "staff"] [cite: 8]
            ] [cite: 8]
            for u in default_users: ws.append_row(u) [cite: 8, 9]
    except: pass

def get_users_db():
    client = get_gspread_client() [cite: 9]
    if not client: return [] [cite: 9]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 9]
        ws = sh.worksheet("Users") [cite: 9]
        return ws.get_all_records() [cite: 9]
    except: return [] [cite: 9]

def change_password(username, new_pass):
    client = get_gspread_client() [cite: 9]
    if not client: return False [cite: 9]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 9]
        ws = sh.worksheet("Users") [cite: 9, 10]
        cell = ws.find(username) [cite: 10]
        if cell: [cite: 10]
            ws.update_cell(cell.row, 2, new_pass) [cite: 10]
            return True [cite: 10]
        return False [cite: 10]
    except: return False [cite: 10]

def check_login(username, password):
    users = get_users_db() [cite: 10]
    for u in users: [cite: 11]
        if str(u['username']).strip() == username and str(u['password']).strip() == password: [cite: 11]
            return u [cite: 11]
    return None [cite: 11]

# --- DATABASE CORE ---
def fetch_all_orders():
    client = get_gspread_client() [cite: 11]
    if not client: return [] [cite: 11]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 11]
        ws = sh.worksheet("Orders") [cite: 11]
        raw_data = ws.get_all_records() [cite: 11]
        processed_data = [] [cite: 11, 12]
        for row in raw_data: [cite: 12]
            try:
                cust = row.get('customer') [cite: 12]
                row['customer'] = json.loads(cust) if isinstance(cust, str) and cust else (cust if isinstance(cust, dict) else {}) [cite: 12]
                items = row.get('items') [cite: 12]
                row['items'] = json.loads(items) if isinstance(items, str) and items else (items if isinstance(items, list) else []) [cite: 13]
                fin = row.get('financial') [cite: 13]
                row['financial'] = json.loads(fin) if isinstance(fin, str) and fin else (fin if isinstance(fin, dict) else {}) [cite: 13]
                processed_data.append(row) [cite: 13]
            except: continue [cite: 13]
        return processed_data [cite: 14]
    except: return [] [cite: 14]

def update_order_status(order_id, new_status, new_payment_status=None, paid_amount=0):
    client = get_gspread_client() [cite: 14]
    if not client: return False [cite: 14]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 14]
        ws = sh.worksheet("Orders") [cite: 14]
        cell = ws.find(order_id) [cite: 14]
        if not cell: return False [cite: 14]
        
        row_idx = cell.row [cite: 14]
        ws.update_cell(row_idx, 3, new_status) [cite: 15]
        if new_payment_status: ws.update_cell(row_idx, 4, new_payment_status) [cite: 15]
        
        if paid_amount > 0: [cite: 15]
            current_fin_str = ws.cell(row_idx, 7).value [cite: 15]
            try: fin = json.loads(current_fin_str) [cite: 15]
            except: fin = {} [cite: 15]
            fin['paid'] = float(fin.get('paid', 0)) + float(paid_amount) [cite: 15]
            fin['debt'] = float(fin.get('total', 0)) - fin['paid'] [cite: 16]
            ws.update_cell(row_idx, 7, json.dumps(fin, ensure_ascii=False)) [cite: 16]
            
        st.cache_data.clear() [cite: 16]
        return True [cite: 16]
    except: return False [cite: 16]

def update_commission_status(order_id, status_text):
    client = get_gspread_client() [cite: 16]
    if not client: return False [cite: 16]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 16]
        ws = sh.worksheet("Orders") [cite: 17]
        cell = ws.find(order_id) [cite: 17]
        if not cell: return False [cite: 17]
        
        row_idx = cell.row [cite: 17]
        old_fin_str = ws.cell(row_idx, 7).value [cite: 17]
        try: fin = json.loads(old_fin_str) [cite: 17]
        except: fin = {} [cite: 17]
        fin['commission_status'] = status_text [cite: 17]
        ws.update_cell(row_idx, 7, json.dumps(fin, ensure_ascii=False)) [cite: 17, 18]
        st.cache_data.clear() [cite: 18]
        return True [cite: 18]
    except: return False [cite: 18]

def delete_order(order_id):
    client = get_gspread_client() [cite: 18]
    if not client: return False [cite: 18]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 18]
        ws = sh.worksheet("Orders") [cite: 18]
        cell = ws.find(order_id) [cite: 18]
        if cell: [cite: 18]
            ws.delete_rows(cell.row) [cite: 18]
            st.cache_data.clear() [cite: 19]
            return True [cite: 19]
        return False [cite: 19]
    except: return False [cite: 19]

def edit_order_info(order_id, new_cust, new_total, new_items, new_profit, new_comm):
    client = get_gspread_client() [cite: 19]
    if not client: return False [cite: 19]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 19]
        ws = sh.worksheet("Orders") [cite: 19]
        cell = ws.find(order_id) [cite: 19]
        if not cell: return False [cite: 19]
        r = cell.row [cite: 20]
        
        ws.update_cell(r, 5, json.dumps(new_cust, ensure_ascii=False)) [cite: 20]
        ws.update_cell(r, 6, json.dumps(new_items, ensure_ascii=False)) [cite: 20]
        
        old_fin_str = ws.cell(r, 7).value [cite: 20]
        try: fin = json.loads(old_fin_str) [cite: 20]
        except: fin = {} [cite: 20]
        fin['total'] = new_total [cite: 20]
        fin['debt'] = new_total - float(fin.get('paid', 0)) [cite: 20, 21]
        fin['total_profit'] = new_profit [cite: 21]
        fin['total_comm'] = new_comm [cite: 21]
        ws.update_cell(r, 7, json.dumps(fin, ensure_ascii=False)) [cite: 21]
        
        save_customer_db(new_cust.get('name'), new_cust.get('phone'), new_cust.get('address')) [cite: 21]
        st.cache_data.clear() [cite: 21]
        return True [cite: 21]
    except: return False [cite: 21]

def add_new_order(order_data):
    client = get_gspread_client() [cite: 21]
    if not client: return False [cite: 21]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 22]
        try: ws = sh.worksheet("Orders") [cite: 22]
        except: 
            ws = sh.add_worksheet("Orders", 1000, 20) [cite: 22]
            ws.append_row(["order_id", "date", "status", "payment_status", "customer", "items", "financial"]) [cite: 22]
        
        row = [ [cite: 22]
            order_data.get('order_id'), order_data.get('date'), order_data.get('status'), order_data.get('payment_status'), [cite: 22]
            json.dumps(order_data.get('customer', {}), ensure_ascii=False), [cite: 23]
            json.dumps(order_data.get('items', []), ensure_ascii=False), [cite: 23]
            json.dumps(order_data.get('financial', {}), ensure_ascii=False) [cite: 23]
        ] [cite: 22]
        ws.append_row(row) [cite: 23]
        st.cache_data.clear() [cite: 23]
        return True [cite: 23]
    except: return False [cite: 23]

def save_cash_log(date, type_, amount, method, note):
    client = get_gspread_client() [cite: 23]
    if not client: return [cite: 23]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 24]
        try: ws = sh.worksheet("Cashbook") [cite: 24]
        except: 
            ws = sh.add_worksheet("Cashbook", 1000, 10) [cite: 24]
            ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"]) [cite: 24]
        if not ws.get_all_values(): ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"]) [cite: 24]
        ws.append_row([str(date), type_, amount, method, note]) [cite: 24]
        st.cache_data.clear() [cite: 24]
    except: pass [cite: 24]

def fetch_cashbook():
    client = get_gspread_client() [cite: 25]
    if not client: return [] [cite: 25]
    try:
        sh = client.open_by_url(SHEET_URL) [cite: 25]
        ws = sh.worksheet("Cashbook") [cite: 25]
        return ws.get_all_records() [cite: 25]
    except: return [] [cite: 25]

def gen_id():
    orders = fetch_all_orders() [cite: 25]
    year = datetime.now().strftime("%y") [cite: 25]
    count = 0 [cite: 25]
    for o in orders: [cite: 25]
        if str(o.get('order_id', '')).endswith(year): count += 1 [cite: 25]
    return f"{count+1:03d}/DH.{year}" [cite: 25]

# --- HÀM CHO TÍNH NĂNG KHÁCH THÊM (CẬP NHẬT MỚI) ---
def fetch_extra_customers():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("ExtraCustomers")
        except: return []
        return ws.get_all_records()
    except: return []

def save_extra_customer(id_, name, before_tax, actual, no_work, tax_rate, tax_pit, refund, status, date_str):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("ExtraCustomers")
        except:
            ws = sh.add_worksheet("ExtraCustomers", 1000, 10)
            ws.append_row(["id", "date", "name", "before_tax", "actual", "no_work", "tax_rate", "tax_pit", "refund", "status"])
        ws.append_row([str(id_), date_str, name, float(before_tax), float(actual), float(no_work), float(tax_rate), float(tax_pit), float(refund), status])
        st.cache_data.clear()
        return True
    except: return False

def update_extra_customer(id_, name, before_tax, actual, no_work, tax_rate, tax_pit, refund, status):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("ExtraCustomers")
        cell = ws.find(str(id_))
        if cell:
            r = cell.row
            ws.update_cell(r, 3, name)
            ws.update_cell(r, 4, float(before_tax))
            ws.update_cell(r, 5, float(actual))
            ws.update_cell(r, 6, float(no_work))
            ws.update_cell(r, 7, float(tax_rate))
            ws.update_cell(r, 8, float(tax_pit))
            ws.update_cell(r, 9, float(refund))
            ws.update_cell(r, 10, status)
            st.cache_data.clear()
            return True
        return False
    except: return False

def delete_extra_customer(id_):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("ExtraCustomers")
        cell = ws.find(str(id_))
        if cell:
            ws.delete_rows(cell.row)
            st.cache_data.clear()
            return True
        return False
    except: return False

# --- PDF GENERATOR ---
class PDFGen(FPDF):
    def header(self): pass [cite: 26]

def create_pdf(order, title):
    pdf = PDFGen() [cite: 26]
    pdf.add_page() [cite: 26]
    SAFE_MODE = False [cite: 26]
    if os.path.exists(FONT_FILENAME): [cite: 26]
        try:
            pdf.add_font('ArialLocal', '', FONT_FILENAME) [cite: 26]
            pdf.set_font('ArialLocal', '', 11) [cite: 26]
        except: SAFE_MODE = True [cite: 26]
    else: SAFE_MODE = True [cite: 26]
    if SAFE_MODE: pdf.set_font('Helvetica', '', 11) [cite: 26]

    def txt(text):
        if not text: return "" [cite: 27]
        text = str(text) [cite: 27]
        return remove_accents(text) if SAFE_MODE else text [cite: 27]

    if os.path.exists(HEADER_IMAGE): [cite: 27]
        try:
            pdf.image(HEADER_IMAGE, x=10, y=10, w=190) [cite: 27]
            pdf.set_y(pdf.get_y() + 35) [cite: 27]
        except: pass [cite: 27]
    else:
        pdf.set_font_size(14) [cite: 27]
        pdf.cell(0, 8, txt('CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT'), 0, 1, 'C') [cite: 28]
        pdf.set_font_size(10) [cite: 28]
        pdf.cell(0, 5, txt('Mã số thuế: 3603995632'), 0, 1, 'C') [cite: 28]
        pdf.cell(0, 5, txt('Địa chỉ: A1/204A, hẻm 244, đường Bùi Hữu Nghĩa, phường Biên Hòa, tỉnh Đồng Nai'), 0, 1, 'C') [cite: 28]
        pdf.cell(0, 5, txt('Điện thoại: 0251 777 6868       Email: anlocphat68.ltd@gmail.com'), 0, 1, 'C') [cite: 28]
        pdf.cell(0, 5, txt('Số tài khoản: 451557254 – Ngân hàng TMCP Việt Nam Thịnh Vượng - CN Đồng Nai'), 0, 1, 'C') [cite: 29]
        pdf.ln(2) [cite: 29]
    
    STAMP_FILE = 'con_dau.png' [cite: 29]
    if os.path.exists(STAMP_FILE): [cite: 29]
        try:
            pdf.image(STAMP_FILE, x=15, y=32, w=35) [cite: 30]
        except: [cite: 30]
            pass [cite: 30]
    pdf.set_font_size(16) [cite: 30]
    pdf.cell(0, 8, txt(title), new_x="LMARGIN", new_y="NEXT", align='C') [cite: 30]
    pdf.set_font_size(11) [cite: 30]
    
    oid = order.get('order_id', '') [cite: 30, 31]
    is_delivery = "GIAO HÀNG" in title.upper() [cite: 31]
    
    if is_delivery: [cite: 31]
        odate = datetime.now().strftime("%d/%m/%Y") [cite: 31]
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi.  Nay bàn giao các hàng hóa và dịch vụ như sau:" [cite: 31]
    else:
        raw_date = order.get('date', '') [cite: 31]
        try: odate = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y") [cite: 32]
        except: odate = raw_date [cite: 32]
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi. Xin trân trọng gửi tới Quý  khách hàng báo giá như sau:" [cite: 32]

    cust = order.get('customer', {}) [cite: 32]
    items = order.get('items', []) [cite: 32]
    
    pdf.cell(0, 6, txt(f"Mã số: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C') [cite: 32, 33]
    pdf.ln(1) [cite: 33]
    pdf.cell(0, 6, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT") [cite: 33]
    pdf.cell(0, 6, txt(f"Điện thoại: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT") [cite: 33]
    pdf.cell(0, 6, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT") [cite: 33]
    
    pdf.ln(2) [cite: 33]
    pdf.multi_cell(0, 5, txt(intro_text)) [cite: 33]
    pdf.ln(2) [cite: 33]
    
    pdf.set_fill_color(230, 230, 230) [cite: 33]
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1) [cite: 33]
    pdf.cell(75, 8, txt("Tên hàng / Quy cách"), 1, 0, 'C', 1) [cite: 33]
    pdf.cell(15, 8, txt("ĐVT"), 1, 0, 'C', 1) [cite: 33, 34]
    pdf.cell(15, 8, "SL", 1, 0, 'C', 1) [cite: 34]
    pdf.cell(35, 8, txt("Đơn giá"), 1, 0, 'C', 1) [cite: 34]
    pdf.cell(40, 8, txt("Thành tiền"), 1, 1, 'C', 1) [cite: 34]
    
    sum_items_total = 0 [cite: 34]
    total_vat = 0 [cite: 34]
    
    for i, item in enumerate(items): [cite: 34]
        try: 
            price = float(item.get('price', 0)) [cite: 35]
            qty = float(item.get('qty', 0)) [cite: 35]
            line_total = price * qty [cite: 35]
            vat_rate = float(item.get('vat_rate', 0)) [cite: 35]
            vat_val = line_total * (vat_rate / 100) [cite: 35]
        except: 
            line_total = 0; vat_val = 0 [cite: 35, 36]
            
        sum_items_total += line_total [cite: 36]
        total_vat += vat_val [cite: 36]
        
        start_y = pdf.get_y() [cite: 36]
        pdf.set_x(20)  [cite: 37]
        pdf.multi_cell(75, 8, txt(item.get('name', '')), 1, 'L') [cite: 37]
        end_y = pdf.get_y() [cite: 37]
        h = end_y - start_y  [cite: 37, 38]
        
        pdf.set_xy(10, start_y) [cite: 38]
        pdf.cell(10, h, str(i+1), 1, 0, 'C')  [cite: 38]
        pdf.set_xy(95, start_y)  [cite: 39]
        
        pdf.cell(15, h, txt(item.get('unit', '')), 1, 0, 'C') [cite: 39]
        pdf.cell(15, h, format_currency(qty), 1, 0, 'R') [cite: 39]
        pdf.cell(35, h, format_currency(price), 1, 0, 'R') [cite: 39]
        pdf.cell(40, h, format_currency(line_total), 1, 1, 'R') [cite: 39]
        pdf.set_y(end_y) [cite: 40]
    
    final_total = sum_items_total + total_vat [cite: 40]
    
    pdf.cell(150, 8, txt("Cộng tiền hàng:"), 1, 0, 'R') [cite: 40]
    pdf.cell(40, 8, format_currency(sum_items_total), 1, 1, 'R') [cite: 40]
    pdf.cell(150, 8, txt(f"Tiền VAT:"), 1, 0, 'R') [cite: 40]
    pdf.cell(40, 8, format_currency(total_vat), 1, 1, 'R') [cite: 40]
    pdf.cell(150, 8, txt("TỔNG CỘNG THANH TOÁN:"), 1, 0, 'R') [cite: 41]
    pdf.cell(40, 8, format_currency(final_total), 1, 1, 'R') [cite: 41]
    pdf.ln(5) [cite: 41]
    
    money_text = "" [cite: 41]
    if SAFE_MODE: money_text = f"Tong cong: {format_currency(final_total)} VND" [cite: 41]
    else:
        try: money_text = read_money_vietnamese(final_total) [cite: 41]
        except: money_text = f"{format_currency(final_total)} đồng." [cite: 41]
    pdf.multi_cell(0, 6, txt(f"Bằng chữ: {money_text}")) [cite: 42]
    pdf.ln(3) [cite: 42]

    pdf.set_x(10) [cite: 42]
    if is_delivery: [cite: 42]
        pdf.cell(95, 5, txt("NGƯỜI NHẬN"), 0, 0, 'C') [cite: 42]
        pdf.cell(95, 5, txt("NGƯỜI GIAO"), 0, 1, 'C') [cite: 42]
        pdf.ln(20)  [cite: 42]
    else:
        pdf.cell(0, 5, txt("NGƯỜI BÁO GIÁ"), 0, 1, 'R') [cite: 42]
        pdf.ln(20) [cite: 42]

    pdf.ln(2) [cite: 42]
    pdf.set_font_size(10) [cite: 42]
    pdf.set_x(10) [cite: 42]
    if is_delivery: [cite: 42]
        pdf.multi_cell(190, 5, txt("* Quý khách vui lòng kiểm tra và phản hồi ngay về tình trạng hàng hoá khi giao nhận!")) [cite: 43]
        pdf.set_x(10) [cite: 43]
        pdf.multi_cell(190, 5, txt("* Giao hàng miễn phí trong nội thành thành phố Biên Hoà với đơn hàng >1.000.000đ")) [cite: 43]
        pdf.set_x(10) [cite: 43]
        pdf.multi_cell(190, 5, txt("Rất mong được hợp tác với Quý khách hàng. Trân trọng!")) [cite: 43]
    else:
        pdf.cell(0, 5, txt("Lưu ý:"), 0, 1) [cite: 43, 44]
        pdf.set_x(10) [cite: 44]
        pdf.cell(0, 5, txt("- Giá trên đã bao gồm vận chuyển, giao hàng."), 0, 1) [cite: 44]
        pdf.set_x(10) [cite: 44]
        pdf.cell(0, 5, txt("- Thời gian hoàn thành, giao hàng: từ 03 - 05 ngày."), 0, 1) [cite: 44]
        pdf.set_x(10) [cite: 44]
        pdf.cell(0, 5, txt("- Báo giá này áp dụng trong vòng 30 ngày."), 0, 1) [cite: 44]
        pdf.ln(2) [cite: 45]
        pdf.set_x(10) [cite: 45]
        pdf.multi_cell(190, 5, txt("Rất mong nhận được sự hợp tác của Quý khách hàng! Trân trọng! ")) [cite: 45, 46]
    return bytes(pdf.output())

# --- LOGIN PAGE ---
def login_page():
    st.title("🔐 Đăng Nhập Hệ Thống")
    init_users() [cite: 46]
    with st.form("login_form"):
        username = st.text_input("Tên đăng nhập")
        password = st.text_input("Mật khẩu", type="password")
        if st.form_submit_button("Đăng nhập", type="primary"):
            user = check_login(username, password)
            if user:
                st.session_state.logged_in = True [cite: 47]
                st.session_state.user = user [cite: 47]
                st.session_state.role = user['role'] [cite: 47]
                st.success(f"Xin chào {username}!") [cite: 47]
                time.sleep(0.5) [cite: 47]
                st.rerun() [cite: 47]
            else: st.error("Sai tên đăng nhập hoặc mật khẩu!") [cite: 48]

# --- MAIN APP ---
def main_app():
    is_admin = st.session_state.role == 'admin' [cite: 48]
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user['username']}** ({st.session_state.role})") [cite: 48]
        if st.button("Đăng xuất"):
            st.session_state.logged_in = False [cite: 48]
            st.rerun() [cite: 48]
        with st.expander("🔑 Đổi mật khẩu"):
            new_p1 = st.text_input("Mật khẩu mới", type="password") [cite: 49]
            new_p2 = st.text_input("Nhập lại", type="password") [cite: 49]
            if st.button("Lưu mật khẩu"): [cite: 49]
                if new_p1 and new_p1 == new_p2: [cite: 49]
                    if change_password(st.session_state.user['username'], new_p1): [cite: 49]
                        st.success("Đổi thành công!") [cite: 50]
                    else: st.error("Lỗi hệ thống") [cite: 50]
                else: st.error("Mật khẩu không khớp") [cite: 50]

    st.title("Hệ Thống In Ấn An Lộc Phát")
    if "service_account" not in st.secrets: [cite: 50]
        st.error("Lỗi: Chưa cấu hình st.secrets") [cite: 50]
        st.stop() [cite: 50]

    menu = st.sidebar.radio("CHỨC NĂNG", [
        "1. Tạo Báo Giá", 
        "2. Quản Lý Đơn Hàng (Pipeline)", 
        "3. Khách Thêm Chiết Khấu", 
        "4. Sổ Quỹ", 
        "5. Dashboard & Báo Cáo"
    ])

    if 'cart' not in st.session_state: st.session_state.cart = [] [cite: 52]
    if 'last_order' not in st.session_state: st.session_state.last_order = None [cite: 52]

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá":
        st.header("📝 Tạo Báo Giá Mới") [cite: 53]
        if 'c_name' not in st.session_state: st.session_state.c_name = "" [cite: 53]
        if 'c_phone' not in st.session_state: st.session_state.c_phone = "" [cite: 53]
        if 'c_addr' not in st.session_state: st.session_state.c_addr = "" [cite: 53]

        customers = fetch_customers() [cite: 53]
        cust_options = [""] + [f"{c['phone']} - {c['name']}" for c in customers] [cite: 53]
        selected_cust = st.selectbox("🔍 Tìm khách cũ (SĐT - Tên):", cust_options) [cite: 53, 54]
        if selected_cust: [cite: 54]
            s_phone = selected_cust.split(" - ")[0] [cite: 54]
            for c in customers: [cite: 54]
                if str(c['phone']) == s_phone: [cite: 54]
                    st.session_state.c_name = c['name'] [cite: 54]
                    st.session_state.c_phone = str(c['phone']) [cite: 55]
                    st.session_state.c_addr = c['address'] [cite: 55]
                    break [cite: 55]
        
        c1, c2 = st.columns(2) [cite: 55]
        name = c1.text_input("Tên Khách Hàng", value=st.session_state.c_name) [cite: 55]
        phone = c2.text_input("Số Điện Thoại", value=st.session_state.c_phone) [cite: 55]
        addr = st.text_input("Địa Chỉ", value=st.session_state.c_addr) [cite: 56]
        
        user_name = st.session_state.user['username'] [cite: 56]
        staff_options = ["Nam", "Dương", "Vạn", "Khác"] [cite: 56]
        default_idx = staff_options.index(user_name) if user_name in staff_options else 0 [cite: 56]
        staff = st.selectbox("Nhân Viên Kinh Doanh", staff_options, index=default_idx, key="in_staff") [cite: 56]

        st.divider() [cite: 56]
        st.subheader("2. Chi tiết hàng hóa & Giá") [cite: 56, 57]
        with st.form("add_item_form", clear_on_submit=True): [cite: 57]
            col1, col2, col3 = st.columns([3, 1, 1]) [cite: 57]
            i_name = col1.text_input("Tên hàng / Quy cách") [cite: 57]
            i_unit = col2.text_input("ĐVT (Cái/M2)") [cite: 57]
            i_qty = col3.number_input("Số lượng", 1.0, step=1.0) [cite: 57]
            col4, col5, col6 = st.columns(3) [cite: 57]
            i_cost = col4.number_input("Giá Vốn (Giá gốc)", 0.0, step=1000.0) [cite: 58]
            i_price = col5.number_input("Giá Bán (Đơn giá)", 0.0, step=1000.0) [cite: 58]
            i_vat = col6.number_input("% VAT", 0.0, 100.0, 0.0, step=1.0) [cite: 58]
            if st.form_submit_button("➕ Thêm vào danh sách"): [cite: 58]
                if i_name: [cite: 58]
                    total_sell = i_qty * i_price [cite: 59]
                    total_cost = i_qty * i_cost [cite: 59]
                    vat_amt = total_sell * (i_vat / 100) [cite: 59]
                    profit = total_sell - total_cost [cite: 59]
            
                    comm_rate = 0.3 [cite: 60]
                    if staff in ["Nam", "Dương"]: comm_rate = 0.6 [cite: 60]
                    elif staff == "Vạn": comm_rate = 0.5 [cite: 60]
                    commission = profit * comm_rate if profit > 0 else 0 [cite: 60]
       
                    st.session_state.cart.append({ [cite: 61]
                        "name": i_name, "unit": i_unit, "qty": i_qty, "cost": i_cost, [cite: 61]
                        "price": i_price, "vat_rate": i_vat, "vat_amt": vat_amt, [cite: 61]
                        "profit": profit, "commission": commission, [cite: 61, 62]
                        "total_line": total_sell + vat_amt [cite: 62]
                    }) [cite: 61]
                    st.rerun() [cite: 62]
                else: st.error("Nhập tên hàng!") [cite: 62]

        if st.session_state.cart: [cite: 62]
            st.write("---") [cite: 63]
            view_df = pd.DataFrame(st.session_state.cart).copy() [cite: 63]
            for col in ['cost', 'price', 'vat_amt', 'profit', 'commission', 'total_line']: [cite: 63]
                view_df[col] = view_df[col].apply(format_currency) [cite: 63]
            view_df.columns = ["Tên hàng", "ĐVT", "SL", "Giá Vốn", "Giá Bán", "% VAT", "Tiền VAT", "Lợi Nhuận", "Hoa Hồng", "Giá Hoá Đơn"] [cite: 63]
            st.dataframe(view_df, use_container_width=True) [cite: 64]
            
            total_final = sum(i['total_line'] for i in st.session_state.cart) [cite: 64]
            total_profit = sum(i['profit'] for i in st.session_state.cart) [cite: 64]
            total_comm = sum(i['commission'] for i in st.session_state.cart) [cite: 64]
            
            m1, m2, m3 = st.columns(3) [cite: 64]
            m1.metric("TỔNG GIÁ TRỊ", format_currency(total_final)) [cite: 65]
            m2.metric("TỔNG LỢI NHUẬN", format_currency(total_profit)) [cite: 65]
            m3.metric("TỔNG HOA HỒNG", format_currency(total_comm)) [cite: 65]
            
            c_del, c_save = st.columns(2) [cite: 65]
            if c_del.button("🗑️ Xóa giỏ"): [cite: 65]
                st.session_state.cart = [] [cite: 66]
                st.rerun() [cite: 66]
            if c_save.button("💾 LƯU BÁO GIÁ", type="primary"): [cite: 66]
                if not name: st.error("Thiếu tên khách!") [cite: 66]
                else:
                    new_order = { [cite: 66]
                        "order_id": gen_id(),  [cite: 67]
                        "date": datetime.now().strftime("%Y-%m-%d"), [cite: 67]
                        "status": "Báo giá", "payment_status": "Chưa TT", [cite: 67]
                        "customer": {"name": name, "phone": phone, "address": addr}, [cite: 68]
                        "items": st.session_state.cart, [cite: 68]
                        "financial": { [cite: 68]
                            "total": total_final, "paid": 0, "debt": total_final, "staff": staff,  [cite: 68, 69]
                            "total_profit": total_profit, "total_comm": total_comm, "commission_status": "Chưa chi" [cite: 69]
                        } [cite: 68]
                    } [cite: 66]
                    if add_new_order(new_order): [cite: 69]
                        save_customer_db(name, phone, addr) [cite: 70]
                        st.session_state.last_order = new_order [cite: 70]
                        st.session_state.cart = [] [cite: 70]
                        st.rerun() [cite: 70]

        if st.session_state.last_order: [cite: 71]
            oid = st.session_state.last_order['order_id'] [cite: 71]
            st.success(f"✅ Đã tạo: {oid}") [cite: 71]
            pdf_bytes = create_pdf(st.session_state.last_order, "BÁO GIÁ") [cite: 71]
            st.download_button("🖨️ Tải PDF", pdf_bytes, f"BG_{oid}.pdf", "application/pdf", type="primary") [cite: 71]

    # --- TAB 2: QUẢN LÝ ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.header("🏭 Quy Trình Sản Xuất") [cite: 72]
        all_orders = fetch_all_orders() [cite: 72]
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"]) [cite: 72]
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            current_orders = [o for o in all_orders if o.get('status') == status_filter] [cite: 72]
            if not current_orders: [cite: 73]
                st.info("Không có đơn hàng nào trong mục này.") [cite: 73]
                return [cite: 73]

            table_data = [] [cite: 73]
            for o in current_orders: [cite: 73]
                cust = o.get('customer', {}) [cite: 73]
                fin = o.get('financial', {}) [cite: 74]
                items = o.get('items', []) [cite: 74]
                main_prod = items[0]['name'] if items else "---" [cite: 74]
                table_data.append({ [cite: 74]
                    "Mã ĐH": o.get('order_id'), "Ngày": o.get('date'), "Khách hàng": cust.get('name'), [cite: 74]
                    "Sản phẩm": main_prod, "Tổng tiền": format_currency(float(fin.get('total', 0))), [cite: 75]
                    "Còn nợ": format_currency(float(fin.get('debt', 0))), [cite: 75]
                    "Nhân viên": fin.get('staff', ''), [cite: 75]
                    "Hoa hồng": format_currency(float(fin.get('total_comm', 0))), [cite: 75]
                    "TT Thanh Toán": o.get('payment_status'), "TT Hoa Hồng": fin.get('commission_status', 'Chưa chi') [cite: 76]
                }) [cite: 74]
            
            event = st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun") [cite: 76]
            
            if event.selection.rows: [cite: 76]
                idx = event.selection.rows[0] [cite: 77]
                sel_order = current_orders[idx] [cite: 77]
                oid = sel_order.get('order_id') [cite: 77]
                st.divider() [cite: 77]
                st.subheader(f"🛠️ Xử lý đơn hàng: {oid}") [cite: 77]
               
                cust = sel_order.get('customer', {}) [cite: 78]
                items = sel_order.get('items', []) [cite: 78]
                fin = sel_order.get('financial', {}) [cite: 78]
                total, paid = float(fin.get('total', 0)), float(fin.get('paid', 0)) [cite: 78]
                debt = total - paid [cite: 78, 79]
                profit_val, comm_val = fin.get('total_profit', 0), fin.get('total_comm', 0) [cite: 79]
                comm_stat = fin.get('commission_status', 'Chưa chi') [cite: 79]

                col_d1, col_d2 = st.columns([2, 1]) [cite: 79]
                with col_d1: [cite: 79]
                    st.write(f"👤 {cust.get('name')} - {cust.get('phone')} | 📍 {cust.get('address')}") [cite: 80]
                    st.write("📦 **Chi tiết hàng hóa:**") [cite: 80]
                    df_items = pd.DataFrame(items) [cite: 80]
                    if not df_items.empty: [cite: 80]
                        cols = ["name", "unit", "qty", "price", "vat_rate", "total_line"] [cite: 80, 81]
                        if set(cols).issubset(df_items.columns): [cite: 81]
                            df_show = df_items[cols].copy() [cite: 81]
                            df_show.columns = ["Tên", "ĐVT", "SL", "Giá", "%VAT", "Thành tiền"] [cite: 81]
                            df_show['Giá'] = df_show['Giá'].apply(format_currency) [cite: 82]
                            df_show['Thành tiền'] = df_show['Thành tiền'].apply(format_currency) [cite: 82]
                            st.dataframe(df_show, hide_index=True, use_container_width=True) [cite: 82]

                with col_d2: [cite: 83]
                    st.info(f"💰 **TÀI CHÍNH**") [cite: 83]
                    st.write(f"Tổng đơn: **{format_currency(total)}**") [cite: 83]
                    st.write(f"Đã thanh toán: {format_currency(paid)}") [cite: 83]
                    st.error(f"CÒN NỢ: **{format_currency(debt)}**") [cite: 83]
                    if is_admin: [cite: 84]
                        with st.expander("👁️ Admin View", expanded=True): [cite: 84]
                            st.write(f"Lợi nhuận: {format_currency(profit_val)}") [cite: 84]
                            st.write(f"Hoa hồng ({fin.get('staff')}): {format_currency(comm_val)}") [cite: 85]
                            st.write(f"TT Hoa hồng: {comm_stat}") [cite: 85]
                            if comm_stat != "Đã chi" and st.button("Chi Hoa Hồng Ngay", key=f"comm_{oid}"): [cite: 85]
                                update_commission_status(oid, "Đã chi") [cite: 86]
                                st.rerun() [cite: 86]

                st.write("---") [cite: 86]
                c_act1, c_act2, c_act3, c_act4 = st.columns(4) [cite: 86]
                with c_act1: [cite: 86]
                    if pdf_type: [cite: 87]
                        pdf_data = create_pdf(sel_order, pdf_type) [cite: 87]
                        st.download_button(f"🖨️ In {pdf_type}", pdf_data, f"{oid}.pdf", "application/pdf", key=f"dl_{oid}", use_container_width=True) [cite: 87]
                with c_act2: [cite: 87]
                    pdf_gh = create_pdf(sel_order, "PHIẾU GIAO HÀNG, KIÊM PHIẾU THU") [cite: 88]
                    st.download_button("🚚 In Phiếu Giao", pdf_gh, f"GH_{oid}.pdf", "application/pdf", key=f"dl_gh_{oid}", use_container_width=True) [cite: 88]
                
                if is_admin: [cite: 88]
                    with c_act3: [cite: 88]
                        if next_status and st.button(f"{btn_text} ➡️", key=f"mv_{oid}", type="primary", use_container_width=True): [cite: 89]
                            update_order_status(oid, next_status) [cite: 89]
                            st.rerun() [cite: 89]
                    with c_act4: [cite: 90]
                        if st.button("🗑️ Xóa Đơn", key=f"del_{oid}", use_container_width=True): [cite: 90]
                            if delete_order(oid): st.success("Đã xóa!"); time.sleep(1); st.rerun() [cite: 90, 91]

                    st.write("---") [cite: 91]
                    st.write("💳 **THANH TOÁN & CẬP NHẬT (Admin Only)**") [cite: 91]
                    tab_pay, tab_edit = st.tabs(["💸 Thu Tiền", "✏️ Sửa Đơn Hàng"]) [cite: 91]
                    
                    with tab_pay: [cite: 92]
                        c_p1, c_p2 = st.columns(2) [cite: 92]
                        pay_method = c_p1.radio("Hình thức:", ["Một phần", "Toàn bộ"], horizontal=True, key=f"pm_{oid}") [cite: 92]
                        pay_val = float(debt) if pay_method == "Toàn bộ" else c_p2.number_input("Nhập số tiền thu:", 0.0, float(debt), float(debt), key=f"p_val_{oid}") [cite: 93]
                        pay_via = c_p2.selectbox("Hình thức thanh toán:", ["TM", "CK"], key=f"via_{oid}") [cite: 93]
                        st.write(f"👉 Xác nhận thu: **{format_currency(pay_val)}** ({pay_via})") [cite: 93]
                        if st.button("Xác nhận Thu Tiền", key=f"cf_pay_{oid}"): [cite: 94]
                            if pay_val > 0: [cite: 94]
                                new_st = status_filter [cite: 94]
                                pay_stat_new = "Đã TT" if (debt - pay_val) <= 0 else "Cọc/Còn nợ" [cite: 95]
                                if (debt - pay_val) <= 0 and status_filter == "Công nợ": new_st = "Hoàn thành" [cite: 95]
                                update_order_status(oid, new_st, pay_stat_new, pay_val) [cite: 95]
                                save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay_val, pay_via, f"Thu tiền đơn {oid}") [cite: 96]
                                st.success("Thành công!"); time.sleep(1); st.rerun() [cite: 96, 97]
                            else: st.warning("Số tiền phải > 0") [cite: 97]

                    with tab_edit: [cite: 97]
                        with st.form(f"form_edit_{oid}"): [cite: 97]
                            ce1, ce2 = st.columns(2) [cite: 98]
                            new_name = ce1.text_input("Tên Khách", value=cust.get('name')) [cite: 98]
                            new_phone = ce2.text_input("SĐT", value=cust.get('phone')) [cite: 98]
                            new_addr = st.text_input("Địa chỉ", value=cust.get('address')) [cite: 99]
                            st.write("📋 **Sửa Hàng Hóa & Giá:**") [cite: 99]
                            edited_df = st.data_editor(pd.DataFrame(items), num_rows="dynamic", key=f"editor_{oid}") [cite: 99]
                            if st.form_submit_button("Lưu Thay Đổi"): [cite: 100]
                                new_items = edited_df.to_dict('records') [cite: 100]
                                r_total, r_profit = 0, 0 [cite: 100]
                                for it in new_items: [cite: 101]
                                    q, p, v, c = float(it.get('qty',0)), float(it.get('price',0)), float(it.get('vat_rate',0)), float(it.get('cost',0)) [cite: 101]
                                    it['total_line'] = q*p + (q*p*(v/100)) [cite: 101]
                                    it['profit'] = (q*p) - (q*c) [cite: 102]
                                    r_total += it['total_line'] [cite: 102]
                                    r_profit += it['profit'] [cite: 103]
                                
                                c_staff = fin.get('staff', '') [cite: 103]
                                rate = 0.6 if c_staff in ["Nam", "Dương"] else (0.5 if c_staff == "Vạn" else 0.3) [cite: 104]
                                r_comm = r_profit * rate if r_profit > 0 else 0 [cite: 104]
                                
                                if edit_order_info(oid, {"name": new_name, "phone": new_phone, "address": new_addr}, r_total, new_items, r_profit, r_comm): [cite: 105]
                                    st.success("Cập nhật thành công!"); time.sleep(1); st.rerun() [cite: 105, 106]
                else: st.info("🔒 Bạn chỉ có quyền xem chi tiết.") [cite: 106]

        with tabs[0]: render_tab_content("Báo giá", "Thiết kế", "✅ Duyệt -> Thiết Kế", "BÁO GIÁ") [cite: 106]
        with tabs[1]: render_tab_content("Thiết kế", "Sản xuất", "✅ Duyệt TK -> Sản Xuất", None) [cite: 106]
        with tabs[2]: render_tab_content("Sản xuất", "Giao hàng", "✅ Xong -> Giao Hàng", None) [cite: 106]
        with tabs[3]: render_tab_content("Giao hàng", "Công nợ", "✅ Giao Xong -> Công Nợ", "PHIẾU GIAO HÀNG") [cite: 106, 107]
        with tabs[4]: render_tab_content("Công nợ", None, "", None) [cite: 107]
        with tabs[5]: render_tab_content("Hoàn thành", None, "", None) [cite: 107]

    # --- TAB 3: KHÁCH THÊM (CHỨC NĂNG MỚI THEO YÊU CẦU) ---
    elif menu == "3. Khách Thêm Chiết Khấu":
        st.header("👥 Quản Lý Khách Thêm (Gửi Giá Chiết Khấu)")
        
        # Tạo state lưu trữ id của dòng đang được chọn chỉnh sửa
        if 'editing_extra_id' not in st.session_state:
            st.session_state.editing_extra_id = None

        extra_list = fetch_extra_customers()
        df_extra = pd.DataFrame(extra_list)
        
        # Thiết lập giá trị mặc định cho Form nhập liệu
        default_name = ""
        default_before = 0.0
        default_actual = 0.0
        default_rate = 10.0
        form_mode = "Thêm Mới"

        # Nếu đang trong chế độ sửa, lấy dữ liệu cũ đắp vào Form
        if st.session_state.editing_extra_id and not df_extra.empty:
            match_row = df_extra[df_extra['id'].astype(str) == str(st.session_state.editing_extra_id)]
            if not match_row.empty:
                default_name = str(match_row.iloc[0]['name'])
                default_before = float(match_row.iloc[0]['before_tax'])
                default_actual = float(match_row.iloc[0]['actual'])
                default_rate = float(match_row.iloc[0]['tax_rate'])
                form_mode = f"Cập Nhật (Mã: {st.session_state.editing_extra_id})"

        st.subheader(f"📝 Form Giao Dịch Khách Thêm - Chế độ: {form_mode}")
        with st.form("extra_cust_form", clear_on_submit=False):
            ex_name = st.text_input("Tên khách hàng", value=default_name)
            col_f1, col_f2, col_f3 = st.columns(3)
            ex_before = col_f1.number_input("Số tiền trước thuế", min_value=0.0, value=default_before, step=10000.0)
            ex_actual = col_f2.number_input("Số tiền thực làm", min_value=0.0, value=default_actual, step=10000.0)
            ex_rate = col_f3.number_input("Thuế suất (%)", min_value=0.0, max_value=100.0, value=default_rate, step=1.0)
            
            # Tính toán logic các trường phụ thuộc theo công thức yêu cầu
            ex_no_work = ex_before - ex_actual
            ex_pit = (ex_rate / 100) * ex_no_work
            ex_refund = ex_before - ex_actual - ex_pit

            st.markdown(f"""
            * Số tiền không làm: **{format_currency(ex_no_work)}**
            * Thuế TNCN tương ứng: **{format_currency(ex_pit)}**
            * **Số tiền còn chuyển lại cho khách: {format_currency(ex_refund)}**
            """)

            cb1, cb2 = st.columns([5, 1])
            submit_btn = cb1.form_submit_button("💾 Lưu Thông Tin", type="primary")
            cancel_btn = cb2.form_submit_button("❌ Hủy")

            if cancel_btn:
                st.session_state.editing_extra_id = None
                st.rerun()

            if submit_btn:
                if not ex_name:
                    st.error("Vui lòng điền tên khách hàng.")
                elif ex_before < ex_actual:
                    st.error("Lỗi: Số tiền trước thuế không thể nhỏ hơn số tiền thực làm!")
                else:
                    if st.session_state.editing_extra_id is None:
                        # Thực hiện Thêm Mới
                        gen_extra_id = int(time.time())
                        if save_extra_customer(gen_extra_id, ex_name, ex_before, ex_actual, ex_no_work, ex_rate, ex_pit, ex_refund, "Chưa chi", datetime.now().strftime("%Y-%m-%d")):
                            st.success("Đã thêm giao dịch khách thêm mới thành công!")
                            time.sleep(0.5)
                            st.rerun()
                    else:
                        # Thực hiện cập nhật (Giữ nguyên trạng thái cũ của dòng)
                        old_status = str(match_row.iloc[0]['status'])
                        if update_extra_customer(st.session_state.editing_extra_id, ex_name, ex_before, ex_actual, ex_no_work, ex_rate, ex_pit, ex_refund, old_status):
                            st.success("Cập nhật thông tin thành công!")
                            st.session_state.editing_extra_id = None
                            time.sleep(0.5)
                            st.rerun()

        st.divider()
        st.subheader("📋 Danh Sách Khách Thêm Đang Quản Lý")
        if df_extra.empty:
            st.info("Hệ thống chưa ghi nhận dữ liệu giao dịch khách thêm nào.")
        else:
            df_display_extra = df_extra.copy()
            for col in ['before_tax', 'actual', 'no_work', 'tax_pit', 'refund']:
                df_display_extra[col] = df_display_extra[col].apply(format_currency)
            df_display_extra.columns = ["Mã ID", "Ngày tạo", "Khách hàng", "Trước thuế", "Thực làm", "Không làm", "Thuế suất (%)", "Thuế TNCN", "Còn chuyển lại", "Tình trạng"]
            
            selected_event = st.dataframe(df_display_extra, use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun")
            
            if selected_event.selection.rows:
                selected_row_idx = selected_event.selection.rows[0]
                selected_row_data = df_extra.iloc[selected_row_idx]
                curr_id = selected_row_data['id']
                curr_status = selected_row_data['status']
                
                st.markdown(f"⚙️ **Thao tác xử lý dòng lệnh khách thêm:** `{selected_row_data['name']}`")
                c_action1, c_action2, c_action3, _ = st.columns([1.5, 1, 1, 3])
                
                # 1. Nút duyệt chi chuyển trạng thái
                if curr_status == "Chưa chi":
                    if c_action1.button("✅ Duyệt Chi Khách này", key=f"btn_pay_ex_{curr_id}", type="primary"):
                        if update_extra_customer(curr_id, selected_row_data['name'], selected_row_data['before_tax'], selected_row_data['actual'], selected_row_data['no_work'], selected_row_data['tax_rate'], selected_row_data['tax_pit'], selected_row_data['refund'], "Đã chi"):
                            st.success("Hệ thống đã chuyển trạng thái sang [ĐÃ CHI]!")
                            time.sleep(0.5)
                            st.rerun()
                else:
                    c_action1.caption("✅ Đã hoàn tất chi")

                # 2. Nút chỉnh sửa
                if c_action2.button("✏️ Sửa dòng này", key=f"btn_edit_ex_{curr_id}"):
                    st.session_state.editing_extra_id = curr_id
                    st.rerun()

                # 3. Nút xóa (chỉ Admin được phép xóa)
                if is_admin:
                    if c_action3.button("🗑️ Xóa dòng này", key=f"btn_del_ex_{curr_id}"):
                        if delete_extra_customer(curr_id):
                            st.success("Đã xóa bỏ bản ghi!")
                            time.sleep(0.5)
                            st.rerun()
                else:
                    c_action3.caption("🔒 Xóa (Admin only)")

    # --- TAB 4: SỔ QUỸ (CHỈ TM) ---
    elif menu == "4. Sổ Quỹ":
        st.header("📊 Sổ Quỹ Tiền Mặt") [cite: 108]
        df = pd.DataFrame(fetch_cashbook()) [cite: 108]
        if df.empty: df = pd.DataFrame(columns=["Date", "Content", "Amount", "TM/CK", "Note"]) [cite: 108]
        if 'date' in df.columns: df.rename(columns={'date': 'Date', 'type': 'Content', 'amount': 'Amount', 'desc': 'Note'}, inplace=True) [cite: 108]
        for col in ["Date", "Content", "Amount", "TM/CK", "Note"]:  [cite: 108]
            if col not in df.columns: df[col] = "" [cite: 108]
        
        df['TM/CK'] = df['TM/CK'].replace("", "TM").fillna("TM") [cite: 108]
        df['TM/CK_Norm'] = df['TM/CK'].astype(str).str.strip().str.upper() [cite: 108]
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0) [cite: 108]
        df_tm = df[df['TM/CK_Norm'] == 'TM'].copy() [cite: 108, 109]

        if not df_tm.empty: [cite: 109]
            total_thu = df_tm[df_tm['Content'] == 'Thu']['Amount'].sum() [cite: 109]
            total_chi = df_tm[df_tm['Content'] == 'Chi']['Amount'].sum() [cite: 109]
            c1, c2, c3 = st.columns(3) [cite: 109]
            c1.metric("Tổng Thu (TM)", format_currency(total_thu)) [cite: 109]
            c2.metric("Tổng Chi (TM)", format_currency(total_chi)) [cite: 109]
            c3.metric("Tồn Quỹ Tiền Mặt", format_currency(total_thu - total_chi)) [cite: 110]
            st.divider() [cite: 110]
            df_tm['Thu'] = df_tm.apply(lambda x: x['Amount'] if x['Content'] == 'Thu' else 0, axis=1) [cite: 110]
            df_tm['Chi'] = df_tm.apply(lambda x: x['Amount'] if x['Content'] == 'Chi' else 0, axis=1) [cite: 110]
            df_display = df_tm[['Date', 'Thu', 'Chi', 'Note']].copy() [cite: 110]
            df_display['Thu'] = df_display['Thu'].apply(lambda x: format_currency(x) if x > 0 else "") [cite: 110, 111]
            df_display['Chi'] = df_display['Chi'].apply(lambda x: format_currency(x) if x > 0 else "") [cite: 111]
            df_display.columns = ["Ngày tháng", "Thu", "Chi", "Nội dung/Ghi chú"] [cite: 111]
            st.dataframe(df_display, use_container_width=True, hide_index=True) [cite: 111]
        else:
            st.info("Chưa có giao dịch Tiền mặt nào.") [cite: 111]

        if is_admin: [cite: 111]
            st.write("---") [cite: 112]
            st.subheader("📝 Ghi Sổ Tiền Mặt") [cite: 112]
            with st.form("cash_entry"): [cite: 112]
                c1, c2 = st.columns(2) [cite: 112]
                type_option = c1.radio("Loại", ["Thu", "Chi"], horizontal=True) [cite: 112]
                st.caption("Hình thức: Tiền Mặt (TM)") [cite: 112]
                d = c2.date_input("Ngày", value=datetime.now()) [cite: 113]
                c3, c4 = st.columns(2) [cite: 113]
                amount = c3.number_input("Số tiền", 0, step=10000) [cite: 113]
                note = c4.text_input("Nội dung / Ghi chú") [cite: 113]
                if st.form_submit_button("💾 Lưu Sổ Quỹ"): [cite: 113]
                    if amount > 0: [cite: 114]
                        save_cash_log(d, type_option, amount, "TM", note) [cite: 114]
                        st.success("Đã lưu!"); time.sleep(1); st.rerun() [cite: 114, 115]
                    else: st.warning("Nhập số tiền > 0") [cite: 115]
        else: st.warning("🔒 Chỉ Admin được ghi sổ.") [cite: 115]

    # --- TAB 5: DASHBOARD & BÁO CÁO ---
    elif menu == "5. Dashboard & Báo Cáo":
        st.header("📈 Dashboard & Báo Cáo Quản Trị") [cite: 116]
        
        orders = fetch_all_orders() [cite: 116]
        cashbook = fetch_cashbook() [cite: 116]
        extra_customers = fetch_extra_customers()
        
        df_orders = pd.DataFrame(orders) [cite: 116]
        df_cash = pd.DataFrame(cashbook) [cite: 116]
        df_ex = pd.DataFrame(extra_customers)
        
        if df_orders.empty: [cite: 116]
            st.info("Chưa có dữ liệu đơn hàng.") [cite: 116]
        else:
            df_orders['total_revenue'] = df_orders['financial'].apply(lambda x: float(x.get('total', 0))) [cite: 117]
            df_orders['total_profit'] = df_orders['financial'].apply(lambda x: float(x.get('total_profit', 0))) [cite: 117]
            df_orders['total_comm'] = df_orders['financial'].apply(lambda x: float(x.get('total_comm', 0))) [cite: 117]
            df_orders['staff'] = df_orders['financial'].apply(lambda x: x.get('staff', 'Unknown')) [cite: 118]
            df_orders['cust_name'] = df_orders['customer'].apply(lambda x: x.get('name', 'Unknown')) [cite: 118]
            df_orders['comm_status'] = df_orders['financial'].apply(lambda x: x.get('commission_status', 'Chưa chi')) [cite: 118]
            
            # Khởi tạo tabs gồm báo cáo khách thêm yêu cầu mới
            t1, t2, t3, t4, t5, t6 = st.tabs(["1. Tổng Quan", "2. Báo Cáo Lãi/Lỗ (P&L)", "3. Phân Tích Doanh Thu", "4. Công Nợ", "5. Hoa Hồng", "6. Báo Cáo Khách Thêm"]) [cite: 118, 119, 120]
            
            # 1. TỔNG QUAN
            with t1:
                st.subheader("Trạng Thái Đơn Hàng") [cite: 120]
                status_counts = df_orders['status'].value_counts().reset_index() [cite: 120]
                status_counts.columns = ['Status', 'Count'] [cite: 120]
                 
                fig = px.pie(status_counts, values='Count', names='Status', title='Tỷ lệ đơn hàng theo trạng thái', hole=0.4) [cite: 121]
                st.plotly_chart(fig, use_container_width=True) [cite: 121]
                
                k1, k2, k3 = st.columns(3) [cite: 122]
                k1.metric("Tổng đơn hàng", len(df_orders)) [cite: 122]
                k2.metric("Đang sản xuất", len(df_orders[df_orders['status'] == 'Sản xuất'])) [cite: 122]
                k3.metric("Hoàn thành", len(df_orders[df_orders['status'] == 'Hoàn thành'])) [cite: 122]

            # 2. P&L REPORT
            with t2:
                if is_admin: [cite: 123]
                    st.subheader("Báo Cáo Kết Quả Kinh Doanh (Ước tính)") [cite: 123]
                    revenue = df_orders['total_revenue'].sum() [cite: 124]
                    
                    total_cogs = 0 [cite: 125]
                    for o in orders: [cite: 125]
                        items = o.get('items', []) [cite: 125]
                        for i in items: [cite: 126]
                            try: [cite: 126]
                                total_cogs += float(i.get('qty', 0)) * float(i.get('cost', 0)) [cite: 126]
                            except: pass [cite: 127]
                            
                    gross_profit = revenue - total_cogs [cite: 127]
                
                    total_expenses = 0 [cite: 128]
                    if not df_cash.empty: [cite: 128]
                        if 'amount' in df_cash.columns and 'type' in df_cash.columns: [cite: 129]
                             df_cash['amt'] = pd.to_numeric(df_cash['amount'], errors='coerce').fillna(0) [cite: 129]
                             total_expenses = df_cash[df_cash['type'] == 'Chi']['amt'].sum() [cite: 129, 130]
                    
                    net_profit = gross_profit - total_expenses [cite: 130]
                    
                    pl_data = { [cite: 131]
                        "Hạng mục": ["1. Doanh thu bán hàng", "2. Giá vốn hàng bán (COGS)", "3. Lợi nhuận gộp (1-2)", "4. Chi phí vận hành (Sổ quỹ)", "5. Lợi nhuận ròng (3-4)"], [cite: 131, 132, 133]
                        "Giá trị": [revenue, total_cogs, gross_profit, total_expenses, net_profit] [cite: 133]
                    } [cite: 131]
                    df_pl = pd.DataFrame(pl_data) [cite: 133]
                    df_pl['Giá trị'] = df_pl['Giá trị'].apply(format_currency) [cite: 134]
                    st.table(df_pl) [cite: 134]
                else:
                    st.warning("🔒 Chỉ Admin mới được xem báo cáo Lãi/Lỗ.") [cite: 134]

            # 3. PHÂN TÍCH DOANH THU
            with t3: [cite: 134, 135]
                st.subheader("Phân Tích Doanh Thu") [cite: 135]
                st.write("###### Theo Nhân Viên") [cite: 135]
                staff_perf = df_orders.groupby('staff')['total_revenue'].sum().reset_index().sort_values('total_revenue', ascending=False) [cite: 135]
                fig_staff = px.bar(staff_perf, x='staff', y='total_revenue', labels={'total_revenue': 'Doanh thu', 'staff': 'Nhân viên'}) [cite: 136]
                st.plotly_chart(fig_staff, use_container_width=True) [cite: 136]
                
                st.write("###### Top 10 Khách Hàng") [cite: 136]
                cust_perf = df_orders.groupby('cust_name')['total_revenue'].sum().reset_index().sort_values('total_revenue', ascending=False).head(10) [cite: 137]
                st.dataframe(cust_perf.style.format({"total_revenue": "{:,.0f}"}), use_container_width=True) [cite: 137]

                st.write("###### Top Sản Phẩm Bán Chạy") [cite: 137]
                all_items = [] [cite: 137]
                for o in orders: [cite: 138]
                    for i in o.get('items', []): [cite: 138]
                        all_items.append({"Product": i.get('name'), "Revenue": float(i.get('total_line', 0))}) [cite: 138]
                
                if all_items: [cite: 138]
                    df_products = pd.DataFrame(all_items) [cite: 139]
                    prod_perf = df_products.groupby('Product')['Revenue'].sum().reset_index().sort_values('Revenue', ascending=False).head(10) [cite: 139]
                    st.bar_chart(prod_perf.set_index('Product')) [cite: 139]

            # 4. CÔNG NỢ
            with t4: [cite: 139]
                st.subheader("Danh Sách Khách Nợ") [cite: 140]
                df_orders['debt'] = df_orders['financial'].apply(lambda x: float(x.get('debt', 0))) [cite: 140]
                debtors = df_orders[df_orders['debt'] > 0][['order_id', 'date', 'cust_name', 'total_revenue', 'debt']].copy() [cite: 140]
                
                if not debtors.empty: [cite: 141]
                    st.metric("Tổng Công Nợ Phải Thu", format_currency(debtors['debt'].sum())) [cite: 141]
                    debtors.columns = ["Mã ĐH", "Ngày", "Khách hàng", "Tổng đơn", "Còn nợ"] [cite: 141]
                    debtors['Tổng đơn'] = debtors['Tổng đơn'].apply(format_currency) [cite: 142]
                    debtors['Còn nợ'] = debtors['Còn nợ'].apply(format_currency) [cite: 142]
                    st.dataframe(debtors, use_container_width=True) [cite: 142]
                else:
                    st.success("Tuyệt vời! Không có công nợ.") [cite: 142, 143]

            # 5. HOA HỒNG
            with t5: [cite: 143]
                st.subheader("Theo Dõi Hoa Hồng Nhân Viên") [cite: 143]
                comm_summary = df_orders.groupby(['staff', 'comm_status'])['total_comm'].sum().unstack(fill_value=0).reset_index() [cite: 144]
                
                if 'Chưa chi' not in comm_summary.columns: comm_summary['Chưa chi'] = 0.0 [cite: 144]
                if 'Đã chi' not in comm_summary.columns: comm_summary['Đã chi'] = 0.0 [cite: 144]
                 
                comm_summary['Tổng hoa hồng'] = comm_summary['Chưa chi'] + comm_summary['Đã chi'] [cite: 145]
                
                st.dataframe( [cite: 145]
                    comm_summary, [cite: 146]
                    column_config={ [cite: 146]
                        "staff": "Nhân viên", [cite: 146]
                        "Chưa chi": st.column_config.NumberColumn("Chưa thanh toán", format="%.0f đ"), [cite: 146]
                        "Đã chi": st.column_config.NumberColumn("Đã thanh toán", format="%.0f đ"), [cite: 147]
                        "Tổng hoa hồng": st.column_config.NumberColumn("Tổng cộng", format="%.0f đ"), [cite: 147]
                    }, [cite: 146]
                    use_container_width=True [cite: 147]
                ) [cite: 145]
                 
                m1, m2, m3 = st.columns(3) [cite: 148]
                m1.metric("Tổng Hoa Hồng", format_currency(df_orders['total_comm'].sum())) [cite: 148]
                total_paid = df_orders[df_orders['comm_status'] == 'Đã chi']['total_comm'].sum() [cite: 149]
                total_pending = df_orders[df_orders['comm_status'] != 'Đã chi']['total_comm'].sum() [cite: 149]
                m2.metric("Đã Thanh Toán", format_currency(total_paid)) [cite: 149]
                m3.metric("Chưa Thanh Toán", format_currency(total_pending)) [cite: 149]

            # 6. BÁO CÁO KHÁCH THÊM (YÊU CẦU MỚI)
            with t6:
                st.subheader("Báo Cáo Khách Thêm Chưa Chi Trả")
                if df_ex.empty:
                    st.info("Chưa ghi nhận dữ liệu Khách thêm.")
                else:
                    # Lọc danh sách những người ở trạng thái 'Chưa chi' theo yêu cầu số 3
                    df_unpaid = df_ex[df_ex['status'] == "Chưa chi"].copy()
                    if df_unpaid.empty:
                        st.success("🎉 Tuyệt vời! Hệ thống không có khách thêm nào chưa chi.")
                    else:
                        st.metric("Tổng Số Tiền Còn Phải Chuyển Lại", format_currency(df_unpaid['refund'].sum()))
                        
                        # Format hiển thị
                        df_report = df_unpaid[['date', 'name', 'refund']].copy()
                        df_report['refund'] = df_report['refund'].apply(format_currency)
                        df_report.columns = ["Ngày tạo", "Tên Khách Hàng", "Số Tiền Còn Chuyển Lại"]
                        st.dataframe(df_report, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    # --- ĐOẠN ĐÃ FIX LỖI KEYERROR: 'USERNAME' ---
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # CHỈ khởi tạo dữ liệu rỗng nếu chưa từng đăng nhập.
    # Không để ghi đè dữ liệu rỗng lên tài khoản đã đăng nhập mỗi lần reload trang!
    if not st.session_state.logged_in:
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
