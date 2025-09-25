# RedFlag - Nextail RO Allocation Guardian
# Streamlit App Version

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io

# Page config
st.set_page_config(
    page_title="RedFlag - Allocation Guardian",
    page_icon="🚩",
    layout="wide"
)

# Title and description
st.title("🚩 RedFlag - Allocation Guardian")
st.markdown("**Catch misallocations before they ship!** Upload your RO file and Linked Lines to detect when inventory is being sent to stores with insufficient stock.")

# Create two columns for file uploaders
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 RO File")
    ro_file = st.file_uploader("Upload your RO Excel file", type=['xlsx', 'xls'], key="ro")

with col2:
    st.subheader("🔗 Linked Lines (Optional)")
    linked_file = st.file_uploader("Upload your Linked Lines file (.xlsx format)", type=['xlsx', 'xls'], key="linked")
    st.caption("⚠️ Please convert .xlsb files to .xlsx before uploading")
    
# Threshold setting
st.sidebar.header("⚙️ Settings")
THRESHOLD = st.sidebar.slider(
    "Minimum stock threshold",
    min_value=1,
    max_value=10,
    value=3,
    help="Flag allocations to stores with less than this many units on hand"
)

# Add a button to process
if st.button("🚩 Run RedFlag Analysis", type="primary", disabled=not ro_file):
    
    # Initialize progress bar
    progress = st.progress(0)
    status = st.empty()
    
    try:
        # ========================================
        # STEP 1: Process Linked Lines (if provided)
        # ========================================
        product_to_group = {}
        group_to_products = {}
        linked_groups = {}
        
        if linked_file:
            status.text("Processing linked lines...")
            progress.progress(10)
            
            # Read the linked lines file - using the "Linked" tab
            try:
                linked_df = pd.read_excel(linked_file, sheet_name='Linked')
            except Exception as e:
                st.warning(f"Could not read 'Linked' sheet, trying first sheet: {str(e)}")
                linked_df = pd.read_excel(linked_file)
            
            # Process the Linked tab structure
            linked_data_list = []
            current_group = 0
            
            for idx, row in linked_df.iterrows():
                product_ref = row.iloc[0] if len(row) > 0 else None
                order_in = row.iloc[1] if len(row) > 1 else None
                
                if pd.isna(product_ref) or pd.isna(order_in):
                    continue
                    
                try:
                    order_val = float(order_in)
                except:
                    continue
                
                if order_val == 1:
                    current_group += 1
                
                linked_data_list.append({
                    'Group': current_group,
                    'ProdReference': str(product_ref).strip()
                })
            
            linked_df_cols = pd.DataFrame(linked_data_list)
            
            if len(linked_df_cols) > 0:
                # Create dictionaries for lookups
                product_to_group = dict(zip(linked_df_cols['ProdReference'], linked_df_cols['Group']))
                
                for group in linked_df_cols['Group'].unique():
                    products = linked_df_cols[linked_df_cols['Group'] == group]['ProdReference'].tolist()
                    group_to_products[group] = products
                
                linked_groups = {k: v for k, v in group_to_products.items() if len(v) > 1}
                
                st.success(f"✅ Found {len(product_to_group)} products in {len(linked_groups)} linked groups")
        
        # ========================================
        # STEP 2: Process RO File
        # ========================================
        status.text("Processing RO file...")
        progress.progress(30)
        
        # Read the RO file
        df = pd.read_excel(ro_file)
        
        # Create working dataframe with required columns
        # Using column positions (A=0, G=6, H=7, I=8, M=12, Y=24)
        working_df = df[[df.columns[i] for i in [0, 6, 7, 8, 12, 24]]].copy()
        working_df.columns = ['Store_Code', 'ProdReference', 'Size', 'Store_Stock', 'Quantity', 'Quantity_28']
        
        # Clean the data
        working_df['Store_Stock'] = pd.to_numeric(working_df['Store_Stock'], errors='coerce').fillna(0)
        working_df['Quantity'] = pd.to_numeric(working_df['Quantity'], errors='coerce').fillna(0)
        working_df['Quantity_28'] = pd.to_numeric(working_df['Quantity_28'], errors='coerce').fillna(0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Rows", f"{len(working_df):,}")
        col2.metric("Unique Stores", f"{working_df['Store_Code'].nunique():,}")
        col3.metric("Unique Products", f"{working_df['ProdReference'].nunique():,}")
        
        # ========================================
        # STEP 3: Apply Linked Lines Logic
        # ========================================
        status.text("Applying linked lines logic...")
        progress.progress(50)
        
        def get_product_group(prod_ref):
            # First try exact match
            if prod_ref in product_to_group:
                group = product_to_group[prod_ref]
                if group in linked_groups:
                    return f"Group_{group}"
            
            # If no exact match, try removing common suffixes
            base_ref = prod_ref
            if prod_ref.endswith('_R'):
                base_ref = prod_ref[:-2]
                if base_ref in product_to_group:
                    group = product_to_group[base_ref]
                    if group in linked_groups:
                        return f"Group_{group}"
            
            # Check for prefix matches
            for linked_prod, group in product_to_group.items():
                if group in linked_groups:
                    if prod_ref.startswith(linked_prod) or linked_prod.startswith(prod_ref):
                        return f"Group_{group}"
            
            return prod_ref
        
        if linked_file:
            working_df['Product_Group'] = working_df['ProdReference'].apply(get_product_group)
            grouped_products = working_df[working_df['Product_Group'].str.startswith('Group_')]['ProdReference'].nunique()
            if grouped_products > 0:
                st.info(f"🔗 {grouped_products} products matched to linked groups")
        else:
            working_df['Product_Group'] = working_df['ProdReference']
        
        # ========================================
        # STEP 4: Detect Misallocations
        # ========================================
        status.text("Detecting misallocations...")
        progress.progress(70)
        
        # Filter only allocations
        allocations = working_df[working_df['Quantity'] > 0].copy()
        
        # Group by Store + Product_Group
        store_product_stock = working_df.groupby(['Store_Code', 'Product_Group'])['Store_Stock'].sum().reset_index()
        store_product_stock.columns = ['Store_Code', 'Product_Group', 'Total_Store_Stock']
        
        store_product_sales = working_df.groupby(['Store_Code', 'Product_Group'])['Quantity_28'].sum().reset_index()
        store_product_sales.columns = ['Store_Code', 'Product_Group', 'Total_Sales_28']
        
        # Merge
        allocations = allocations.merge(store_product_stock, on=['Store_Code', 'Product_Group'], how='left')
        allocations = allocations.merge(store_product_sales, on=['Store_Code', 'Product_Group'], how='left')
        
        # Flag misallocations
        allocations['Is_Misallocation'] = allocations['Total_Store_Stock'] < THRESHOLD
        allocations['Is_Linked'] = allocations['Product_Group'].str.startswith('Group_')
        
        misallocations = allocations[allocations['Is_Misallocation']].copy()
        
        # ========================================
        # STEP 5: Display Results
        # ========================================
        status.text("Generating report...")
        progress.progress(90)
        
        st.markdown("---")
        
        if len(misallocations) > 0:
            # Alert box
            st.error(f"🚩 **RED FLAGS DETECTED: {len(misallocations)} allocations need review**")
            
            # Statistics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Misallocation Rate", 
                f"{(len(misallocations)/len(allocations)*100):.1f}%",
                delta=f"{len(misallocations)} issues"
            )
            col2.metric("Stores Affected", f"{misallocations['Store_Code'].nunique()}")
            col3.metric("Products Affected", f"{misallocations['ProdReference'].nunique()}")
            col4.metric("Units at Risk", f"{misallocations['Quantity'].sum():,}")
            
            # Create summary
            st.subheader("📋 Flagged Allocations")
            
            summary_data = []
            for store in misallocations['Store_Code'].unique():
                store_misalloc = misallocations[misallocations['Store_Code'] == store]
                
                for prod_group in store_misalloc['Product_Group'].unique():
                    group_data = store_misalloc[store_misalloc['Product_Group'] == prod_group]
                    products_in_group = group_data['ProdReference'].unique()
                    
                    linked_info = ""
                    if prod_group.startswith('Group_') and linked_file:
                        group_num = float(prod_group.replace('Group_', ''))
                        if group_num in group_to_products:
                            all_linked = group_to_products[group_num]
                            other_linked = [p for p in all_linked if p not in products_in_group]
                            if other_linked:
                                linked_info = ", ".join(other_linked[:3])
                                if len(other_linked) > 3:
                                    linked_info += f" +{len(other_linked)-3} more"
                    
                    summary_data.append({
                        'Store': store,
                        'Product': ', '.join(products_in_group[:2]) + (f' +{len(products_in_group)-2}' if len(products_in_group) > 2 else ''),
                        'Current Stock': int(group_data['Total_Store_Stock'].iloc[0]),
                        'Units to Send': int(group_data['Quantity'].sum()),
                        '28-Day Sales': int(group_data['Total_Sales_28'].iloc[0]),
                        'Linked With': linked_info if linked_info else '-'
                    })
            
            summary_df = pd.DataFrame(summary_data)
            summary_df = summary_df.sort_values(['Current Stock', 'Units to Send'], ascending=[True, False])
            
            # Display table with formatting
            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Store": st.column_config.TextColumn("Store", width="small"),
                    "Current Stock": st.column_config.NumberColumn("Current Stock", format="%d"),
                    "Units to Send": st.column_config.NumberColumn("To Send", format="%d"),
                    "28-Day Sales": st.column_config.NumberColumn("28-Day Sales", format="%d"),
                }
            )
            
            # Download button for full details
            csv = summary_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Full Report (CSV)",
                data=csv,
                file_name=f"redflag_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
            
        else:
            st.success("✅ **ALL CLEAR!** No red flags detected. All allocations are going to stores with adequate stock.")
        
        progress.progress(100)
        status.text("Analysis complete!")
        
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        st.exception(e)

# Footer
st.markdown("---")
st.markdown("**RedFlag** - Your allocation safety net | Built with Streamlit")

# Sidebar info
st.sidebar.markdown("---")
st.sidebar.markdown("### 🚩 About RedFlag")
st.sidebar.markdown("RedFlag catches allocation mistakes before they become shipping problems.")

st.sidebar.markdown("### How it works")
st.sidebar.markdown("""
1. Upload your RO allocation file
2. Optionally upload Linked Lines for grouped products
3. RedFlag checks if stores have sufficient stock
4. Review flagged allocations before shipping
""")

st.sidebar.markdown("### File Requirements")
st.sidebar.markdown("""
**RO File columns:**
- A: Store Code
- G: Product Reference  
- I: Store Stock
- M: Quantity to send
- Y: 28-day sales

**Linked Lines:**
- Use the 'Linked' tab
- Column B: Order indicator (1 = new group)
- ⚠️ Must be .xlsx format (not .xlsb)
""")

st.sidebar.markdown("### Support")
st.sidebar.markdown("Questions? Issues? Contact the allocation team.")