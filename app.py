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
FONT_FILENAME = 'arial.ttf' 

# --- HÀM HỖ TRỢ CƠ BẢN ---
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

# --- TÍNH NĂNG MỚI: XÓA VÀ SỬA ---
def delete_order(order_id):
    """Xóa hoàn toàn dòng chứa đơn hàng"""
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
    except Exception as e:
        st.error(f"Lỗi xóa: {e}")
        return False

def edit_order_info(order_id, new_cust, new_total, new_items):
    """Cập nhật thông tin đơn hàng"""
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if not cell: return False
        
        r = cell.row
        
        # Cập nhật Customer (Cột 5 - E)
        ws.update_cell(r, 5, json.dumps(new_cust, ensure_ascii=False))
        
        # Cập nhật Items (Cột 6 - F)
        ws.update_cell(r, 6, json.dumps(new_items, ensure_ascii=False))

        # Cập nhật Financial (Cột 7 - G)
        # Phải lấy data cũ để giữ lại số tiền đã thanh toán (paid)
        old_fin_str = ws.cell(r, 7).value
        try: fin = json.loads(old_fin_str)
        except: fin = {}
        
        fin['total'] = new_total
        fin['debt'] = new_total - float(fin.get('paid', 0)) # Tính lại nợ
        
        ws.update_cell(r, 7, json.dumps(fin, ensure_ascii=False))
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi sửa: {e}")
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
        pass

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

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá":
        st.title("📝 Tạo Báo Giá Mới")
        
        st.subheader("1. Thông tin khách hàng")
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên Khách Hàng", key="in_name")
        phone = c2.text_input("Số Điện Thoại", key="in_phone")
        addr = st.text_input("Địa Chỉ", key="in_addr")
        staff = st.selectbox("Nhân Viên", ["Nam", "Dương", "Thảo", "Khác"], key="in_staff")

        st.divider()
        st.subheader("2. Chi tiết hàng hóa")
        with st.form("add_item_form", clear_on_submit=True):
            c3, c4, c5 = st.columns([3, 1, 2])
            i_name = c3.text_input("Tên hàng")
            i_qty = c4.number_input("SL", 1.0, step=1.0)
            i_price = c5.number_input("Đơn giá", 0.0, step=1000.0)
            if st.form_submit_button("➕ Thêm vào danh sách"):
                if i_name:
                    st.session_state.cart.append({
                        "name": i_name, "qty": i_qty, "price": i_price, "total": i_qty*i_price
                    })
                    st.rerun()
                else: st.error("Nhập tên hàng!")

        if st.session_state.cart:
            st.write("---")
            cart_df = pd.DataFrame(st.session_state.cart)
            st.table(cart_df)
            total = sum(i['total'] for i in st.session_state.cart)
            st.metric("TỔNG TIỀN", format_currency(total))
            
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
                        "financial": {"total": total, "paid": 0, "debt": total, "staff": staff}
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

    # --- TAB 2: PIPELINE (ĐÃ THÊM SỬA & XÓA) ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.title("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            orders = [o for o in all_orders if o.get('status') == status_filter]
            if not orders: st.info("Trống.")
            
            for o in orders:
                oid = o.get('order_id')
                cust = o.get('customer', {})
                items = o.get('items', [])
                fin = o.get('financial', {})
                total = fin.get('total', 0)
                
                with st.expander(f"📄 {oid} | {cust.get('name')} | {format_currency(total)}"):
                    # 1. Hàng nút chức năng chính
                    c1, c2, c3, c4 = st.columns(4)
                    
                    # Nút in (nếu có)
                    if pdf_type:
                        pdf = create_pdf(o, pdf_type)
                        c1.download_button(f"🖨️ In PDF", pdf, f"{oid}.pdf", "application/pdf")
                    
                    # Nút chuyển trạng thái
                    if next_status:
                        if c2.button(btn_text, key=f"mv_{oid}"):
                            update_order_status(oid, next_status)
                            st.rerun()
                            
                    # --- PHẦN MỚI: SỬA ĐƠN HÀNG ---
                    with st.expander("✏️ CHỈNH SỬA THÔNG TIN"):
                        with st.form(f"edit_{oid}"):
                            e_name = st.text_input("Tên khách", value=cust.get('name', ''))
                            e_phone = st.text_input("SĐT", value=cust.get('phone', ''))
                            e_addr = st.text_input("Địa chỉ", value=cust.get('address', ''))
                            e_total = st.number_input("Tổng tiền (Điều chỉnh giá)", value=float(total), step=1000.0)
                            
                            # Chỉnh sửa Item (Cơ bản: chỉ sửa tên món đầu tiên hoặc ghi chú chung)
                            # Để đơn giản trên giao diện, ta cho phép sửa món hàng đầu tiên đại diện
                            first_item_name = items[0]['name'] if items else ""
                            e_item_name = st.text_input("Tên hàng hóa (Chính)", value=first_item_name)
                            
                            if st.form_submit_button("Lưu Thay Đổi"):
                                new_cust = {"name": e_name, "phone": e_phone, "address": e_addr}
                                
                                # Cập nhật items
                                new_items = items
                                if new_items: new_items[0]['name'] = e_item_name
                                else: new_items = [{"name": e_item_name, "qty": 1, "price": e_total, "total": e_total}]

                                if edit_order_info(oid, new_cust, e_total, new_items):
                                    st.success("Đã cập nhật!")
                                    time.sleep(1)
                                    st.rerun()
                    
                    # --- PHẦN MỚI: XÓA ĐƠN HÀNG ---
                    if st.button("🗑️ XÓA ĐƠN NÀY", key=f"del_{oid}", type="primary"):
                        if delete_order(oid):
                            st.warning(f"Đã xóa đơn {oid}")
                            time.sleep(1)
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
                    pay = c1.number_input("Thu:", 0.0, float(debt), float(debt), key=f"pay_{oid}")
                    if c2.button("Thu Tiền", key=f"cf_{oid}"):
                        new_st = "Hoàn thành" if (debt - pay) <= 0 else "Công nợ"
                        pay_st = "Đã TT" if (debt - pay) <= 0 else "Cọc"
                        update_order_status(oid, new_st, pay_st, pay)
                        save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay, f"Thu {oid}")
                        st.success("Xong!")
                        st.rerun()
                    
                    # Cũng cho phép xóa ở đây nếu đơn sai
                    if st.button("🗑️ Xóa đơn", key=f"deld_{oid}"):
                         if delete_order(oid): st.rerun()

        with tabs[5]: # Hoàn thành
            orders = [o for o in all_orders if o.get('status') == 'Hoàn thành']
            if orders:
                data = [{"Mã": o['order_id'], "Khách": o['customer']['name'], "Tổng": format_currency(o['financial']['total'])} for o in orders]
                st.dataframe(pd.DataFrame(data), use_container_width=True)

    # --- TAB 3: TÀI CHÍNH ---
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
