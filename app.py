import streamlit as st
import pandas as pd
import json
import time
import os
import traceback # Thư viện bắt lỗi hệ thống
import unicodedata
from datetime import datetime
from fpdf import FPDF
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials

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
    try: return "{:,.0f}".format(float(value))
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

def edit_order_info(order_id, new_cust, new_total, new_items):
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
        ws.update_cell(r, 7, json.dumps(fin, ensure_ascii=False))
        
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

# --- PDF GENERATOR (ĐÃ SỬA LỖI FONT STYLE) ---
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

    # --- HÌNH TIÊU ĐỀ ---
    if os.path.exists(HEADER_IMAGE):
        try:
            pdf.image(HEADER_IMAGE, x=10, y=10, w=190)
            pdf.set_y(pdf.get_y() + 40)
        except: pass
    else:
        pdf.set_font_size(14)
        pdf.cell(0, 10, txt('CÔNG TY IN ẤN AN LỘC PHÁT'), new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(5)

    # --- TIÊU ĐỀ PHIẾU ---
    pdf.set_font_size(16)
    # KHÔNG DÙNG style='B' ở đây nữa để tránh lỗi
    pdf.cell(0, 10, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font_size(11)
    
    oid = order.get('order_id', '')
    if "GIAO HÀNG" in title.upper():
        odate = datetime.now().strftime("%d/%m/%Y")
    else:
        raw_date = order.get('date', '')
        try: odate = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except: odate = raw_date

    cust = order.get('customer', {})
    items = order.get('items', [])
    fin = order.get('financial', {})
    
    pdf.cell(0, 8, txt(f"Mã số: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    pdf.cell(0, 7, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"Điện thoại: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Header Bảng
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(75, 8, txt("Tên hàng / Quy cách"), 1, 0, 'C', 1)
    pdf.cell(15, 8, txt("ĐVT"), 1, 0, 'C', 1)
    pdf.cell(15, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(35, 8, txt("Đơn giá"), 1, 0, 'C', 1)
    pdf.cell(40, 8, txt("Thành tiền"), 1, 1, 'C', 1)
    pdf.ln(8)
    
    sum_items_total = 0
    total_vat = 0
    
    for i, item in enumerate(items):
        try: 
            price = float(item.get('price', 0))
            qty = float(item.get('qty', 0))
            line_total = price * qty
            vat_rate = float(item.get('vat_rate', 0))
            vat_val = line_total * (vat_rate / 100)
        except: line_total = 0; vat_val = 0
        
        sum_items_total += line_total
        total_vat += vat_val
        
        pdf.cell(10, 8, str(i+1), 1, 0, 'C')
        pdf.cell(75, 8, txt(item.get('name', '')), 1, 0)
        pdf.cell(15, 8, txt(item.get('unit', '')), 1, 0, 'C')
        pdf.cell(15, 8, txt(str(item.get('qty', 0))), 1, 0, 'C')
        pdf.cell(35, 8, format_currency(price), 1, 0, 'R')
        pdf.cell(40, 8, format_currency(line_total), 1, 1, 'R')
        pdf.ln(8)
    
    final_total = sum_items_total + total_vat
    
    pdf.cell(150, 8, txt("Cộng tiền hàng:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(sum_items_total), 1, 1, 'R')
    pdf.ln(8)
    
    pdf.cell(150, 8, txt(f"Tiền VAT:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total_vat), 1, 1, 'R')
    pdf.ln(8)
    
    # KHÔNG DÙNG style='B' - Chỉ in thường
    pdf.cell(150, 8, txt("TỔNG CỘNG THANH TOÁN:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(final_total), 1, 1, 'R')
    pdf.ln(10)
    
    money_text = ""
    if SAFE_MODE: money_text = f"Tong cong: {format_currency(final_total)} VND"
    else:
        try: money_text = read_money_vietnamese(final_total)
        except: money_text = f"{format_currency(final_total)} đồng."
    pdf.multi_cell(0, 8, txt(f"Bằng chữ: {money_text}"))
    
    return bytes(pdf.output())

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Hệ Thống In Ấn", layout="wide")
    
    # Kiểm tra cấu hình secrets ngay khi mở app
    if "service_account" not in st.secrets:
        st.error("⚠️ Lỗi cấu hình: Chưa tìm thấy `st.secrets`. Vui lòng cấu hình kết nối Google Sheets.")
        st.stop()

    menu = st.sidebar.radio("CHỨC NĂNG", ["1. Tạo Báo Giá", "2. Quản Lý Đơn Hàng (Pipeline)", "3. Sổ Quỹ & Báo Cáo"])

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'last_order' not in st.session_state: st.session_state.last_order = None

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên Khách Hàng", key="in_name")
        phone = c2.text_input("Số Điện Thoại", key="in_phone")
        addr = st.text_input("Địa Chỉ", key="in_addr")
        staff = st.selectbox("Nhân Viên Kinh Doanh", ["Nam", "Dương", "Vạn", "Khác"], key="in_staff")

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
            cart_df = pd.DataFrame(st.session_state.cart)
            view_df = cart_df.copy()
            for col in ['cost', 'price', 'vat_amt', 'profit', 'commission', 'total_line']:
                view_df[col] = view_df[col].apply(format_currency)
                
            view_df.columns = ["Tên hàng", "ĐVT", "SL", "Giá Vốn", "Giá Bán", "% VAT", "Tiền VAT", "Lợi Nhuận", "Hoa Hồng", "Giá Hoá Đơn"]
            st.dataframe(view_df, use_container_width=True)
            
            total_final = sum(i['total_line'] for i in st.session_state.cart)
            total_profit = sum(i['profit'] for i in st.session_state.cart)
            total_comm = sum(i['commission'] for i in st.session_state.cart)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("TỔNG GIÁ TRỊ (Gồm VAT)", format_currency(total_final))
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
        st.title("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            current_orders = [o for o in all_orders if o.get('status') == status_filter]
