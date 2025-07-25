import sqlite3
import os
import time
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from datetime import datetime
from reportlab.lib.pagesizes import letter

def list_databases():
    """List all .db files in the current directory."""
    db_files = [f for f in os.listdir() if f.endswith('.db')]
    return db_files

def select_or_create_database():
    """Prompt user to select an existing database or create a new one."""
    db_files = list_databases()
    if db_files:
        print("\nExisting Databases:")
        for i, db in enumerate(db_files, 1):
            print(f"{i}. {db}")
        print(f"{len(db_files) + 1}. Create new database")
        choice = input(f"Select a database (1-{len(db_files) + 1}): ")
        try:
            choice = int(choice)
            if 1 <= choice <= len(db_files):
                return db_files[choice - 1]
            elif choice == len(db_files) + 1:
                return input("Enter new database name (e.g., chemicals.db): ") or "chemicals.db"
            else:
                print("Invalid choice, using default: chemicals.db")
                return "chemicals.db"
        except ValueError:
            print("Invalid input, using default: chemicals.db")
            return "chemicals.db"
    else:
        return input("No databases found. Enter new database name (e.g., chemicals.db): ") or "chemicals.db"

def create_or_open_database(db_name):
    """Create or open a SQLite database for storing chemical data."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chemicals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mix_rate TEXT,
            warnings TEXT,
            description TEXT
        )
    ''')
    conn.commit()
    return conn, cursor


def delete_database():
    """Let user delete a selected database after confirmation."""
    db_files = list_databases()
    if not db_files:
        print("No databases found to delete.")
        return

    print("\nDatabases Available for Deletion:")
    for i, db in enumerate(db_files, 1):
        print(f"{i}. {db}")

    try:
        choice = int(input(f"Enter number of database to delete (1-{len(db_files)}), or 0 to cancel: "))
        if choice == 0:
            print("Cancelled.")
            return
        if 1 <= choice <= len(db_files):
            selected_db = db_files[choice - 1]
            confirm = input(f"Are you sure you want to permanently delete '{selected_db}'? (y/n): ").strip().lower()
            if confirm == 'y':
                os.remove(selected_db)
                print(f"'{selected_db}' has been deleted.")
            else:
                print("Deletion cancelled.")
        else:
            print("Invalid choice.")
    except ValueError:
        print("Invalid input. Deletion cancelled.")


def add_chemical(cursor, name, mix_rate, warnings, description):
    """Add a chemical to the database."""
    cursor.execute('INSERT INTO chemicals (name, mix_rate, warnings, description) VALUES (?, ?, ?, ?)',
                   (name, mix_rate, warnings, description))
    return name

def create_sample_file(filename):
    """Create a sample text file for mass adding chemicals."""
    sample_content = """Acorn Fertilizer,2 oz,Handle with gloves,High-nitrogen blend for tree growth
Acorn Soil Conditioner,1 lb,Avoid inhalation,Improves soil structure"""
    try:
        with open(filename, 'w') as file:
            file.write(sample_content)
        print(f"Sample file '{filename}' created successfully.")
    except Exception as e:
        print(f"Error creating sample file: {e}")

def mass_add_chemicals(cursor, filename):
    """Add multiple chemicals from a text file with improved validation."""
    if not filename.endswith('.txt'):
        filename += '.txt'

    if not os.path.exists(filename):
        print(f"File '{filename}' not found.")
        create_sample = input("Would you like to create a sample file? (y/n): ").lower()
        if create_sample == 'y':
            create_sample_file(filename)
        return

    added_count = 0
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line_number, line in enumerate(file, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines or comments
                    continue
                parts = line.split(',', 3)  # Split into at most 4 parts
                if len(parts) != 4:
                    print(f"Skipping line {line_number}: Invalid format (expected 'name,mix_rate,warnings,description')")
                    continue
                name, mix_rate, warnings, description = [part.strip() for part in parts]
                if not name:
                    print(f"Skipping line {line_number}: Chemical name cannot be empty")
                    continue
                try:
                    add_chemical(cursor, name, f"{mix_rate} per 100 gal", warnings, description)
                    print(f"Line {line_number}: Added '{name}'")
                    added_count += 1
                except sqlite3.IntegrityError:
                    print(f"Skipping line {line_number}: Chemical '{name}' already exists")
        print(f"Mass add completed: {added_count} chemicals added.")
    except Exception as e:
        print(f"Error processing file '{filename}': {e}")

def delete_chemical(cursor, name):
    """Delete a chemical from the database."""
    cursor.execute('DELETE FROM chemicals WHERE name = ?', (name,))
    if cursor.rowcount > 0:
        print(f"Deleted {name} from the database.")
    else:
        print(f"Chemical {name} not found.")

def edit_chemical(cursor):
    """Edit an existing chemical in the database."""
    name = input("Enter the name of the chemical you want to edit: ").strip()

    # Check if chemical exists
    cursor.execute('SELECT * FROM chemicals WHERE name = ?', (name,))
    row = cursor.fetchone()
    if not row:
        print(f"No chemical found with the name '{name}'.")
        return

    print(f"Editing chemical: {name}")
    print("Leave fields blank to keep current values.\n")

    new_name = input(f"New name [{row[1]}]: ") or row[1]
    new_mix_rate = input(f"New mix rate [{row[2]}]: ") or row[2]
    new_warnings = input(f"New warnings [{row[3]}]: ") or row[3]
    new_description = input(f"New description [{row[4]}]: ") or row[4]

    cursor.execute('''
        UPDATE chemicals
        SET name = ?, mix_rate = ?, warnings = ?, description = ?
        WHERE id = ?
    ''', (new_name, new_mix_rate, new_warnings, new_description, row[0]))

    print(f"Chemical '{name}' has been updated to '{new_name}'.")


def view_chemicals(cursor):
    """Display all chemicals in the database."""
    cursor.execute('SELECT name, mix_rate, warnings, description FROM chemicals')
    rows = cursor.fetchall()
    if not rows:
        print("No chemicals in the database.")
        return []
    print("\nCurrent Chemicals:")
    for row in rows:
        print(f"Name: {row[0]}, Mix Rate: {row[1]}, Warnings: {row[2]}, Description: {row[3]}")
    return rows

def generate_pdf(db_name, output_pdf, company_info, subcontractor, title="Squirrel TEcH LLC Chemical Inventory", logo_path="squirrel_logo.png"):

    """Generate a wrapped PDF report using Platypus."""
    conn, cursor = create_or_open_database(db_name)
    chemicals = view_chemicals(cursor)

    doc = SimpleDocTemplate(output_pdf, pagesize=letter,
                            rightMargin=30, leftMargin=30,
                            topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    styleN = styles['Normal']
    styleH = styles['Heading1']

    # Add logo if available
    if os.path.exists(logo_path):
        try:
            img_reader = ImageReader(logo_path)
            orig_width, orig_height = img_reader.getSize()
            target_width = 150  # in points
            aspect_ratio = orig_height / orig_width
            target_height = target_width * aspect_ratio
            logo = Image(logo_path, width=target_width, height=target_height)
            elements.append(logo)
            elements.append(Spacer(1, 12))
        except Exception as e:
            print(f"Error loading logo '{logo_path}': {e}")


    # Title & info
    elements.append(Paragraph(title, styleH))
    elements.append(Spacer(1, 12))
    if "name" in company_info and company_info["name"]:
        elements.append(Paragraph(f"<b>Company:</b> {company_info['name']}", styleN))
    if "address" in company_info and company_info["address"]:
        elements.append(Paragraph(f"<b>Address:</b> {company_info['address']}", styleN))
    if subcontractor:
        elements.append(Paragraph(f"Subcontractor: {subcontractor}", styleN))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styleN))
    elements.append(Spacer(1, 24))

    # Table headers
    data = [
        ["Name", "Mix Rate (per 100 gal)", "Warnings", "Description"]
    ]

    # Add chemical data
    for chem in chemicals:
        row = [
            Paragraph(chem[0], styleN),
            Paragraph(chem[1], styleN),
            Paragraph(chem[2], styleN),
            Paragraph(chem[3], styleN)
        ]
        data.append(row)

    # Table style
    table = Table(data, colWidths=[100, 100, 120, 170])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.black),
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Thank you for using NUTtall X by STDA.", styleN))
    elements.append(Paragraph("© 2025 Squirrel TEcH LLC. All rights reserved.", styleN))
    elements.append(Paragraph("Innovation through roots, reason, and acorns.", styleN))

    doc.build(elements)
    print(f"PDF report saved as {output_pdf}")
    conn.close()



def main():
    print("NUTtall X by STDA V3.2.3.5")
    time.sleep(1)
    print()
    time.sleep(1)
    print("Booting...")
    time.sleep(1)
    for i in range(4):
        print("🌰")
        time.sleep(1)
    db_name = select_or_create_database()
    conn, cursor = create_or_open_database(db_name)

    company_info = {
        "name": "Squirrel TEcH LLC",
        "address": "Palmyra, Utah"
    }

    while True:
        print("\nTree Care Chemicals Manager")
        print("1. Add Chemical")
        print("2. Mass Add Chemicals from File")
        print("3. Delete Chemical")
        print("4. Edit Chemical")
        print("5. View Chemicals")
        print("6. Save as PDF")
        print("7. Delete Database")
        print("8. Exit")
        choice = input("Choose an option (1-8): ")


        if choice == "1":
            name = input("Enter chemical name: ")
            mix_rate = input("Enter mix rate (amount per 100 gallons, e.g., 2 oz): ")
            warnings = input("Enter warnings: ")
            description = input("Enter description: ")
            add_chemical(cursor, name, f"{mix_rate} per 100 gal", warnings, description)
            conn.commit()

        elif choice == "2":
            filename = input("Enter text file name (e.g., chemicals.txt): ")
            mass_add_chemicals(cursor, filename)
            conn.commit()

        elif choice == "3":
            name = input("Enter chemical name to delete: ")
            delete_chemical(cursor, name)
            conn.commit()

        elif choice == "4":
            edit_chemical(cursor)
            conn.commit()

        elif choice == "5":
            view_chemicals(cursor)


        elif choice == "6":
            output_pdf = input("Enter PDF filename (e.g., chemicals_report.pdf): ") or "chemicals_report.pdf"

            # Ask for custom company info
            print("\n-- Company Info --")
            company_name = input("Enter your company name (leave blank for 'Squirrel TEcH LLC'): ") or "Squirrel TEcH LLC"
            company_address = input("Enter your company address (leave blank for 'Palmyra, Utah'): ") or "Palmyra, Utah"
            subcontractor = input("Enter subcontractor company name (leave blank if none): ")

            # Optional custom title and logo
            custom_title = input("Enter custom report title (leave blank for default): ")
            logo_path = input("Enter path to logo image (leave blank for default Squirrel TEcH logo): ") or "squirrel_logo.png"

            company_info = {
                "name": company_name,
                "address": company_address
            }

            generate_pdf(
                db_name,
                output_pdf,
                company_info,
                subcontractor,
                title=custom_title or "Squirrel TEcH LLC Chemical Inventory",
                logo_path=logo_path
            )


            


        elif choice == "7":
            delete_database()

        elif choice == "8":
            conn.close()
            print("Database saved. Exiting.")
            break
        

        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()