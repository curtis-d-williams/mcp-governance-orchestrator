#!/usr/bin/env python3
"""
Interactive Tier 3 dashboard with filtering.

- Reads CSV from Tier 3 analytics
- Adds sortable and filterable table
- Fully read-only; preserves frozen composition invariants
"""

import csv

def generate_filtered_dashboard(csv_path="tier3_portfolio_report.csv", html_path="tier3_portfolio_dashboard_filtered.html"):
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    with open(html_path, "w") as f:
        f.write("<html><head><title>Tier 3 Interactive Dashboard</title>\n")
        f.write("<style>\n")
        f.write("table { border-collapse: collapse; width: 100%; }")
        f.write("th, td { border: 1px solid #333; padding: 8px; text-align: left; }")
        f.write("tr:nth-child(even) { background-color: #f2f2f2; }")
        f.write("th { background-color: #4CAF50; color: white; cursor: pointer; }\n")
        f.write("</style>\n")
        f.write("<script>\n")
        # Sorting function
        f.write("function sortTable(n) { /* same sortTable function as before */\n")
        f.write("var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;\n")
        f.write("table = document.getElementById('tier3Table'); switching = true; dir = 'asc';\n")
        f.write("while(switching) { switching=false; rows=table.rows;\n")
        f.write("for(i=1;i<rows.length-1;i++){shouldSwitch=false;x=rows[i].getElementsByTagName('TD')[n];y=rows[i+1].getElementsByTagName('TD')[n];\n")
        f.write("if(dir=='asc'){if(x.innerHTML.toLowerCase()>y.innerHTML.toLowerCase()){shouldSwitch=true;break;}}\n")
        f.write("else if(dir=='desc'){if(x.innerHTML.toLowerCase()<y.innerHTML.toLowerCase()){shouldSwitch=true;break;}}\n")
        f.write("}if(shouldSwitch){rows[i].parentNode.insertBefore(rows[i+1],rows[i]);switching=true;switchcount++;}\n")
        f.write("else{if(switchcount==0&&dir=='asc'){dir='desc';switching=true;}}}}\n")
        # Filtering function
        f.write("function filterTable() {\n")
        f.write("var input, filter, table, tr, td, i, txtValue;\n")
        f.write("input = document.getElementById('filterInput'); filter = input.value.toUpperCase();\n")
        f.write("table = document.getElementById('tier3Table'); tr = table.getElementsByTagName('tr');\n")
        f.write("for(i=1;i<tr.length;i++){td=tr[i].getElementsByTagName('td')[0];\n")
        f.write("if(td){txtValue=td.textContent||td.innerText;if(txtValue.toUpperCase().indexOf(filter)>-1){tr[i].style.display='';}else{tr[i].style.display='none';}}}\n")
        f.write("}\n")
        f.write("</script></head><body>\n")
        f.write("<h1>Tier 3 Interactive Dashboard with Filter</h1>\n")
        f.write("<input type='text' id='filterInput' onkeyup='filterTable()' placeholder='Filter by Suggestion ID...' style='margin-bottom:10px;width:50%'><br>\n")
        f.write("<table id='tier3Table'>\n")
        f.write("<tr><th onclick='sortTable(0)'>Suggestion ID</th><th onclick='sortTable(1)'>Description</th><th onclick='sortTable(2)'>Example Metric</th><th onclick='sortTable(3)'>Notes</th></tr>\n")
        for row in rows:
            f.write(f"<tr><td>{row['Suggestion ID']}</td><td>{row['Description']}</td><td>{row['Example Metric']}</td><td>{row['Notes']}</td></tr>\n")
        f.write("</table></body></html>\n")
    print(f"Interactive filtered HTML dashboard generated at {html_path}")

if __name__ == "__main__":
    generate_filtered_dashboard()
