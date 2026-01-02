import streamlit as st
import pandas as pd
import json
import time
import os
import requests
from datetime import datetime
from fpdf import FPDF
from docxtpl import DocxTemplate
import plotly.express as px
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials

# --- CẤU HÌNH HỆ THỐNG ---
# Đã cập nhật Link Google Sheet của bạn
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit"
TEMPLATE_CONTRACT = 'Hop dong .docx' 
FONT_FILENAME = 'Roboto-Regular.ttf'

# --- HÀM HỖ TRỢ: TẢI FONT TỰ ĐỘNG (Tránh lỗi Unicode) ---
def check_and_download_font():
    if not os.path.exists(FONT_FILENAME):
        try:
            url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf"
            response = requests.get(url)
            with open(FONT_FILENAME, 'wb') as f:
                f.write(response.content)
        except: pass

# --- HÀM HỖ TRỢ TIỀN TỆ ---
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
            st.error("Chưa cấu hình Secrets!")
            return None
        
        creds_dict = dict(st.secrets["service_account"])
        # Tự động sửa lỗi xuống dòng trong Private Key
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
        return None

# --- XỬ LÝ DỮ LIỆU (DATABASE CORE) ---
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
                # Xử lý an toàn: Dùng .get() để tránh lỗi nếu thiếu cột
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
        ws.update_cell(row_idx, 3, new_status) # Cột Status
        
        if new_payment_status:
            ws.update_cell(row_idx, 4, new_payment_status) # Cột Payment
            
        if paid_amount > 0:
            current_fin_str = ws.cell(row_idx, 7).value
            try: current_fin = json.loads(current_fin_str) if current_fin_str else {}
            except: current_fin = {}
            
            curr_paid = float(current_fin.get('paid', 0))
            curr_total = float(current_fin.get('total', 0))
            current_fin['paid'] = curr_paid + float(paid_amount)
            current_fin['debt'] = curr_total - current_fin['paid']
            
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
            order_data.get('order_id'), order_data.get('date'), order_data.get('status'), order_data.get('payment_status'),
            json.dumps(order_data.get('customer', {}), ensure_ascii=False),
            json.dumps(order_data.get('items', []), ensure_ascii=False),
            json.dumps(order_data.get('financial', {}), ensure_ascii=False)
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
    count = 0
    for o in orders:
        if str(o.get('order_id', '')).endswith(year): count += 1
    return f"{count+1:03d}/DH.{year}"

# --- PDF GENERATOR (ĐÃ FIX FONT) ---
class PDFGen(FPDF):
    def header(self):
        check_and_download_font()
        try:
            self.add_font('Roboto', '', FONT_FILENAME, uni=True)
            self.set_font('Roboto', '', 14)
            self.cell(0, 10, 'CÔNG TY IN ẤN AN LỘC PHÁT', 0, 1, 'C')
            self.ln(10)
        except: pass

def create_pdf(order, title):
    pdf = PDFGen()
    pdf.add_page()
    check_and_download_font()
    try:
        pdf.add_font('Roboto', '', FONT_FILENAME, uni=True)
        pdf.set_font('Roboto', '', 11)
    except: pdf.set_font('Arial', '', 11)

    oid = order.get('order_id', '')
    odate = order.get('date', '')
    cust = order.get('customer', {})
    items = order.get('items', [])
    
    pdf.set_font_size(16)
    pdf.cell(0, 10, title, 0, 1, 'C')
    pdf.set_font_size(11)
    pdf.cell(0, 8, f"Mã: {oid} | Ngày: {odate}", 0, 1, 'C')
    pdf.ln(5)
    
    pdf.cell(0, 7, f"Khách hàng: {cust.get('name', '')}", 0, 1)
    pdf.cell(0, 7, f"SĐT: {cust.get('phone', '')}", 0, 1)
    pdf.cell(0, 7, f"Địa chỉ: {cust.get('address', '')}", 0, 1)
    pdf.ln(5)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(80, 8, "Tên hàng", 1, 0, 'C', 1)
    pdf.cell(20, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(30, 8, "Đơn giá", 1, 0, 'C', 1)
    pdf.cell(40, 8, "Thành tiền", 1, 1, 'C', 1)
    
    total = 0
    for i, item in enumerate(items):
        try: item_total = float(item.get('total', 0))
        except: item_total = 0
        total += item_total
        
        pdf.cell(10, 8, str(i+1), 1, 0, 'C')
        pdf.cell(80, 8, str(item.get('name', '')), 1, 0)
        pdf.cell(20, 8, str(item.get('qty', 0)), 1, 0, 'C')
        pdf.cell(30, 8, format_currency(item.get('price', 0)), 1, 0, 'R')
        pdf.cell(40, 8, format_currency(item_total), 1, 1, 'R')
    
    pdf.cell(140, 8, "TỔNG CỘNG:", 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total), 1, 1, 'R')
    pdf.ln(10)
    try: money_text = read_money_vietnamese(total)
    except: money_text = f"{format_currency(total)} đồng."
    pdf.multi_cell(0, 8, f"Bằng chữ: {money_text}")
    return bytes(pdf.output())

# --- GIAO DIỆN CHÍNH ---
def main():
    st.set_page_config(page_title="Hệ Thống In Ấn", layout="wide")
    menu = st.sidebar.radio("CHỨC NĂNG", ["1. Tạo Báo Giá", "2. Quản Lý Đơn Hàng (Pipeline)", "3. Sổ Quỹ & Báo Cáo"])

    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        with st.form("create_order"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Tên Khách Hàng")
            phone = c2.text_input("Số Điện Thoại")
            addr = st.text_input("Địa Chỉ")
            staff = st.selectbox("Nhân Viên", ["Nam", "Dương", "Thảo", "Khác"])
            st.divider()
            c3, c4, c5 = st.columns([3, 1, 2])
            i_name = c3.text_input("Tên hàng")
            i_qty = c4.number_input("Số lượng", 1, step=1)
            i_price = c5.number_input("Đơn giá", 0, step=1000)
            total = i_qty * i_price
            st.info(f"💰 Thành tiền: {format_currency(total)}")
            
            if st.form_submit_button("Lưu & Tạo Báo Giá"):
                if not name: st.error("Chưa nhập tên khách!")
                else:
                    new_order = {
                        "order_id": gen_id(), "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá", "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": [{"name": i_name, "qty": i_qty, "price": i_price, "total": total}],
                        "financial": {"total": total, "paid": 0, "debt": total, "staff": staff}
                    }
                    if add_new_order(new_order): st.success("Thành công!")

    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.title("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        with tabs[0]: # Báo Giá
            orders = [o for o in all_orders if o.get('status') == 'Báo giá']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id', '???')
                cname = o.get('customer', {}).get('name', '???')
                total = o.get('financial', {}).get('total', 0)
                with st.expander(f"📄 {oid} | {cname} | {format_currency(total)}"):
                    c1, c2 = st.columns(2)
                    pdf = create_pdf(o, "BÁO GIÁ")
                    if pdf: c1.download_button("🖨️ Tải PDF", pdf, f"BG_{oid}.pdf")
                    if c2.button("✅ Duyệt -> Thiết Kế", key=f"app_{oid}"):
                        update_order_status(oid, "Thiết kế")
                        st.rerun()

        with tabs[1]: # Thiết Kế
            orders = [o for o in all_orders if o.get('status') == 'Thiết kế']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                with st.expander(f"🎨 {oid} | {cname}"):
                    if st.button("✅ Duyệt TK -> Sản Xuất", key=f"des_{oid}"):
                        update_order_status(oid, "Sản xuất")
                        st.rerun()

        with tabs[2]: # Sản Xuất
            orders = [o for o in all_orders if o.get('status') == 'Sản xuất']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                with st.expander(f"⚙️ {oid} | {cname}"):
                    if st.button("✅ Xong -> Giao Hàng", key=f"prod_{oid}"):
                        update_order_status(oid, "Giao hàng")
                        st.rerun()

        with tabs[3]: # Giao Hàng
            orders = [o for o in all_orders if o.get('status') == 'Giao hàng']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                with st.expander(f"🚚 {oid} | {cname}"):
                    c1, c2 = st.columns(2)
                    pdf_gh = create_pdf(o, "PHIẾU GIAO HÀNG")
                    if pdf_gh: c1.download_button("🖨️ In Phiếu Giao", pdf_gh, f"GH_{oid}.pdf")
                    if c2.button("✅ Giao Xong -> Công Nợ", key=f"del_{oid}"):
                        update_order_status(oid, "Công nợ")
                        st.rerun()

        with tabs[4]: # Công Nợ
            orders = [o for o in all_orders if o.get('status') == 'Công nợ']
            if not orders: st.info("Hết nợ.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                fin = o.get('financial', {})
                debt = float(fin.get('total', 0)) - float(fin.get('paid', 0))
                with st.expander(f"💰 {oid} | {cname} | Nợ: {format_currency(debt)}"):
                    c1, c2 = st.columns(2)
                    pay_val = c1.number_input("Số tiền thu:", 0.0, float(debt), float(debt), key=f"pay_{oid}")
                    if c2.button("Thu Tiền", key=f"conf_pay_{oid}"):
                        new_status = "Hoàn thành" if (debt - pay_val) <= 0 else "Công nợ"
                        pay_st = "Đã TT" if (debt - pay_val) <= 0 else "Cọc/Còn nợ"
                        update_order_status(oid, new_status, pay_st, pay_val)
                        save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay_val, f"Thu đơn {oid}")
                        st.success("Đã thu tiền!")
                        time.sleep(1)
                        st.rerun()

        with tabs[5]: # Hoàn Thành
            orders = [o for o in all_orders if o.get('status') == 'Hoàn thành']
            if orders:
                df = pd.DataFrame([{"Mã": x.get('order_id'), "Khách": x.get('customer', {}).get('name'), "Tổng": format_currency(x.get('financial', {}).get('total', 0)), "Ngày": x.get('date')} for x in orders])
                st.dataframe(df, use_container_width=True)

    elif menu == "3. Sổ Quỹ & Báo Cáo":
        st.title("📊 Tài Chính & Báo Cáo")
        tab1, tab2 = st.tabs(["Sổ Quỹ Tiền Mặt", "Báo Cáo Hiệu Suất"])
        
        with tab1:
            df_cash = pd.DataFrame(fetch_cashbook())
            if not df_cash.empty:
                df_cash['amount'] = pd.to_numeric(df_cash['amount'], errors='coerce').fillna(0)
                total_thu = df_cash[df_cash['type'] == 'Thu']['amount'].sum()
                total_chi = df_cash[df_cash['type'] == 'Chi']['amount'].sum()
                ton_quy = total_thu - total_chi
                m1, m2, m3 = st.columns(3)
                m1.metric("Tổng Thu", format_currency(total_thu))
                m2.metric("Tổng Chi", format_currency(total_chi))
                m3.metric("TỒN QUỸ", format_currency(ton_quy))
                st.divider()

            with st.form("add_expense"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Ngày")
                a = c2.number_input("Số tiền chi", 0, step=10000)
                desc = c3.text_input("Nội dung")
                if st.form_submit_button("Lưu Chi Phí"):
                    save_cash_log(d, "Chi", a, desc)
                    st.success("Đã lưu!")
                    st.rerun()
            if not df_cash.empty: st.dataframe(df_cash, use_container_width=True)

        with tab2:
            all_orders = fetch_all_orders()
            if all_orders:
                data = [{"Status": o.get('status'), "Staff": o.get('financial', {}).get('staff', 'Unknown'), "Revenue": o.get('financial', {}).get('total', 0)} for o in all_orders]
                df = pd.DataFrame(data)
                c1, c2 = st.columns(2)
                with c1: st.write("Đơn hàng theo trạng thái"); st.bar_chart(df['Status'].value_counts()) if not df.empty else None
                with c2: st.write("Doanh số theo nhân viên"); st.bar_chart(df.groupby("Staff")["Revenue"].sum()) if not df.empty else None

if __name__ == "__main__":
    main()
