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
    st.subheader("🔗 Linked Lines")
    
    # Check if default linked lines file exists in the repository
    use_default_linked = st.checkbox("Use default Linked Lines file", value=True)
    
    if use_default_linked:
        linked_file = "linked_lines_default.xlsx"
        st.success("✅ Using default Linked Lines file")
        st.caption("Uncheck above to upload a different version")
    else:
        linked_file = st.file_uploader("Upload a different Linked Lines file (.xlsx format)", type=['xlsx', 'xls'], key="linked")
    
# Threshold setting
st.sidebar.header("⚙️ Settings")
THRESHOLD = st.sidebar.slider(
    "Minimum (Stock + L28 Sales) threshold",
    min_value=1,
    max_value=10,
    value=4,
    help="Flag allocations to stores where (On Hand + 28-day Sales) is less than this threshold"
)

# All-out threshold settings
st.sidebar.markdown("---")
st.sidebar.subheader("📦 All-Out Strategy")
USA_ALLOUT_THRESHOLD = st.sidebar.number_input(
    "USA Warehouse Threshold",
    min_value=0,
    max_value=100,
    value=40,
    help="Flag styles with less than this many units remaining in USA warehouse"
)
CDA_ALLOUT_THRESHOLD = st.sidebar.number_input(
    "CDA Warehouse Threshold",
    min_value=0,
    max_value=100,
    value=30,
    help="Flag styles with less than this many units remaining in CDA warehouse"
)

st.sidebar.markdown("---")
st.sidebar.markdown("**New Logic:**")
st.sidebar.markdown("✅ Dimensions are grouped together")
st.sidebar.markdown("✅ 28-day sales count as proof of carrying the style")

# Special door constants
ECOM_DOORS = ['883', '886']
CLEARANCE_DOORS = ['3017', '3221', '7003']

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
        product_to_details = {}  # NEW: Store product names and colors
        
        if linked_file:
            status.text("Processing linked lines...")
            progress.progress(10)
            
            # Read the linked lines file
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
                style_name = row.iloc[3] if len(row) > 3 else None  # Column D
                color = row.iloc[4] if len(row) > 4 else None  # Column E
                
                if pd.isna(product_ref) or pd.isna(order_in):
                    continue
                    
                try:
                    order_val = float(order_in)
                except:
                    continue
                
                if order_val == 1:
                    current_group += 1
                
                # Store product details
                product_key = str(product_ref).strip()
                if not pd.isna(style_name) or not pd.isna(color):
                    product_to_details[product_key] = {
                        'style_name': str(style_name) if not pd.isna(style_name) else '',
                        'color': str(color) if not pd.isna(color) else ''
                    }
                
                linked_data_list.append({
                    'Group': current_group,
                    'ProdReference': product_key
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
        # Using column positions (A=0, F=5, G=6, H=7, I=8, M=12, Y=24, R=17)
        working_df = df[[df.columns[i] for i in [0, 5, 6, 7, 8, 12, 24, 17]]].copy()
        working_df.columns = ['Store_Code', 'ProdName', 'ProdReference', 'Size', 'Store_Stock', 'Quantity', 'Quantity_28', 'Wh_Stock']
        
        # Clean the data
        working_df['Store_Code'] = working_df['Store_Code'].astype(str)
        working_df['Store_Stock'] = pd.to_numeric(working_df['Store_Stock'], errors='coerce').fillna(0)
        working_df['Quantity'] = pd.to_numeric(working_df['Quantity'], errors='coerce').fillna(0)
        working_df['Quantity_28'] = pd.to_numeric(working_df['Quantity_28'], errors='coerce').fillna(0)
        working_df['Wh_Stock'] = pd.to_numeric(working_df['Wh_Stock'], errors='coerce').fillna(0)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Rows", f"{len(working_df):,}")
        col2.metric("Unique Stores", f"{working_df['Store_Code'].nunique():,}")
        col3.metric("Unique Products", f"{working_df['ProdReference'].nunique():,}")
        
        # ========================================
        # STEP 3: Apply Grouping Logic (Linked Lines + Dimensions)
        # ========================================
        status.text("Applying grouping logic...")
        progress.progress(50)
        
        def get_base_product(prod_ref):
            """Extract base product without dimension suffix"""
            base_product = prod_ref
            
            # Remove _R suffix
            if base_product.endswith('_R'):
                base_product = base_product[:-2]
            
            # Check if product has dimension (ends with _XX where XX is numbers)
            if '_' in base_product:
                parts = base_product.rsplit('_', 1)
                if len(parts) == 2 and parts[1].isdigit():
                    base_product = parts[0]
            
            return base_product
        
        def get_product_group(prod_ref):
            # Get base product without dimension
            base_product = get_base_product(prod_ref)
            has_dimension = base_product != prod_ref.replace('_R', '')
            
            # Check if base product is in linked groups
            if base_product in product_to_group:
                group = product_to_group[base_product]
                if group in linked_groups:
                    return f"Group_{group}"
            
            # Try without _R suffix for linked lines matching
            if base_product.endswith('_R'):
                base_no_r = base_product[:-2]
                if base_no_r in product_to_group:
                    group = product_to_group[base_no_r]
                    if group in linked_groups:
                        return f"Group_{group}"
            
            # Check for prefix matches with linked products
            for linked_prod, group in product_to_group.items():
                if group in linked_groups:
                    if base_product.startswith(linked_prod) or linked_prod.startswith(base_product):
                        return f"Group_{group}"
            
            # If not linked but has dimension, group by base product
            if has_dimension:
                return f"Dim_{base_product}"
            
            # No grouping found, return original
            return prod_ref
        
        working_df['Base_Product'] = working_df['ProdReference'].apply(get_base_product)
        working_df['Product_Group'] = working_df['ProdReference'].apply(get_product_group)
        
        # Create unique SKU identifier for warehouse calculations
        working_df['SKU'] = working_df['ProdReference'] + '_' + working_df['Size'].astype(str)
        
        # Count grouped products
        grouped_products = working_df[working_df['Product_Group'].str.startswith(('Group_', 'Dim_'))]['ProdReference'].nunique()
        if grouped_products > 0:
            linked_count = working_df[working_df['Product_Group'].str.startswith('Group_')]['ProdReference'].nunique()
            dim_count = working_df[working_df['Product_Group'].str.startswith('Dim_')]['ProdReference'].nunique()
            st.info(f"🔗 {linked_count} products in linked groups | 📏 {dim_count} products grouped by dimension")
        
        # ========================================
        # STEP 4: Detect Misallocations with New Logic
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
        
        # NEW LOGIC: Flag misallocations based on (Stock + L28 Sales) < Threshold
        allocations['Combined_Metric'] = allocations['Total_Store_Stock'] + allocations['Total_Sales_28']
        allocations['Is_Misallocation'] = allocations['Combined_Metric'] < THRESHOLD
        
        # Add flags for grouped products and special doors
        allocations['Is_Linked'] = allocations['Product_Group'].str.startswith('Group_')
        allocations['Is_Dimension_Grouped'] = allocations['Product_Group'].str.startswith('Dim_')
        allocations['Is_ECOM'] = allocations['Store_Code'].isin(ECOM_DOORS)
        allocations['Is_Clearance'] = allocations['Store_Code'].isin(CLEARANCE_DOORS)
        
        misallocations = allocations[allocations['Is_Misallocation']].copy()
        
        # ========================================
        # STEP 4.5: Calculate All-Out Candidates
        # ========================================
        status.text("Checking all-out strategy...")
        progress.progress(80)
        
        # Get unique SKUs with their warehouse quantities (only count each SKU once)
        unique_skus = working_df[['SKU', 'Product_Group', 'Base_Product', 'ProdReference', 'ProdName', 'Size', 'Wh_Stock']].drop_duplicates(subset=['SKU'])
        
        # Group by Product_Group (which includes linked lines) to get total warehouse inventory
        product_wh_summary = unique_skus.groupby('Product_Group').agg({
            'Wh_Stock': 'sum'
        }).reset_index()
        product_wh_summary.columns = ['Product_Group', 'Warehouse_Remaining']
        
        # Flag products that should go all-out
        product_wh_summary['Should_AllOut_USA'] = (
            (product_wh_summary['Warehouse_Remaining'] > 0) & 
            (product_wh_summary['Warehouse_Remaining'] < USA_ALLOUT_THRESHOLD)
        )
        product_wh_summary['Should_AllOut_CDA'] = (
            (product_wh_summary['Warehouse_Remaining'] > 0) & 
            (product_wh_summary['Warehouse_Remaining'] < CDA_ALLOUT_THRESHOLD)
        )
        product_wh_summary['Should_AllOut'] = product_wh_summary['Should_AllOut_USA'] | product_wh_summary['Should_AllOut_CDA']
        
        allout_candidates = product_wh_summary[product_wh_summary['Should_AllOut']].copy()
        
        # ========================================
        # STEP 5: Display Results - Misallocations
        # ========================================
        status.text("Generating report...")
        progress.progress(90)
        
        st.markdown("---")
        
        if len(misallocations) > 0:
            # Count unique product references (styles)
            unique_styles = misallocations['ProdReference'].nunique()
            
            # Alert box
            st.error(f"🚩 **RED FLAGS DETECTED: {unique_styles} unique styles need review**")
            
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
            st.caption(f"Showing allocations where (On Hand + L28 Sales) < {THRESHOLD}")
            
            summary_data = []
            for store in misallocations['Store_Code'].unique():
                store_misalloc = misallocations[misallocations['Store_Code'] == store]
                
                for prod_group in store_misalloc['Product_Group'].unique():
                    group_data = store_misalloc[store_misalloc['Product_Group'] == prod_group]
                    products_in_group = group_data['ProdReference'].unique()
                    base_product = group_data['Base_Product'].iloc[0]
                    
                    # Get product name from column F - find first non-null value
                    product_display = ""
                    prod_name_values = group_data['ProdName'].dropna()
                    if len(prod_name_values) > 0:
                        product_display = str(prod_name_values.iloc[0])
                    
                    # Parse product name to extract style name and color
                    # Format is typically: "STYLE NAME||COLOR" or similar
                    style_name = ""
                    color = ""
                    if product_display and '||' in product_display:
                        parts = product_display.split('||')
                        style_name = parts[1].strip() if len(parts) > 1 else ""
                        color = parts[2].strip() if len(parts) > 2 else ""
                    
                    # Determine group type
                    group_type = ""
                    if prod_group.startswith('Group_'):
                        group_type = "Linked"
                        if linked_file:
                            group_num = float(prod_group.replace('Group_', ''))
                            if group_num in group_to_products:
                                all_linked = group_to_products[group_num]
                                other_linked = [p for p in all_linked if p not in products_in_group]
                                if other_linked:
                                    group_type = f"Linked with {len(other_linked)} others"
                    elif prod_group.startswith('Dim_'):
                        group_type = "Dimension Group"
                    
                    # Check if special door
                    is_special = group_data['Is_ECOM'].iloc[0] or group_data['Is_Clearance'].iloc[0]
                    
                    summary_data.append({
                        'Store': store,
                        'Product': ', '.join(products_in_group[:2]) + (f' +{len(products_in_group)-2}' if len(products_in_group) > 2 else ''),
                        'Style Name': style_name if style_name else '-',
                        'Color': color if color else '-',
                        'On Hand': int(group_data['Total_Store_Stock'].iloc[0]),
                        'L28 Sales': int(group_data['Total_Sales_28'].iloc[0]),
                        'Combined': int(group_data['Combined_Metric'].iloc[0]),
                        'Units to Send': int(group_data['Quantity'].sum()),
                        'Group Type': group_type if group_type else '-',
                        'Is_Special': is_special
                    })
            
            summary_df = pd.DataFrame(summary_data)
            # Sort by Style Name, then Color, then Units to Send (descending)
            summary_df = summary_df.sort_values(['Style Name', 'Color', 'Units to Send'], ascending=[True, True, False])
            
            # Apply styling for special doors
            def highlight_special_doors(row):
                if row['Is_Special']:
                    return ['background-color: #e0e0e0'] * len(row)
                return [''] * len(row)
            
            # Apply styling to the dataframe that still has Is_Special
            styled_df = summary_df.style.apply(highlight_special_doors, axis=1)
            
            # Display table with formatting
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Store": st.column_config.TextColumn("Store", width="small"),
                    "Style Name": st.column_config.TextColumn("Style Name", width="medium"),
                    "Color": st.column_config.TextColumn("Color", width="small"),
                    "On Hand": st.column_config.NumberColumn("On Hand", format="%d"),
                    "L28 Sales": st.column_config.NumberColumn("L28 Sales", format="%d"),
                    "Combined": st.column_config.NumberColumn("Combined", format="%d", help="On Hand + L28 Sales"),
                    "Units to Send": st.column_config.NumberColumn("To Send", format="%d"),
                }
            )
            
            st.caption("🔲 Grey rows = ECOM (883, 886) or Clearance (3017, 3221, 7003) doors")
            
            # Download button for full details
            csv = summary_df.drop(columns=['Is_Special']).to_csv(index=False)
            st.download_button(
                label="📥 Download Misallocations Report (CSV)",
                data=csv,
                file_name=f"redflag_misallocations_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
            
        else:
            st.success("✅ **ALL CLEAR!** No red flags detected. All allocations are going to stores with adequate stock.")
        
        # ========================================
        # STEP 6: Display All-Out Candidates
        # ========================================
        st.markdown("---")
        
        if len(allout_candidates) > 0:
            st.warning(f"📦 **ALL-OUT STRATEGY: {len(allout_candidates)} styles should go all-out**")
            st.caption(f"Showing styles with < {USA_ALLOUT_THRESHOLD} units (USA) or < {CDA_ALLOUT_THRESHOLD} units (CDA) remaining in warehouse")
            
            # Statistics
            col1, col2 = st.columns(2)
            col1.metric("Styles Affected", f"{len(allout_candidates)}")
            col2.metric("Units Left in Warehouse", f"{allout_candidates['Warehouse_Remaining'].sum():,}")
            
            # Create all-out summary
            st.subheader("📋 All-Out Candidates")
            
            allout_display = []
            for _, row in allout_candidates.iterrows():
                prod_group = row['Product_Group']
                
                # Get a representative product from this group for display
                group_products = unique_skus[unique_skus['Product_Group'] == prod_group]
                display_product = group_products['ProdReference'].iloc[0] if len(group_products) > 0 else prod_group
                
                # Get product name from column F (ProdName)
                product_display = group_products['ProdName'].iloc[0] if len(group_products) > 0 and pd.notna(group_products['ProdName'].iloc[0]) else ""
                
                # Determine which threshold triggered
                threshold_type = ""
                if row['Should_AllOut_USA'] and row['Should_AllOut_CDA']:
                    threshold_type = "Both"
                elif row['Should_AllOut_USA']:
                    threshold_type = f"USA (<{USA_ALLOUT_THRESHOLD})"
                else:
                    threshold_type = f"CDA (<{CDA_ALLOUT_THRESHOLD})"
                
                # Show group info
                group_info = ""
                if prod_group.startswith('Group_'):
                    group_info = f" (Linked: {len(group_products)} products)"
                elif prod_group.startswith('Dim_'):
                    group_info = f" (Dimensions: {len(group_products)} sizes)"
                
                allout_display.append({
                    'Product': display_product + group_info,
                    'Name': product_display if product_display else '-',
                    'Warehouse Remaining': int(row['Warehouse_Remaining']),
                    'Threshold': threshold_type
                })
            
            allout_df = pd.DataFrame(allout_display)
            allout_df = allout_df.sort_values('Warehouse Remaining', ascending=True)
            
            st.dataframe(
                allout_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Product": st.column_config.TextColumn("Product", width="medium"),
                    "Name": st.column_config.TextColumn("Product Name", width="medium"),
                    "Warehouse Remaining": st.column_config.NumberColumn("Warehouse Remaining", format="%d"),
                    "Threshold": st.column_config.TextColumn("Threshold", width="small")
                }
            )
            
            # Download button
            csv_allout = allout_df.to_csv(index=False)
            st.download_button(
                label="📥 Download All-Out Report (CSV)",
                data=csv_allout,
                file_name=f"redflag_allout_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
        else:
            st.success("✅ **EFFICIENT ALLOCATION!** No styles will leave inefficient quantities in warehouse.")
        
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
3. RedFlag checks: (On Hand + L28 Sales) ≥ Threshold
4. Review flagged allocations before shipping
5. Check all-out candidates to maximize efficiency
""")

st.sidebar.markdown("### File Requirements")
st.sidebar.markdown("""
**RO File columns:**
- A: Store Code
- G: Product Reference  
- I: Store Stock
- M: Quantity to send
- Y: 28-day sales
- W: Warehouse stock remaining

**Linked Lines:**
- Use the 'Linked' tab
- Column B: Order indicator (1 = new group)
- Column D: Style Name
- Column E: Color
""")

st.sidebar.markdown("### Grouping Logic")
st.sidebar.markdown("""
Products are grouped by:
- **Linked Lines**: From your file
- **Dimensions**: Same style/color, different dimension (_30, _32, etc.)
""")

st.sidebar.markdown("### Special Doors")
st.sidebar.markdown("""
- **ECOM**: 883, 886
- **Clearance**: 3017, 3221, 7003

These doors are highlighted in grey in results.
""")

st.sidebar.markdown("### Support")
st.sidebar.markdown("Questions? Issues? Contact the allocation team.")
