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
    """Cập nhật thông tin đơn hàng"""
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if not cell: return False
        r = cell.row
        
        # Update Customer
        ws.update_cell(r, 5, json.dumps(new_cust, ensure_ascii=False))
        # Update Items
        ws.update_cell(r, 6, json.dumps(new_items, ensure_ascii=False))
        
        # Update Financial (giữ lại số tiền đã trả)
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

# --- PDF GENERATOR (CẬP NHẬT CỘT ĐVT) ---
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

    pdf.set_font_size(14)
    pdf.cell(0, 10, txt('CÔNG TY IN ẤN AN LỘC PHÁT'), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    pdf.set_font_size(16)
    pdf.cell(0, 10, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font_size(11)
    
    oid = order.get('order_id', '')
    odate = order.get('date', '')
    cust = order.get('customer', {})
    items = order.get('items', [])
    
    pdf.cell(0, 8, txt(f"Mã: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    pdf.cell(0, 7, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"SĐT: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Header Bảng (Thêm cột ĐVT)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(75, 8, txt("Tên hàng / Quy cách"), 1, 0, 'C', 1)
    pdf.cell(15, 8, txt("ĐVT"), 1, 0, 'C', 1) # Cột ĐVT Mới
    pdf.cell(15, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(35, 8, txt("Đơn giá"), 1, 0, 'C', 1)
    pdf.cell(40, 8, txt("Thành tiền"), 1, 1, 'C', 1)
    
    # Reset X để xuống dòng đúng
    pdf.ln(8)
    
    total = 0
    for i, item in enumerate(items):
        try: 
            val = float(item.get('total', 0))
            price = float(item.get('price', 0))
        except: val = 0; price = 0
        total += val
        
        pdf.cell(10, 8, str(i+1), 1, 0, 'C')
        pdf.cell(75, 8, txt(item.get('name', '')), 1, 0)
        pdf.cell(15, 8, txt(item.get('unit', '')), 1, 0, 'C') # In ĐVT
        pdf.cell(15, 8, txt(str(item.get('qty', 0))), 1, 0, 'C')
        pdf.cell(35, 8, format_currency(price), 1, 0, 'R')
        pdf.cell(40, 8, format_currency(val), 1, 1, 'R')
        pdf.ln(8)
    
    pdf.cell(150, 8, txt("TỔNG CỘNG:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total), 1, 1, 'R')
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

    # --- TAB 1: TẠO BÁO GIÁ (THÊM CỘT GIÁ VỐN, GIÁ HÓA ĐƠN) ---
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
            # Layout mới: Tên | ĐVT | SL | Giá Vốn | Giá Bán (Hóa đơn)
            col_name, col_unit, col_qty = st.columns([3, 1, 1])
            i_name = col_name.text_input("Tên hàng / Quy cách")
            i_unit = col_unit.text_input("ĐVT (Cái/Bộ)")
            i_qty = col_qty.number_input("SL", 1.0, step=1.0)
            
            col_cost, col_price = st.columns(2)
            i_cost = col_cost.number_input("Giá Vốn (Để tính lãi)", 0.0, step=1000.0)
            i_price = col_price.number_input("Giá Bán (Hóa đơn)", 0.0, step=1000.0)
            
            if st.form_submit_button("➕ Thêm vào danh sách"):
                if i_name:
                    st.session_state.cart.append({
                        "name": i_name, 
                        "unit": i_unit,
                        "qty": i_qty, 
                        "cost": i_cost,
                        "price": i_price, 
                        "total": i_qty * i_price
                    })
                    st.rerun()
                else: st.error("Nhập tên hàng!")

        if st.session_state.cart:
            st.write("---")
            cart_df = pd.DataFrame(st.session_state.cart)
            
            # Hiển thị bảng đẹp hơn với đầy đủ cột
            view_df = cart_df.copy()
            view_df['cost'] = view_df['cost'].apply(format_currency)
            view_df['price'] = view_df['price'].apply(format_currency)
            view_df['total'] = view_df['total'].apply(format_currency)
            
            # Đổi tên cột hiển thị
            view_df.columns = ["Tên hàng", "ĐVT", "SL", "Giá Vốn", "Giá Bán", "Thành tiền"]
            st.table(view_df)
            
            total = sum(i['total'] for i in st.session_state.cart)
            st.metric("TỔNG TIỀN ĐƠN HÀNG", format_currency(total))
            
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
                        "financial": {"total": total, "paid": 0, "debt": total, "staff": staff, "commission_status": "Chưa chi"}
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

    # --- TAB 2: QUẢN LÝ (CẬP NHẬT CHỈNH SỬA TOÀN BỘ ITEM) ---
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
                
                total = float(fin.get('total', 0))
                paid = float(fin.get('paid', 0))
                debt = total - paid
                pay_stat = o.get('payment_status', 'Chưa TT')
                comm_stat = fin.get('commission_status', 'Chưa chi')

                with st.expander(f"📄 {oid} | {cust.get('name')} | Còn: {format_currency(debt)}"):
                    c_info, c_items, c_fin = st.columns([1.5, 2, 1.5])
                    
                    with c_info:
                        st.write("👤 **Khách:** " + cust.get('name'))
                        st.caption(f"SĐT: {cust.get('phone')} | ĐC: {cust.get('address')}")
                        st.write(f"📅 {o.get('date')} | 🔄 {status_filter}")

                    with c_items:
                        st.write("📦 **Hàng hóa:**")
                        if items:
                            df_i = pd.DataFrame(items)
                            # Chọn các cột cần thiết để hiển thị gọn
                            cols_to_show = ["name", "qty", "price", "total"]
                            df_show = df_i[cols_to_show].copy() if set(cols_to_show).issubset(df_i.columns) else df_i
                            df_show.columns = ["Tên", "SL", "Giá", "Thành tiền"]
                            st.dataframe(df_show, hide_index=True, use_container_width=True)

                    with c_fin:
                        st.write(f"💰 Tổng: **{format_currency(total)}**")
                        st.write(f"Đã trả: {format_currency(paid)}")
                        st.write(f"Còn nợ: **{format_currency(debt)}**")
                        
                        # Hiển thị trạng thái rõ ràng
                        if pay_stat == "Đã TT": st.success(f"TT: {pay_stat}")
                        elif pay_stat == "Cọc": st.warning(f"TT: {pay_stat}")
                        else: st.error(f"TT: {pay_stat}")
                        
                        if comm_stat == "Đã chi": st.success(f"HH: {comm_stat}")
                        else: st.warning(f"HH: {comm_stat}")
                        
                        # Nút xác nhận hoa hồng
                        if comm_stat != "Đã chi":
                            if st.button("Chi Hoa Hồng", key=f"ch_{oid}"):
                                update_commission_status(oid, "Đã chi")
                                st.rerun()

                    st.divider()
                    c1, c2, c3 = st.columns([1, 1, 2])
                    if pdf_type:
                        pdf = create_pdf(o, pdf_type)
                        c1.download_button(f"🖨️ In {pdf_type}", pdf, f"{oid}.pdf", "application/pdf")
                    
                    if next_status:
                        if c2.button(btn_text, key=f"mv_{oid}"):
                            update_order_status(oid, next_status)
                            st.rerun()
                    
                    # --- SỬA ĐƠN HÀNG NÂNG CAO (DATA EDITOR) ---
                    with st.expander("✏️ Sửa Đơn Hàng (Toàn diện)"):
                        with st.form(f"edit_{oid}"):
                            col_e1, col_e2 = st.columns(2)
                            e_name = col_e1.text_input("Tên", value=cust.get('name'))
                            e_phone = col_e2.text_input("SĐT", value=cust.get('phone'))
                            e_addr = st.text_input("ĐC", value=cust.get('address'))
                            
                            st.write("📋 **Sửa chi tiết hàng hóa (Sửa trực tiếp trong bảng):**")
                            # Chuyển items sang DataFrame để sửa
                            df_edit = pd.DataFrame(items)
                            
                            # Cấu hình bảng sửa: Cho phép thêm/xóa dòng
                            edited_df = st.data_editor(
                                df_edit, 
                                num_rows="dynamic",
                                column_config={
                                    "name": "Tên hàng",
                                    "unit": "ĐVT",
                                    "qty": st.column_config.NumberColumn("SL", min_value=1),
                                    "cost": st.column_config.NumberColumn("Giá Vốn"),
                                    "price": st.column_config.NumberColumn("Giá Bán"),
                                    "total": st.column_config.NumberColumn("Thành tiền (Tự tính)", disabled=True) 
                                },
                                key=f"editor_{oid}"
                            )
                            
                            # Tự động tính lại tổng tiền từ bảng đã sửa
                            # Lưu ý: total trong bảng chỉ để hiển thị, ta cần tính lại thực tế
                            new_items_list = edited_df.to_dict('records')
                            recalc_total = sum([row.get('qty', 0) * row.get('price', 0) for row in new_items_list])
                            
                            st.write(f"**Tổng tiền mới (Tự động cập nhật): {format_currency(recalc_total)}**")

                            if st.form_submit_button("Lưu Thay Đổi"):
                                # Cập nhật lại total cho từng dòng
                                for item in new_items_list:
                                    item['total'] = item.get('qty', 0) * item.get('price', 0)
                                
                                new_cust = {"name": e_name, "phone": e_phone, "address": e_addr}
                                
                                if edit_order_info(oid, new_cust, recalc_total, new_items_list):
                                    st.success("Đã cập nhật!")
                                    time.sleep(1)
                                    st.rerun()
                    
                    if st.button("🗑️ XÓA ĐƠN", key=f"del_{oid}", type="primary"):
                        if delete_order(oid):
                            st.warning("Đã xóa!")
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
                
                # Tính TT hoa hồng & TT thanh toán cho hiển thị
                comm_stat = fin.get('commission_status', 'Chưa chi')
                pay_stat = o.get('payment_status', 'Chưa TT')

                with st.expander(f"💰 {oid} | Nợ: {format_currency(debt)} | HH: {comm_stat}"):
                    c1, c2 = st.columns(2)
                    pay = c1.number_input("Thu:", 0.0, float(debt), float(debt), key=f"pay_{oid}")
                    
                    st.caption(f"Trạng thái hiện tại: {pay_stat}")
                    st.caption(f"Hoa hồng: {comm_stat}")

                    if c2.button("Thu Tiền", key=f"cf_{oid}"):
                        new_st = "Hoàn thành" if (debt - pay) <= 0 else "Công nợ"
                        pay_st = "Đã TT" if (debt - pay) <= 0 else "Cọc"
                        update_order_status(oid, new_st, pay_st, pay)
                        save_cash_log(datetime.now().strftime("%Y-%m-%d"), "Thu", pay, f"Thu {oid}")
                        st.success("Xong!")
                        st.rerun()
                    
                    if st.button("🗑️ Xóa đơn", key=f"deld_{oid}"):
                         if delete_order(oid): st.rerun()

        with tabs[5]: # Hoàn thành
            orders = [o for o in all_orders if o.get('status') == 'Hoàn thành']
            if orders:
                # Hiển thị bảng tổng hợp có thêm cột trạng thái
                data = []
                for o in orders:
                    data.append({
                        "Mã": o['order_id'],
                        "Khách": o['customer']['name'],
                        "Tổng": format_currency(o['financial']['total']),
                        "TT Thanh Toán": o.get('payment_status'),
                        "Hoa Hồng": o['financial'].get('commission_status', 'Chưa chi')
                    })
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
