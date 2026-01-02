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
FONT_FILENAME = 'Roboto-Regular.ttf'

# --- HÀM HỖ TRỢ ---
def format_currency(value):
    if value is None: return "0"
    try: return "{:,.0f}".format(float(value))
    except: return "0"

def read_money_vietnamese(amount):
    try: return num2words(amount, lang='vi').capitalize() + " đồng chẵn."
    except: return "..................... đồng."

# --- TẢI FONT (XỬ LÝ LỖI FILE HỎNG) ---
def check_and_download_font():
    """Tải font và kiểm tra xem file có hợp lệ không"""
    url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf"
    
    # Nếu file tồn tại nhưng kích thước quá nhỏ (lỗi tải), xóa đi
    if os.path.exists(FONT_FILENAME) and os.path.getsize(FONT_FILENAME) < 1000:
        os.remove(FONT_FILENAME)
        
    if not os.path.exists(FONT_FILENAME):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(FONT_FILENAME, 'wb') as f:
                    f.write(response.content)
        except: pass

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
            try: current_fin = json.loads(current_fin_str) if current_fin_str else {}
            except: current_fin = {}
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

# --- PDF GENERATOR (FIX LỖI CRASH FONT TUYỆT ĐỐI) ---
class PDFGen(FPDF):
    def header(self):
        # Tránh set font ngay tại đây nếu font chưa load được
        pass

def create_pdf(order, title):
    pdf = PDFGen()
    pdf.add_page()
    
    # 1. Tải Font
    check_and_download_font()
    
    # 2. Cài đặt font & Chế độ Safe Mode
    SAFE_MODE = False
    try:
        # Thử load font Roboto
        pdf.add_font('Roboto', '', FONT_FILENAME)
        pdf.set_font('Roboto', '', 11)
    except:
        # Nếu lỗi (do file font hỏng/không tải được), dùng Helvetica và Bật Safe Mode
        pdf.set_font('Helvetica', '', 11)
        SAFE_MODE = True

    # 3. Hàm xử lý text bất chấp mọi loại lỗi font
    def txt(text):
        if not text: return ""
        text = str(text)
        
        if not SAFE_MODE:
            return text
        
        # --- LOGIC SAFE MODE (BỎ DẤU ĐỂ KHÔNG SẬP APP) ---
        # Thay thế các ký tự đặc biệt tiếng Việt thủ công
        replacements = {
            'đ': 'd', 'Đ': 'D',
            'ă': 'a', 'â': 'a', 'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
            'ê': 'e', 'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
            'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
            'ô': 'o', 'ơ': 'o', 'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
            'ư': 'u', 'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y'
        }
        # Bước 1: Thay thế thủ công
        for k, v in replacements.items():
            text = text.replace(k, v).replace(k.upper(), v.upper())
            
        # Bước 2: Chuẩn hóa unicode và loại bỏ các dấu còn sót
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        return text

    # --- NỘI DUNG PDF ---
    
    # Header Công Ty
    # Kiểm tra font riêng cho header
    header_font = 'Roboto' if not SAFE_MODE else 'Helvetica'
    pdf.set_font(header_font, '', 14)
    pdf.cell(0, 10, txt('CÔNG TY IN ẤN AN LỘC PHÁT'), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)

    # Tiêu đề
    pdf.set_font_size(16)
    pdf.cell(0, 10, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    
    # Thông tin đơn
    pdf.set_font_size(11)
    oid = order.get('order_id', '')
    odate = order.get('date', '')
    pdf.cell(0, 8, txt(f"Mã số: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    
    cust = order.get('customer', {})
    pdf.cell(0, 7, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"Điện thoại: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Table Header
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", border=1, align='C', fill=True)
    pdf.cell(90, 8, txt("Tên hàng / Quy cách"), border=1, align='C', fill=True)
    pdf.cell(20, 8, "SL", border=1, align='C', fill=True)
    pdf.cell(30, 8, txt("Đơn giá"), border=1, align='C', fill=True)
    pdf.cell(40, 8, txt("Thành tiền"), border=1, align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
    
    # Dữ liệu bảng
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
    
    # Tổng cộng
    pdf.cell(150, 8, txt("TỔNG CỘNG:"), border=1, align='R')
    pdf.cell(40, 8, format_currency(total), border=1, align='R', new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    
    # Đọc tiền
    if SAFE_MODE:
        pdf.multi_cell(0, 8, txt(f"Tong cong: {format_currency(total)} VND"))
    else:
        try: money_text = read_money_vietnamese(total)
        except: money_text = f"{format_currency(total)} đồng."
        pdf.multi_cell(0, 8, txt(f"Bằng chữ: {money_text}"))
    
    return pdf.output()

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
        
        # 1. BÁO GIÁ
        with tabs[0]:
            orders = [o for o in all_orders if o.get('status') == 'Báo giá']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id', '???')
                cname = o.get('customer', {}).get('name', '???')
                total = o.get('financial', {}).get('total', 0)
                with st.expander(f"📄 {oid} | {cname} | {format_currency(total)}"):
                    c1, c2 = st.columns(2)
                    pdf = create_pdf(o, "BÁO GIÁ")
                    if pdf: c1.download_button("🖨️ Tải PDF", pdf, f"BG_{oid}.pdf", mime="application/pdf")
                    if c2.button("✅ Duyệt -> Thiết Kế", key=f"app_{oid}"):
                        update_order_status(oid, "Thiết kế")
                        st.rerun()

        # 2. THIẾT KẾ
        with tabs[1]:
            orders = [o for o in all_orders if o.get('status') == 'Thiết kế']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                with st.expander(f"🎨 {oid} | {cname}"):
                    if st.button("✅ Duyệt TK -> Sản Xuất", key=f"des_{oid}"):
                        update_order_status(oid, "Sản xuất")
                        st.rerun()

        # 3. SẢN XUẤT
        with tabs[2]:
            orders = [o for o in all_orders if o.get('status') == 'Sản xuất']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                with st.expander(f"⚙️ {oid} | {cname}"):
                    if st.button("✅ Xong -> Giao Hàng", key=f"prod_{oid}"):
                        update_order_status(oid, "Giao hàng")
                        st.rerun()

        # 4. GIAO HÀNG
        with tabs[3]:
            orders = [o for o in all_orders if o.get('status') == 'Giao hàng']
            if not orders: st.info("Trống.")
            for o in orders:
                oid = o.get('order_id')
                cname = o.get('customer', {}).get('name')
                with st.expander(f"🚚 {oid} | {cname}"):
                    c1, c2 = st.columns(2)
                    pdf_gh = create_pdf(o, "PHIẾU GIAO HÀNG")
                    if pdf_gh: c1.download_button("🖨️ In Phiếu Giao", pdf_gh, f"GH_{oid}.pdf", mime="application/pdf")
                    if c2.button("✅ Giao Xong -> Công Nợ", key=f"del_{oid}"):
                        update_order_status(oid, "Công nợ")
                        st.rerun()

        # 5. CÔNG NỢ
        with tabs[4]:
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

        # 6. HOÀN THÀNH
        with tabs[5]:
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
