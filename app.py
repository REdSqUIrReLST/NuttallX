from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
import sqlite3
from datetime import datetime
import os
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production
DB_NAME = "AECD.db"

def get_db_connection():
    """Get database connection and ensure all tables exist."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    # Create tables if they don't exist
    cursor = conn.cursor()

    # Ensure chemicals table exists (should already exist from main.py)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chemicals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mix_rate TEXT,
            warnings TEXT,
            description TEXT
        )
    ''')

    # Create trucks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trucks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            truck_name TEXT NOT NULL UNIQUE,
            license_plate TEXT,
            description TEXT
        )
    ''')

    # Create tanks table (modified to include truck_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tanks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tank_name TEXT NOT NULL UNIQUE,
            capacity INTEGER,
            location TEXT,
            truck_id INTEGER,
            FOREIGN KEY (truck_id) REFERENCES trucks (id)
        )
    ''')
    
    # Add truck_id column if it doesn't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE tanks ADD COLUMN truck_id INTEGER')
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists, ignore the error
        pass

    # Create usage_log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chemical_name TEXT NOT NULL,
            tank_name TEXT NOT NULL,
            amount_used REAL NOT NULL,
            date_logged TEXT NOT NULL,
            notes TEXT
        )
    ''')

    conn.commit()
    return conn

@app.route('/')
def index():
    """Dashboard homepage."""
    conn = get_db_connection()

    # Get summary statistics
    chemical_count = conn.execute('SELECT COUNT(*) FROM chemicals').fetchone()[0]
    tank_count = conn.execute('SELECT COUNT(*) FROM tanks').fetchone()[0]
    truck_count = conn.execute('SELECT COUNT(*) FROM trucks').fetchone()[0]
    recent_logs = conn.execute('''
        SELECT chemical_name, tank_name, amount_used, date_logged 
        FROM usage_log 
        ORDER BY date_logged DESC 
        LIMIT 5
    ''').fetchall()

    conn.close()

    return render_template('index.html', 
                         chemical_count=chemical_count,
                         tank_count=tank_count,
                         truck_count=truck_count,
                         recent_logs=recent_logs)

@app.route('/chemicals')
def view_chemicals():
    """List all chemicals."""
    conn = get_db_connection()
    chemicals = conn.execute('SELECT * FROM chemicals ORDER BY name').fetchall()
    conn.close()
    return render_template('view_chemicals.html', chemicals=chemicals)

@app.route('/trucks')
def view_trucks():
    """List all trucks."""
    conn = get_db_connection()
    trucks = conn.execute('SELECT * FROM trucks ORDER BY truck_name').fetchall()
    conn.close()
    return render_template('view_trucks.html', trucks=trucks)

@app.route('/trucks/add', methods=['GET', 'POST'])
def add_truck():
    """Add a new truck."""
    if request.method == 'POST':
        truck_name = request.form['truck_name']
        license_plate = request.form.get('license_plate', '')
        description = request.form.get('description', '')

        if truck_name:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO trucks (truck_name, license_plate, description) VALUES (?, ?, ?)',
                           (truck_name, license_plate, description))
                conn.commit()
                flash(f'Truck "{truck_name}" added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash(f'Truck "{truck_name}" already exists!', 'error')
            finally:
                conn.close()
        else:
            flash('Truck name is required!', 'error')

        return redirect(url_for('view_trucks'))

    return render_template('add_truck.html')

@app.route('/trucks/edit/<int:truck_id>', methods=['GET', 'POST'])
def edit_truck(truck_id):
    """Edit an existing truck."""
    conn = get_db_connection()
    
    if request.method == 'POST':
        truck_name = request.form['truck_name']
        license_plate = request.form.get('license_plate', '')
        description = request.form.get('description', '')
        
        if truck_name:
            try:
                conn.execute('''
                    UPDATE trucks 
                    SET truck_name = ?, license_plate = ?, description = ?
                    WHERE id = ?
                ''', (truck_name, license_plate, description, truck_id))
                conn.commit()
                flash(f'Truck updated successfully!', 'success')
                conn.close()
                return redirect(url_for('view_trucks'))
            except sqlite3.IntegrityError:
                flash(f'Truck name "{truck_name}" already exists!', 'error')
        else:
            flash('Truck name is required!', 'error')
    
    # Get truck to edit
    truck = conn.execute('SELECT * FROM trucks WHERE id = ?', (truck_id,)).fetchone()
    conn.close()
    
    if not truck:
        flash('Truck not found!', 'error')
        return redirect(url_for('view_trucks'))
    
    return render_template('edit_truck.html', truck=truck)

@app.route('/trucks/delete/<int:truck_id>')
def delete_truck(truck_id):
    """Delete a specific truck."""
    conn = get_db_connection()
    
    try:
        # Check if truck exists
        truck = conn.execute('SELECT * FROM trucks WHERE id = ?', (truck_id,)).fetchone()
        if not truck:
            flash('Truck not found!', 'error')
        else:
            # Check if truck has tanks assigned
            tanks_count = conn.execute('SELECT COUNT(*) FROM tanks WHERE truck_id = ?', (truck_id,)).fetchone()[0]
            if tanks_count > 0:
                flash(f'Cannot delete truck "{truck["truck_name"]}" because it has {tanks_count} tank(s) assigned. Reassign or delete the tanks first.', 'error')
            else:
                conn.execute('DELETE FROM trucks WHERE id = ?', (truck_id,))
                conn.commit()
                flash(f'Truck "{truck["truck_name"]}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting truck: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('view_trucks'))

@app.route('/tanks')
def view_tanks():
    """List all tanks with their assigned trucks."""
    conn = get_db_connection()
    tanks = conn.execute('''
        SELECT t.*, tr.truck_name 
        FROM tanks t 
        LEFT JOIN trucks tr ON t.truck_id = tr.id 
        ORDER BY t.tank_name
    ''').fetchall()
    conn.close()
    return render_template('view_tanks.html', tanks=tanks)

@app.route('/tanks/add', methods=['GET', 'POST'])
def add_tank():
    """Add a new tank."""
    conn = get_db_connection()
    
    if request.method == 'POST':
        tank_name = request.form['tank_name']
        capacity = request.form.get('capacity', type=int)
        location = request.form.get('location', '')
        truck_id = request.form.get('truck_id', type=int)

        if tank_name:
            try:
                conn.execute('INSERT INTO tanks (tank_name, capacity, location, truck_id) VALUES (?, ?, ?, ?)',
                           (tank_name, capacity, location, truck_id))
                conn.commit()
                flash(f'Tank "{tank_name}" added successfully!', 'success')
                conn.close()
                return redirect(url_for('view_tanks'))
            except sqlite3.IntegrityError:
                flash(f'Tank "{tank_name}" already exists!', 'error')
        else:
            flash('Tank name is required!', 'error')

    # Get trucks for the form
    trucks = conn.execute('SELECT * FROM trucks ORDER BY truck_name').fetchall()
    conn.close()
    return render_template('add_tank.html', trucks=trucks)

@app.route('/tanks/edit/<int:tank_id>', methods=['GET', 'POST'])
def edit_tank(tank_id):
    """Edit an existing tank."""
    conn = get_db_connection()
    
    if request.method == 'POST':
        tank_name = request.form['tank_name']
        capacity = request.form.get('capacity', type=int)
        location = request.form.get('location', '')
        truck_id = request.form.get('truck_id', type=int)
        
        if tank_name:
            try:
                conn.execute('''
                    UPDATE tanks 
                    SET tank_name = ?, capacity = ?, location = ?, truck_id = ?
                    WHERE id = ?
                ''', (tank_name, capacity, location, truck_id, tank_id))
                conn.commit()
                flash(f'Tank updated successfully!', 'success')
                conn.close()
                return redirect(url_for('view_tanks'))
            except sqlite3.IntegrityError:
                flash(f'Tank name "{tank_name}" already exists!', 'error')
        else:
            flash('Tank name is required!', 'error')
    
    # Get tank to edit and trucks for the form
    tank = conn.execute('SELECT * FROM tanks WHERE id = ?', (tank_id,)).fetchone()
    trucks = conn.execute('SELECT * FROM trucks ORDER BY truck_name').fetchall()
    conn.close()
    
    if not tank:
        flash('Tank not found!', 'error')
        return redirect(url_for('view_tanks'))
    
    return render_template('edit_tank.html', tank=tank, trucks=trucks)

@app.route('/tanks/delete/<int:tank_id>')
def delete_tank(tank_id):
    """Delete a specific tank."""
    conn = get_db_connection()
    
    try:
        # Check if tank exists
        tank = conn.execute('SELECT * FROM tanks WHERE id = ?', (tank_id,)).fetchone()
        if not tank:
            flash('Tank not found!', 'error')
        else:
            # Check if tank is being used in logs
            logs_using_tank = conn.execute('SELECT COUNT(*) FROM usage_log WHERE tank_name = ?', (tank['tank_name'],)).fetchone()[0]
            if logs_using_tank > 0:
                flash(f'Cannot delete tank "{tank["tank_name"]}" because it has {logs_using_tank} usage log(s). Delete the logs first.', 'error')
            else:
                conn.execute('DELETE FROM tanks WHERE id = ?', (tank_id,))
                conn.commit()
                flash(f'Tank "{tank["tank_name"]}" deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting tank: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('view_tanks'))

@app.route('/log', methods=['GET', 'POST'])
def log_usage():
    """Log chemical usage."""
    conn = get_db_connection()

    if request.method == 'POST':
        chemical_names = request.form.getlist('chemical_names')
        tank_name = request.form['tank_name']
        amount_used = request.form.get('amount_used', type=float)
        notes = request.form.get('notes', '')
        date_logged = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if chemical_names and tank_name and amount_used is not None:
            # Combine all selected chemicals into one entry
            combined_chemicals = ', '.join(chemical_names)
            conn.execute('''
                INSERT INTO usage_log (chemical_name, tank_name, amount_used, date_logged, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (combined_chemicals, tank_name, amount_used, date_logged, notes))
            conn.commit()
            flash(f'Usage logged successfully for {len(chemical_names)} chemical(s) in one entry!', 'success')
            conn.close()
            return redirect(url_for('view_logs'))
        else:
            flash('All fields except notes are required!', 'error')

    # Get chemicals and tanks for the form
    chemicals = conn.execute('SELECT name FROM chemicals ORDER BY name').fetchall()
    tanks = conn.execute('SELECT tank_name FROM tanks ORDER BY tank_name').fetchall()
    conn.close()

    return render_template('log_usage.html', chemicals=chemicals, tanks=tanks)

@app.route('/logs')
def view_logs():
    """View all usage logs."""
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT * FROM usage_log 
        ORDER BY date_logged DESC
    ''').fetchall()
    conn.close()
    return render_template('view_logs.html', logs=logs)

@app.route('/logs/delete/<int:log_id>')
def delete_log(log_id):
    """Delete a specific usage log entry."""
    conn = get_db_connection()

    try:
        # Check if log exists
        log = conn.execute('SELECT * FROM usage_log WHERE id = ?', (log_id,)).fetchone()
        if not log:
            flash('Usage log not found!', 'error')
        else:
            conn.execute('DELETE FROM usage_log WHERE id = ?', (log_id,))
            conn.commit()
            flash('Usage log deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting log: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('view_logs'))

@app.route('/logs/edit/<int:log_id>', methods=['GET', 'POST'])
def edit_log(log_id):
    """Edit a specific usage log entry."""
    conn = get_db_connection()

    if request.method == 'POST':
        chemical_name = request.form['chemical_name']
        tank_name = request.form['tank_name']
        amount_used = request.form.get('amount_used', type=float)
        notes = request.form.get('notes', '')

        if chemical_name and tank_name and amount_used is not None:
            try:
                conn.execute('''
                    UPDATE usage_log 
                    SET chemical_name = ?, tank_name = ?, amount_used = ?, notes = ?
                    WHERE id = ?
                ''', (chemical_name, tank_name, amount_used, notes, log_id))
                conn.commit()
                flash('Usage log updated successfully!', 'success')
                conn.close()
                return redirect(url_for('view_logs'))
            except Exception as e:
                flash(f'Error updating log: {str(e)}', 'error')
        else:
            flash('All fields except notes are required!', 'error')

    # Get log to edit
    log = conn.execute('SELECT * FROM usage_log WHERE id = ?', (log_id,)).fetchone()
    if not log:
        flash('Usage log not found!', 'error')
        conn.close()
        return redirect(url_for('view_logs'))

    # Get chemicals and tanks for the form
    chemicals = conn.execute('SELECT name FROM chemicals ORDER BY name').fetchall()
    tanks = conn.execute('SELECT tank_name FROM tanks ORDER BY tank_name').fetchall()
    conn.close()

    return render_template('edit_log.html', log=log, chemicals=chemicals, tanks=tanks)

@app.route('/export/chemicals')
def export_chemicals_pdf():
    """Export chemicals list as PDF."""
    conn = get_db_connection()
    chemicals = conn.execute('SELECT * FROM chemicals ORDER BY name').fetchall()
    conn.close()

    # Create PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                          rightMargin=30, leftMargin=30, 
                          topMargin=30, bottomMargin=30)

    elements = []
    styles = getSampleStyleSheet()

    # Title
    title = Paragraph("NUTtall X - Chemical Inventory Report", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    # Date
    date_p = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
    elements.append(date_p)
    elements.append(Spacer(1, 24))

    if chemicals:
        # Table data
        data = [['Name', 'Mix Rate', 'Warnings', 'Description']]
        for chem in chemicals:
            data.append([
                Paragraph(chem['name'], styles['Normal']),
                Paragraph(chem['mix_rate'] or '-', styles['Normal']),
                Paragraph(chem['warnings'] or '-', styles['Normal']),
                Paragraph(chem['description'] or '-', styles['Normal'])
            ])

        # Create table
        table = Table(data, colWidths=[1.5*inch, 1.5*inch, 2*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No chemicals found.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"chemicals_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mimetype='application/pdf'
    )

@app.route('/export/tanks')
def export_tanks_pdf():
    """Export tanks list as PDF."""
    conn = get_db_connection()
    tanks = conn.execute('SELECT * FROM tanks ORDER BY tank_name').fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                          rightMargin=30, leftMargin=30,
                          topMargin=30, bottomMargin=30)

    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph("NUTtall X - Tank Inventory Report", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    date_p = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
    elements.append(date_p)
    elements.append(Spacer(1, 24))

    if tanks:
        data = [['Tank Name', 'Capacity', 'Location']]
        for tank in tanks:
            data.append([
                tank['tank_name'],
                str(tank['capacity']) if tank['capacity'] else '-',
                tank['location'] or '-'
            ])

        table = Table(data, colWidths=[2*inch, 2*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No tanks found.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"tanks_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mimetype='application/pdf'
    )

@app.route('/export/logs')
def export_logs_pdf():
    """Export usage logs as PDF."""
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT * FROM usage_log 
        ORDER BY date_logged DESC
    ''').fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                          rightMargin=30, leftMargin=30,
                          topMargin=30, bottomMargin=30)

    elements = []
    styles = getSampleStyleSheet()

    title = Paragraph("NUTtall X - Usage Logs Report", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    date_p = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
    elements.append(date_p)
    elements.append(Spacer(1, 24))

    if logs:
        data = [['Date', 'Chemical', 'Tank', 'Amount', 'Notes']]
        for log in logs:
            data.append([
                Paragraph(log['date_logged'], styles['Normal']),
                Paragraph(log['chemical_name'], styles['Normal']),
                Paragraph(log['tank_name'], styles['Normal']),
                Paragraph(str(log['amount_used']), styles['Normal']),
                Paragraph(log['notes'] or '-', styles['Normal'])
            ])

        table = Table(data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No usage logs found.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"usage_logs_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mimetype='application/pdf'
    )

@app.route('/reports')
def view_reports():
    """View all generated PDF reports in the current directory."""
    # Get all PDF files in the current directory
    pdf_files = []
    for filename in os.listdir('.'):
        if filename.endswith('.pdf'):
            file_path = os.path.join('.', filename)
            file_stat = os.stat(file_path)
            pdf_files.append({
                'name': filename,
                'size': round(file_stat.st_size / 1024, 2),  # Size in KB
                'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })

    # Sort by modification date (newest first)
    pdf_files.sort(key=lambda x: x['modified'], reverse=True)

    return render_template('view_reports.html', reports=pdf_files)

@app.route('/reports/delete/<filename>')
def delete_report(filename):
    """Delete a specific PDF report."""
    # Security check - only allow deletion of PDF files
    if not filename.endswith('.pdf'):
        flash('Invalid file type!', 'error')
        return redirect(url_for('view_reports'))

    file_path = os.path.join('.', filename)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'Report "{filename}" deleted successfully!', 'success')
        else:
            flash(f'Report "{filename}" not found!', 'error')
    except Exception as e:
        flash(f'Error deleting report: {str(e)}', 'error')

    return redirect(url_for('view_reports'))

@app.route('/reports/download/<filename>')
def download_report(filename):
    """Download a specific PDF report."""
    # Security check - only allow download of PDF files
    if not filename.endswith('.pdf'):
        flash('Invalid file type!', 'error')
        return redirect(url_for('view_reports'))

    file_path = os.path.join('.', filename)

    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=filename)
    else:
        flash(f'Report "{filename}" not found!', 'error')
        return redirect(url_for('view_reports'))

@app.route('/reports/rename/<filename>', methods=['GET', 'POST'])
def rename_report(filename):
    """Rename a specific PDF report."""
    # Security check - only allow renaming of PDF files
    if not filename.endswith('.pdf'):
        flash('Invalid file type!', 'error')
        return redirect(url_for('view_reports'))

    old_path = os.path.join('.', filename)

    if not os.path.exists(old_path):
        flash(f'Report "{filename}" not found!', 'error')
        return redirect(url_for('view_reports'))

    if request.method == 'POST':
        new_name = request.form.get('new_name', '').strip()

        if not new_name:
            flash('New filename cannot be empty!', 'error')
            return render_template('rename_report.html', filename=filename)

        # Ensure the new name ends with .pdf
        if not new_name.endswith('.pdf'):
            new_name += '.pdf'

        new_path = os.path.join('.', new_name)

        # Check if the new filename already exists
        if os.path.exists(new_path):
            flash(f'A report named "{new_name}" already exists!', 'error')
            return render_template('rename_report.html', filename=filename)

        try:
            os.rename(old_path, new_path)
            flash(f'Report renamed from "{filename}" to "{new_name}" successfully!', 'success')
            return redirect(url_for('view_reports'))
        except Exception as e:
            flash(f'Error renaming report: {str(e)}', 'error')
            return render_template('rename_report.html', filename=filename)

    return render_template('rename_report.html', filename=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)