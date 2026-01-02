import streamlit as st
import pandas as pd
import json
import time
import os
import requests
import unicodedata
from datetime import datetime
from fpdf import FPDF
from docxtpl import DocxTemplate
import plotly.express as px
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials

# --- CẤU HÌNH ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit"
TEMPLATE_CONTRACT = 'Hop dong .docx' 
# Tên file font BẮT BUỘC phải khớp với file bạn upload lên GitHub (phân biệt hoa thường)
FONT_FILENAME = 'arial.ttf' 

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
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
        return None

# --- DATABASE CORE (LẤY DỮ LIỆU) ---
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
                # Dùng .get() và kiểm tra chuỗi rỗng để tránh lỗi JSON
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

# --- CẬP NHẬT TRẠNG THÁI ---
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

# --- THÊM ĐƠN MỚI ---
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

# --- GHI SỔ QUỸ ---
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

# --- PDF GENERATOR (DÙNG FONT LOCAL arial.ttf) ---
class PDFGen(FPDF):
    def header(self):
        # Lưu ý: Font phải được add trước khi dùng trong header
        # Nhưng vì header được gọi tự động, ta sẽ set font trong main body trước
        pass

def create_pdf(order, title):
    pdf = PDFGen()
    
    # 1. Đăng ký Font (Quan trọng nhất)
    # Kiểm tra file font có tồn tại không
    if not os.path.exists(FONT_FILENAME):
        # Nếu không thấy file font, báo lỗi lên PDF để người dùng biết
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, f"LOI: Khong tim thay file '{FONT_FILENAME}' tren he thong.", new_x="LMARGIN", new_y="NEXT")
        return bytes(pdf.output())

    # Đăng ký font với tên 'DejaVu' (hoặc tên tùy ý)
    # fpdf2 tự động nhận diện unicode từ ttf
    pdf.add_font('DejaVu', '', FONT_FILENAME)
    
    pdf.add_page()
    pdf.set_font('DejaVu', '', 11)

    # Hàm in text an toàn (chuyển về string)
    def txt(text):
        return str(text) if text is not None else ""

    # --- Header Công Ty ---
    pdf.set_font('DejaVu', '', 14)
    pdf.cell(0, 10, txt('CÔNG TY IN ẤN AN LỘC PHÁT'), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)

    # --- Tiêu đề ---
    pdf.set_font_size(16)
    pdf.cell(0, 10, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    
    # --- Thông tin đơn ---
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
    
    # --- Bảng Hàng Hóa ---
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", border=1, align='C', fill=True)
    pdf.cell(90, 8, txt("Tên hàng / Quy cách"), border=1, align='C', fill=True)
    pdf.cell(20, 8, "SL", border=1, align='C', fill=True)
    pdf.cell(30, 8, txt("Đơn giá"), border=1, align='C', fill=True)
    pdf.cell(40, 8, txt("Thành tiền"), border=1, align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
    
    total = 0
    items = order.get('items', [])
    for i, item in enumerate(items):
        try: item_total = float(item.get('total', 0))
        except: item_total = 0
        total += item_total
        
        pdf.cell(10, 8, str(i+1), border=1, align='C')
        pdf.cell(90, 8, txt(item.get('name', '')), border=1)
        pdf.cell(20, 8, txt(str(item.get('qty', 0))), border=1, align='C')
        pdf.cell(30, 8, format_currency(item.get('price', 0)), border=1, align='R')
        pdf.cell(40, 8, format_currency(item_total), border=1, align='R', new_x="LMARGIN", new_y="NEXT")
    
    # --- Tổng cộng ---
    pdf.cell(150, 8, txt("TỔNG CỘNG:"), border=1, align='R')
    pdf.cell(40, 8, format_currency(total), border=1, align='R', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    try: money_text = read_money_vietnamese(total)
    except: money_text = f"{format_currency(total)} đồng."
    
    pdf.multi_cell(0, 8, txt(f"Bằng chữ: {money_text}"))
    
    return bytes(pdf.output())

# --- GIAO DIỆN CHÍNH ---
def main():
    st.set_page_config(page_title="Hệ Thống In Ấn", layout="wide")
    
    # Kiểm tra font ngay khi vào app
    if not os.path.exists(FONT_FILENAME):
        st.warning(f"⚠️ CẢNH BÁO: Chưa tìm thấy file '{FONT_FILENAME}' trong thư mục GitHub. Tính năng in PDF tiếng Việt sẽ bị lỗi!")

    menu = st.sidebar.radio("CHỨC NĂNG", ["1. Tạo Báo Giá", "2. Quản Lý Đơn Hàng (Pipeline)", "3. Sổ Quỹ & Báo Cáo"])

    # Khởi tạo session state
    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'last_order' not in st.session_state: st.session_state.last_order = None

    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        
        with st.container():
            c1, c2 = st.columns(2)
            name = c1.text_input("Tên Khách Hàng", key="in_name")
            phone = c2.text_input("Số Điện Thoại", key="in_phone")
            addr = st.text_input("Địa Chỉ", key="in_addr")
            staff = st.selectbox("Nhân Viên", ["Nam", "Dương", "Thảo", "Khác"], key="in_staff")

        st.divider()
        st.subheader("Chi tiết hàng hóa")
        
        with st.form("add_item_form", clear_on_submit=True):
            c3, c4, c5 = st.columns([3, 1, 2])
            i_name = c3.text_input("Tên hàng / Quy cách")
            i_qty = c4.number_input("Số lượng", 1, step=1.0)
            i_price = c5.number_input("Đơn giá", 0, step=1000.0)
            
            if st.form_submit_button("➕ Thêm vào danh sách"):
                if i_name:
                    item_total = i_qty * i_price
                    st.session_state.cart.append({
                        "name": i_name, "qty": i_qty, "price": i_price, "total": item_total
                    })
                    st.toast(f"Đã thêm: {i_name}")
                else: st.error("Vui lòng nhập tên hàng!")

        if st.session_state.cart:
            st.write("---")
            st.write("📋 **Danh sách hàng:**")
            
            cart_df = pd.DataFrame(st.session_state.cart)
            display_df = cart_df.copy()
            display_df['price'] = display_df['price'].apply(format_currency)
            display_df['total'] = display_df['total'].apply(format_currency)
            display_df.columns = ["Tên hàng", "Số lượng", "Đơn giá", "Thành tiền"]
            
            st.table(display_df)
            total_order = sum(item['total'] for item in st.session_state.cart)
            st.metric(label="TỔNG GIÁ TRỊ", value=f"{format_currency(total_order)} VNĐ")
            
            c_del, c_save = st.columns(2)
            if c_del.button("🗑️ Xóa giỏ hàng"):
                st.session_state.cart = []
                st.rerun()
            
            if c_save.button("💾 LƯU BÁO GIÁ", type="primary"):
                if not name:
                    st.error("Vui lòng nhập tên khách hàng!")
                else:
                    new_order = {
                        "order_id": gen_id(), 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá", 
                        "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": st.session_state.cart,
                        "financial": {"total": total_order, "paid": 0, "debt": total_order, "staff": staff}
                    }
                    if add_new_order(new_order):
                        st.session_state.last_order = new_order
                        st.session_state.cart = []
                        st.rerun()

        if st.session_state.last_order:
            oid = st.session_state.last_order['order_id']
            st.success(f"✅ Đã tạo đơn: **{oid}**")
            
            pdf_bytes = create_pdf(st.session_state.last_order, "BÁO GIÁ")
            
            c_print, c_new = st.columns(2)
            c_print.download_button("🖨️ Tải Báo Giá PDF", pdf_bytes, f"BG_{oid}.pdf", "application/pdf", type="primary")
            if c_new.button("Tạo đơn mới"):
                st.session_state.last_order = None
                st.rerun()

    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.title("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            orders = [o for o in all_orders if o.get('status') == status_filter]
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id', '???')
                cname = o.get('customer', {}).get('name', '???')
                total = o.get('financial', {}).get('total', 0)
                
                with st.expander(f"📄 {oid} | {cname} | {format_currency(total)}"):
                    c1, c2 = st.columns(2)
                    if pdf_type:
                        pdf = create_pdf(o, pdf_type)
                        c1.download_button(f"🖨️ In {pdf_type}", pdf, f"{oid}.pdf", "application/pdf")
                    
                    if next_status:
                        if c2.button(btn_text, key=f"btn_{oid}"):
                            update_order_status(oid, next_status)
                            st.rerun()

        with tabs[0]: render_tab_content("Báo giá", "Thiết kế", "✅ Duyệt -> Thiết Kế", "BÁO GIÁ")
        with tabs[1]: render_tab_content("Thiết kế", "Sản xuất", "✅ Duyệt TK -> Sản Xuất")
        with tabs[2]: render_tab_content("Sản xuất", "Giao hàng", "✅ Xong -> Giao Hàng")
        with tabs[3]: render_tab_content("Giao hàng", "Công nợ", "✅ Giao Xong -> Công Nợ", "PHIẾU GIAO HÀNG")
        
        with tabs[4]: # Công nợ
            orders = [o for o in all_orders if o.get('status') == 'Công nợ']
            if not orders: st.info("Hết nợ.")
            for o in orders:
                oid = o.get('order_id')
                fin = o.get('financial', {})
                debt = float(fin.get('total', 0)) - float(fin.get('paid', 0))
                with st.expander(f"💰 {oid} | Nợ: {format_currency(debt)}"):
                    c1, c2 = st.columns(2)
                    pay = c1.number_input("Thu:", 0.0, float(debt), float(debt), key=f"p_{oid}")
                    if c2.button("Thu Tiền", key=f"pay_{oid}"):
                        new_st = "Hoàn thành" if (debt - pay) <= 0 else "Công nợ"
                        pay_st = "Đã TT" if (debt - pay) <= 0 else "Cọc"
                        update_order_status(oid, new_st, pay_st, pay)
                        save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay, f"Thu {oid}")
                        st.success("Xong!")
                        time.sleep(1)
                        st.rerun()

        with tabs[5]: # Hoàn thành
            orders = [o for o in all_orders if o.get('status') == 'Hoàn thành']
            if orders:
                df = pd.DataFrame([{"Mã": x.get('order_id'), "Khách": x.get('customer', {}).get('name'), "Tổng": format_currency(x.get('financial', {}).get('total', 0))} for x in orders])
                st.dataframe(df, use_container_width=True)

    elif menu == "3. Sổ Quỹ & Báo Cáo":
        st.title("📊 Tài Chính")
        tab1, tab2 = st.tabs(["Sổ Quỹ", "Báo Cáo"])
        
        with tab1:
            df = pd.DataFrame(fetch_cashbook())
            if not df.empty:
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
                thu = df[df['type'] == 'Thu']['amount'].sum()
                chi = df[df['type'] == 'Chi']['amount'].sum()
                c1, c2, c3 = st.columns(3)
                c1.metric("Thu", format_currency(thu))
                c2.metric("Chi", format_currency(chi))
                c3.metric("Tồn", format_currency(thu - chi))
                st.divider()
            
            with st.form("expense"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Ngày")
                a = c2.number_input("Chi phí", 0, step=10000)
                desc = c3.text_input("Nội dung")
                if st.form_submit_button("Lưu Chi"):
                    save_cash_log(d, "Chi", a, desc)
                    st.rerun()
            if not df.empty: st.dataframe(df, use_container_width=True)

        with tab2:
            orders = fetch_all_orders()
            if orders:
                df = pd.DataFrame([{"Status": o.get('status'), "Staff": o.get('financial', {}).get('staff'), "Total": o.get('financial', {}).get('total', 0)} for o in orders])
                if not df.empty:
                    st.bar_chart(df['Status'].value_counts())
                    st.bar_chart(df.groupby("Staff")['Total'].sum())

if __name__ == "__main__":
    main()
