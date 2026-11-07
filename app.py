import streamlit as st
import pandas as pd
import json
import time
import os
import requests
import unicodedata
import traceback
import io
import re
from datetime import datetime
from fpdf import FPDF
from num2words import num2words
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px

# Thư viện xử lý xuất file Word (.docx)
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

# --- CẤU HÌNH ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1Oq3fo2vK-LGHMZq3djZ3mmX5TZMGVZeJVu-MObC5_cU/edit"
FONT_FILENAME = 'arial.ttf' 
HEADER_IMAGE = 'tieu_de.png'

# --- HÀM HỖ TRỢ CHUNG ---
def remove_accents(input_str):
    if not input_str: return ""
    input_str = str(input_str)
    s = input_str.replace('đ', 'd').replace('Đ', 'D')
    nfkd_form = unicodedata.normalize('NFKD', s)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def format_currency(value):
    if value is None: return "0"
    try:
        val = float(value)
        if val.is_integer():
            return "{:,.0f}".format(val).replace(",", ".")
        else:
            return "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0"

def read_money_vietnamese(amount):
    try:
        num = int(round(float(amount)))
        if num == 0: return "Không đồng chẵn."
        text = num2words(num, lang='vi').capitalize()
        text = text.replace("mươi một", "mươi mốt")
        return text + " đồng chẵn."
    except:
        return "..................... đồng chẵn."

# --- KẾT NỐI GOOGLE SHEETS ---
@st.cache_resource
def get_gspread_client():
    try:
        if "service_account" not in st.secrets:
            st.error("❌ Lỗi: Không tìm thấy mục [service_account] trong st.secrets")
            return None
        
        creds_dict = dict(st.secrets["service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"⚠️ Lỗi kết nối Google: {e}")
        return None

# --- QUẢN LÝ KHÁCH HÀNG ---
def fetch_customers():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Customers")
        except: return [] 
        return ws.get_all_records()
    except: return []

def save_customer_db(name, phone, address):
    client = get_gspread_client()
    if not client or not phone: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Customers")
        except: 
            ws = sh.add_worksheet("Customers", 1000, 5)
            ws.append_row(["phone", "name", "address", "last_order"])
        
        try: phones = ws.col_values(1) 
        except: phones = []

        if phone not in phones:
            ws.append_row([str(phone), name, address, datetime.now().strftime("%Y-%m-%d")])
            st.cache_data.clear() 
    except: pass

# --- QUẢN LÝ NGƯỜI DÙNG ---
def init_users():
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Users")
        except:
            ws = sh.add_worksheet("Users", 100, 3)
            ws.append_row(["username", "password", "role"])
            default_users = [
                ["Nam", "Emyeu0901", "admin"],
                ["Duong", "Duong", "staff"],
                ["Van", "Van", "staff"]
            ]
            for u in default_users: ws.append_row(u)
    except: pass

def get_users_db():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Users")
        return ws.get_all_records()
    except: return []

def change_password(username, new_pass):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Users")
        cell = ws.find(username)
        if cell:
            ws.update_cell(cell.row, 2, new_pass)
            return True
        return False
    except: return False

def check_login(username, password):
    users = get_users_db()
    for u in users:
        if str(u['username']).strip() == username and str(u['password']).strip() == password:
            return u
    return None

# --- DATABASE ĐƠN HÀNG (ORDERS) ---
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
        if new_status: 
            ws.update_cell(row_idx, 3, new_status)
        if new_payment_status: 
            ws.update_cell(row_idx, 4, new_payment_status)
        
        if paid_amount > 0:
            current_fin_str = ws.cell(row_idx, 7).value
            try: fin = json.loads(current_fin_str)
            except: fin = {}
            fin['paid'] = float(fin.get('paid', 0)) + float(paid_amount)
            fin['debt'] = float(fin.get('total', 0)) - fin['paid']
            if fin['debt'] < 0: fin['debt'] = 0
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

def update_multiple_commissions(order_ids, status_text):
    client = get_gspread_client()
    if not client or not order_ids: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        id_list = ws.col_values(1)
        for oid in order_ids:
            if oid in id_list:
                row_idx = id_list.index(oid) + 1
                old_fin_str = ws.cell(row_idx, 7).value
                try: fin = json.loads(old_fin_str)
                except: fin = {}
                fin['commission_status'] = status_text
                ws.update_cell(row_idx, 7, json.dumps(fin, ensure_ascii=False))
        st.cache_data.clear()
        return True
    except:
        return False

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

def edit_order_info(order_id, new_cust, new_total, new_items, new_profit, new_comm):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Orders")
        cell = ws.find(order_id)
        if not cell: return False
        r = cell.row
        
        ws.update_cell(r, 5, json.dumps(new_cust, ensure_ascii=False))
        ws.update_cell(r, 6, json.dumps(new_items, ensure_ascii=False))
        
        old_fin_str = ws.cell(r, 7).value
        try: fin = json.loads(old_fin_str)
        except: fin = {}
        fin['total'] = new_total
        fin['debt'] = new_total - float(fin.get('paid', 0))
        if fin['debt'] < 0: fin['debt'] = 0
        fin['total_profit'] = new_profit
        fin['total_comm'] = new_comm
        ws.update_cell(r, 7, json.dumps(fin, ensure_ascii=False))
        
        save_customer_db(new_cust.get('name'), new_cust.get('phone'), new_cust.get('address'))
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

def save_cash_log(date, type_, amount, method, note):
    client = get_gspread_client()
    if not client: return
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("Cashbook")
        except: 
            ws = sh.add_worksheet("Cashbook", 1000, 10)
            ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"])
        if not ws.get_all_values(): ws.append_row(["Date", "Content", "Amount", "TM/CK", "Note"])
        ws.append_row([str(date), type_, amount, method, note])
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
    max_num = 0
    for o in orders:
        oid = str(o.get('order_id', '')).strip()
        if "/DH." + year in oid:
            try:
                num_part = oid.split("/")[0]
                num = int(num_part)
                if num > max_num:
                    max_num = num
            except:
                continue
    next_num = max_num + 1
    return f"{next_num:03d}/DH.{year}"

# --- DATABASE KHÁCH THÊM ---
def fetch_extra_customers():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        try: ws = sh.worksheet("ExtraCustomers")
        except: return []
        return ws.get_all_records()
    except: return []

def save_extra_customer(id_, name, pre_tax, actual, not_done, vat_rate, pit_tax, refund, status):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("ExtraCustomers")
        except:
            ws = sh.add_worksheet("ExtraCustomers", 1000, 10)
            ws.append_row(["id", "customer", "pre_tax", "actual", "not_done", "vat_rate", "pit_tax", "refund", "status"])
        ws.append_row([str(id_), name, float(pre_tax), float(actual), float(not_done), float(vat_rate), float(pit_tax), float(refund), status])
        st.cache_data.clear()
        return True
    except: return False

def update_extra_customer_status(id_, status):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("ExtraCustomers")
        cell = ws.find(str(id_))
        if cell:
            ws.update_cell(cell.row, 9, status)
            st.cache_data.clear()
            return True
        return False
    except: return False

def update_extra_customers_batch(df_records):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("ExtraCustomers")
        ws.clear()
        ws.append_row(["id", "customer", "pre_tax", "actual", "not_done", "vat_rate", "pit_tax", "refund", "status"])
        for r in df_records:
            ws.append_row([str(r['id']), r['customer'], float(r['pre_tax']), float(r['actual']), float(r['not_done']), float(r['vat_rate']), float(r['pit_tax']), float(r['refund']), r['status']])
        st.cache_data.clear()
        return True
    except: return False

# --- QUẢN LÝ HỢP ĐỒNG (AUTO-NUMBERING & DATABASE) ---
def get_contract_code_prefix(contract_type):
    if contract_type == "Hợp đồng in ấn":
        return "HĐIA"
    elif contract_type == "Hợp đồng in ấn và quảng cáo":
        return "HĐQC"
    return "HĐMB"

def get_next_contract_seq(contract_type="Hợp đồng mua bán"):
    client = get_gspread_client()
    curr_year = datetime.now().strftime("%y")
    max_num = 9
    prefix = get_contract_code_prefix(contract_type)
    
    if client:
        try:
            sh = client.open_by_url(SHEET_URL)
            try:
                ws = sh.worksheet("Contracts")
                col_hd = ws.col_values(1)
                for code in col_hd:
                    code_str = str(code).strip()
                    if f"-ALP.{curr_year}" in code_str:
                        m = re.match(rf"^(\d+)/[A-ZĐ]+-ALP\.{curr_year}", code_str)
                        if m:
                            val = int(m.group(1))
                            if val > max_num:
                                max_num = val
            except: pass
        except: pass

    next_seq = max_num + 1
    return {
        "seq": next_seq,
        "year": curr_year,
        "prefix": prefix,
        "so_hd": f"{next_seq}/{prefix}-ALP.{curr_year}",
        "so_bbgn": f"{next_seq}/BBGN.ALP.{curr_year}",
        "so_bbnt": f"{next_seq}/BBNT.ALP.{curr_year}",
        "so_dntt": f"{next_seq}/ĐNTT.ALP.{curr_year}",
        "so_bbtl": f"{next_seq}/BBTL.ALP.{curr_year}"
    }

def save_contract_to_sheet(contract_data):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        try:
            ws = sh.worksheet("Contracts")
        except:
            ws = sh.add_worksheet("Contracts", 1000, 16)
            ws.append_row([
                "so_hd", "loai_hd", "ngay_ky", "khach_hang", "mst", "noi_dung", 
                "tong_tien", "tinh_trang", "dot1_amt", "dot2_amt", "items_json", "extra_json", "created_at"
            ])
        ws.append_row([
            contract_data['so_hd'],
            contract_data.get('loai_hd', 'Hợp đồng mua bán'),
            contract_data['ngay_ky'],
            contract_data['khach_hang'],
            contract_data['mst'],
            contract_data.get('noi_dung', ''),
            float(contract_data['tong_tien']),
            contract_data.get('tinh_trang', 'Chuẩn bị ký'),
            float(contract_data['dot1_amt']),
            float(contract_data['dot2_amt']),
            json.dumps(contract_data['items'], ensure_ascii=False),
            json.dumps(contract_data['extra_info'], ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Lỗi lưu hợp đồng: {e}")
        return False

def update_contract_status_sheet(so_hd, new_status):
    client = get_gspread_client()
    if not client: return False
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Contracts")
        cell = ws.find(so_hd)
        if cell:
            ws.update_cell(cell.row, 8, new_status)
            st.cache_data.clear()
            return True
        return False
    except Exception as e:
        st.error(f"Lỗi cập nhật trạng thái hợp đồng: {e}")
        return False

def fetch_all_contracts():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open_by_url(SHEET_URL)
        ws = sh.worksheet("Contracts")
        raw = ws.get_all_records()
        for r in raw:
            try:
                r['items'] = json.loads(r.get('items_json', '[]'))
                r['extra_info'] = json.loads(r.get('extra_json', '{}'))
            except: pass
        return raw
    except: return []

# --- HÀM XUẤT TRỌN BỘ 5 VĂN BẢN WORD (.DOCX) ĐẦY ĐỦ 100% ---
def create_full_contract_docx(c_data):
    doc = Document()
    
    for section in doc.sections:
        section.top_margin = Inches(0.79)
        section.bottom_margin = Inches(0.79)
        section.left_margin = Inches(0.79)
        section.right_margin = Inches(0.79)

    def set_run_font(run, size=11, bold=False, italic=False, color=None):
        run.font.name = 'Times New Roman'
        run.font.size = Pt(size)
        run.bold = bold
        run.italic = italic
        if color: run.font.color.rgb = color

    def add_p(text="", align=WD_ALIGN_PARAGRAPH.LEFT, bold=False, italic=False, size=11, space_after=3):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = 1.15
        if text:
            r = p.add_run(text)
            set_run_font(r, size=size, bold=bold, italic=italic)
        return p

    def add_quoc_hieu(so_vb, tieu_de_vb):
        add_p("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, size=12, space_after=2)
        add_p("Độc lập - Tự do - Hạnh phúc", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, size=12, space_after=4)
        add_p("-------------------", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, size=10, space_after=10)
        add_p(tieu_de_vb.upper(), align=WD_ALIGN_PARAGRAPH.CENTER, bold=True, size=14, space_after=3)
        add_p(f"Số: {so_vb}", align=WD_ALIGN_PARAGRAPH.CENTER, italic=True, size=11, space_after=10)

    so_hd = c_data['so_hd']
    so_bbgn = c_data['so_bbgn']
    so_bbnt = c_data['so_bbnt']
    so_dntt = c_data['so_dntt']
    so_bbtl = c_data['so_bbtl']
    loai_hd = c_data.get('loai_hd', 'Hợp đồng mua bán')
    
    if loai_hd == "Hợp đồng in ấn":
        hd_title = "HỢP ĐỒNG DỊCH VỤ IN ẤN"
        term_goods = "sản phẩm in ấn"
        term_service = "cung ứng sản phẩm và dịch vụ in ấn"
        party_a_title = "BÊN CUNG ỨNG DỊCH VỤ (BÊN A)"
        party_b_title = "BÊN ĐẶT IN (BÊN B)"
        role_a_short = "Bên A"
        role_b_short = "Bên B"
    elif loai_hd == "Hợp đồng in ấn và quảng cáo":
        hd_title = "HỢP ĐỒNG THIẾT KẾ, IN ẤN VÀ QUẢNG CÁO"
        term_goods = "ấn phẩm và hạng mục quảng cáo"
        term_service = "thiết kế, sản xuất ấn phẩm và thi công quảng cáo"
        party_a_title = "BÊN THỰC HIỆN DỊCH VỤ (BÊN A)"
        party_b_title = "BÊN ĐẶT HÀNG (BÊN B)"
        role_a_short = "Bên A"
        role_b_short = "Bên B"
    else:
        hd_title = "HỢP ĐỒNG MUA BÁN HÀNG HÓA"
        term_goods = "hàng hóa"
        term_service = "mua bán hàng hóa"
        party_a_title = "BÊN BÁN (BÊN A)"
        party_b_title = "BÊN MUA (BÊN B)"
        role_a_short = "Bên Bán"
        role_b_short = "Bên Mua"
    
    d_day = c_data['ngay_ky_dt'].strftime("%d")
    d_month = c_data['ngay_ky_dt'].strftime("%m")
    d_year = c_data['ngay_ky_dt'].strftime("%Y")
    
    cust = c_data['customer']
    items = c_data['items']
    ext = c_data['extra_info']
    grand_total = float(c_data['tong_tien'])
    dot1_amt = float(c_data['dot1_amt'])
    dot2_amt = float(c_data['dot2_amt'])

    # 1. HỢP ĐỒNG
    add_quoc_hieu(so_hd, hd_title)
    add_p("- Căn cứ Bộ luật Dân sự số 91/2015/QH13 được Quốc hội nước CHXHCN Việt Nam thông qua ngày 24/11/2015 và các văn bản hướng dẫn thi hành;", italic=True)
    add_p("- Căn cứ Luật Thương mại số 36/2005/QH11 được Quốc hội nước CHXHCN Việt Nam thông qua ngày 14/06/2005 và các văn bản hướng dẫn thi hành;", italic=True)
    add_p(f"- Căn cứ nhu cầu {term_service} và năng lực thực tế của hai Bên,", italic=True)
    add_p(f"Hôm nay, ngày {d_day} tháng {d_month} năm {d_year}, tại trụ sở CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT, hai Bên gồm có:", italic=True, space_after=6)

    add_p(f"{party_a_title}: CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT", bold=True)
    add_p("• Địa chỉ trụ sở: N1/1, Tổ 12, Khu phố 3, Phường Long Hưng, Thành phố Đồng Nai, Việt Nam")
    add_p("• Mã số thuế: 3603995632")
    add_p("• Điện thoại: 0706 279 379                 	 • Email: anlocphat68.ltd@gmail.com")
    add_p("• Tài khoản ngân hàng số: 868080")
    add_p("  Tại Ngân hàng:  Ngân hàng TMCP Kỹ thương Việt Nam - THP- TCB TAM HIEP")
    add_p("• Đại diện bởi: Ông LÊ VĂN VẠN 	• Chức vụ: Giám đốc")
    add_p("")

    add_p(f"{party_b_title}: {cust.get('name', '').upper()}", bold=True)
    add_p(f"• Địa chỉ trụ sở: {cust.get('address', '')}")
    add_p(f"• Mã số thuế: {cust.get('mst', '')}")
    add_p(f"• Điện thoại: {cust.get('phone', '')}              • Email: {cust.get('email', '')}")
    add_p(f"• Tài khoản ngân hàng số: {cust.get('bank_no', '')}")
    add_p(f"  Tại Ngân hàng: {cust.get('bank_name', '')}")
    add_p(f"• Đại diện bởi: {cust.get('rep_name', '')}              • Chức vụ: {cust.get('rep_role', 'Giám đốc')}")
    if cust.get('auth_doc'):
        add_p(f"• Văn bản ủy quyền (nếu có): {cust.get('auth_doc')}")
    
    add_p(f"Sau khi bàn bạc và thống nhất trên tinh thần bình đẳng và cùng có lợi, hai Bên thỏa thuận ký kết {hd_title} với các điều khoản và điều kiện cụ thể sau đây:")
    
    add_p(f"ĐIỀU 1. ĐỐI TƯỢNG {term_goods.upper()} VÀ GIÁ CẢ", bold=True)
    add_p(f"1.1. {role_a_short} đồng ý cung cấp và {role_b_short} đồng ý mua danh mục {term_goods} với quy cách, số lượng và đơn giá chi tiết như sau:")

    tbl = doc.add_table(rows=1, cols=7)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["STT", f"Tên {term_goods} / Quy cách", "ĐVT", "Số lượng", "Đơn giá (VNĐ)", "Thuế GTGT", "Thành tiền (VNĐ)"]
    hdr_cells = tbl.rows[0].cells
    for idx, h in enumerate(headers):
        hdr_cells[idx].text = h
        p = hdr_cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.runs[0], size=10, bold=True)
        hdr_cells[idx]._tc.get_or_add_tcPr().append(parse_xml(r'<w:shd {} w:fill="EDEDED"/>'.format(nsdecls('w'))))

    for idx, it in enumerate(items):
        r_cells = tbl.add_row().cells
        r_cells[0].text = str(idx + 1)
        r_cells[1].text = str(it.get('name', ''))
        r_cells[2].text = str(it.get('unit', ''))
        r_cells[3].text = format_currency(it.get('qty', 0))
        r_cells[4].text = format_currency(it.get('price', 0))
        r_cells[5].text = f"{it.get('vat_rate', 0)}%"
        r_cells[6].text = format_currency(it.get('total_line', 0))
        
        r_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_cells[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_cells[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_cells[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_cells[5].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_cells[6].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for c in r_cells: set_run_font(c.paragraphs[0].runs[0], size=10)

    tot_row = tbl.add_row().cells
    tot_row[0].merge(tot_row[5])
    tot_row[0].text = "TỔNG CỘNG GIÁ TRỊ HỢP ĐỒNG (ĐÃ BAO GỒM THUẾ GTGT):"
    tot_row[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run_font(tot_row[0].paragraphs[0].runs[0], size=10, bold=True)
    tot_row[6].text = format_currency(grand_total)
    tot_row[6].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run_font(tot_row[6].paragraphs[0].runs[0], size=10, bold=True)

    add_p("")
    add_p(f"1.2. Tổng giá trị Hợp đồng bằng chữ: {c_data['sotienbangchu']}")
    add_p("1.3. Đơn giá nêu trên đã bao gồm thuế Giá trị gia tăng (GTGT), chi phí đóng gói chuẩn của nhà sản xuất. Mọi chi phí phát sinh ngoài thỏa thuận chỉ có hiệu lực khi hai Bên lập phụ lục văn bản có đóng dấu xác nhận.")
    
    add_p("ĐIỀU 2. TIÊU CHUẨN CHẤT LƯỢNG VÀ BẢO HÀNH", bold=True)
    add_p(f"2.1. {term_goods.capitalize()} do {role_a_short} cung cấp phải mới 100%, chưa qua sử dụng, đúng chủng loại, đúng tiêu chuẩn kỹ thuật (đúng market đã duyệt) và quy định pháp luật Việt Nam.")
    add_p(f"2.2. Thời hạn bảo hành sản phẩm: {ext.get('warranty_months', '12')} tháng kể từ ngày hai Bên ký kết Biên bản nghiệm thu và bàn giao {term_goods} hoàn tất.")
    add_p(f"2.3. Điều kiện bảo hành (Bảo vệ quyền lợi {role_a_short}): {role_a_short} chỉ chịu trách nhiệm bảo hành đối với các khuyết tật, hư hỏng do lỗi kỹ thuật của nhà sản xuất. {role_a_short} hoàn toàn miễn trừ trách nhiệm bảo hành trong các trường hợp: {role_b_short} bảo quản sai hướng dẫn, tự ý tháo dỡ, sửa chữa hoặc can thiệp kỹ thuật trái phép, hư hại do thiên tai, hỏa hoạn, va đập vật lý hoặc do sự cố nguồn điện bên phía {role_b_short}.")

    add_p("ĐIỀU 3. THỜI HẠN, ĐỊA ĐIỂM VÀ PHƯƠNG THỨC GIAO NHẬN", bold=True)
    add_p(f"3.1. Thời hạn giao hàng: {role_a_short} sẽ giao hàng cho {role_b_short} trong vòng {ext.get('delivery_days', '05')} ngày làm việc kể từ ngày {role_b_short} hoàn tất nghĩa vụ thanh toán tiền tạm ứng (hoặc kể từ ngày ký kết Hợp đồng và duyệt mẫu thiết kế).")
    add_p(f"3.2. Địa điểm giao hàng: Giao tại kho của {role_b_short} tại: {ext.get('delivery_address', cust.get('address'))}")
    add_p(f"3.3. Chi phí bốc xếp và vận chuyển: Do {role_a_short.lower()} chịu trách nhiệm chi trả và được tính vào giá {term_goods}.")
    add_p(f"3.4. Kiểm tra và bàn giao: Khi nhận hàng, đại diện có thẩm quyền của {role_b_short} phải kiểm tra số lượng, bao bì, ngoại quan và quy cách {term_goods} ngay tại thời điểm giao. Nếu phát hiện thiếu hụt, hư hỏng bên ngoài, {role_b_short} phải lập biên bản có chữ ký của hai Bên tại chỗ.")
    add_p(f"3.5. Giới hạn thời gian khiếu nại: Hết thời hạn 05 (năm) ngày làm việc kể từ thời điểm ký nhận bàn giao, nếu {role_b_short} không có thông báo bằng văn bản gửi đến {role_a_short} về các khuyết tật ẩn tì, {term_goods} được coi là đã được nghiệm thu đầy đủ, nguyên vẹn và đạt chuẩn chất lượng theo đúng Hợp đồng. Mọi khiếu nại sau thời hạn này đều không có giá trị pháp lý.")

    add_p("ĐIỀU 4. PHƯƠNG THỨC VÀ TIẾN ĐỘ THANH TOÁN", bold=True)
    add_p(f"4.1. Hình thức thanh toán: Chuyển khoản vào tài khoản ngân hàng của {role_a_short} quy định tại phần thông tin chủ thể.")
    add_p(f"4.2. Tiến độ thanh toán: {role_b_short} thanh toán cho {role_a_short} làm 02 đợt:")
    add_p(f"• Đợt 1 (Tạm ứng): {role_b_short} thanh toán {ext.get('adv_pct', 50)}% tổng giá trị Hợp đồng, tương đương số tiền: {format_currency(dot1_amt)} VNĐ trong vòng 03 ngày làm việc kể từ ngày ký Hợp đồng.")
    add_p(f"• Đợt 2 (Thanh toán dứt điểm): {role_b_short} thanh toán toàn bộ {100 - int(ext.get('adv_pct', 50))}% giá trị còn lại của Hợp đồng, tương đương số tiền: {format_currency(dot2_amt)} VNĐ ngay trước khi nhận hàng hoặc trong vòng 05 ngày làm việc kể từ ngày ký Biên bản bàn giao {term_goods}.")
    add_p(f"4.3. Quyền giữ hàng và dừng bàn giao (Chặt chẽ cho {role_a_short}): Trường hợp {role_b_short} chưa hoàn thành nghĩa vụ thanh toán của bất kỳ đợt nào đến hạn, {role_a_short} có toàn quyền tạm ngưng sản xuất, tạm giữ hàng hoặc từ chối bàn giao mà không bị coi là vi phạm tiến độ bàn giao {term_goods}.")

    add_p("ĐIỀU 5. BẢO LƯU QUYỀN SỞ HỮU VÀ CHUYỂN DỊCH RỦI RO", bold=True)
    add_p(f"5.1. Bảo lưu quyền sở hữu (Điều 332 Bộ luật Dân sự 2015): Toàn bộ {term_goods} thuộc Hợp đồng này vẫn thuộc quyền sở hữu hợp pháp của {role_a_short} cho đến khi {role_b_short} thanh toán đầy đủ 100% giá trị Hợp đồng cùng các chi phí phát sinh (nếu có). Trong thời gian này, {role_b_short} không được bán, chuyển nhượng, thế chấp, cầm cố hoặc định đoạt tài sản dưới bất kỳ hình thức nào khi chưa có sự đồng ý bằng văn bản của {role_a_short}.")
    add_p(f"5.2. Chuyển giao rủi ro: Rủi ro về mất mát hoặc hư hỏng đối với {term_goods} được chuyển giao sang cho {role_b_short} kể từ thời điểm {term_goods} được bàn giao và đại diện {role_b_short} ký nhận vào Biên bản bàn giao {term_goods}.")

    add_p("ĐIỀU 6. PHẠT VI PHẠM VÀ BỒI THƯỜNG THIỆT HẠI", bold=True)
    add_p(f"6.1. Phạt chậm thanh toán (Bảo vệ {role_a_short}): Nếu {role_b_short} chậm thanh toán so với thời hạn thỏa thuận tại Điều 4, {role_b_short} phải chịu khoản lãi phạt chậm trả tính trên số tiền chậm thanh toán với mức lãi suất bằng 0,05% / ngày hoặc 150% lãi suất cơ bản do NHNN công bố cho từng ngày chậm thanh toán.")
    add_p(f"6.2. Nếu {role_b_short} chậm thanh toán quá 15 (mười lăm) ngày làm việc, {role_a_short} có quyền đơn phương chấm dứt Hợp đồng, thu hồi toàn bộ số {term_goods} đã giao ({role_b_short} chịu mọi phí tổn phát sinh), đồng thời phạt vi phạm 8% (tám phần trăm) giá trị phần Hợp đồng bị vi phạm và yêu cầu bồi thường toàn bộ thiệt hại thực tế phát sinh.")
    add_p(f"6.3. Trường hợp {role_a_short} chậm giao hàng do nguyên nhân chủ quan của {role_a_short}, {role_a_short} sẽ chịu mức phạt vi phạm là 0,05% / ngày trên giá trị số hàng giao chậm, nhưng tổng số tiền phạt không vượt quá 8% giá trị phần nghĩa vụ bị vi phạm theo Điều 301 Luật Thương mại.")

    add_p("ĐIỀU 7. SỰ KIỆN BẤT KHẢ KHÁNG", bold=True)
    add_p(f"7.1. Sự kiện bất khả kháng là những sự kiện xảy ra một cách khách quan, không thể lường trước được và không thể khắc phục được mặc dù đã áp dụng mọi biện pháp cần thiết (bao gồm thiên tai, dịch bệnh, chiến tranh, đình công, thay đổi chính sách pháp luật của Nhà nước làm gián đoạn việc cung ứng {term_goods}).")
    add_p("7.2. Bên gặp sự kiện bất khả kháng được miễn trách nhiệm đối với nghĩa vụ chậm thực hiện, với điều kiện phải thông báo bằng văn bản cho Bên kia trong vòng 03 (ba) ngày làm việc kể từ ngày sự kiện xảy ra và cung cấp chứng nhận hợp lệ của cơ quan có thẩm quyền.")

    add_p("ĐIỀU 8. LUẬT ÁP DỤNG VÀ GIẢI QUYẾT TRANH CHẤP", bold=True)
    add_p("8.1. Hợp đồng này được điều chỉnh và giải thích theo các quy định của pháp luật nước Cộng hòa Xã hội Chủ nghĩa Việt Nam.")
    add_p(f"8.2. Mọi tranh chấp phát sinh từ hoặc liên quan đến Hợp đồng này trước hết sẽ được giải quyết thông qua thương lượng hòa giải giữa hai Bên. Nếu sau 30 (ba mươi) ngày kể từ ngày phát sinh tranh chấp mà thương lượng không thành, tranh chấp sẽ được đưa ra giải quyết tại Tòa án nhân dân có thẩm quyền tại thành phố Đồng Nai để bảo đảm tối đa quyền lợi tố tụng hợp pháp cho {role_a_short}. Toàn bộ án phí và chi phí pháp lý phát sinh do Bên thua kiện gánh chịu.")

    add_p("ĐIỀU 9. ĐIỀU KHOẢN CHUNG VÀ HIỆU LỰC HỢP ĐỒNG", bold=True)
    add_p("9.1. Hợp đồng này có hiệu lực kể từ ngày đại diện hợp pháp của hai Bên ký tên và đóng dấu pháp lý.")
    add_p("9.2. Mọi sửa đổi, bổ sung đối với Hợp đồng này chỉ có giá trị khi được lập thành Phụ lục văn bản và được người đại diện có thẩm quyền của hai Bên ký duyệt.")
    add_p("9.3. Hai Bên cam kết thông tin cung cấp tại Hợp đồng là hoàn toàn trung thực và người ký tên có đầy đủ thẩm quyền đại diện theo quy định của pháp luật và Điều lệ Công ty.")
    add_p("9.4. Hợp đồng này gồm có 04 trang, được lập thành 04 bản có giá trị pháp lý như nhau, mỗi Bên giữ 02 bản để thực hiện.")
    add_p("")

    sig_tab = doc.add_table(rows=1, cols=2)
    sig_tab.alignment = WD_TABLE_ALIGNMENT.CENTER
    c1, c2 = sig_tab.rows[0].cells
    c1.text = f"ĐẠI DIỆN {party_a_title}\n(Ký tên, ghi rõ họ tên và đóng dấu)\n\n\n\n\nLÊ VĂN VẠN"
    c2.text = f"ĐẠI DIỆN {party_b_title}\n(Ký tên, ghi rõ họ tên và đóng dấu)\n\n\n\n\n{cust.get('rep_name', '')}"
    c1.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    c2.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(c1.paragraphs[0].runs[0], bold=True)
    set_run_font(c2.paragraphs[0].runs[0], bold=True)

    # 2. BIÊN BẢN GIAO NHẬN
    doc.add_page_break()
    add_quoc_hieu(so_bbgn, f"BIÊN BẢN GIAO NHẬN {term_goods.upper()}")
    add_p(f"(Kèm theo {hd_title} số: {so_hd})", align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
    add_p(f"Hôm nay, vào lúc, ngày {d_day} tháng {d_month} năm {d_year}, tại địa điểm: {ext.get('delivery_address', cust.get('address'))}. Chúng tôi gồm có:", italic=True)
    
    add_p(f"I. {party_a_title}: CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT", bold=True)
    add_p("• Địa chỉ trụ sở: N1/1, Tổ 12, Khu phố 3, Phường Long Hưng, Thành phố Đồng Nai, Việt Nam")
    add_p("• Mã số thuế: 3603995632")
    add_p("• Điện thoại: 0706 279 379                 	 • Email: anlocphat68.ltd@gmail.com")
    add_p("• Tài khoản ngân hàng số: 868080")
    add_p("  Tại Ngân hàng:  Ngân hàng TMCP Kỹ thương Việt Nam - THP- TCB TAM HIEP")
    add_p("• Đại diện bởi: Ông LÊ VĂN VẠN 	• Chức vụ: Giám đốc")
    
    add_p(f"II. BÊN NHẬN HÀNG ({party_b_title}): {cust.get('name', '').upper()}", bold=True)
    add_p(f"• Đại diện bởi: {ext.get('receiver_name', cust.get('rep_name'))}           • Chức vụ: {ext.get('receiver_role', 'Đại diện')}")
    add_p(f"• Số điện thoại liên hệ: {ext.get('receiver_phone', cust.get('phone'))}              • Số CCCD/Hộ chiếu: {ext.get('receiver_id', '........................')}")
    add_p(f"Hai Bên cùng tiến hành bàn giao và tiếp nhận {term_goods} theo các nội dung chi tiết dưới đây:")

    t_gn = doc.add_table(rows=1, cols=5)
    t_gn.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, h in enumerate(["STT", f"Tên {term_goods} / Quy cách", "ĐVT", "Số lượng theo HĐ", "Số lượng thực giao"]):
        t_gn.rows[0].cells[idx].text = h
        p = t_gn.rows[0].cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.runs[0], size=10, bold=True)
        t_gn.rows[0].cells[idx]._tc.get_or_add_tcPr().append(parse_xml(r'<w:shd {} w:fill="EDEDED"/>'.format(nsdecls('w'))))

    for idx, it in enumerate(items):
        r = t_gn.add_row().cells
        r[0].text = str(idx + 1)
        r[1].text = str(it.get('name', ''))
        r[2].text = str(it.get('unit', ''))
        r[3].text = format_currency(it.get('qty', 0))
        r[4].text = format_currency(it.get('qty', 0))
        r[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for c in r: set_run_font(c.paragraphs[0].runs[0], size=10)

    add_p("")
    add_p(f"III. HỒ SƠ, TÀI LIỆU KÈM THEO {term_goods.upper()}:", bold=True)
    add_p("• Hóa đơn tài chính GTGT (hoặc Phiếu xuất kho kiêm vận chuyển nội bộ): Đầy đủ theo quy định.")
    add_p("• Mẫu market đã duyệt / Chứng nhận tiêu chuẩn chất lượng (nếu có).")
    add_p("• Phiếu bảo hành / Tài liệu hướng dẫn bàn giao.")
    
    add_p("IV. Ý KIẾN VÀ KẾT LUẬN CỦA HAI BÊN:", bold=True)
    add_p(f"1. {role_b_short} đã kiểm tra số lượng và ngoại quan {term_goods} thực tế đối chiếu với chứng từ giao nhận, xác nhận {role_a_short} đã giao đúng, đủ số lượng và {term_goods} nguyên vẹn theo đúng bảng kê trên.")
    add_p(f"2. Kể từ thời điểm ký biên bản này, rủi ro mất mát hoặc hư hỏng đối với {term_goods} được chuyển giao sang cho {role_b_short}. Biên bản này là căn cứ chứng minh {role_a_short} đã hoàn thành nghĩa vụ giao hàng.")
    add_p("3. Biên bản giao nhận được lập thành 02 bản có giá trị pháp lý tương đương, mỗi Bên giữ 01 bản để làm căn cứ hạch toán và nghiệm thu.")
    add_p("")

    sig_gn = doc.add_table(rows=1, cols=2)
    sig_gn.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_gn.rows[0].cells[0].text = f"ĐẠI DIỆN BÊN GIAO HÀNG ({role_a_short.upper()})\n(Ký và ghi rõ họ tên)\n\n\n\n\nLÊ VĂN VẠN"
    sig_gn.rows[0].cells[1].text = f"ĐẠI DIỆN BÊN NHẬN HÀNG ({role_b_short.upper()})\n(Ký và ghi rõ họ tên)\n\n\n\n\n{ext.get('receiver_name', cust.get('rep_name'))}"
    sig_gn.rows[0].cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    sig_gn.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(sig_gn.rows[0].cells[0].paragraphs[0].runs[0], bold=True)
    set_run_font(sig_gn.rows[0].cells[1].paragraphs[0].runs[0], bold=True)

    # 3. BIÊN BẢN NGHIỆM THU
    doc.add_page_break()
    add_quoc_hieu(so_bbnt, f"BIÊN BẢN NGHIỆM THU {term_goods.upper()}")
    add_p(f"(Căn cứ theo {hd_title} số: {so_hd})", align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
    add_p(f"Hôm nay, ngày {d_day} tháng {d_month} năm {d_year}, tại: {ext.get('delivery_address', cust.get('address'))}, hai Bên gồm có:", italic=True)
    
    add_p(f"{party_a_title}: CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT", bold=True)
    add_p("• Địa chỉ trụ sở: N1/1, Tổ 12, Khu phố 3, Phường Long Hưng, Thành phố Đồng Nai, Việt Nam")
    add_p("• Mã số thuế: 3603995632")
    add_p("• Điện thoại: 0706 279 379                 	 • Email: anlocphat68.ltd@gmail.com")
    add_p("• Tài khoản ngân hàng số: 868080 tại Techcombank - THP- TCB TAM HIEP")
    add_p("• Đại diện bởi: Ông LÊ VĂN VẠN 	• Chức vụ: Giám đốc")
    
    add_p(f"{party_b_title}: {cust.get('name', '').upper()}", bold=True)
    add_p(f"• Đại diện bởi: {cust.get('rep_name', '')}           • Chức vụ: {cust.get('rep_role', 'Giám đốc')}")
    add_p(f"Hai Bên đã cùng nhau tiến hành kiểm tra và nghiệm thu {term_goods} với các nội dung sau:")

    t_nt = doc.add_table(rows=1, cols=5)
    t_nt.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, h in enumerate(["STT", f"Danh mục {term_goods}", "ĐVT", "Số lượng", "Đánh giá kết quả"]):
        t_nt.rows[0].cells[idx].text = h
        p = t_nt.rows[0].cells[idx].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.runs[0], size=10, bold=True)
        t_nt.rows[0].cells[idx]._tc.get_or_add_tcPr().append(parse_xml(r'<w:shd {} w:fill="EDEDED"/>'.format(nsdecls('w'))))

    for idx, it in enumerate(items):
        r = t_nt.add_row().cells
        r[0].text = str(idx + 1)
        r[1].text = str(it.get('name', ''))
        r[2].text = str(it.get('unit', ''))
        r[3].text = format_currency(it.get('qty', 0))
        r[4].text = "ĐẠT YÊU CẦU"
        r[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r[2].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r[3].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for c in r: set_run_font(c.paragraphs[0].runs[0], size=10)

    add_p("")
    add_p("KẾT LUẬN CỦA HỘI ĐỒNG NGHIỆM THU:", bold=True)
    add_p(f"1. Về số lượng & quy cách: {term_goods.capitalize()} được cung cấp đủ số lượng, đồng bộ phụ kiện, đúng chủng loại và xuất xứ thỏa thuận trong Hợp đồng.")
    add_p("2. Về chất lượng & vận hành: Hoạt động ổn định, đạt đầy đủ các thông số kỹ thuật tiêu chuẩn, đúng maket đã duyệt, không có lỗi hay hư hỏng phát sinh.")
    add_p(f"3. Ý kiến thống nhất: {role_b_short} chính thức chấp thuận nghiệm thu toàn bộ lô hàng nêu trên.")
    add_p(f"4. Thời điểm kích hoạt bảo hành: Thời hạn bảo hành {ext.get('warranty_months', '12')} tháng chính thức được tính kể từ ngày ký Biên bản nghiệm thu này.")
    add_p(f"5. Biên bản này là cơ sở pháp lý để {role_a_short} lập Giấy đề nghị thanh toán và {role_b_short} hoàn tất nghĩa vụ thanh toán dứt điểm đợt cuối theo Hợp đồng.")
    add_p("")

    sig_nt = doc.add_table(rows=1, cols=2)
    sig_nt.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_nt.rows[0].cells[0].text = f"ĐẠI DIỆN KỸ THUẬT {role_a_short.upper()}\n(Ký, đóng dấu và ghi rõ họ tên)\n\n\n\n\nLÊ VĂN VẠN"
    sig_nt.rows[0].cells[1].text = f"ĐẠI DIỆN NGHIỆM THU {role_b_short.upper()}\n(Ký, đóng dấu và ghi rõ họ tên)\n\n\n\n\n{cust.get('rep_name', '')}"
    sig_nt.rows[0].cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    sig_nt.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(sig_nt.rows[0].cells[0].paragraphs[0].runs[0], bold=True)
    set_run_font(sig_nt.rows[0].cells[1].paragraphs[0].runs[0], bold=True)

    # 4. GIẤY ĐỀ NGHỊ THANH TOÁN
    doc.add_page_break()
    add_quoc_hieu(so_dntt, "GIẤY ĐỀ NGHỊ THANH TOÁN")
    add_p("Kính gửi: BAN GIÁM ĐỐC", bold=True)
    add_p(f"Đơn vị: {cust.get('name', '').upper()}", bold=True)
    add_p(f"Địa chỉ: {cust.get('address', '')}")
    add_p(f"- Căn cứ {hd_title} số: {so_hd} giữa hai bên;")
    add_p(f"- Căn cứ Biên bản giao nhận số: {so_bbgn} và Biên bản nghiệm thu số: {so_bbnt};")
    add_p("- Căn cứ tiến độ thực hiện và thỏa thuận thanh toán giữa hai Bên,")
    add_p(f"Công ty An Lộc Phát trân trọng đề nghị Quý Công ty thanh toán khoản tiền {term_service} với chi tiết cụ thể như sau:")
    
    t_tt = doc.add_table(rows=4, cols=2)
    t_tt.alignment = WD_TABLE_ALIGNMENT.CENTER
    t_tt.rows[0].cells[0].text = "1. Tổng giá trị Hợp đồng (bao gồm VAT):"
    t_tt.rows[0].cells[1].text = f"{format_currency(grand_total)} VNĐ"
    t_tt.rows[1].cells[0].text = f"2. Số tiền {role_b_short} đã thanh toán tạm ứng (Đợt 1):"
    t_tt.rows[1].cells[1].text = f"{format_currency(dot1_amt)} VNĐ"
    t_tt.rows[2].cells[0].text = "3. Số tiền đề nghị thanh toán đợt này (Đợt 2 / Quyết toán):"
    t_tt.rows[2].cells[1].text = f"{format_currency(dot2_amt)} VNĐ"
    t_tt.rows[3].cells[0].text = "4. Số tiền bằng chữ:"
    t_tt.rows[3].cells[1].text = read_money_vietnamese(dot2_amt)
    for r in t_tt.rows: set_run_font(r.cells[0].paragraphs[0].runs[0], bold=True)

    add_p("")
    add_p(f"THÔNG TIN TÀI KHOẢN THỤ HƯỞNG CỦA {role_a_short.upper()}:", bold=True)
    add_p("• Tên đơn vị thụ hưởng: CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT")
    add_p("• Số tài khoản: 868080")
    add_p("• Mở tại Ngân hàng: Ngân hàng TMCP Kỹ thương Việt Nam - THP- TCB TAM HIEP")
    add_p(f"• Nội dung chuyển khoản: Thanh toán tiền hàng theo HĐ số {so_hd}")
    add_p("")
    
    sig_tt = doc.add_table(rows=1, cols=2)
    sig_tt.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_tt.rows[0].cells[1].text = "GIÁM ĐỐC\n(Ký tên, đóng dấu)\n\n\n\n\nLÊ VĂN VẠN"
    sig_tt.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(sig_tt.rows[0].cells[1].paragraphs[0].runs[0], bold=True)

    # 5. BIÊN BẢN THANH LÝ
    doc.add_page_break()
    add_quoc_hieu(so_bbtl, f"BIÊN BẢN THANH LÝ {hd_title.upper()}")
    add_p(f"(Căn cứ {hd_title} số: {so_hd}, ký ngày {d_day}/{d_month}/{d_year})", align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
    add_p(f"Hôm nay, ngày {d_day} tháng {d_month} năm {d_year}, tại trụ sở CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT, hai Bên gồm có:", italic=True)
    
    add_p(f"{party_a_title}: CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT", bold=True)
    add_p("• Địa chỉ trụ sở: N1/1, Tổ 12, Khu phố 3, Phường Long Hưng, Thành phố Đồng Nai, Việt Nam")
    add_p("• Mã số thuế: 3603995632")
    add_p("• Điện thoại: 0706 279 379                 	 • Email: anlocphat68.ltd@gmail.com")
    add_p("• Tài khoản ngân hàng số: 868080 tại Techcombank - THP- TCB TAM HIEP")
    add_p("• Đại diện bởi: Ông LÊ VĂN VẠN 	• Chức vụ: Giám đốc")
    
    add_p(f"{party_b_title}: {cust.get('name', '').upper()}", bold=True)
    add_p(f"• Địa chỉ: {cust.get('address', '')}              • Mã số thuế: {cust.get('mst', '')}")
    add_p(f"• Đại diện bởi: {cust.get('rep_name', '')}              • Chức vụ: {cust.get('rep_role', 'Giám đốc')}")
    add_p("Hai Bên cùng thống nhất lập và ký kết Biên bản thanh lý Hợp đồng với các điều khoản sau:")
    
    add_p(f"ĐIỀU 1. ĐÁNH GIÁ NGHĨA VỤ GIAO NHẬN {term_goods.upper()}", bold=True)
    add_p(f"1. {role_a_short} đã hoàn thành việc giao toàn bộ {term_goods} đúng số lượng, chủng loại, xuất xứ và quy cách kỹ thuật theo thỏa thuận tại Hợp đồng và Biên bản nghiệm thu số {so_bbnt} ngày {d_day}/{d_month}/{d_year}.")
    add_p(f"2. {role_b_short} xác nhận đã tiếp nhận đầy đủ {term_goods}, hồ sơ chứng từ, hóa đơn VAT hợp lệ và không có bất kỳ khiếu nại hay tranh chấp nào liên quan đến chất lượng và số lượng {term_goods}.")
    
    add_p("ĐIỀU 2. ĐỐI SOÁT VÀ QUYẾT TOÁN TÀI CHÍNH", bold=True)
    add_p(f"• Tổng giá trị Hợp đồng thanh toán (đã có VAT): {format_currency(grand_total)} VNĐ.")
    add_p(f"• Số tiền {role_b_short} đã thanh toán cho {role_a_short}: {format_currency(grand_total)} VNĐ.")
    add_p(f"• Số tiền còn lại {role_b_short} phải thanh toán: 0 (Không) đồng.")
    add_p("Hai Bên xác nhận nghĩa vụ tài chính theo Hợp đồng đã được tất toán trọn vẹn, không bên nào còn nợ tiền bên nào.")
    
    add_p("ĐIỀU 3. DUY TRÌ NGHĨA VỤ BẢO HÀNH (BẢO VỆ HAI BÊN)", bold=True)
    add_p(f"Việc ký kết Biên bản thanh lý này đồng nghĩa với việc chấm dứt toàn bộ các quyền và nghĩa vụ thương mại chung của Hợp đồng, ngoại trừ trách nhiệm bảo hành kỹ thuật của {role_a_short} theo Điều 2 của Hợp đồng vẫn tiếp tục có hiệu lực cho đến hết ngày hết hạn bảo hành.")
    
    add_p("ĐIỀU 4. HIỆU LỰC THI HÀNH", bold=True)
    add_p(f"Biên bản thanh lý này có hiệu lực kể từ ngày ký. Kể từ thời điểm này, Hợp đồng số {so_hd} chính thức hết hiệu lực pháp lý (trừ nghĩa vụ bảo hành). Biên bản được lập thành 04 bản có giá trị pháp lý như nhau, mỗi Bên giữ 02 bản.")
    add_p("")

    sig_tl = doc.add_table(rows=1, cols=2)
    sig_tl.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_tl.rows[0].cells[0].text = f"ĐẠI DIỆN {party_a_title}\n(Ký tên, đóng dấu và ghi rõ họ tên)\n\n\n\n\nLÊ VĂN VẠN"
    sig_tl.rows[0].cells[1].text = f"ĐẠI DIỆN {party_b_title}\n(Ký tên, đóng dấu và ghi rõ họ tên)\n\n\n\n\n{cust.get('rep_name', '')}"
    sig_tl.rows[0].cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    sig_tl.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run_font(sig_tl.rows[0].cells[0].paragraphs[0].runs[0], bold=True)
    set_run_font(sig_tl.rows[0].cells[1].paragraphs[0].runs[0], bold=True)

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- PDF GENERATOR (BÁO GIÁ & GIAO HÀNG) ---
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

    if os.path.exists(HEADER_IMAGE):
        try:
            pdf.image(HEADER_IMAGE, x=10, y=10, w=190)
            pdf.set_y(pdf.get_y() + 35) 
        except: pass
    else:
        pdf.set_font_size(14)
        pdf.cell(0, 8, txt('CÔNG TY TNHH SẢN XUẤT KINH DOANH THƯƠNG MẠI AN LỘC PHÁT'), 0, 1, 'C')
        pdf.set_font_size(10)
        pdf.cell(0, 5, txt('Mã số thuế: 3603995632'), 0, 1, 'C')
        pdf.cell(0, 5, txt('Địa chỉ: A1/204A, hẻm 244, đường Bùi Hữu Nghĩa, phường Biên Hòa, tỉnh Đồng Nai'), 0, 1, 'C')
        pdf.cell(0, 5, txt('Điện thoại: 0251 777 6868       Email: anlocphat68.ltd@gmail.com'), 0, 1, 'C')
        pdf.cell(0, 5, txt('Số tài khoản: 451557254 – Ngân hàng TMCP Việt Nam Thịnh Vượng - CN Đồng Nai'), 0, 1, 'C')
        pdf.ln(2)
        
    STAMP_FILE = 'con_dau.png'
    if os.path.exists(STAMP_FILE):
        try:
            pdf.image(STAMP_FILE, x=15, y=32, w=35)
        except: pass
        
    pdf.set_font_size(16)
    pdf.cell(0, 8, txt(title), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font_size(11)
    
    oid = order.get('order_id', '')
    is_delivery = "GIAO HÀNG" in title.upper()
    
    if is_delivery:
        odate = datetime.now().strftime("%d/%m/%Y")
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi.  Nay bàn giao các hàng hóa và dịch vụ như sau:"
    else:
        raw_date = order.get('date', '')
        try: odate = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except: odate = raw_date
        intro_text = "Công ty TNHH SX KD TM An Lộc Phát xin cám ơn sự quan tâm của Quý khách hàng đến sản phẩm và dịch vụ của chúng tôi. Xin trân trọng gửi tới Quý khách hàng báo giá như sau:"

    cust = order.get('customer', {})
    items = order.get('items', [])
    
    pdf.cell(0, 6, txt(f"Mã số: {oid} | Ngày: {odate}"), new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(1)
    pdf.cell(0, 6, txt(f"Khách hàng: {cust.get('name', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Điện thoại: {cust.get('phone', '')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, txt(f"Địa chỉ: {cust.get('address', '')}"), new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(2)
    pdf.multi_cell(0, 5, txt(intro_text))
    pdf.ln(2)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(10, 8, "STT", 1, 0, 'C', 1)
    pdf.cell(75, 8, txt("Tên hàng / Quy cách"), 1, 0, 'C', 1)
    pdf.cell(15, 8, txt("ĐVT"), 1, 0, 'C', 1)
    pdf.cell(15, 8, "SL", 1, 0, 'C', 1)
    pdf.cell(35, 8, txt("Đơn giá"), 1, 0, 'C', 1)
    pdf.cell(40, 8, txt("Thành tiền"), 1, 1, 'C', 1)
    
    sum_items_total = 0
    total_vat = 0
    
    for i, item in enumerate(items):
        try: 
            price = float(item.get('price', 0))
            qty = float(item.get('qty', 0))
            line_total = price * qty
            vat_rate = float(item.get('vat_rate', 0))
            vat_val = line_total * (vat_rate / 100)
        except: 
            line_total = 0; vat_val = 0
            
        sum_items_total += line_total
        total_vat += vat_val
        
        start_y = pdf.get_y()
        pdf.set_x(20) 
        pdf.multi_cell(75, 8, txt(item.get('name', '')), 1, 'L')
        end_y = pdf.get_y()
        h = end_y - start_y 
        
        pdf.set_xy(10, start_y)
        pdf.cell(10, h, str(i+1), 1, 0, 'C')
        pdf.set_xy(95, start_y)
        
        pdf.cell(15, h, txt(item.get('unit', '')), 1, 0, 'C')
        pdf.cell(15, h, format_currency(qty), 1, 0, 'R')
        pdf.cell(35, h, format_currency(price), 1, 0, 'R')
        pdf.cell(40, h, format_currency(line_total), 1, 1, 'R')
        pdf.set_y(end_y)
    
    final_total = sum_items_total + total_vat
    pdf.cell(150, 8, txt("Cộng tiền hàng:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(sum_items_total), 1, 1, 'R')
    pdf.cell(150, 8, txt(f"Tiền VAT:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(total_vat), 1, 1, 'R')
    pdf.cell(150, 8, txt("TỔNG CỘNG THANH TOÁN:"), 1, 0, 'R')
    pdf.cell(40, 8, format_currency(final_total), 1, 1, 'R')
    pdf.ln(5)
    
    money_text = ""
    if SAFE_MODE: money_text = f"Tong cong: {format_currency(final_total)} VND"
    else:
        try: money_text = read_money_vietnamese(final_total)
        except: money_text = f"{format_currency(final_total)} đồng."
    pdf.multi_cell(0, 6, txt(f"Bằng chữ: {money_text}"))
    pdf.ln(3)

    pdf.set_x(10)
    if is_delivery:
        pdf.cell(95, 5, txt("NGƯỜI NHẬN"), 0, 0, 'C')
        pdf.cell(95, 5, txt("NGƯỜI GIAO"), 0, 1, 'C')
        pdf.ln(20) 
    else:
        pdf.cell(0, 5, txt("NGƯỜI BÁO GIÁ"), 0, 1, 'R')
        pdf.ln(20)

    pdf.ln(2)
    pdf.set_font_size(10)
    pdf.set_x(10)
    if is_delivery:
        pdf.multi_cell(190, 5, txt("* Quý khách vui lòng kiểm tra và phản hồi ngay về tình trạng hàng hoá khi giao nhận!"))
        pdf.set_x(10)
        pdf.multi_cell(190, 5, txt("* Giao hàng miễn phí trong nội thành thành phố Biên Hoà với đơn hàng >1.000.000đ"))
        pdf.set_x(10)
        pdf.multi_cell(190, 5, txt("Rất mong được hợp tác với Quý khách hàng. Trân trọng!"))
    else:
        pdf.cell(0, 5, txt("Lưu ý:"), 0, 1)
        pdf.set_x(10)
        pdf.cell(0, 5, txt("- Giá trên đã bao gồm vận chuyển, giao hàng."), 0, 1)
        pdf.set_x(10)
        pdf.cell(0, 5, txt("- Thời gian hoàn thành, giao hàng: từ 03 - 05 ngày."), 0, 1)
        pdf.set_x(10)
        pdf.cell(0, 5, txt("- Báo giá này áp dụng trong vòng 30 ngày."), 0, 1)
        pdf.ln(2)
        pdf.set_x(10)
        pdf.multi_cell(190, 5, txt("Rất mong nhận được sự hợp tác của Quý khách hàng!\nTrân trọng! "))
    return bytes(pdf.output())

# --- LOGIN PAGE ---
def login_page():
    st.title("🔐 Đăng Nhập Hệ Thống")
    init_users()
    with st.form("login_form"):
        username = st.text_input("Tên đăng nhập")
        password = st.text_input("Mật khẩu", type="password")
        if st.form_submit_button("Đăng nhập", type="primary"):
            user = check_login(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.session_state.role = user['role']
                st.success(f"Xin chào {username}!")
                time.sleep(0.5)
                st.rerun()
            else: st.error("Sai tên đăng nhập hoặc mật khẩu!")

# --- MAIN APP ---
def main_app():
    is_admin = st.session_state.role == 'admin'
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user['username']}** ({st.session_state.role})")
        if st.button("Đăng xuất"):
            st.session_state.logged_in = False
            st.rerun()
        with st.expander("🔑 Đổi mật khẩu"):
            new_p1 = st.text_input("Mật khẩu mới", type="password")
            new_p2 = st.text_input("Nhập lại", type="password")
            if st.button("Lưu mật khẩu"):
                if new_p1 and new_p1 == new_p2:
                    if change_password(st.session_state.user['username'], new_p1):
                        st.success("Đổi thành công!")
                    else: st.error("Lỗi hệ thống")
                else: st.error("Mật khẩu không khớp")

    st.title("Hệ Thống In Ấn An Lộc Phát")
    if "service_account" not in st.secrets:
        st.error("Lỗi: Chưa cấu hình st.secrets")
        st.stop()

    menu = st.sidebar.radio("CHỨC NĂNG", [
        "1. Tạo Báo Giá", 
        "2. Quản Lý Đơn Hàng (Pipeline)", 
        "3. Quản Lý Hợp Đồng & Chứng Từ",
        "4. Khách Thêm", 
        "5. Sổ Quỹ", 
        "6. Dashboard & Báo Cáo"
    ])

    if 'cart' not in st.session_state: st.session_state.cart = []
    if 'last_order' not in st.session_state: st.session_state.last_order = None

    # --- TAB 1: TẠO BÁO GIÁ ---
    if menu == "1. Tạo Báo Giá":
        st.header("📝 Tạo Báo Giá Mới")
        if 'c_name' not in st.session_state: st.session_state.c_name = ""
        if 'c_phone' not in st.session_state: st.session_state.c_phone = ""
        if 'c_addr' not in st.session_state: st.session_state.c_addr = ""

        customers = fetch_customers()
        cust_options = [""] + [f"{c['phone']} - {c['name']}" for c in customers]
        selected_cust = st.selectbox("🔍 Tìm khách cũ (SĐT - Tên):", cust_options)
        if selected_cust:
            s_phone = selected_cust.split(" - ")[0]
            for c in customers:
                if str(c['phone']) == s_phone:
                    st.session_state.c_name = c['name']
                    st.session_state.c_phone = str(c['phone'])
                    st.session_state.c_addr = c['address']
                    break
        
        c1, c2 = st.columns(2)
        name = c1.text_input("Tên Khách Hàng", value=st.session_state.c_name)
        phone = c2.text_input("Số Điện Thoại", value=st.session_state.c_phone)
        addr = st.text_input("Địa Chỉ", value=st.session_state.c_addr)
        
        user_name = st.session_state.user['username']
        staff_options = ["Nam", "Dương", "Vạn", "Khác"]
        default_idx = staff_options.index(user_name) if user_name in staff_options else 0
        staff = st.selectbox("Nhân Viên Kinh Doanh", staff_options, index=default_idx, key="in_staff")

        st.divider()
        st.subheader("2. Chi tiết hàng hóa & Giá")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            i_name = col1.text_input("Tên hàng / Quy cách")
            i_unit = col2.text_input("ĐVT (Cái/M2)")
            i_qty = col3.number_input("Số lượng", 1.0, step=1.0)
            col4, col5, col6 = st.columns(3)
            i_cost = col4.number_input("Giá Vốn (Giá gốc)", 0.0, step=1000.0)
            i_price = col5.number_input("Giá Bán (Đơn giá)", 0.0, step=1000.0)
            i_vat = col6.number_input("% VAT", 0.0, 100.0, 0.0, step=1.0)
            if st.form_submit_button("➕ Thêm vào danh sách"):
                if i_name:
                    total_sell = i_qty * i_price
                    total_cost = i_qty * i_cost
                    vat_amt = total_sell * (i_vat / 100)
                    profit = total_sell - total_cost
            
                    comm_rate = 0.3
                    if staff in ["Nam", "Dương"]: comm_rate = 0.5
                    elif staff == "Vạn": comm_rate = 0.5
                    commission = profit * comm_rate if profit > 0 else 0
       
                    st.session_state.cart.append({
                        "name": i_name, "unit": i_unit, "qty": i_qty, "cost": i_cost,
                        "price": i_price, "vat_rate": i_vat, "vat_amt": vat_amt,
                        "profit": profit, "commission": commission,
                        "total_line": total_sell + vat_amt
                    })
                    st.rerun()
                else: st.error("Nhập tên hàng!")

        if st.session_state.cart:
            st.write("---")
            view_df = pd.DataFrame(st.session_state.cart).copy()
            for col in ['cost', 'price', 'vat_amt', 'profit', 'commission', 'total_line']:
                view_df[col] = view_df[col].apply(format_currency)
            view_df.columns = ["Tên hàng", "ĐVT", "SL", "Giá Vốn", "Giá Bán", "% VAT", "Tiền VAT", "Lợi Nhuận", "Hoa Hồng", "Giá Hoá Đơn"]
            st.dataframe(view_df, use_container_width=True)
            
            total_final = sum(i['total_line'] for i in st.session_state.cart)
            total_profit = sum(i['profit'] for i in st.session_state.cart)
            total_comm = sum(i['commission'] for i in st.session_state.cart)
            
            m1, m2, m3 = st.columns(3)
            m1.metric("TỔNG GIÁ TRỊ", format_currency(total_final))
            m2.metric("TỔNG LỢI NHUẬN", format_currency(total_profit))
            m3.metric("TỔNG HOA HỒNG", format_currency(total_comm))
            
            c_del, c_save = st.columns(2)
            if c_del.button("🗑️ Xóa giỏ"):
                st.session_state.cart = []
                st.rerun()
            if c_save.button("💾 LƯU BÁO GIÁ", type="primary"):
                if not name: st.error("Thiếu tên khách!")
                else:
                    new_order = {
                        "order_id": gen_id(), 
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "status": "Báo giá", "payment_status": "Chưa TT",
                        "customer": {"name": name, "phone": phone, "address": addr},
                        "items": st.session_state.cart,
                        "financial": {
                            "total": total_final, "paid": 0, "debt": total_final, "staff": staff, 
                            "total_profit": total_profit, "total_comm": total_comm, "commission_status": "Chưa chi"
                        }
                    }
                    if add_new_order(new_order):
                        save_customer_db(name, phone, addr)
                        st.session_state.last_order = new_order
                        st.session_state.cart = []
                        st.rerun()

        if st.session_state.last_order:
            oid = st.session_state.last_order['order_id']
            st.success(f"✅ Đã tạo: {oid}")
            pdf_bytes = create_pdf(st.session_state.last_order, "BÁO GIÁ")
            st.download_button("🖨️ Tải PDF", pdf_bytes, f"BG_{oid}.pdf", "application/pdf", type="primary")

    # --- TAB 2: QUẢN LÝ ĐƠN HÀNG (PIPELINE) ---
    elif menu == "2. Quản Lý Đơn Hàng (Pipeline)":
        st.header("🏭 Quy Trình Sản Xuất")
        all_orders = fetch_all_orders()
        tabs = st.tabs(["1️⃣ Báo Giá", "2️⃣ Thiết Kế", "3️⃣ Sản Xuất", "4️⃣ Giao Hàng", "5️⃣ Công Nợ", "✅ Hoàn Thành"])
        
        def render_tab_content(status_filter, next_status, btn_text, pdf_type=None):
            current_orders = [o for o in all_orders if o.get('status') == status_filter]
            if not current_orders:
                st.info("Không có đơn hàng nào trong mục này.")
                return

            table_data = []
            for o in current_orders:
                cust = o.get('customer', {})
                fin = o.get('financial', {})
                items = o.get('items', [])
                main_prod = items[0]['name'] if items else "---"
                table_data.append({
                    "Mã ĐH": o.get('order_id'), "Ngày": o.get('date'), "Khách hàng": cust.get('name'),
                    "Sản phẩm": main_prod, "Tổng tiền": format_currency(float(fin.get('total', 0))),
                    "Còn nợ": format_currency(float(fin.get('debt', 0))),
                    "Nhân viên": fin.get('staff', ''),
                    "Hoa hồng": format_currency(float(fin.get('total_comm', 0))),
                    "TT Thanh Toán": o.get('payment_status'), "TT Hoa Hồng": fin.get('commission_status', 'Chưa chi')
                })
            
            event = st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", key=f"tbl_{status_filter}")
            
            if event.selection.rows:
                idx = event.selection.rows[0]
                if idx >= len(current_orders):
                    st.warning("Đang đồng bộ lại dữ liệu bảng đơn hàng...")
                    st.rerun()
                    return
                
                sel_order = current_orders[idx]
                oid = sel_order.get('order_id')
                st.divider()
                st.subheader(f"🛠️ Xử lý đơn hàng: {oid}")
                
                cust = sel_order.get('customer', {})
                items = sel_order.get('items', [])
                fin = sel_order.get('financial', {})
                total, paid = float(fin.get('total', 0)), float(fin.get('paid', 0))
                debt = total - paid
                if debt < 0: debt = 0
                profit_val, comm_val = fin.get('total_profit', 0), fin.get('total_comm', 0)
                comm_stat = fin.get('commission_status', 'Chưa chi')

                col_d1, col_d2 = st.columns([2, 1])
                with col_d1:
                    st.write(f"👤 {cust.get('name')} - {cust.get('phone')} | 📍 {cust.get('address')}")
                    st.write("📦 **Chi tiết hàng hóa:**")
                    df_items = pd.DataFrame(items)
                    if not df_items.empty:
                        cols = ["name", "unit", "qty", "price", "vat_rate", "total_line"]
                        if set(cols).issubset(df_items.columns):
                            df_show = df_items[cols].copy()
                            df_show.columns = ["Tên", "ĐVT", "SL", "Giá", "%VAT", "Thành tiền"]
                            df_show['Giá'] = df_show['Giá'].apply(format_currency)
                            df_show['Thành tiền'] = df_show['Thành tiền'].apply(format_currency)
                            st.dataframe(df_show, hide_index=True, use_container_width=True)

                with col_d2:
                    st.info(f"💰 **TÀI CHÍNH**")
                    st.write(f"Tổng đơn: **{format_currency(total)}**")
                    st.write(f"Đã thanh
