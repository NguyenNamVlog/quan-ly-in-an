import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime
from fpdf import FPDF
from docxtpl import DocxTemplate
import plotly.express as px
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials

# --- CẤU HÌNH ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit" # <--- THAY LINK CỦA BẠN VÀO ĐÂY
TEMPLATE_CONTRACT = 'Hop dong .docx' 
FONT_PATH = 'Arial.ttf'

# --- HÀM HỖ TRỢ ---
def format_currency(value):
    if value is None: return "0"
    return "{:,.0f}".format(float(value))

def read_money_vietnamese(amount):
    try:
        return num2words(amount, lang='vi').capitalize() + " đồng chẵn."
    except:
        return "..................... đồng."

# --- KẾT NỐI GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets:
            st.error("Chưa cấu hình Secrets!")
            return None
        
        creds_dict = dict(st.secrets["service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
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
                row['customer'] = json.loads(row['customer']) if isinstance(row['customer'], str) else row['customer']
                row['items'] = json.loads(row['items']) if isinstance(row['items'], str) else row['items']
                row['financial'] = json.loads(row['financial']) if isinstance(row['financial'], str) else row['financial']
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
        
        if new_payment_status:
            ws.update_cell(row_idx, 4, new_payment_status)
            
        if paid_amount > 0:
            current_fin_str = ws.cell(row_idx, 7).value
            current_fin = json.loads(current_fin_str)
            current_fin['paid'] = float(current_fin.get('paid', 0)) + float(paid_amount)
            current_fin['debt'] = float(current_fin.get('total', 0)) - current_fin['paid']
            ws.update_cell(row_idx, 7, json.dumps(current_fin, ensure_ascii=False))
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi update: {e}")
        return False

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
            order_data['order_id'], order_data['date'], order_data['status'], order_data['payment_status'],
            json.dumps(order_data['customer'], ensure_ascii=False),
            json.dumps(order_data['items'], ensure_ascii=False),
            json.dumps(order_data['financial'], ensure_ascii=False)
        ]
        ws.append_row(row)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu mới: {e}")
        return False

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
    count = len([o for o in orders if str(o.get('order_id')).endswith(year)])
    return f"{count+1:03d}/DH.{year}"

# --- PDF GENERATOR ---
class PDFGen(FPDF):
    def header(self):
        try:
            self.add_font('Arial', '', FONT_PATH, uni=True)
            self.set_font('Arial', '', 14)
            self.cell(0, 10, 'CÔNG TY IN ẤN AN LỘC PHÁT', 0, 1, 'C')
            self.ln(10)
        except: pass

def create_pdf(order, title):
    pdf = PDFGen()
    pdf.add_page()
    try: pdf.add_font('Arial', '', FONT_PATH, uni=True); pdf.set_font('Arial', '', 11)
    except: pdf.set_font('Arial', '', 11)
    
    pdf.set_font_size(16)
    pdf.cell(0, 10, title, 0, 1, 'C')
    pdf.set_font_size(11)
    pdf.cell(0, 8, f"Mã: {order['order_id']} | Ngày: {order['date']}", 0, 1, 'C')
    pdf.ln(5)
    
    cust = order['customer']
    pdf.cell(0, 7, f"Khách hàng: {cust.get('name')}", 0, 1)
    pdf.cell(0, 7, f"SĐT: {cust.get('phone')}", 0, 1)
    pdf.cell(0, 7, f"Địa chỉ: {cust.get('address')}", 0, 1)
    pdf.ln(5)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(80, 8, "Tên hàng", 1, 0, 'C', 1)
    pdf.cell(20, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Đơn giá", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Thành tiền", 1, 1, 'C', 1)
    
    total = 0
    for i, item in enumerate(order['items']):
        total += item['total']
        pdf.cell(10, 8, str(i+1), 1, 0, 'C')
        pdf.cell(80, 8, str(item['name']), 1, 0)
        pdf.cell(20, 8, str(item['qty']), 1, 0, 'C')
        pdf.cell(30, 8, format_currency(item['price']), 1, 0, 'R')
        pdf.cell(40, 8, format_currency(item['total']), 1, 1, 'R')
    
    pdf.cell(140, 8, "TỔNG CỘNG:", 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total), 1, 1, 'R')
    pdf.ln(10)
    pdf.multi_cell(0, 8, f"Bằng chữ: {read_money_vietnamese(total)}")
    return bytes(pdf.output())

# --- UI MAIN ---
def main():
    st.set_page_config(page_title="Hệ Thống In Ấn", layout="wide")
    
    menu = st.sidebar.radio("CHỨC NĂNG", [
        "1. Tạo Báo Giá", 
        "2. Quản Lý Đơn Hàng (Pipeline)", 
        "3. Sổ Quỹ & Báo Cáo"
    ])

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        with st.form("create_order"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Tên Khách Hàng")
            phone = c2.text_input("Số Điện Thoại")
            addr = st.text_input("Địa Chỉ")
            staff = st.selectbox("Nhân Viên Kinh Doanh", ["Nam", "Dương", "Thảo", "Khác"])
            st.divider()
            st.write("Sản Phẩm:")
            c3, c4, c5 = st.columns([3, 1, 2])
            i_name = c3.text_input("Tên hàng / Quy cách")
            i_qty = c4.number_input("Số lượng", 1, step=1)
            i_price = c5.number_input("Đơn giá", 0, step=1000)
            total = i_qty * i_price
            st.info(f"💰 Thành tiền: {format_currency(total)}")
            
            if st.form_submit_button("Lưu & Tạo Báo Giá"):
                if not name: st.error("Chưa nhập tên khách!")
                else:
                    new_order = {
                        "order_id": gen_id(),
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá",
                        "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": [{"name": i_name, "qty": i_qty, "price": i_price, "total": total}],
                        "financial": {"total": total, "paid": 0, "debt": total, "staff": staff}
                    }
                    if add_new_order(new_order):
                        st.success(f"Đã tạo đơn {new_order['order_id']} thành công!")

    # --- TAB 2: QUẢN LÝ PIPELINE ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.title("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        with tabs[0]: # Báo Giá
            orders = [o for o in all_orders if o['status'] == 'Báo giá']
            for o in orders:
                with st.expander(f"📄 {o['order_id']} | {o['customer']['name']} | {format_currency(o['financial']['total'])}"):
                    c1, c2 = st.columns(2)
                    pdf = create_pdf(o, "BÁO GIÁ")
                    if pdf: c1.download_button("🖨️ Tải PDF Báo Giá", pdf, f"BG_{o['order_id']}.pdf")
                    if c2.button("✅ Duyệt -> Thiết Kế", key=f"app_{o['order_id']}"):
                        update_order_status(o['order_id'], "Thiết kế")
                        st.rerun()

        with tabs[1]: # Thiết Kế
            orders = [o for o in all_orders if o['status'] == 'Thiết kế']
            for o in orders:
                with st.expander(f"🎨 {o['order_id']} | {o['customer']['name']}"):
                    if st.button("✅ Duyệt TK -> Sản Xuất", key=f"des_{o['order_id']}"):
                        update_order_status(o['order_id'], "Sản xuất")
                        st.rerun()

        with tabs[2]: # Sản Xuất
            orders = [o for o in all_orders if o['status'] == 'Sản xuất']
            for o in orders:
                with st.expander(f"⚙️ {o['order_id']} | {o['customer']['name']}"):
                    if st.button("✅ Xong -> Giao Hàng", key=f"prod_{o['order_id']}"):
                        update_order_status(o['order_id'], "Giao hàng")
                        st.rerun()

        with tabs[3]: # Giao Hàng
            orders = [o for o in all_orders if o['status'] == 'Giao hàng']
            for o in orders:
                with st.expander(f"🚚 {o['order_id']} | {o['customer']['name']}"):
                    c1, c2 = st.columns(2)
                    pdf_gh = create_pdf(o, "PHIẾU GIAO HÀNG")
