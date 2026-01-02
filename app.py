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

# --- CẤU HÌNH HỆ THỐNG ---
TEMPLATE_CONTRACT = 'Hop dong .docx' 
FONT_PATH = 'Arial.ttf'

# [QUAN TRỌNG] Thay Link Google Sheet của bạn vào đây
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit" 

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

# --- KẾT NỐI GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets:
            st.error("⚠️ Chưa cấu hình Secrets!")
            return None

        creds_dict = dict(st.secrets["service_account"])
        # Fix lỗi xuống dòng trong private key
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Lỗi kết nối Google: {e}")
        return None

# --- XỬ LÝ DỮ LIỆU (DATABASE) ---
def load_db():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        worksheet = sh.worksheet("Orders")
        all_records = worksheet.get_all_records()
        
        # Nếu sheet rỗng
        if not all_records: return []

        data = []
        for item in all_records:
            try:
                # Parse các chuỗi JSON lại thành Dict/List Python
                # Google Sheet lưu dict dưới dạng string, ta cần json.loads để code hiểu
                if 'customer' in item and isinstance(item['customer'], str) and item['customer'].strip():
                    item['customer'] = json.loads(item['customer'])
                else: item['customer'] = {}

                if 'items' in item and isinstance(item['items'], str) and item['items'].strip():
                    item['items'] = json.loads(item['items'])
                else: item['items'] = []

                if 'financial' in item and isinstance(item['financial'], str) and item['financial'].strip():
                    item['financial'] = json.loads(item['financial'])
                else: item['financial'] = {}
                
                data.append(item)
            except Exception as e:
                # Bỏ qua dòng lỗi để không sập app
                continue
        return data
    except gspread.WorksheetNotFound:
        return []
    except Exception as e:
        # Nếu lỗi quyền 403, thông báo
        if "403" in str(e): st.error("Lỗi quyền truy cập Sheet. Hãy share quyền Editor cho email trong secrets.")
        return []

def save_db(data):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            worksheet = sh.worksheet("Orders")
        except:
            worksheet = sh.add_worksheet(title="Orders", rows=1000, cols=20)

        if not data:
            worksheet.clear()
            return

        # Chuẩn bị dữ liệu để lưu (Dict -> JSON String)
        data_to_save = []
        for item in data:
            row = item.copy()
            row['customer'] = json.dumps(item['customer'], ensure_ascii=False)
            row['items'] = json.dumps(item['items'], ensure_ascii=False)
            row['financial'] = json.dumps(item['financial'], ensure_ascii=False)
            data_to_save.append(row)
        
        df = pd.DataFrame(data_to_save)
        
        # Chuyển đổi tất cả thành string để đảm bảo không lỗi khi ghi vào sheet
        df = df.astype(str)

        worksheet.clear()
        # Ghi header và data
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.cache_data.clear() # Xóa cache để cập nhật mới
        
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")

def load_cash():
    client = get_gspread_client()
    if not client: return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])
    try:
        sh = client.open_by_url(SHEET_URL)
        worksheet = sh.worksheet("Cashbook")
        data = worksheet.get_all_records()
        if not data: return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])
        return pd.DataFrame(data)
    except:
        return pd.DataFrame(columns=["Ngày", "Nội dung", "Loại", "Số tiền", "Ghi chú"])

def save_cash(df):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            worksheet = sh.worksheet("Cashbook")
        except:
            worksheet = sh.add_worksheet(title="Cashbook", rows=1000, cols=10)
        
        worksheet.clear()
        if not df.empty:
            df_str = df.astype(str)
            worksheet.update([df_str.columns.values.tolist()] + df_str.values.tolist())
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Lỗi lưu sổ quỹ: {e}")

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

# --- XUẤT PDF & WORD (GIỮ NGUYÊN) ---
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
        st.warning("Không tìm thấy font Arial. Sử dụng font mặc định (có thể lỗi tiếng Việt).")
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
    
    # Table Header
    pdf.cell(10, 10, "STT", 1, 0, 'C', 1)
    pdf.cell(80, 10, "Tên Hàng / Quy Cách", 1, 0, 'C', 1)
    pdf.cell(30, 10, "Kích thước", 1, 0, 'C', 1)
    pdf.cell(15, 10, "SL", 1, 0, 'C', 1)
    pdf.cell(25, 10, "Đơn giá", 1, 0, 'C', 1)
    pdf.cell(30, 10, "Thành tiền", 1, 1, 'C', 1)

    pdf.set_font('Arial', '', 10)
    items = order.get('items', [])
    total_val = 0
    for i, item in enumerate(items):
        # Kiểm tra item là dict
        if not isinstance(item, dict): continue
        
        pdf.cell(10, 10, str(i+1), 1, 0, 'C')
        pdf.cell(80, 10, str(item.get('name', '')), 1, 0)
        pdf.cell(30, 10, str(item.get('size', '')), 1, 0, 'C')
        pdf.cell(15, 10, format_currency(item.get('qty', 0)), 1, 0, 'C')
        pdf.cell(25, 10, format_currency(item.get('price', 0)), 1, 0, 'R')
        total_item = item.get('total', 0)
        pdf.cell(30, 10, format_currency(total_item), 1, 1, 'R')
        total_val += total_item

    pdf.set_font('Arial', 'B', 11)
    pdf.cell(160, 10, "TỔNG CỘNG:", 1, 0, 'R')
    pdf.cell(30, 10, format_currency(total_val), 1, 1, 'R')
    pdf.ln(5)
    pdf.set_font('Arial', 'I', 11)
    pdf.multi_cell(0, 10, f"Bằng chữ: {read_money(total_val)}")
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(95, 10, "KHÁCH HÀNG", 0, 0, 'C')
    pdf.cell(95, 10, "NHÀ CUNG CẤP", 0, 1, 'C')
    return bytes(pdf.output())

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
    except: return None

# --- LOGIN ---
def login_screen():
    st.title("🔐 Đăng Nhập")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            username = st.text_input("Tên đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("Đăng Nhập", use_container_width=True):
                if username == "admin" and password == "admin":
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Sai thông tin!")

# --- MAIN APP ---
def run_app():
    st.sidebar.title(f"👤 Admin")
    if st.sidebar.button("Đăng Xuất"):
        st.session_state.logged_in = False
        st.rerun()
    
    menu = st.sidebar.radio("Menu", ["1. Lên Đơn Mới / Sửa", "2. Quản Lý Đơn Hàng", "3. Sổ Quỹ", "4. Báo Cáo"])

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'editing_order' not in st.session_state: st.session_state.editing_order = None

    # --- TAB 1: LÊN ĐƠN ---
    if menu == "1. Lên Đơn Mới / Sửa":
        mode = "EDIT" if st.session_state.editing_order else "NEW"
        st.title(f"📝 {('SỬA ĐƠN: ' + st.session_state.editing_order['order_id']) if mode=='EDIT' else 'TẠO ĐƠN MỚI'}")
        
        # Load data cũ nếu đang sửa
        default_cust = {}
        if mode == "EDIT":
            default_cust = st.session_state.editing_order.get('customer', {})
            # Chỉ load lại giỏ hàng nếu giỏ hàng hiện tại đang trống (để tránh overwrite khi đang sửa dở)
            if not st.session_state.cart and st.session_state.editing_order.get('items'):
                st.session_state.cart = st.session_state.editing_order.get('items')

        with st.container():
            st.subheader("Khách Hàng")
            c1, c2, c3 = st.columns(3)
            cust_name = c1.text_input("Tên KH", value=default_cust.get('name', ''))
            cust_contact = c2.text_input("Người LH", value=default_cust.get('contact', ''))
            cust_phone = c3.text_input("SĐT", value=default_cust.get('phone', ''))
            c4, c5, c6 = st.columns(3)
            cust_addr = c4.text_input("Địa chỉ", value=default_cust.get('address', ''))
            cust_mst = c5.text_input("MST", value=default_cust.get('tax_code', ''))
            
            # Nhân viên
            staffs = ["Nam", "Dương", "Thảo", "Khác"]
            s_idx = 0
            if mode == "EDIT":
                s_val = st.session_state.editing_order.get('financial', {}).get('staff', '')
                if s_val in staffs: s_idx = staffs.index(s_val)
            staff_name = c6.selectbox("Nhân viên", staffs, index=s_idx)

        st.divider()
        
        # Form thêm hàng
        with st.form("add_item", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns([3, 2, 1, 2])
            i_name = c1.text_input("Tên hàng")
            i_size = c2.text_input("Quy cách")
            i_qty = c3.number_input("SL", 1.0, step=1.0)
            i_price = c4.number_input("Giá bán", 0.0, step=1000.0)
            
            with st.expander("Giá vốn (Nội bộ)"):
                ec1, ec2 = st.columns(2)
                i_cost = ec1.number_input("Giá vốn", 0.0, step=1000.0)
                i_inv = ec2.number_input("Giá HĐ", 0.0, step=1000.0)
                
            if st.form_submit_button("➕ Thêm vào giỏ"):
                st.session_state.cart.append({
                    "name": i_name, "size": i_size, "qty": i_qty, "price": i_price,
                    "total": i_qty * i_price, "cost": i_qty * i_cost, "inv_price": i_inv
                })
                st.rerun()

        # Hiển thị giỏ hàng
        if st.session_state.cart:
            st.write("---")
            for idx, item in enumerate(st.session_state.cart):
                c_text, c_del = st.columns([9, 1])
                c_text.text(f"{idx+1}. {item['name']} ({item['size']}) | SL: {item['qty']} | Tiền: {format_currency(item['total'])}")
                if c_del.button("❌", key=f"del_{idx}"):
                    st.session_state.cart.pop(idx)
                    st.rerun()
            
            # Tính toán tài chính
            total_rev = sum(x['total'] for x in st.session_state.cart)
            total_cost = sum(x['cost'] for x in st.session_state.cart)
            gross_profit = total_rev - total_cost
            net_profit = gross_profit * 0.9 # Trừ 10% quản lý phí
            
            # Hoa hồng
            comm_rate = 60.0 if staff_name in ["Nam", "Dương"] else 10.0
            if mode == "EDIT": 
                comm_rate = st.session_state.editing_order.get('financial', {}).get('commission_rate', comm_rate)
            
            comm_rate = st.number_input("Hoa hồng (%)", value=float(comm_rate))
            comm_amt = net_profit * (comm_rate / 100)

            c1, c2, c3 = st.columns(3)
            c1.metric("Tổng đơn", format_currency(total_rev))
            c2.metric("Lợi nhuận ròng", format_currency(net_profit))
            c3.metric(f"Hoa hồng ({comm_rate}%)", format_currency(comm_amt))

            # Nút Lưu
            if st.button("💾 LƯU ĐƠN HÀNG", type="primary", use_container_width=True):
                if not cust_name:
                    st.error("Chưa nhập tên khách!")
                else:
                    db = load_db()
                    if mode == "NEW":
                        order_id = generate_order_id()
                        status = "Báo giá"
                        date_str = datetime.now().strftime("%d/%m/%Y")
                        pay_st = "Chưa TT"
                        comm_st = "Chưa TT"
                    else:
                        order_id = st.session_state.editing_order['order_id']
                        status = st.session_state.editing_order['status']
                        date_str = st.session_state.editing_order['date']
                        pay_st = st.session_state.editing_order.get('payment_status', 'Chưa TT')
                        comm_st = st.session_state.editing_order.get('financial', {}).get('commission_status', 'Chưa TT')
                        # Xóa đơn cũ để lưu đè
                        db = [x for x in db if x.get('order_id') != order_id]

                    new_order = {
                        "order_id": order_id, "date": date_str, "status": status, "payment_status": pay_st,
                        "customer": {"name": cust_name, "contact": cust_contact, "phone": cust_phone, "address": cust_addr, "tax_code": cust_mst},
                        "items": st.session_state.cart,
                        "financial": {"total_revenue": total_rev, "total_cost": total_cost, "profit_net": net_profit, 
                                      "commission": comm_amt, "commission_rate": comm_rate, "staff": staff_name, "commission_status": comm_st}
                    }
                    db.append(new_order)
                    save_db(db)
                    st.success(f"Đã lưu đơn {order_id}")
                    st.session_state.cart = []
                    st.session_state.editing_order = None
                    time.sleep(1)
                    st.rerun()
            
            if mode == "EDIT":
                if st.button("Hủy sửa"):
                    st.session_state.editing_order = None
                    st.session_state.cart = []
                    st.rerun()

    # --- MODULE 2: QUẢN LÝ ĐƠN HÀNG (HIỂN THỊ NÚT ĐẦY ĐỦ) ---
    elif menu == "2. Quản Lý Đơn Hàng":
        st.title("🏭 Quản Lý Đơn Hàng")
        db = load_db()
        
        # Chuẩn bị Dataframe hiển thị
        view_data = []
        for o in db:
            view_data.append({
                "Mã ĐH": o.get('order_id'),
                "Khách hàng": o.get('customer', {}).get('name'),
                "Tổng tiền": o.get('financial', {}).get('total_revenue', 0),
                "Thanh toán": o.get('payment_status', 'Chưa TT'),
                "Trạng thái": o.get('status', 'Báo giá'),
                "NV": o.get('financial', {}).get('staff', '')
            })
        
        df = pd.DataFrame(view_data)
        
        # Tabs lọc trạng thái
        tabs = st.tabs(["Tất cả", "Báo giá", "Thiết kế", "Sản xuất", "Giao hàng", "Hoàn thành"])
        
        for i, tab in enumerate(tabs):
            with tab:
                status_filter = ["Tất cả", "Báo giá", "Thiết kế", "Sản xuất", "Giao hàng", "Hoàn thành"][i]
                
                # Lọc dữ liệu theo tab
                if status_filter == "Tất cả":
                    filtered_df = df
                else:
                    filtered_df = df[df['Trạng thái'] == status_filter] if not df.empty else df

                if not filtered_df.empty:
                    # Format tiền tệ hiển thị
                    display_df = filtered_df.copy()
                    display_df['Tổng tiền'] = display_df['Tổng tiền'].apply(format_currency)
                    st.dataframe(display_df, use_container_width=True)
                    
                    st.divider()
                    
                    # Chọn đơn hàng để thao tác
                    col_sel, col_act = st.columns([1, 2])
                    with col_sel:
                        selected_id = st.selectbox(f"Chọn đơn ({status_filter})", filtered_df['Mã ĐH'].unique(), key=f"sel_{i}")
                    
                    # Tìm object đơn hàng gốc trong db
                    order_obj = next((item for item in db if item.get('order_id') == selected_id), None)
                    
                    if order_obj:
                        with col_act:
                            st.subheader(f"Thao tác: {selected_id}")
                            
                            # Hàng 1: Nút chức năng chính
                            b1, b2, b3 = st.columns(3)
                            if b1.button("✏️ Sửa", key=f"edit_{selected_id}_{i}"):
                                st.session_state.editing_order = order_obj
                                st.session_state.cart = [] # Reset cart để load từ order
                                st.success("Đã chuyển sang tab Sửa Đơn")
                            
                            if b2.button("🗑️ Xóa", key=f"del_{selected_id}_{i}"):
                                if order_obj.get('status') == "Báo giá":
                                    new_db = [x for x in db if x.get('order_id') != selected_id]
                                    save_db(new_db)
                                    st.success("Đã xóa!")
                                    st.rerun()
                                else:
                                    st.error("Chỉ được xóa đơn 'Báo giá'!")

                            # Nút chuyển trạng thái
                            steps = ["Báo giá", "Thiết kế", "Sản xuất", "Giao hàng", "Hoàn thành"]
                            curr_st = order_obj.get('status', 'Báo giá')
                            if curr_st in steps and steps.index(curr_st) < len(steps) - 1:
                                next_st = steps[steps.index(curr_st) + 1]
                                if b3.button(f"⏩ {next_st}", key=f"next_{selected_id}_{i}"):
                                    order_obj['status'] = next_st
                                    save_db(db)
                                    st.rerun()

                            st.markdown("---")
                            
                            # Hàng 2: Tài chính
                            c_pay, c_comm = st.columns(2)
                            with c_pay:
                                st.caption(f"Khách: {order_obj.get('payment_status')}")
                                if order_obj.get('payment_status') == 'Chưa TT':
                                    if st.button("Đã Thu Tiền", key=f"p_{selected_id}_{i}"):
                                        order_obj['payment_status'] = 'Đã TT'
                                        save_db(db)
                                        st.rerun()
                                else:
                                    if st.button("Hủy Thu Tiền", key=f"unp_{selected_id}_{i}"):
                                        order_obj['payment_status'] = 'Chưa TT'
                                        save_db(db)
                                        st.rerun()
                            
                            with c_comm:
                                comm_st = order_obj.get('financial', {}).get('commission_status', 'Chưa TT')
                                st.caption(f"HH: {comm_st}")
                                if comm_st == 'Chưa TT':
                                    if st.button("Đã Chi HH", key=f"cm_{selected_id}_{i}"):
                                        order_obj['financial']['commission_status'] = 'Đã TT'
                                        save_db(db)
                                        st.rerun()
                            
                            st.markdown("---")
                            
                            # Hàng 3: In ấn
                            p1, p2, p3 = st.columns(3)
                            with p1:
                                pdf_data = create_pdf(order_obj, "BÁO GIÁ")
                                if pdf_data: st.download_button("📄 Báo Giá", pdf_data, f"BG_{selected_id}.pdf", key=f"dl_bg_{selected_id}_{i}")
                            with p2:
                                if order_obj.get('status') in ["Giao hàng", "Hoàn thành"]:
                                    pdf_gh = create_pdf(order_obj, "PHIẾU GIAO HÀNG")
                                    if pdf_gh: st.download_button("🚚 Phiếu GH", pdf_gh, f"GH_{selected_id}.pdf", key=f"dl_gh_{selected_id}_{i}")
                            with p3:
                                doc_data = create_contract(order_obj)
                                if doc_data: st.download_button("📝 Hợp Đồng", doc_data, f"HD_{selected_id}.docx", key=f"dl_hd_{selected_id}_{i}")

                else:
                    st.info("Không có đơn hàng nào.")

    # --- MODULE 3: SỔ QUỸ ---
    elif menu == "3. Quản Lý Tiền Mặt":
        st.title("💰 Sổ Quỹ")
        df_cash = load_cash()
        
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("cash_form"):
                d_date = st.date_input("Ngày")
                d_type = st.radio("Loại", ["Thu", "Chi"], horizontal=True)
                d_desc = st.text_input("Nội dung")
                d_amt = st.number_input("Số tiền", step=10000)
                if st.form_submit_button("Lưu"):
                    new_row = {"Ngày": str(d_date), "Nội dung": d_desc, "Loại": d_type, "Số tiền": d_amt, "Ghi chú": ""}
                    df_cash = pd.concat([df_cash, pd.DataFrame([new_row])], ignore_index=True)
                    save_cash(df_cash)
                    st.success("Đã lưu")
                    st.rerun()
        
        with c2:
            thu = df_cash[df_cash['Loại']=='Thu']['Số tiền'].sum()
            chi = df_cash[df_cash['Loại']=='Chi']['Số tiền'].sum()
            st.metric("Tồn Quỹ Hiện Tại", format_currency(thu - chi))
            
            show_df = df_cash.copy()
            show_df['Số tiền'] = show_df['Số tiền'].apply(format_currency)
            st.dataframe(show_df, use_container_width=True)

    # --- MODULE 4: BÁO CÁO ---
    elif menu == "4. Báo Cáo":
        st.title("📊 Báo Cáo")
        db = load_db()
        if db:
            # Chuyển đổi list of dicts thành dataframe phẳng để dễ visualize
            flat_data = []
            for o in db:
                fin = o.get('financial', {})
                flat_data.append({
                    "NV": fin.get('staff', ''),
                    "Doanh thu": fin.get('total_revenue', 0),
                    "Chi phí": fin.get('total_cost', 0),
                    "Lợi nhuận": fin.get('profit_net', 0),
                    "Hoa hồng": fin.get('commission', 0),
                    "Trạng thái": o.get('status'),
                    "Thanh toán": o.get('payment_status')
                })
            df = pd.DataFrame(flat_data)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Tổng Doanh Thu", format_currency(df['Doanh thu'].sum()))
            c2.metric("Tổng Lợi Nhuận", format_currency(df['Lợi nhuận'].sum()))
            c3.metric("Tổng Hoa Hồng", format_currency(df['Hoa hồng'].sum()))
            
            st.divider()
            
            g1, g2 = st.columns(2)
            with g1:
                st.write("Doanh thu theo Nhân viên")
                fig = px.bar(df.groupby("NV")['Doanh thu'].sum().reset_index(), x="NV", y="Doanh thu", text_auto=True)
                st.plotly_chart(fig, use_container_width=True)
            with g2:
                st.write("Tỷ lệ trạng thái đơn")
                fig2 = px.pie(df, names="Trạng thái")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu báo cáo.")

if __name__ == "__main__":
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if not st.session_state.logged_in: login_screen()
    else: run_app()
