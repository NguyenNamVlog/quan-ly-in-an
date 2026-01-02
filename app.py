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
    """Lấy toàn bộ đơn hàng từ Sheet về"""
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        raw_data = ws.get_all_records()
        
        # Parse JSON data
        processed_data = []
        for row in raw_data:
            try:
                # Nếu là string JSON thì parse, nếu là dict rồi thì giữ nguyên
                row['customer'] = json.loads(row['customer']) if isinstance(row['customer'], str) else row['customer']
                row['items'] = json.loads(row['items']) if isinstance(row['items'], str) else row['items']
                row['financial'] = json.loads(row['financial']) if isinstance(row['financial'], str) else row['financial']
                processed_data.append(row)
            except: continue
        return processed_data
    except Exception as e:
        # st.error(f"Lỗi tải data: {e}")
        return []

def update_order_status(order_id, new_status, new_payment_status=None, paid_amount=0):
    """Cập nhật trạng thái đơn hàng - Logic cốt lõi của Pipeline"""
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        
        # Tìm dòng chứa order_id
        cell = ws.find(order_id)
        if not cell:
            st.error("Không tìm thấy đơn hàng!")
            return False
        
        row_idx = cell.row
        
        # Cập nhật Status (Cột 3 - C)
        ws.update_cell(row_idx, 3, new_status)
        
        # Nếu có cập nhật thanh toán
        if new_payment_status:
            ws.update_cell(row_idx, 4, new_payment_status) # Cột 4 - D
            
        # Nếu có cập nhật số tiền đã trả (Cập nhật vào cột Financial - Cột 7 - G)
        if paid_amount > 0:
            # Lấy data cũ
            current_fin_str = ws.cell(row_idx, 7).value
            current_fin = json.loads(current_fin_str)
            
            # Tính toán lại
            current_fin['paid'] = float(current_fin.get('paid', 0)) + float(paid_amount)
            current_fin['debt'] = float(current_fin.get('total', 0)) - current_fin['paid']
            
            # Lưu lại
            ws.update_cell(row_idx, 7, json.dumps(current_fin, ensure_ascii=False))
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi update: {e}")
        return False

def add_new_order(order_data):
    """Thêm đơn mới vào cuối danh sách"""
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
            order_data['order_id'],
            order_data['date'],
            order_data['status'],
            order_data['payment_status'],
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
    """Ghi sổ quỹ"""
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Cashbook")
        except: 
            ws = sh.add_worksheet("Cashbook", 1000, 10)
            ws.append_row(["date", "type", "amount", "category", "desc"])
        
        ws.append_row([str(date), type_, amount, "Thu tiền hàng", desc])
        st.cache_data.clear()
    except: pass

def gen_id():
    # Sinh mã đơn hàng tự động
    orders = fetch_all_orders()
    year = datetime.now().strftime("%y")
    count = len([o for o in orders if str(o.get('order_id')).endswith(year)])
    return f"{count+1:03d}/DH.{year}"

# --- PDF GENERATOR (GIỮ NGUYÊN) ---
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
    
    # Table Header
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
    
    # Sidebar
    menu = st.sidebar.radio("CHỨC NĂNG", [
        "1. Tạo Báo Giá", 
        "2. Quản Lý Đơn Hàng (Pipeline)", 
        "3. Sổ Quỹ & Báo Cáo"
    ])

    # --- TAB 1: TẠO BÁO GIÁ (ĐẦU VÀO) ---
    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        
        with st.form("create_order"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Tên Khách Hàng")
            phone = c2.text_input("Số Điện Thoại")
            addr = st.text_input("Địa Chỉ")
            staff = st.selectbox("Nhân Viên Kinh Doanh", ["Nam", "Dương", "Thảo", "Khác"])
            
            st.divider()
            st.write("San Phẩm:")
            # Giản lược: Nhập 1 sản phẩm chính (Có thể nâng cấp thêm nhiều dòng sau)
            c3, c4, c5 = st.columns([3, 1, 2])
            i_name = c3.text_input("Tên hàng / Quy cách")
            i_qty = c4.number_input("Số lượng", 1, step=1)
            i_price = c5.number_input("Đơn giá", 0, step=1000)
            
            total = i_qty * i_price
            st.info(f"💰 Thành tiền: {format_currency(total)}")
            
            if st.form_submit_button("Lưu & Tạo Báo Giá"):
                if not name:
                    st.error("Chưa nhập tên khách!")
                else:
                    new_order = {
                        "order_id": gen_id(),
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá", # Trạng thái bắt đầu
                        "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": [{"name": i_name, "qty": i_qty, "price": i_price, "total": total}],
                        "financial": {"total": total, "paid": 0, "debt": total, "staff": staff}
                    }
                    if add_new_order(new_order):
                        st.success(f"Đã tạo đơn {new_order['order_id']} thành công! Chuyển sang Tab Quản Lý để duyệt.")
                        
    # --- TAB 2: QUẢN LÝ PIPELINE (LÕI XỬ LÝ) ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.title("🏭 Quy Trình Sản Xuất")
        
        # Load tất cả dữ liệu 1 lần
        all_orders = fetch_all_orders()
        
        # Chia Tab theo đúng quy trình
        tabs = st.tabs([
            "1️⃣ Báo Giá", 
            "2️⃣ Thiết Kế", 
            "3️⃣ Sản Xuất", 
            "4️⃣ Giao Hàng", 
            "5️⃣ Công Nợ", 
            "✅ Hoàn Thành"
        ])
        
        # === 1. BÁO GIÁ ===
        with tabs[0]:
            orders = [o for o in all_orders if o['status'] == 'Báo giá']
            if not orders: st.info("Không có báo giá nào đang chờ.")
            for o in orders:
                with st.expander(f"📄 {o['order_id']} | {o['customer']['name']} | {format_currency(o['financial']['total'])}"):
                    c1, c2 = st.columns(2)
                    # Output: In Báo Giá
                    pdf = create_pdf(o, "BÁO GIÁ")
                    if pdf: c1.download_button("🖨️ Tải File PDF Báo Giá", pdf, f"BG_{o['order_id']}.pdf")
                    
                    # Action: Duyệt -> Thiết kế
                    if c2.button("✅ DUYỆT -> CHUYỂN THIẾT KẾ", key=f"to_des_{o['order_id']}"):
                        update_order_status(o['order_id'], "Thiết kế")
                        st.rerun()

        # === 2. THIẾT KẾ ===
        with tabs[1]:
            orders = [o for o in all_orders if o['status'] == 'Thiết kế']
            if not orders: st.info("Trống.")
            for o in orders:
                with st.expander(f"🎨 {o['order_id']} | {o['customer']['name']}"):
                    st.write(f"Sản phẩm: {o['items'][0]['name']}")
                    # Action: Xong -> Sản xuất
                    if st.button("✅ DUYỆT THIẾT KẾ -> CHUYỂN SẢN XUẤT", key=f"to_prod_{o['order_id']}"):
                        update_order_status(o['order_id'], "Sản xuất")
                        st.rerun()

        # === 3. SẢN XUẤT ===
        with tabs[2]:
            orders = [o for o in all_orders if o['status'] == 'Sản xuất']
            if not orders: st.info("Trống.")
            for o in orders:
                with st.expander(f"⚙️ {o['order_id']} | {o['customer']['name']}"):
                    st.warning("Đang trong quá trình in ấn...")
                    # Action: Xong -> Giao hàng
                    if st.button("✅ SẢN XUẤT XONG -> CHUYỂN GIAO HÀNG", key=f"to_ship_{o['order_id']}"):
                        update_order_status(o['order_id'], "Giao hàng")
                        st.rerun()

        # === 4. GIAO HÀNG ===
        with tabs[3]:
            orders = [o for o in all_orders if o['status'] == 'Giao hàng']
            if not orders: st.info("Trống.")
            for o in orders:
                with st.expander(f"🚚 {o['order_id']} | {o['customer']['name']}"):
                    c1, c2 = st.columns(2)
                    # Output: Phiếu giao hàng
                    pdf = create_pdf(o, "PHIẾU GIAO HÀNG")
                    if pdf: c1.download_button("🖨️ In Phiếu Giao Hàng", pdf, f"GH_{o['order_id']}.pdf")
                    
                    # Output: Hợp đồng (Word demo)
                    c1.download_button("📝 Xuất Hợp Đồng (Word)", b"Demo", "HopDong.docx", disabled=True)

                    # Action: Giao xong -> Công nợ
                    if c2.button("✅ ĐÃ GIAO XONG -> CHUYỂN CÔNG NỢ", key=f"to_debt_{o['order_id']}"):
                        update_order_status(o['order_id'], "Công nợ")
                        st.rerun()

        # === 5. CÔNG NỢ (THU TIỀN) ===
        with tabs[4]:
            orders = [o for o in all_orders if o['status'] == 'Công nợ']
            if not orders: st.info("Hết nợ.")
            for o in orders:
                fin = o['financial']
                debt = float(fin['total']) - float(fin.get('paid', 0))
                
                with st.expander(f"💰 {o['order_id']} | {o['customer']['name']} | Còn nợ: {format_currency(debt)}"):
                    c1, c2 = st.columns(2)
                    pay_val = c1.number_input("Số tiền khách trả:", 0.0, float(debt), float(debt), key=f"pay_{o['order_id']}")
                    
                    if c2.button("💸 XÁC NHẬN THU TIỀN", key=f"conf_pay_{o['order_id']}"):
                        new_debt = debt - pay_val
                        new_status = "Công nợ"
                        new_pay_st = "Cọc/Còn nợ"
                        
                        # Logic: Hết nợ thì hoàn thành
                        if new_debt <= 0:
                            new_status = "Hoàn thành"
                            new_pay_st = "Đã TT"
                        
                        # Cập nhật Order & Ghi Sổ Quỹ
                        update_order_status(o['order_id'], new_status, new_pay_st, pay_val)
                        save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay_val, f"Thu tiền đơn {o['order_id']}")
                        
                        st.success("Đã thu tiền thành công!")
                        time.sleep(1)
                        st.rerun()

        # === 6. HOÀN THÀNH ===
        with tabs[5]:
            orders = [o for o in all_orders if o['status'] == 'Hoàn thành']
            if not orders: st.info("Chưa có đơn hoàn thành.")
            else:
                df = pd.DataFrame([{
                    "Mã": o['order_id'],
                    "Khách": o['customer']['name'],
                    "Tổng tiền": format_currency(o['financial']['total']),
                    "Ngày": o['date']
                } for o in orders])
                st.dataframe(df, use_container_width=True)

    # --- TAB 3: SỔ QUỸ & BÁO CÁO ---
    elif menu == "3. Sổ Quỹ & Báo Cáo":
        st.title("📊 Thống Kê & Tài Chính")
        
        tab1, tab2 = st.tabs(["Sổ Quỹ Tiền Mặt", "Báo Cáo Hiệu Suất"])
        
        with tab1:
            # Load Cashbook
            client = get_gspread_client()
            try:
                sh = client.open_by_url(SHEET_URL)
                ws = sh.worksheet("Cashbook")
                cash_data = ws.get_all_records()
                df_cash = pd.DataFrame(cash_data)
                
                # Form nhập chi
                with st.form("add_expense"):
                    st.write("Nhập chi phí phát sinh:")
                    c1, c2, c3 = st.columns(3)
                    d = c1.date_input("Ngày")
                    a = c2.number_input("Số tiền chi", 0, step=10000)
                    desc = c3.text_input("Nội dung chi")
                    if st.form_submit_button("Lưu Chi Phí"):
                        save_cash_log(d, "Chi", a, desc)
                        st.rerun()
                
                if not df_cash.empty:
                    df_cash['amount'] = pd.to_numeric(df_cash['amount'])
                    thu = df_cash[df_cash['type'] == 'Thu']['amount'].sum()
                    chi = df_cash[df_cash['type'] == 'Chi']['amount'].sum()
                    
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Tổng Thu", format_currency(thu))
                    k2.metric("Tổng Chi", format_currency(chi))
                    k3.metric("Tồn Quỹ", format_currency(thu - chi))
                    
                    st.dataframe(df_cash, use_container_width=True)
            except: st.error("Lỗi đọc sổ quỹ")

        with tab2:
            all_orders = fetch_all_orders()
            if all_orders:
                # Prepare data
                data = []
                for o in all_orders:
                    data.append({
                        "Status": o['status'],
                        "Staff": o['financial'].get('staff', 'Unknown'),
                        "Revenue": o['financial'].get('total', 0)
                    })
                df = pd.DataFrame(data)
                
                c1, c2 = st.columns(2)
                with c1:
                    st.write("Đơn hàng theo trạng thái")
                    st.bar_chart(df['Status'].value_counts())
                with c2:
                    st.write("Doanh số theo nhân viên")
                    staff_rev = df.groupby("Staff")["Revenue"].sum()
                    st.bar_chart(staff_rev)

if __name__ == "__main__":
    main()
