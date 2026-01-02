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

# [2] THÔNG TIN ĐĂNG NHẬP
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

# --- QUẢN LÝ DATABASE (ĐÃ SỬA LỖI TRÙNG TYPE) ---
def get_db_connection():
    try:
        # Tạo bản sao của cấu hình để xử lý
        creds = CREDENTIALS_DICT.copy()
        
        # [QUAN TRỌNG] Xóa key 'type' trong dict để tránh xung đột với tham số của st.connection
        if "type" in creds:
            del creds["type"]

        # Truyền các tham số còn lại vào
        conn = st.connection("gsheets", type=GSheetsConnection, **creds)
        return conn
    except Exception as e:
        st.error(f"Lỗi kết nối: {e}")
        return None

def load_db():
    try:
        conn = get_db_connection()
        if conn is None: return []
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
        if conn is None: return

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
        if conn is None: return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])
        
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Cashbook", ttl=0)
        if df.empty: return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])
        return df
    except:
        return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])

def save_cash(df):
    try:
        conn = get_db_connection()
        if conn is None: return
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
        
        default_cust =
