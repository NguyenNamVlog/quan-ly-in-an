import streamlit as st
import pandas as pd
import json
from datetime import datetime
from fpdf import FPDF
from docxtpl import DocxTemplate
from num2words import num2words
from streamlit_gsheets import GSheetsConnection

# --- CẤU HÌNH HỆ THỐNG ---
TEMPLATE_CONTRACT = 'Hop dong .docx' 
FONT_PATH = 'Arial.ttf'

# [1] DÁN LINK GOOGLE SHEET CỦA BẠN VÀO DƯỚI ĐÂY:
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit" 

# [2] THÔNG TIN ĐĂNG NHẬP (ĐÚNG CHUẨN PYTHON DICTIONARY)
# Lưu ý: Tôi đã thay dấu '=' thành dấu ':' để không bị lỗi SyntaxError
CREDENTIALS_DICT = {
    "type": "service_account",
    "project_id": "quanlyinan",
    "private_key_id": "becc31a465356195dbb8352429f10ec4a76a3dad",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCRixepQSVgPNAl\nkGDUK4pLknV2ayZBPj2hSir4SE2Q0rm1D1fOBJAejCMvV23Crz3H+w9w7+ST08ci\nVQuVpm6Ous4fvZNtU9bzvh4soHWDUib7UqBIhgGs8Zjocs0tf555JxueTEp5Gppv\n8ycfxJ6HjXFUJyiz2WFOwgZXwcDOgiUxD/eKQdxfzDQI4MyvKj+iKA1sVJd6AALH\nkdwybJmMndWCBS/TcSn8ZdSEgn5JNrQnRXBtQVyUZ+uEz3iWupEHPlSlTsmIDyvq\nS5c+/RWLkrL22L2A8BIiQpVEGZc/KBgNOiag2PMX8yTixIbYTMpV6MbXUFYQAh/b\nzJu1ebOZAgMBAAECggEAKyJc9dWP3TDIw4lBmT/6MaGLXHgvE0D+BPI1P/Y1vskl\nLqsIa89gYx1HRD2WEw/asI0Qq3j9dm5aYytvTn/P3k8wzaliqxEg8IYU7Ub07OGJ\nGg0H4daNYpMLrUBw3J4o+mEDx2t22uNuh+U5YCnmjef2gWlFn9+5/hx0wsdyfAEV\n2HWP5dPpuWmCchkmvpA/+d8KO5laZ2u3bjYOzFnJqnu7GqWtesngSL15tjQZ5RnG\nlrJtkqy2N0YzlJB9CaQfsXvZ4hhuP6jjwG4SRXgcfFdWcErbC+M7HSaPAbnxpIfj\nqGLDd+h+Lk+QUg2yC9jXzT7+ar+x3b/MirGm9LCUzQKBgQDBPESsPYy+Z85bXKgX\n4YLYZtUnk0OHMSNyWeVeBeSYYdvuEbejo+1QZC0G5yJnCcV7gSMopnHNa08g4JBl\ndXbVRePMVMo4eVcfZ3fbtrGvW8GrIe2rVZpQ3bvDsj8OUXxNyOCyXQywFGCfuDWa\nS+6VzIN2nrKauxzX/w7R5uhCtwKBgQDA0Sz7QDcRKpnFRs4HAycSvqbQrAkCrCI1\n6EvhqpD3h1ftVqTTVvIWsKym0Pp/A2W7cYtjqic1lnYH09Ag7Y5r5r0kbA94ACqG\n8Cw6ixjM//zbmon+dHtRkr4YMu4dqUjvjN/yhdTap8MYIY5UYAtVGprywA4PFhU9\nZAH5b5IsLwKBgQCKw9Pw+LZUmckX1N8lXx2Od7JEnD1XHVN+L85GCedSApxkRzbf\n/b1TCM1I8rzCz8KQYXk1HOoGgTQuwPUQ1xzCJVFkD9O0YHbPJ4dsMbNB4ZufYFsD\nuhJ6VfEbpKohhyTD2yh5Ddcpr0iAClH7/uFTk60ohuhts0cQWapz0+Ug2wKBgQCD\npc36deujMtzujttYelSRPc6TpwI36uMov0Qf/d8gwi3MhF3hVfnQeCxJcWG2mtE4\n29t53tEKi4Jm8b2m3cth7JazaXxeSG7A1va7ugDi5tzz613QeCNCnNhhmVRuuAhu\nVlcJNUsRR32y2iZdgX37S0EEAREYR9GUqtWWQxEgTQKBgECULpGVDkRGSGLrCPPG\nep0iMdgunHhHc4Vdk01Nq0y/JGhCYAw1R910nm7jXnJM8C06U7srXWB45ohOC4w7\nhq1C9FMmWriEKSQyoQw1C4H9UePjezwn+MTHIRbQYlUMJQqIjQGMRfr4i+o8v8je\ncZ6vlyaYkVlaKQuZY25/HJA4\n-----END PRIVATE KEY-----\n",
    "client_email": "quanlyinan@quanlyinan.iam.gserviceaccount.com",
    "client_id": "105384981732403020965",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/quanlyinan%40quanlyinan.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

# --- HÀM TIỆN ÍCH ---
def format_currency(value):
    if value is None: return "0"
    try:
        return "{:,.0f}".format(float(value))
    except:
        return "0"

def read_money(amount):
    try:
        text = num2words(amount, lang='vi')
        return text.capitalize() + " đồng chẵn."
    except:
        return "..................... đồng."

# --- QUẢN LÝ DATABASE (KẾT NỐI TRỰC TIẾP) ---
def get_db_connection():
    try:
        # Sử dụng trực tiếp Dict đã khai báo ở trên
        conn = st.connection("gsheets", type=GSheetsConnection, **CREDENTIALS_DICT)
        return conn
    except Exception as e:
        st.error(f"Lỗi cấu hình Key: {e}")
        return None

def load_db():
    try:
        conn = get_db_connection()
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Orders", ttl=0)
        
        if df.empty: return []
        
        data = []
        for _, row in df.iterrows():
            item = row.to_dict()
            try:
                if isinstance(item.get('customer'), str): item['customer'] = json.loads(item['customer'])
                if isinstance(item.get('items'), str): item['items'] = json.loads(item['items'])
                if isinstance(item.get('financial'), str): item['financial'] = json.loads(item['financial'])
            except: continue
            data.append(item)
        return data
    except Exception as e:
        return []

def save_db(data):
    try:
        conn = get_db_connection()
        if not data:
            df = pd.DataFrame()
            conn.update(spreadsheet=SHEET_URL, worksheet="Orders", data=df)
            return

        data_to_save = []
        for item in data:
            clean_item = item.copy()
            clean_item['customer'] = json.dumps(item['customer'], ensure_ascii=False)
            clean_item['items'] = json.dumps(item['items'], ensure_ascii=False)
            clean_item['financial'] = json.dumps(item['financial'], ensure_ascii=False)
            data_to_save.append(clean_item)
            
        df = pd.DataFrame(data_to_save)
        conn.update(spreadsheet=SHEET_URL, worksheet="Orders", data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Lỗi lưu Database: {e}")

def load_cash():
    try:
        conn = get_db_connection()
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Cashbook", ttl=0)
        if df.empty: return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])
        return df
    except:
        return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])

def save_cash(df):
    try:
        conn = get_db_connection()
        conn.update(spreadsheet=SHEET_URL, worksheet="Cashbook", data=df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Lỗi lưu Sổ quỹ: {e}")

def generate_order_id():
    data = load_db()
    today = datetime.now()
    year_suffix = today.strftime("%y")
    count = 0
    if data:
        for item in data:
            if item.get('order_id', '').endswith(f".{year_suffix}"):
                count += 1
    return f"{count + 1:03d}/ĐHALP.{year_suffix}"

# --- XUẤT PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT', 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 5, 'ĐC: A1/204A, hẻm 244, đường Bùi Hữu Nghĩa, phường Biên Hòa, Đồng Nai', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Trang {self.page_no()}', 0, 0, 'C')

def create_pdf(order, doc_type="BÁO GIÁ"):
    pdf = PDFReport()
    try:
        pdf.add_font('Arial', '', FONT_PATH)
        pdf.add_font('Arial', 'B', FONT_PATH)
        pdf.add_font('Arial', 'I', FONT_PATH)
    except:
        st.error(f"Lỗi: Không tìm thấy file font {FONT_PATH}.")
        return None

    pdf.add_page()
    pdf.set_font('Arial', 'B', 18)
    pdf.cell(0, 10, doc_type, 0, 1, 'C')
    pdf.set_font('Arial', 'I', 11)
    pdf.cell(0, 6, f"Số: {order.get('order_id', '')}", 0, 1, 'C')
    pdf.cell(0, 6, f"Ngày: {order.get('date', '')}", 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_font('Arial', '', 11)
    c = order.get('customer', {})
    pdf.cell(0, 7, f"Kính gửi: {c.get('name', '')}", 0, 1)
    pdf.cell(0, 7, f"Đại diện: {c.get('contact', '')} - SĐT: {c.get('phone', '')}", 0, 1)
    pdf.cell(0, 7, f"Địa chỉ: {c.get('address', '')}", 0, 1)
    pdf.cell(0, 7, f"MST: {c.get('tax_code', '')}", 0, 1)
    pdf.ln(5)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font('Arial', 'B', 10)
    
    w_stt, w_ten, w_qc, w_sl, w_gia, w_tien = 10, 80, 30, 15, 25, 30
    if doc_type == "BÁO GIÁ":
        pdf.cell(w_stt, 10, "STT", 1, 0, 'C', 1)
        pdf.cell(w_ten, 10, "Tên Hàng / Quy Cách", 1, 0, 'C', 1)
        pdf.cell(w_qc, 10, "Kích thước", 1, 0, 'C', 1)
        pdf.cell(w_sl, 10, "SL", 1, 0, 'C', 1)
        pdf.cell(w_gia, 10, "Đơn giá", 1, 0, 'C', 1)
        pdf.cell(w_tien, 10, "Thành tiền", 1, 1, 'C', 1)
    else:
        pdf.cell(10, 10, "STT", 1, 0, 'C', 1)
        pdf.cell(90, 10, "Tên Hàng Hóa", 1, 0, 'C', 1)
        pdf.cell(20, 10, "ĐVT", 1, 0, 'C', 1)
        pdf.cell(20, 10, "SL", 1, 0, 'C', 1)
        pdf.cell(50, 10, "Ghi chú", 1, 1, 'C', 1)

    pdf.set_font('Arial', '', 10)
    items = order.get('items', [])
    total_val = 0
    for i, item in enumerate(items):
        if doc_type == "BÁO GIÁ":
            pdf.cell(w_stt, 10, str(i+1), 1, 0, 'C')
            pdf.cell(w_ten, 10, str(item.get('name', '')), 1, 0)
            pdf.cell(w_qc, 10, str(item.get('size', '')), 1, 0, 'C')
            pdf.cell(w_sl, 10, format_currency(item.get('qty', 0)), 1, 0, 'C')
            pdf.cell(w_gia, 10, format_currency(item.get('price', 0)), 1, 0, 'R')
            pdf.cell(w_tien, 10, format_currency(item.get('total', 0)), 1, 1, 'R')
            total_val += item.get('total', 0)
        else:
            pdf.cell(10, 10, str(i+1), 1, 0, 'C')
            pdf.cell(90, 10, f"{item.get('name','')} ({item.get('size','')})", 1, 0)
            pdf.cell(20, 10, "Cái", 1, 0, 'C')
            pdf.cell(20, 10, format_currency(item.get('qty', 0)), 1, 0, 'C')
            pdf.cell(50, 10, "", 1, 1)

    if doc_type == "BÁO GIÁ":
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(w_stt + w_ten + w_qc + w_sl + w_gia, 10, "TỔNG CỘNG:", 1, 0, 'R')
        pdf.cell(w_tien, 10, format_currency(total_val), 1, 1, 'R')
        pdf.set_font('Arial', 'I', 11)
        pdf.multi_cell(0, 10, f"Bằng chữ: {read_money(total_val)}")

    pdf.ln(10)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(95, 10, "KHÁCH HÀNG", 0, 0, 'C')
    pdf.cell(95, 10, "NHÀ CUNG CẤP", 0, 1, 'C')
    return bytes(pdf.output())

# --- XUẤT WORD ---
def create_contract(order):
    try:
        doc = DocxTemplate(TEMPLATE_CONTRACT)
        items = order.get('items', [])
        items_desc = "\n".join([f"- {i.get('name','')} ({i.get('size','')}) x {format_currency(i.get('qty',0))}" for i in items])
        total_val = order.get('financial', {}).get('total_revenue', 0)
        c = order.get('customer', {})
        context = {
            'contract_number': order.get('order_id', ''),
            'customer_name': c.get('name', ''),
            'address': c.get('address', ''),
            'tax_code': c.get('tax_code', ''),
            'contact_person': c.get('contact', ''),
            'phone': c.get('phone', ''),
            'product_name': items_desc,
            'total_amount': format_currency(total_val),
            'amount_in_words': read_money(total_val),
            'date_day': datetime.now().strftime("%d"),
            'date_month': datetime.now().strftime("%m"),
            'date_year': datetime.now().strftime("%Y")
        }
        doc.render(context)
        path = f"HD_{order.get('order_id','').replace('/','_')}.docx"
        doc.save(path)
        with open(path, "rb") as f: return f.read()
    except Exception as e:
        return None

# --- ĐĂNG NHẬP ---
def login_screen():
    st.title("🔐 Đăng Nhập Hệ Thống")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            submitted = st.form_submit_button("Đăng Nhập", use_container_width=True)
            if submitted:
                if username == "admin" and password == "admin":
                    st.session_state.logged_in = True
                    st.success("Thành công")
                    st.rerun()
                else:
                    st.error("Sai thông tin")

# --- APP ---
def run_app():
    st.sidebar.title(f"👤 Admin")
    if st.sidebar.button("Đăng Xuất"):
        st.session_state.logged_in = False
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.title("MENU QUẢN LÝ")
    menu = st.sidebar.radio("Chức năng:", ["1. Lên Đơn Mới / Sửa Đơn", "2. Quản Lý Đơn Hàng", "3. Quản Lý Tiền Mặt", "4. Báo Cáo"])

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'editing_order' not in st.session_state: st.session_state.editing_order = None

    # MODULE 1
    if menu == "1. Lên Đơn Mới / Sửa Đơn":
        mode = "EDIT" if st.session_state.editing_order else "NEW"
        order_title = st.session_state.editing_order['order_id'] if mode == 'EDIT' else 'TẠO ĐƠN HÀNG MỚI'
        st.title(f"📝 {order_title}")
        
        default_cust = {}
        if mode == "EDIT":
            default_cust = st.session_state.editing_order.get('customer', {})
            if not st.session_state.cart and st.session_state.editing_order.get('items'):
                st.session_state.cart = st.session_state.editing_order.get('items')
        
        with st.container():
            st.subheader("Thông tin Khách Hàng")
            c1, c2, c3 = st.columns(3)
            cust_name = c1.text_input("Tên Khách hàng", value=default_cust.get('name', ''))
            cust_contact = c2.text_input("Người liên hệ", value=default_cust.get('contact', ''))
            cust_phone = c3.text_input("SĐT", value=default_cust.get('phone', ''))
            c4, c5, c6 = st.columns(3)
            cust_addr = c4.text_input("Địa chỉ", value=default_cust.get('address', ''))
            cust_mst = c5.text_input("MST", value=default_cust.get('tax_code', ''))
            
            staff_opts = ["Nam", "Dương", "Thảo", "Khác"]
            default_staff_idx = 0
            if mode == "EDIT":
                saved_staff = st.session_state.editing_order.get('financial', {}).get('staff', '')
                if saved_staff in staff_opts: default_staff_idx = staff_opts.index(saved_staff)
            staff_name = c6.selectbox("Nhân viên KD", staff_opts, index=default_staff_idx)

        st.markdown("---")
        st.subheader("Chi tiết Hàng Hóa")
        with st.form("add_item", clear_on_submit=True):
            c_a, c_b, c_c, c_d = st.columns([3, 2, 1, 2])
            i_name = c_a.text_input("Tên hàng")
            i_size = c_b.text_input("Quy cách")
            i_qty = c_c.number_input("SL", min_value=1.0, value=1.0)
            i_price = c_d.number_input("Đơn giá bán", min_value=0.0, step=1000.0)
            with st.expander("Giá vốn & Hóa đơn (Nội bộ)"):
                ec1, ec2 = st.columns(2)
                i_cost = ec1.number_input("Giá vốn (Đơn giá)", min_value=0.0, step=1000.0)
                i_inv = ec2.number_input("Giá xuất HĐ (Đơn giá)", min_value=0.0, step=1000.0)
            if st.form_submit_button("➕ Thêm Hàng"):
                item = {"name": i_name, "size": i_size, "qty": i_qty, "price": i_price, 
                        "total": i_price * i_qty, "cost": i_cost * i_qty, "inv_price": i_inv}
                st.session_state.cart.append(item)
                st.rerun()

        if st.session_state.cart:
            st.write("### Danh sách hàng hóa:")
            for i, item in enumerate(st.session_state.cart):
                col_text, col_del = st.columns([8, 1])
                col_text.text(f"{i+1}. {item['name']} ({item['size']}) - SL: {item['qty']} - Tiền: {format_currency(item['total'])}")
                if col_del.button("❌", key=f"del_item_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()

            grand_total = sum(x['total'] for x in st.session_state.cart)
            grand_cost = sum(x['cost'] for x in st.session_state.cart)
            profit_gross = grand_total - grand_cost
            mgmt_fee = profit_gross * 0.1
            profit_net = profit_gross - mgmt_fee
            
            if staff_name in ["Nam", "Dương"]:
                comm_rate = 60.0
            else:
                comm_rate = st.number_input("Tỷ lệ hoa hồng (%)", value=10.0 if mode=="NEW" else st.session_state.editing_order.get('financial',{}).get('commission_rate', 10.0))
            comm_amt = profit_net * (comm_rate / 100)
            
            st.info(f"🔤 {read_money(grand_total)}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Tổng Cộng", format_currency(grand_total))
            m2.metric("Lợi Nhuận Ròng", format_currency(profit_net))
            m3.metric(f"Hoa Hồng ({comm_rate}%)", format_currency(comm_amt))
            
            st.markdown("---")
            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                btn_label = "💾 CẬP NHẬT ĐƠN HÀNG" if mode == "EDIT" else "💾 TẠO ĐƠN HÀNG MỚI"
                if st.button(btn_label, type="primary", use_container_width=True):
                    if not cust_name:
                        st.error("Thiếu tên khách hàng!")
                    else:
                        if mode == "NEW":
                            order_id = generate_order_id()
                            status = "Báo giá"
                            created_date = datetime.now().strftime("%d/%m/%Y")
                            comm_status = "Chưa TT"
                            pay_status = "Chưa TT"
                            data = load_db()
                        else:
                            order_id = st.session_state.editing_order['order_id']
                            status = st.session_state.editing_order['status']
                            created_date = st.session_state.editing_order['date']
                            comm_status = st.session_state.editing_order.get('financial', {}).get('commission_status', 'Chưa TT')
                            pay_status = st.session_state.editing_order.get('payment_status', 'Chưa TT')
                            data = load_db()
                            data = [x for x in data if x.get('order_id') != order_id]
                        
                        final_order = {
                            "order_id": order_id, "date": created_date, "status": status, "payment_status": pay_status,
                            "customer": {"name": cust_name, "contact": cust_contact, "phone": cust_phone, "address": cust_addr, "tax_code": cust_mst},
                            "items": st.session_state.cart,
                            "financial": {"total_revenue": grand_total, "total_cost": grand_cost, "profit_net": profit_net, 
                                          "commission": comm_amt, "commission_rate": comm_rate, "staff": staff_name, "commission_status": comm_status}
                        }
                        data.append(final_order)
                        save_db(data)
                        st.session_state.cart = []
                        st.session_state.editing_order = None
                        st.success(f"Đã lưu thành công đơn hàng {order_id}!")
                        st.rerun()
            with btn_col2:
                if mode == "EDIT":
                    if st.button("Hủy bỏ chế độ sửa", use_container_width=True):
                        st.session_state.editing_order = None
                        st.session_state.cart = []
                        st.rerun()

    # MODULE 2
    elif menu == "2. Quản Lý Đơn Hàng":
        st.title("🏭 Quản Lý Đơn Hàng")
        db = load_db()
        cols = ["Mã ĐH", "Khách hàng", "Tổng tiền", "Thanh toán", "Hoa hồng", "TT Hoa hồng", "Trạng thái", "NV"]
        view_data = []
        if db:
            for o in db:
                view_data.append({
                    "Mã ĐH": o.get('order_id', ''),
                    "Khách hàng": o.get('customer', {}).get('name', ''),
                    "Tổng tiền": o.get('financial', {}).get('total_revenue', 0),
                    "Thanh toán": o.get('payment_status', 'Chưa TT'),
                    "Hoa hồng": o.get('financial', {}).get('commission', 0),
                    "TT Hoa hồng": o.get('financial', {}).get('commission_status', 'Chưa TT'),
                    "Trạng thái": o.get('status', 'Báo giá'),
                    "NV": o.get('financial', {}).get('staff', '')
                })
        df_view = pd.DataFrame(view_data, columns=cols)
        tab_names = ["Tất cả", "Báo giá", "Thiết kế", "Sản xuất", "Giao hàng", "Hoàn thành"]
        tabs = st.tabs(tab_names)
        
        for i, tab_obj in enumerate(tabs):
            current_tab_name = tab_names[i]
            with tab_obj:
                if df_view.empty: curr_df = pd.DataFrame(columns=cols)
                else:
                    if current_tab_name == "Tất cả": curr_df = df_view
                    else: curr_df = df_view[df_view['Trạng thái'] == current_tab_name] if 'Trạng thái' in df_view.columns else pd.DataFrame(columns=cols)

                if not curr_df.empty:
                    show_df = curr_df.copy()
                    show_df['Tổng tiền'] = show_df['Tổng tiền'].apply(format_currency)
                    show_df['Hoa hồng'] = show_df['Hoa hồng'].apply(format_currency)
                    st.dataframe(show_df, use_container_width=True)
                    
                    st.write("---")
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        sel_id = st.selectbox(f"Chọn đơn hàng ({current_tab_name})", curr_df['Mã ĐH'].unique(), key=f"s_{i}")
                    if sel_id:
                        order_obj = next((x for x in db if x.get('order_id') == sel_id), None)
                        if order_obj:
                            with c2:
                                st.subheader(f"Thao tác: {sel_id}")
                                b1, b2, b3 = st.columns(3)
                                if b1.button("✏️ Sửa Đơn", key=f"ed_{sel_id}_{i}"):
                                    st.session_state.editing_order = order_obj
                                    st.session_state.cart = []
                                    st.success(f"Chuyển sửa {sel_id}...")
                                if b2.button("🗑️ Xóa Đơn", key=f"dl_{sel_id}_{i}"):
                                    if order_obj.get('status') == "Báo giá":
                                        new_db = [x for x in db if x.get('order_id') != sel_id]
                                        save_db(new_db)
                                        st.success("Đã xóa!")
                                        st.rerun()
                                    else: st.error("Chỉ xóa đơn 'Báo giá'")
                                steps = ["Báo giá", "Thiết kế", "Sản xuất", "Giao hàng", "Hoàn thành"]
                                curr_st = order_obj.get('status', 'Báo giá')
                                if curr_st in steps and steps.index(curr_st) < len(steps)-1:
                                    next_st = steps[steps.index(curr_st) + 1]
                                    if b3.button(f"⏩ Sang {next_st}", key=f"mv_{sel_id}_{i}"):
                                        order_obj['status'] = next_st
                                        save_db(db) # Save full db with updated item
                                        st.rerun()
                                
                                st.markdown("---")
                                c_fin1, c_fin2 = st.columns(2)
                                with c_fin1:
                                    pay_stat = order_obj.get('payment_status', 'Chưa TT')
                                    st.caption(f"Khách TT: {pay_stat}")
                                    if pay_stat == 'Chưa TT':
                                        if st.button("✅ Khách Đã Trả", key=f"pay_c_{sel_id}_{i}"):
                                            order_obj['payment_status'] = 'Đã TT'
                                            save_db(db)
                                            st.rerun()
                                    else:
                                        if st.button("❌ Hủy Khách Trả", key=f"unpay_c_{sel_id}_{i}"):
                                            order_obj['payment_status'] = 'Chưa TT'
                                            save_db(db)
                                            st.rerun()
                                with c_fin2:
                                    comm_stat = order_obj.get('financial', {}).get('commission_status', 'Chưa TT')
                                    st.caption(f"Hoa hồng: {comm_stat}")
                                    if comm_stat == 'Chưa TT':
                                        if st.button("💰 Đã Chi HH", key=f"pay_hh_{sel_id}_{i}"):
                                            order_obj['financial']['commission_status'] = 'Đã TT'
                                            save_db(db)
                                            st.rerun()
                                    else:
                                        if st.button("↩️ Hủy Chi HH", key=f"unpay_hh_{sel_id}_{i}"):
                                            order_obj['financial']['commission_status'] = 'Chưa TT'
                                            save_db(db)
                                            st.rerun()
                                
                                st.markdown("---")
                                p1, p2, p3 = st.columns(3)
                                with p1:
                                    pdf_bg = create_pdf(order_obj, "BÁO GIÁ")
                                    if pdf_bg: st.download_button("📄 Báo Giá", pdf_bg, f"BG_{sel_id.replace('/','_')}.pdf", key=f"btn_bg_{sel_id}_{i}")
                                with p2:
                                    doc_hd = create_contract(order_obj)
                                    if doc_hd: st.download_button("📝 Hợp Đồng", doc_hd, f"HD_{sel_id.replace('/','_')}.docx", key=f"btn_hd_{sel_id}_{i}")
                                with p3:
                                    if order_obj.get('status') in ["Giao hàng", "Hoàn thành"]:
                                        pdf_gh = create_pdf(order_obj, "PHIẾU GIAO HÀNG")
                                        if pdf_gh: st.download_button("🚚 Phiếu GH", pdf_gh, f"PGH_{sel_id.replace('/','_')}.pdf", key=f"btn_gh_{sel_id}_{i}")
                else:
                    if not df_view.empty: st.info(f"Không có đơn hàng nào ở trạng thái {current_tab_name}")

    # MODULE 3
    elif menu == "3. Quản Lý Tiền Mặt":
        st.title("💰 Sổ Quỹ Tiền Mặt")
        df_cash = load_cash()
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("cash"):
                d_date = st.date_input("Ngày")
                d_type = st.radio("Loại", ["Thu", "Chi"], horizontal=True)
                d_desc = st.text_input("Nội dung")
                d_amt = st.number_input("Số tiền", step=10000)
                if st.form_submit_button("Lưu Giao Dịch"):
                    new = {"Ngày": d_date, "Nội dung": d_desc, "Loại": d_type, "Số tiền": d_amt, "Ghi chú": ""}
                    df_cash = pd.concat([df_cash, pd.DataFrame([new])], ignore_index=True)
                    save_cash(df_cash)
                    st.success("Đã lưu")
        with c2:
            thu = df_cash[df_cash['Loại']=='Thu']['Số tiền'].sum()
            chi = df_cash[df_cash['Loại']=='Chi']['Số tiền'].sum()
            st.metric("Tồn Quỹ", format_currency(thu - chi))
            if not df_cash.empty:
                show_cash = df_cash.copy()
                show_cash['Số tiền'] = show_cash['Số tiền'].apply(format_currency)
                st.dataframe(show_cash, use_container_width=True)

    # MODULE 4
    elif menu == "4. Báo Cáo":
        st.title("📊 Báo Cáo Tổng Hợp")
        db = load_db()
        if db:
            data = []
            for o in db:
                financial = o.get('financial', {})
                data.append({
                    "NV": financial.get('staff', ''),
                    "Doanh thu": financial.get('total_revenue', 0),
                    "Chi phí": financial.get('total_cost', 0),
                    "Lợi nhuận": financial.get('profit_net', 0),
                    "Hoa hồng": financial.get('commission', 0),
                    "TT Hoa hồng": financial.get('commission_status', 'Chưa TT'),
                    "Thanh toán": o.get('payment_status', 'Chưa TT'),
                    "Trạng thái": o.get('status', 'Báo giá')
                })
            df = pd.DataFrame(data)
            
            st.subheader("1. Tài Chính Doanh Nghiệp")
            total_rev = df['Doanh thu'].sum()
            total_cost = df['Chi phí'].sum()
            total_prof = df['Lợi nhuận'].sum()
            total_debt = df[df['Thanh toán'] == 'Chưa TT']['Doanh thu'].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Doanh Thu", format_currency(total_rev))
            k2.metric("Chi Phí", format_currency(total_cost))
            k3.metric("Lợi Nhuận", format_currency(total_prof))
            k4.metric("Tổng Công Nợ", format_currency(total_debt), delta="Chưa thu", delta_color="inverse")
            st.markdown("---")

            st.subheader("2. Tình Hình Hoa Hồng")
            df['HH Đã Chi'] = df.apply(lambda x: x['Hoa hồng'] if x['TT Hoa hồng'] == 'Đã TT' else 0, axis=1)
            df['HH Chưa Chi'] = df.apply(lambda x: x['Hoa hồng'] if x['TT Hoa hồng'] == 'Chưa TT' else 0, axis=1)
            
            total_comm = df['Hoa hồng'].sum()
            paid_comm = df['HH Đã Chi'].sum()
            unpaid_comm = df['HH Chưa Chi'].sum()
            
            h1, h2, h3 = st.columns(3)
            h1.metric("Tổng Quỹ Hoa Hồng", format_currency(total_comm))
            h2.metric("Đã Chi Trả", format_currency(paid_comm), delta="Đã TT")
            h3.metric("Còn Nợ NV", format_currency(unpaid_comm), delta="-Nợ", delta_color="inverse")
            st.markdown("---")

            g1, g2 = st.columns(2)
            with g1:
                st.subheader("Tỷ lệ Trạng Thái Đơn")
                if not df.empty:
                    cnt = df['Trạng thái'].value_counts().reset_index()
                    cnt.columns = ['Trạng thái', 'Số lượng']
                    fig = px.pie(cnt, values='Số lượng', names='Trạng thái', hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)
            with g2:
                st.subheader("Hiệu Quả Kinh Doanh theo NV")
                if not df.empty:
                    grp_nv = df.groupby("NV")[['Doanh thu', 'Hoa hồng']].sum().reset_index()
                    fig_bar = px.bar(grp_nv, x="NV", y="Doanh thu", text_auto='.2s')
                    st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("📋 Chi tiết Hoa hồng từng Nhân viên")
            if not df.empty:
                grp_staff = df.groupby("NV")[['Doanh thu', 'Hoa hồng', 'HH Đã Chi', 'HH Chưa Chi']].sum().reset_index()
                show_staff = grp_staff.copy()
                for c in ['Doanh thu', 'Hoa hồng', 'HH Đã Chi', 'HH Chưa Chi']:
                    show_staff[c] = show_staff[c].apply(format_currency)
                st.dataframe(show_staff, use_container_width=True)
        else:
            st.warning("Chưa có dữ liệu.")

def main():
    st.set_page_config(page_title="Phần Mềm Quản Lý In Ấn ALP", layout="wide", page_icon="🖨️")
    st.markdown("<style>.stMetric {background-color: #f0f2f6; padding: 10px; border-radius: 5px;}</style>", unsafe_allow_html=True)
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        login_screen()
    else:
        run_app()

if __name__ == "__main__":
    main()
