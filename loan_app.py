import plotly.express as px # type: ignore
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import io
import hashlib

st.set_page_config(page_title="Prosper Macro Loans", layout="wide")

# ====================== DATABASE ======================
conn = sqlite3.connect('loans.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
             id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS loans (
             id INTEGER PRIMARY KEY, borrower_name TEXT, phone TEXT, amount REAL,
             interest_rate REAL, term_months INTEGER, total_repayment REAL,
             disbursement_date TEXT, due_date TEXT, amount_paid REAL DEFAULT 0,
             loan_officer TEXT, frozen INTEGER DEFAULT 0,
             is_balance_frozen INTEGER DEFAULT 0, frozen_balance REAL DEFAULT 0,
             collateral_type TEXT DEFAULT '', admin_fee REAL DEFAULT 0,
             loan_status TEXT DEFAULT 'Active', customer_id TEXT)''')

# Ensure existing databases have new columns
for column_sql in [
    "ALTER TABLE loans ADD COLUMN collateral_type TEXT DEFAULT ''",
    "ALTER TABLE loans ADD COLUMN admin_fee REAL DEFAULT 0",
    "ALTER TABLE loans ADD COLUMN loan_status TEXT DEFAULT 'Active'",
    "ALTER TABLE loans ADD COLUMN customer_id TEXT"
]:
    try:
        c.execute(column_sql)
    except sqlite3.OperationalError:
        pass

c.execute('''CREATE TABLE IF NOT EXISTS payments (
             id INTEGER PRIMARY KEY, loan_id INTEGER, amount REAL, payment_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS topups (
             id INTEGER PRIMARY KEY, loan_id INTEGER, topup_amount REAL, 
             topup_date TEXT, additional_months INTEGER, previous_balance REAL,
             new_due_date TEXT)''')

# Create topups table if it doesn't exist
try:
    c.execute('''CREATE TABLE IF NOT EXISTS topups (
                 id INTEGER PRIMARY KEY, loan_id INTEGER, topup_amount REAL, 
                 topup_date TEXT, additional_months INTEGER, previous_balance REAL,
                 new_due_date TEXT)''')
except sqlite3.OperationalError:
    pass

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Ensure default users exist with hashed passwords
c.execute("INSERT OR IGNORE INTO users (username, password, role, full_name) VALUES (?,?,?,?)",
          ('admin', hash_password('123456'), 'Admin', 'System Administrator'))
c.execute("INSERT OR IGNORE INTO users (username, password, role, full_name) VALUES (?,?,?,?)",
          ('officer1', hash_password('1234'), 'Officer', 'John Officer'))
conn.commit()

# ====================== HELPER FUNCTIONS ======================
def calculate_balance(total, paid):
    return max(0, total - paid)

def calculate_penalty(due_date_str, balance, frozen, is_balance_frozen):
    if is_balance_frozen or frozen or balance <= 0:
        return 0
    try:
        due = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        grace_end = due + timedelta(days=10)
        if today <= grace_end: return 0
        days_late = (today - grace_end).days
        return round(balance * 0.01 * days_late)
    except:
        return 0

def get_loan_status(balance, penalty):
    if balance <= 0:
        return "✅ Fully Paid"
    if penalty > 0:
        return "⚠️ Overdue"
    return "Active"

def format_currency(value):
    """Format numbers with commas for currency display"""
    return f"UGX {value:,.0f}"

def load_loans():
    loans = pd.read_sql_query("SELECT * FROM loans WHERE loan_status='Active' ORDER BY id ASC", conn)
    if loans.empty:
        return loans

    loans['balance'] = loans.apply(lambda x: calculate_balance(x.get('total_repayment', 0), x.get('amount_paid', 0)), axis=1)
    loans['penalty'] = loans.apply(
        lambda x: calculate_penalty(
            x.get('due_date', ''),
            x.get('balance', 0),
            x.get('frozen', 0),
            x.get('is_balance_frozen', 0)
        ),
        axis=1
    )
    loans['total_due'] = loans['balance'] + loans['penalty']
    loans['status'] = loans.apply(lambda x: get_loan_status(x['balance'], x['penalty']), axis=1)
    return loans


def filter_loans(df, borrower, phone, officer, status, overdue):
    if borrower:
        df = df[df['borrower_name'].str.contains(borrower, case=False, na=False)]
    if phone:
        df = df[df['phone'].str.contains(phone, case=False, na=False)]
    if officer:
        df = df[df['loan_officer'].str.contains(officer, case=False, na=False)]
    if status and status != 'All':
        df = df[df['status'] == status]
    if overdue == 'Only overdue':
        df = df[df['penalty'] > 0]
    return df

def generate_customer_id(name, phone):
    """Generate unique customer ID from name and phone"""
    return f"{name.replace(' ', '_')}_{phone}"

# ====================== LOGIN ======================
# Initialize session state defaults
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = ''
    st.session_state.username = ''

if not st.session_state.logged_in:
    st.title("🔐 PROSPER MACRO SOLUTIONS LTD")
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        hashed = hash_password(password)
        user = pd.read_sql_query("SELECT * FROM users WHERE username=? AND password=?", conn, params=(username, hashed))
        if not user.empty:
            st.session_state.logged_in = True
            st.session_state.user_role = user.iloc[0]['role']
            st.session_state.username = user.iloc[0]['username']
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()

# ====================== APP ======================
st.title("💼 PROSPER MACRO SOLUTIONS LTD")
st.subheader(f"Loan Management System | {st.session_state.username} ({st.session_state.user_role})")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Dashboard",
    "📝 New Loan",
    "📋 Portfolio",
    "💰 Record Payment",
    "📋 Reports",
    "✏️ Manage Loan",
    "👥 Admin"
])

# ====================== DASHBOARD ======================
with tab1:
    st.subheader("Business Dashboard")
    payments_df = pd.read_sql_query("SELECT * FROM payments", conn)
    df = load_loans()
    total_collected = payments_df['amount'].sum() if not payments_df.empty else 0

    if not df.empty:
        col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
        col1.metric("Total Disbursed", format_currency(df['amount'].sum()))
        col2.metric("Outstanding", format_currency(df['balance'].sum()))
        col3.metric("Total Collected", format_currency(total_collected))
        col4.metric("Overdue Loans", len(df[df['penalty'] > 0]))
        col5.metric("Total Loans", len(df))

        with st.expander("📌 Key Portfolio Charts", expanded=True):
            status_counts = df['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig1 = px.pie(status_counts, names='Status', values='Count', title='Loan Status Distribution')
            st.plotly_chart(fig1, use_container_width=True)

            officer_summary = df.groupby('loan_officer')['amount_paid'].sum().reset_index()
            fig2 = px.bar(officer_summary, x='loan_officer', y='amount_paid', title='Collections by Loan Officer')
            st.plotly_chart(fig2, use_container_width=True)

            if not payments_df.empty:
                payments_df['payment_date'] = pd.to_datetime(payments_df['payment_date'])
                payments_df['month'] = payments_df['payment_date'].dt.strftime('%Y-%m')
                monthly = payments_df.groupby('month')['amount'].sum().reset_index()
                fig3 = px.line(monthly, x='month', y='amount', markers=True, title='Monthly Collections')
                st.plotly_chart(fig3, use_container_width=True)

        st.markdown("---")
        with st.expander("📋 Recent Loans", expanded=True):
            display_df = df[['id', 'borrower_name', 'phone', 'amount', 'balance', 'penalty', 'loan_officer']].copy()
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No loans found.")

# ====================== NEW LOAN ======================
with tab2:
    st.subheader("Create New Loan")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Borrower Name *")
        phone = st.text_input("Phone Number *")
        amount = st.number_input("Loan Amount (UGX)", min_value=10000, value=100000, step=5000, format="%d")
        officer = st.text_input("Loan Officer", value=st.session_state.username)
    with col2:
        rate = st.number_input("Interest Rate (%)", value=14.0, step=0.5)
        months = st.number_input("Term (Months)", min_value=1, value=1)
        disb_date = st.date_input("Disbursement Date", datetime.now().date())
        collateral_type = st.selectbox(
            "Type of Collateral Offered",
            ["None", "Land Title", "Vehicle", "Equipment", "Property", "Savings"],
            index=0
        )
        admin_fee_input = st.number_input("Administration Fee (UGX)", min_value=0, value=10000, step=1000, format="%d",
                                         help="This fee is applied only for new customers.")
    
    if st.button("💾 Save New Loan", type="primary"):
        if name and phone:
            customer_id = generate_customer_id(name, phone)
            # Check if customer has completed a loan before
            existing_customer = c.execute("SELECT COUNT(*) FROM loans WHERE customer_id=? AND loan_status='Completed'", (customer_id,)).fetchone()[0] > 0
            admin_fee = 0 if existing_customer else admin_fee_input
            total = amount * (1 + (rate / 100) * months) + admin_fee
            due_date = disb_date + timedelta(days=30 * months)
            c.execute("""INSERT INTO loans (borrower_name, phone, amount, interest_rate, term_months, 
                         total_repayment, disbursement_date, due_date, loan_officer, collateral_type, admin_fee, loan_status, customer_id)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                      (name, phone, amount, rate, months, total, str(disb_date), str(due_date), officer,
                       collateral_type, admin_fee, 'Active', customer_id))
            conn.commit()
            if existing_customer:
                st.success(f"✅ Loan for **{name}** created without administration fee.")
            else:
                st.success(f"✅ New customer loan created with {format_currency(admin_fee)} administration fee.")
            st.rerun()

# ====================== PORTFOLIO ======================
with tab3:
    st.subheader("Loans Portfolio")
    df = load_loans()

    if not df.empty:
        borrower_search, phone_search, officer_search = st.columns(3)
        with borrower_search:
            borrower = st.text_input("Borrower Name")
        with phone_search:
            phone = st.text_input("Phone Number")
        with officer_search:
            officer = st.text_input("Loan Officer")

        status = st.selectbox("Status", ["All", "Active", "⚠️ Overdue", "✅ Fully Paid"], key="portfolio_status")
        overdue = st.selectbox("Overdue Filter", ["All", "Only overdue"], key="portfolio_overdue")

        filtered_df = filter_loans(df, borrower, phone, officer, status, overdue)

        col_exp1, col_exp2 = st.columns([1, 4])
        with col_exp1:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, index=False)
            output.seek(0)
            st.download_button("⬇️ Download Portfolio", output, "portfolio.xlsx", 
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="exp_port")

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    else:
        st.info("No loans found.")

# ====================== RECORD PAYMENT ======================
with tab4:
    st.subheader("Record Payment")
    col1, col2 = st.columns(2)
    with col1:
        loan_id = st.number_input("Loan ID", min_value=1)
        pay_amount = st.number_input("Payment Amount (UGX)", min_value=1000, format="%d")
    with col2:
        pay_date = st.date_input("Payment Date", datetime.now().date())
    
    if st.button("💰 Record Payment", type="primary"):
        c.execute("SELECT id FROM loans WHERE id=?", (loan_id,))
        if c.fetchone():
            pay_date_str = pay_date.strftime('%Y-%m-%d')
            c.execute("INSERT INTO payments (loan_id, amount, payment_date) VALUES (?,?,?)", (loan_id, pay_amount, pay_date_str))
            c.execute("UPDATE loans SET amount_paid = amount_paid + ? WHERE id=?", (pay_amount, loan_id))
            conn.commit()
            st.success("✅ Payment recorded!")
            st.rerun()
        else:
            st.error("Loan ID not found")

# ====================== REPORTS ======================
with tab5:
    st.subheader("Reports & Statements")
    report_type = st.selectbox("Select Report", ["Portfolio Summary", "Overdue Loans", "Loan Statement"])
    df = load_loans()

    if report_type == "Loan Statement":
        stmt_id = st.number_input("Enter Loan ID", min_value=1)
        if st.button("Generate Statement"):
            loan = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(stmt_id,))
            payments = pd.read_sql_query("SELECT * FROM payments WHERE loan_id=? ORDER BY payment_date DESC", conn, params=(stmt_id,))
            topups = pd.read_sql_query("SELECT * FROM topups WHERE loan_id=? ORDER BY topup_date DESC", conn, params=(stmt_id,))
            if not loan.empty:
                st.dataframe(loan, hide_index=True)
                st.subheader("Payment History")
                st.dataframe(payments, hide_index=True)
                if not topups.empty:
                    st.subheader("Top-up History")
                    st.dataframe(topups, hide_index=True)
            else:
                st.error("Loan not found.")

    elif report_type == "Overdue Loans":
        overdue = df[df['penalty'] > 0].copy()
        if not overdue.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                overdue.to_excel(writer, index=False)
            output.seek(0)
            st.download_button("⬇️ Download Overdue Report", output, "overdue_loans.xlsx", 
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="exp_overdue")
            st.dataframe(overdue, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 No overdue loans at the moment!")

    else:
        if not df.empty:
            df['total_due'] = df['balance'] + df['penalty']
            st.metric("Total Loans", len(df))
            st.metric("Outstanding", format_currency(df['balance'].sum()))
            st.metric("Overdue Loans", len(df[df['penalty'] > 0]))

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            st.download_button("⬇️ Download Portfolio Summary", output, "portfolio_summary.xlsx", 
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="exp_summary")

            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No loans found.")

# ====================== MANAGE LOAN ======================
with tab6:
    st.subheader("Manage Loan")
    manage_id = st.number_input("Loan ID", min_value=1, key="manage_id")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("❄️ Freeze / Unfreeze"):
            c.execute("UPDATE loans SET frozen = NOT frozen WHERE id=?", (manage_id,))
            conn.commit()
            st.success("Status updated!")
            st.rerun()
    with col2:
        if st.button("🔒 Freeze Balance"):
            loan = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(manage_id,))
            if not loan.empty:
                bal = calculate_balance(loan.iloc[0]['total_repayment'], loan.iloc[0]['amount_paid'])
                c.execute("UPDATE loans SET is_balance_frozen=1, frozen_balance=? WHERE id=?", (bal, manage_id))
                conn.commit()
                st.success(f"Balance frozen at {format_currency(bal)}")
                st.rerun()
    with col3:
        if st.button("🔓 Unfreeze Balance"):
            c.execute("UPDATE loans SET is_balance_frozen=0, frozen_balance=0 WHERE id=?", (manage_id,))
            conn.commit()
            st.success("Balance unfrozen!")
            st.rerun()

    st.divider()
    st.subheader("➕ Top-up Loan")
    
    # Load current loan info for top-up
    current_loan = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(manage_id,))
    
    if not current_loan.empty:
        loan_row = current_loan.iloc[0]
        current_balance = calculate_balance(loan_row['total_repayment'], loan_row['amount_paid'])
        
        st.info(f"📊 Current Balance: **{format_currency(current_balance)}**")
        
        topup_date = st.date_input("Top-up Date", datetime.now().date(), key="topup_date")
        topup_amount = st.number_input("Top-up Amount (UGX)", min_value=10000, value=50000, step=10000, format="%d")
        topup_months = st.number_input("Additional Months", min_value=1, value=1)
        
        if st.button("Add Top-up", type="primary"):
            # Calculate new values including current balance
            interest_on_topup = topup_amount * (loan_row['interest_rate'] / 100) * topup_months
            
            new_total = loan_row['total_repayment'] + interest_on_topup
            new_term = int(loan_row['term_months']) + int(topup_months)
            new_due = topup_date + timedelta(days=30 * topup_months)
            
            # Record top-up in topups table
            c.execute("""INSERT INTO topups (loan_id, topup_amount, topup_date, additional_months, previous_balance, new_due_date)
                         VALUES (?,?,?,?,?,?)""",
                      (manage_id, topup_amount, str(topup_date), topup_months, current_balance, str(new_due)))
            
            # Update loan record
            c.execute("""UPDATE loans SET total_repayment=?, term_months=?, due_date=? WHERE id=?""",
                      (new_total, new_term, str(new_due), manage_id))
            conn.commit()
            st.success(f"""✅ Top-up added successfully!

**Summary:**
- Previous Balance: {format_currency(current_balance)}
- Top-up Amount: {format_currency(topup_amount)}
- Interest on Top-up: {format_currency(interest_on_topup)}
- New Due Date: {new_due}""")
            st.rerun()

    st.divider()
    st.subheader("💾 Mark Loan as Completed")
    if st.button("Mark as Fully Paid", type="secondary", key="mark_completed"):
        c.execute("UPDATE loans SET loan_status='Completed' WHERE id=?", (manage_id,))
        conn.commit()
        st.success("✅ Loan marked as completed!")
        st.rerun()

    st.divider()
    if st.button("✏️ Load for Editing"):
        loan_data = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(manage_id,))
        if not loan_data.empty:
            st.session_state.edit_loan = loan_data.iloc[0].to_dict()
            st.success("Loan loaded!")

    if 'edit_loan' in st.session_state:
        loan = st.session_state.edit_loan
        st.write(f"**Editing: {loan['borrower_name']}**")
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Borrower Name", loan['borrower_name'])
            new_phone = st.text_input("Phone", loan['phone'])
            new_amount = st.number_input("Amount", value=float(loan['amount']), format="%d")
            new_officer = st.text_input("Officer", loan['loan_officer'])
        with col2:
            new_rate = st.number_input("Rate (%)", value=float(loan['interest_rate']))
            new_months = st.number_input("Months", value=int(loan['term_months']))
            new_disb = st.date_input("Disbursement Date", datetime.strptime(loan['disbursement_date'], '%Y-%m-%d').date())
            new_due = st.date_input("Due Date", datetime.strptime(loan['due_date'], '%Y-%m-%d').date())
            new_frozen = st.checkbox("Frozen", value=bool(loan.get('frozen', 0)))
        
        if st.button("💾 Save Changes", type="primary"):
            new_total = new_amount * (1 + (new_rate / 100) * new_months)
            c.execute("""UPDATE loans SET borrower_name=?, phone=?, amount=?, interest_rate=?, term_months=?, 
                        total_repayment=?, disbursement_date=?, due_date=?, loan_officer=?, frozen=? WHERE id=?""",
                      (new_name, new_phone, new_amount, new_rate, new_months, new_total, 
                       str(new_disb), str(new_due), new_officer, int(new_frozen), manage_id))
            conn.commit()
            st.success("✅ Loan updated successfully!")
            del st.session_state.edit_loan
            st.rerun()

st.sidebar.success(f"👤 {st.session_state.username} ({st.session_state.user_role})")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ====================== ADMIN ======================
with tab7:

    if st.session_state.user_role != "Admin":
        st.error("Access denied. Admin only.")
        st.stop()

    st.subheader("👥 User Administration")

    admin_action = st.selectbox(
        "Choose Action",
        ["View Users", "Add User", "Change Password", "Delete User"]
    )

    # ================= VIEW USERS =================
    if admin_action == "View Users":
        users_df = pd.read_sql_query(
            "SELECT id, username, role, full_name FROM users",
            conn
        )

        st.dataframe(users_df, use_container_width=True, hide_index=True)

    # ================= ADD USER =================
    elif admin_action == "Add User":

        st.write("### Add New User")

        new_fullname = st.text_input("Full Name")
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        new_role = st.selectbox("Role", ["Admin", "Officer"])

        if st.button("➕ Create User"):

            try:
                c.execute("""
                    INSERT INTO users (username, password, role, full_name)
                    VALUES (?, ?, ?, ?)
                """, (
                    new_username,
                    hash_password(new_password),
                    new_role,
                    new_fullname
                ))

                conn.commit()

                st.success("✅ User created successfully!")

            except:
                st.error("Username already exists")

    # ================= CHANGE PASSWORD =================
    elif admin_action == "Change Password":

        users = pd.read_sql_query(
            "SELECT username FROM users",
            conn
        )

        selected_user = st.selectbox(
            "Select User",
            users['username']
        )

        new_pass = st.text_input(
            "New Password",
            type="password"
        )

        if st.button("🔑 Update Password"):

            c.execute("""
                UPDATE users
                SET password=?
                WHERE username=?
            """, (hash_password(new_pass), selected_user))

            conn.commit()

            st.success("✅ Password updated!")

    # ================= DELETE USER =================
    elif admin_action == "Delete User":

        users = pd.read_sql_query(
            "SELECT username FROM users WHERE username != 'admin'",
            conn
        )

        del_user = st.selectbox(
            "Select User",
            users['username']
        )

        if st.button("🗑️ Delete User"):

            c.execute(
                "DELETE FROM users WHERE username=?",
                (del_user,)
            )

            conn.commit()

            st.success("✅ User deleted!")
