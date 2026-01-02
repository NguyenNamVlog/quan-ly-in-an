import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime
from fpdf import FPDF
from docxtpl import DocxTemplate # Dùng cho Hợp đồng Word
import plotly.express as px
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials

# --- CẤU HÌNH ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit" # <--- THAY LINK CỦA BẠN
TEMPLATE_CONTRACT = 'Hop dong .docx' 
FONT_PATH = 'Arial.ttf' # Cần file font này để xuất PDF tiếng Việt

# --- HÀM HỖ TRỢ ---
def format_currency(value):
    if value is None: return "0"
    return "{:,.0f}".format(float(value))

def read_money_vietnamese(amount):
    try:
        return num2words(amount, lang='vi').capitalize() + " đồng chẵn."
    except:
        return "..................... đồng."

# --- KẾT NỐI GOOGLE SHEETS (Backend) ---
@st.cache_resource
def get_db_connection():
    try:
        if "service_account" not in st.secrets:
            st.error("Chưa cấu hình Secrets!")
            return None
        
        creds_dict = dict(st.secrets["service_account"])
        # Fix lỗi xuống dòng trong Private Key
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
        return None

# --- LOAD/SAVE DATA ---
def load_data(sheet_name):
    client = get_db_connection()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet(sheet_name)
        data = ws.get_all_records()
        return data
    except Exception as e:
        return []

def save_order(order_data):
    client = get_db_connection()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("Orders")
        except:
            ws = sh.add_worksheet("Orders", 1000, 20)
            ws.append_row(["order_id", "date", "status", "payment_status", "customer", "items", "financial"])
        
        # Load existing data
        all_data = load_data("Orders")
        
        # Check if update or new
        row_idx = -1
        for idx, row in enumerate(all_data):
            if str(row.get('order_id')) == str(order_data['order_id']):
                row_idx = idx + 2 # +2 vì dòng 1 là header, index bắt đầu từ 0
                break
        
        # Prepare row data (Convert dict/list to JSON string)
        row_values = [
            order_data['order_id'],
            order_data['date'],
            order_data['status'],
            order_data['payment_status'],
            json.dumps(order_data['customer'], ensure_ascii=False),
            json.dumps(order_data['items'], ensure_ascii=False),
            json.dumps(order_data['financial'], ensure_ascii=False)
        ]

        if row_idx > 0:
            # Update
            ws.update(f"A{row_idx}:G{row_idx}", [row_values])
        else:
            # Insert new
            ws.append_row(row_values)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu: {e}")
        return False

def save_cash_entry(entry):
    client = get_db_connection()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("Cashbook")
        except:
            ws = sh.add_worksheet("Cashbook", 1000, 10)
            ws.append_row(["date", "type", "amount", "category", "desc"])
        
        ws.append_row([entry['date'], entry['type'], entry['amount'], entry['category'], entry['desc']])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu sổ quỹ: {e}")
        return False

def gen_id():
    data = load_data("Orders")
    year = datetime.now().strftime("%y")
    count = len([d for d in data if str(d.get('order_id', '')).endswith(year)])
    return f"{count+1:03d}/DH.{year}"

# --- XUẤT PDF ---
class PDFGen(FPDF):
    def header(self):
        try:
            self.add_font('Arial', '', FONT_PATH, uni=True)
            self.set_font('Arial', '', 16)
            self.cell(0, 10, 'CÔNG TY IN ẤN AN LỘC PHÁT', 0, 1, 'C')
            self.set_font('Arial', '', 10)
            self.cell(0, 5, 'Biên Hòa, Đồng Nai', 0, 1, 'C')
            self.ln(10)
        except: pass

def create_pdf_doc(order, doc_type):
    pdf = PDFGen()
    pdf.add_page()
    
    # Check font
    try:
        pdf.add_font('Arial', '', FONT_PATH, uni=True)
        pdf.set_font('Arial', '', 12)
    except:
        st.warning("Thiếu font Arial.ttf, PDF có thể lỗi font.")
        pdf.set_font('Arial', '', 12)

    # Title
    pdf.set_font_size(18)
    pdf.cell(0, 10, doc_type, 0, 1, 'C')
    pdf.set_font_size(10)
    pdf.cell(0, 5, f"Số: {order['order_id']} | Ngày: {order['date']}", 0, 1, 'C')
    pdf.ln(5)

    # Customer
    cust = order.get('customer', {})
    if isinstance(cust, str): cust = json.loads(cust)
    
    pdf.cell(0, 8, f"Khách hàng: {cust.get('name')}", 0, 1)
    pdf.cell(0, 8, f"Địa chỉ: {cust.get('address')}", 0, 1)
    pdf.cell(0, 8, f"Điện thoại: {cust.get('phone')}", 0, 1)
    pdf.ln(5)

    # Table
    w = [10, 80, 20, 25, 25, 30] # Column widths
    headers = ["STT", "Tên hàng", "ĐVT", "SL", "Đơn giá", "Thành tiền"]
    
    # Header
    for i, h in enumerate(headers):
        pdf.cell(w[i], 8, h, 1, 0, 'C')
    pdf.ln()

    # Rows
    items = order.get('items', [])
    if isinstance(items, str): items = json.loads(items)
    
    total = 0
    for idx, item in enumerate(items):
        total += item['total']
        pdf.cell(w[0], 8, str(idx+1), 1, 0, 'C')
        pdf.cell(w[1], 8, str(item['name']), 1, 0)
        pdf.cell(w[2], 8, str(item.get('unit', 'Cái')), 1, 0, 'C')
        pdf.cell(w[3], 8, str(item['qty']), 1, 0, 'C')
        pdf.cell(w[4], 8, format_currency(item['price']), 1, 0, 'R')
        pdf.cell(w[5], 8, format_currency(item['total']), 1, 1, 'R')

    # Footer
    pdf.cell(sum(w)-30, 8, "TỔNG CỘNG:", 1, 0, 'R')
    pdf.cell(30, 8, format_currency(total), 1, 1, 'R')
    pdf.ln(5)
    pdf.multi_cell(0, 8, f"Bằng chữ: {read_money_vietnamese(total)}")
    
    return bytes(pdf.output())

# --- MÀN HÌNH CHÍNH ---
def main():
    st.set_page_config(page_title="Hệ Thống Quản Lý In Ấn", layout="wide", page_icon="🖨️")
    
    # Sidebar
    st.sidebar.header("DANH MỤC")
    menu = st.sidebar.radio("Chức năng", [
        "1. Tạo Báo Giá Mới", 
        "2. Quản Lý Đơn Hàng (Quy trình)", 
        "3. Sổ Quỹ Tiền Mặt", 
        "4. Thống Kê & Báo Cáo"
    ])

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá Mới":
        st.title("📝 Tạo Báo Giá Mới")
        
        with st.container(border=True):
            st.subheader("1. Thông tin khách hàng")
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Tên Khách")
            phone = c2.text_input("Số điện thoại")
            addr = c3.text_input("Địa chỉ")
            
            c4, c5 = st.columns(2)
            staff = c4.selectbox("Nhân viên KD", ["Nam", "Dương", "Thảo", "Khác"])
            
        with st.container(border=True):
            st.subheader("2. Chi tiết đơn hàng")
            if 'temp_items' not in st.session_state: st.session_state.temp_items = []
            
            with st.form("add_item"):
                f1, f2, f3, f4 = st.columns([3, 1, 1, 2])
                i_name = f1.text_input("Tên hàng / Quy cách")
                i_unit = f2.text_input("ĐVT", "Cái")
                i_qty = f3.number_input("SL", 1, 10000, 1)
                i_price = f4.number_input("Đơn giá", 0, step=1000)
                
                if st.form_submit_button("Thêm dòng"):
                    st.session_state.temp_items.append({
                        "name": i_name, "unit": i_unit, "qty": i_qty, 
                        "price": i_price, "total": i_qty*i_price
                    })
                    st.rerun()
            
            # Show items
            if st.session_state.temp_items:
                df_items = pd.DataFrame(st.session_state.temp_items)
                st.dataframe(df_items, use_container_width=True)
                
                total_val = df_items['total'].sum()
                st.metric("Tổng giá trị báo giá", format_currency(total_val))
                
                if st.button("LƯU & TẠO BÁO GIÁ", type="primary"):
                    if not name: st.error("Thiếu tên khách!"); return
                    
                    new_order = {
                        "order_id": gen_id(),
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá", # Trạng thái khởi tạo
                        "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": st.session_state.temp_items,
                        "financial": {"total": total_val, "paid": 0, "debt": total_val, "staff": staff}
                    }
                    if save_order(new_order):
                        st.success(f"Đã tạo đơn {new_order['order_id']} thành công!")
                        st.session_state.temp_items = []
                        time.sleep(1)
                        st.rerun()

    # --- TAB 2: QUẢN LÝ QUY TRÌNH (CORE) ---
    elif menu == "2. Quản Lý Đơn Hàng (Quy trình)":
        st.title("🏭 Quản Lý Quy Trình Đơn Hàng")
        
        # Load data
        raw_data = load_data("Orders")
        if not raw_data:
            st.info("Chưa có đơn hàng nào.")
            return

        # Parse data
        orders = []
        for r in raw_data:
            try:
                r['customer'] = json.loads(r['customer']) if isinstance(r['customer'], str) else r['customer']
                r['items'] = json.loads(r['items']) if isinstance(r['items'], str) else r['items']
                r['financial'] = json.loads(r['financial']) if isinstance(r['financial'], str) else r['financial']
                orders.append(r)
            except: continue
        
        # Filter Tabs
        tabs = st.tabs(["1. Báo Giá", "2. Thiết Kế", "3. Sản Xuất", "4. Giao Hàng", "5. Công Nợ", "6. Hoàn Thành"])
        
        # --- LOGIC QUY TRÌNH TỪNG BƯỚC ---
        
        # 1. TAB BÁO GIÁ
        with tabs[0]:
            lst = [o for o in orders if o['status'] == "Báo giá"]
            for o in lst:
                with st.expander(f"📄 {o['order_id']} - {o['customer']['name']} ({format_currency(o['financial']['total'])})"):
                    c1, c2 = st.columns(2)
                    # Input: PDF Báo giá
                    pdf = create_pdf_doc(o, "BÁO GIÁ")
                    if pdf: c1.download_button("Tải File Báo Giá (PDF)", pdf, f"BG_{o['order_id']}.pdf")
                    
                    # Logic: Duyệt -> Thiết kế
                    if c2.button("✅ Duyệt Báo Giá -> Chuyển Thiết Kế", key=f"app_{o['order_id']}"):
                        o['status'] = "Thiết kế"
                        save_order(o)
                        st.rerun()
                        
        # 2. TAB THIẾT KẾ
        with tabs[1]:
            lst = [o for o in orders if o['status'] == "Thiết kế"]
            for o in lst:
                with st.expander(f"🎨 {o['order_id']} - {o['customer']['name']}"):
                    st.info("Đang trong giai đoạn thiết kế...")
                    # Logic: Duyệt -> Sản xuất
                    if st.button("✅ Duyệt Thiết Kế -> Chuyển Sản Xuất", key=f"des_{o['order_id']}"):
                        o['status'] = "Sản xuất"
                        save_order(o)
                        st.rerun()

        # 3. TAB SẢN XUẤT
        with tabs[2]:
            lst = [o for o in orders if o['status'] == "Sản xuất"]
            for o in lst:
                with st.expander(f"⚙️ {o['order_id']} - {o['customer']['name']}"):
                    st.warning("Đang sản xuất...")
                    # Logic: Xong -> Giao hàng
                    if st.button("✅ SX Xong -> Chuyển Giao Hàng", key=f"prod_{o['order_id']}"):
                        o['status'] = "Giao hàng"
                        save_order(o)
                        st.rerun()

        # 4. TAB GIAO HÀNG
        with tabs[3]:
            lst = [o for o in orders if o['status'] == "Giao hàng"]
            for o in lst:
                with st.expander(f"🚚 {o['order_id']} - {o['customer']['name']}"):
                    c1, c2, c3 = st.columns(3)
                    # Output: Phiếu giao hàng
                    pdf_gh = create_pdf_doc(o, "PHIẾU GIAO HÀNG")
                    if pdf_gh: c1.download_button("In Phiếu Giao Hàng", pdf_gh, f"GH_{o['order_id']}.pdf")
                    
                    # Option: Hợp đồng
                    c2.download_button("Xuất Hợp Đồng (Word)", data=b"Demo Content", file_name="HopDong.docx", disabled=True, help="Cần file template .docx thực tế")

                    # Logic: Giao xong -> Công nợ
                    if c3.button("✅ Giao Xong -> Chuyển Công Nợ", key=f"del_{o['order_id']}"):
                        o['status'] = "Công nợ"
                        save_order(o)
                        st.rerun()

        # 5. TAB CÔNG NỢ
        with tabs[4]:
            lst = [o for o in orders if o['status'] == "Công nợ"]
            for o in lst:
                with st.expander(f"💰 {o['order_id']} - {o['customer']['name']} | Nợ: {format_currency(o['financial']['debt'])}"):
                    fin = o['financial']
                    
                    c1, c2 = st.columns(2)
                    pay_amount = c1.number_input("Nhập số tiền thu:", 0.0, float(fin['debt']), float(fin['debt']), key=f"pay_in_{o['order_id']}")
                    
                    if c2.button("Thu Tiền", key=f"pay_btn_{o['order_id']}"):
                        # Update Order
                        fin['paid'] += pay_amount
                        fin['debt'] = fin['total'] - fin['paid']
                        
                        # Logic: Hết nợ -> Hoàn thành
                        if fin['debt'] <= 0:
                            o['status'] = "Hoàn thành"
                            o['payment_status'] = "Đã TT"
                        else:
                            o['payment_status'] = "Cọc/Còn nợ"
                        
                        save_order(o)
                        
                        # Update Sổ quỹ
                        save_cash_entry({
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "type": "Thu",
                            "amount": pay_amount,
                            "category": "Thu tiền đơn hàng",
                            "desc": f"Thu đơn {o['order_id']}"
                        })
                        st.success("Đã thu tiền và cập nhật sổ quỹ!")
                        time.sleep(1)
                        st.rerun()

        # 6. TAB HOÀN THÀNH
        with tabs[5]:
            lst = [o for o in orders if o['status'] == "Hoàn thành"]
            if lst:
                df_view = pd.DataFrame([{
                    "Mã": x['order_id'], "Khách": x['customer']['name'], 
                    "Tổng": format_currency(x['financial']['total']), "Ngày": x['date']
                } for x in lst])
                st.dataframe(df_view, use_container_width=True)
            else:
                st.info("Chưa có đơn hàng hoàn thành.")

    # --- TAB 3: SỔ QUỸ ---
    elif menu == "3. Sổ Quỹ Tiền Mặt":
        st.title("💰 Sổ Quỹ Tiền Mặt")
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            with st.form("cash_entry"):
                d = st.date_input("Ngày")
                t = st.selectbox("Loại", ["Thu", "Chi"])
                a = st.number_input("Số tiền", 0, step=10000)
                cat = st.text_input("Hạng mục (VD: Tiền điện, Mua giấy...)")
                desc = st.text_area("Ghi chú")
                
                if st.form_submit_button("Lưu Giao Dịch"):
                    save_cash_entry({
                        "date": str(d), "type": t, "amount": a, 
                        "category": cat, "desc": desc
                    })
                    st.success("Đã lưu!")
                    st.rerun()

        with c2:
            raw_cash = load_data("Cashbook")
            if raw_cash:
                df = pd.DataFrame(raw_cash)
                # Tính toán
                df['amount'] = pd.to_numeric(df['amount'])
                thu = df[df['type'] == 'Thu']['amount'].sum()
                chi = df[df['type'] == 'Chi']['amount'].sum()
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Tổng Thu", format_currency(thu), delta="VNĐ")
                m2.metric("Tổng Chi", format_currency(chi), delta="-VNĐ", delta_color="inverse")
                m3.metric("Tồn Quỹ", format_currency(thu - chi))
                
                st.dataframe(df, use_container_width=True)

    # --- TAB 4: BÁO CÁO ---
    elif menu == "4. Thống Kê & Báo Cáo":
        st.title("📊 Báo Cáo Kinh Doanh")
        
        raw_data = load_data("Orders")
        if not raw_data: st.warning("Chưa có dữ liệu."); return

        # Prepare Data
        df_list = []
        for r in raw_data:
            try:
                fin = json.loads(r['financial']) if isinstance(r['financial'], str) else r['financial']
                df_list.append({
                    "Status": r['status'],
                    "Payment": r['payment_status'],
                    "Staff": fin.get('staff', 'Unknown'),
                    "Debt": fin.get('debt', 0),
                    "Revenue": fin.get('total', 0)
                })
            except: continue
            
        df = pd.DataFrame(df_list)
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("Đơn hàng theo Trạng thái")
            status_count = df['Status'].value_counts()
            fig = px.pie(values=status_count.values, names=status_count.index, hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
        with c2:
            st.subheader("Doanh số theo Nhân viên")
            staff_rev = df.groupby("Staff")["Revenue"].sum().reset_index()
            fig2 = px.bar(staff_rev, x="Staff", y="Revenue", text_auto=True)
            st.plotly_chart(fig2, use_container_width=True)
            
        st.subheader("Tình trạng Công nợ")
        st.metric("Tổng nợ khách hàng đang thiếu", format_currency(df['Debt'].sum()))

if __name__ == "__main__":
    main()
